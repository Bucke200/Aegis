"""Tests for VIP management, reference media, and fingerprints."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.main import app
from aegis.api.security import create_access_token
from aegis.api.services.fingerprints import FingerprintService
from aegis.api.services.users import UserService
from aegis.common.db import get_session
from aegis.common.models.enums import FingerprintKind, Sensitivity, UserRole
from aegis.common.models.ops import AuditLog
from aegis.common.models.reference import SensitiveFingerprint
from aegis.common.storage import StoredObject, get_object_storage, sha256_hex

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def _png() -> bytes:
    image = Image.new("L", (64, 64))
    pixels = image.load()
    for x in range(64):
        for y in range(64):
            pixels[x, y] = (x * 3 + y) % 256
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.media_bucket = "aegis-media"
        self.uploads: list[dict[str, Any]] = []

    def put_bytes(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        retention_days: int | None = None,
    ) -> StoredObject:
        self.uploads.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "data": data,
                "content_type": content_type,
            }
        )
        return StoredObject(bucket=bucket, object_key=object_key, sha256=sha256_hex(data), size=len(data))


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(pg_engine, fake_storage: FakeStorage) -> Iterator[TestClient]:
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
    app.dependency_overrides[get_object_storage] = lambda: fake_storage

    with Session(pg_engine) as setup:
        admin = UserService(setup).create_user(
            email=f"admin-{uuid.uuid4().hex[:8]}@example.test",
            password="admin-pass",
            role=UserRole.ADMIN,
        )
        setup.commit()
        token = create_access_token(admin.id, admin.role.value)

    try:
        with TestClient(app) as test_client:
            test_client.headers["Authorization"] = f"Bearer {token}"
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _create_vip(client: TestClient, name: str = "Vip API") -> str:
    response = client.post("/vips", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


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
def test_vip_lifecycle_writes_audit_rows(client: TestClient, pg_engine) -> None:
    created = client.post("/vips", json={"name": "Vip Lifecycle", "sensitivity": "high"})
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
            for row in session.execute(select(AuditLog.action).where(AuditLog.target == vip_id).order_by(AuditLog.at))
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


@DB_REQUIRED
def test_reference_media_upload_stores_hashes(client: TestClient, fake_storage: FakeStorage) -> None:
    vip_id = _create_vip(client, "Vip Media")
    data = _png()

    uploaded = client.post(
        f"/vips/{vip_id}/reference-media",
        files={"file": ("ref.png", data, "image/png")},
        data={"kind": "portrait"},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["phash"]
    assert body["dhash"]
    assert body["kind"] == "portrait"

    assert len(fake_storage.uploads) == 1
    assert fake_storage.uploads[0]["data"] == data
    assert fake_storage.uploads[0]["object_key"].startswith(f"reference/{vip_id}/")

    listed = client.get(f"/vips/{vip_id}/reference-media")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    unsupported = client.post(
        f"/vips/{vip_id}/reference-media",
        files={"file": ("ref.gif", b"GIF89a", "image/gif")},
    )
    assert unsupported.status_code == 415

    corrupt = client.post(
        f"/vips/{vip_id}/reference-media",
        files={"file": ("ref.png", b"not an image", "image/png")},
    )
    assert corrupt.status_code == 422

    removed = client.delete(f"/vips/{vip_id}/reference-media/{body['id']}")
    assert removed.status_code == 204
    assert client.get(f"/vips/{vip_id}/reference-media").json() == []


@DB_REQUIRED
def test_fingerprint_registration_stores_only_hashes(client: TestClient, pg_engine, caplog) -> None:
    vip_id = _create_vip(client, "Vip Fingerprints")
    value = "+91 50000 00001"

    with caplog.at_level("DEBUG"):
        response = client.post(
            f"/vips/{vip_id}/sensitive-fingerprints",
            json={"kind": "phone", "value": value},
        )
    assert response.status_code == 201
    body = response.json()
    assert "value" not in body
    assert "salted_hash" not in body
    assert value not in response.text
    assert value not in caplog.text
    assert "5000000001" not in caplog.text

    with Session(pg_engine) as session:
        stored = session.execute(select(SensitiveFingerprint).where(SensitiveFingerprint.vip_id == vip_id)).scalar_one()
        details = session.execute(
            select(AuditLog.details).where(AuditLog.target == vip_id, AuditLog.action == "vip.fingerprint_added")
        ).scalar_one()
        service = FingerprintService(session)
        assert service.matches(uuid.UUID(vip_id), "+915000000001", FingerprintKind.PHONE)
        assert not service.matches(uuid.UUID(vip_id), "+915000000002", FingerprintKind.PHONE)

    assert stored.salted_hash != value
    assert stored.salt_id == "default"
    assert value not in str(details)

    invalid = client.post(
        f"/vips/{vip_id}/sensitive-fingerprints",
        json={"kind": "email", "value": "not-an-email"},
    )
    assert invalid.status_code == 422

    listed = client.get(f"/vips/{vip_id}/sensitive-fingerprints")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    removed = client.delete(f"/vips/{vip_id}/sensitive-fingerprints/{body['id']}")
    assert removed.status_code == 204
