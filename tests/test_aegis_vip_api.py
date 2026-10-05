"""Tests for VIP management."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.main import app
from aegis.common.db import get_session
from aegis.common.models.enums import Sensitivity
from aegis.common.models.ops import AuditLog

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def test_vip_create_defaults() -> None:
    payload = schemas.VipCreate(name="Vip")
    assert payload.sensitivity == Sensitivity.NORMAL
    assert payload.monitoring_active is True


def test_vip_create_requires_a_name() -> None:
    with pytest.raises(ValidationError):
        schemas.VipCreate(name="")


def test_vip_update_is_all_optional() -> None:
    assert schemas.VipUpdate().model_dump(exclude_unset=True) == {}


@DB_REQUIRED
def test_vip_lifecycle_writes_audit_rows(pg_engine) -> None:
    def override_session() -> Iterator[Session]:
        session = Session(bind=pg_engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        created = client.post("/vips", json={"name": "Vip API", "sensitivity": "high"})
        assert created.status_code == 201
        vip = created.json()
        assert vip["config_version"] == 1
        vip_id = vip["id"]

        alias = client.post(f"/vips/{vip_id}/aliases", json={"alias": "vs", "kind": "nickname"})
        assert alias.status_code == 201
        duplicate = client.post(f"/vips/{vip_id}/aliases", json={"alias": "vs", "kind": "nickname"})
        assert duplicate.status_code == 409

        keyword = client.post(f"/vips/{vip_id}/context-keywords", json={"keyword": "politics"})
        assert keyword.status_code == 201

        account = client.post(
            f"/vips/{vip_id}/official-accounts",
            json={
                "source": "telegram",
                "platform_account_id": "tg-1",
                "handle": "@official",
                "verification_evidence": "https://example.test/badge",
            },
        )
        assert account.status_code == 201
        assert account.json()["verified_at"] is not None

        paused = client.patch(f"/vips/{vip_id}", json={"monitoring_active": False})
        assert paused.status_code == 200
        assert paused.json()["monitoring_active"] is False
        assert paused.json()["config_version"] > 1

        resumed = client.patch(f"/vips/{vip_id}", json={"monitoring_active": True})
        assert resumed.json()["monitoring_active"] is True

        updated = client.patch(f"/vips/{vip_id}", json={"sensitivity": "low"})
        assert updated.json()["sensitivity"] == "low"

        assert client.get(f"/vips/{uuid.uuid4()}").status_code == 404
        assert client.delete(f"/vips/{vip_id}/aliases/nickname/vs").status_code == 204
        assert client.delete(f"/vips/{vip_id}/context-keywords/politics").status_code == 204
        assert client.delete(f"/vips/{vip_id}/official-accounts/{account.json()['id']}").status_code == 204

        with Session(pg_engine) as session:
            actions = [
                row[0]
                for row in session.execute(
                    select(AuditLog.action).where(AuditLog.target == vip_id).order_by(AuditLog.at)
                )
            ]
        assert actions == [
            "vip.created",
            "vip.alias_added",
            "vip.context_keyword_added",
            "vip.official_account_added",
            "vip.monitoring_paused",
            "vip.monitoring_resumed",
            "vip.updated",
            "vip.alias_removed",
            "vip.context_keyword_removed",
            "vip.official_account_removed",
        ]

        listed = client.get("/vips")
        assert listed.status_code == 200
        assert any(row["id"] == vip_id for row in listed.json())
    finally:
        app.dependency_overrides.clear()
