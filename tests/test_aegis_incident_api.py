"""Incident API integration tests (Postgres)."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.api.main import app
from aegis.api.security import create_access_token
from aegis.api.services.users import UserService
from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.db import get_session
from aegis.common.models.enums import (
    IncidentEventType,
    IncidentSubject,
    Severity,
    Source,
    UserRole,
)
from aegis.common.models.incidents import Incident, IncidentEvent, IncidentNote, IncidentVip
from aegis.common.models.ops import Label, User
from aegis.common.models.reference import VIP
from aegis.pipeline.normalizer import Normalizer

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def _payload(text: str, seed: int) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=seed,
            campaign_accounts=1,
            impersonators=0,
            leaks=0,
            hinglish_threats=0,
            criticism=0,
        )
    )[0]
    payload = json.loads(item.model_dump_json())
    payload["content"]["text"] = text
    return payload


def _create_item(session: Session, text: str, seed: int) -> uuid.UUID:
    normalized = Normalizer().normalize(session, _payload(text, seed))
    return uuid.UUID(normalized.item_id)


def _create_incident(
    session: Session,
    item_id: uuid.UUID,
    vip_id: uuid.UUID,
    *,
    severity: Severity = Severity.MEDIUM,
    risk: float = 0.6,
    merged_into_id: uuid.UUID | None = None,
) -> Incident:
    incident = Incident(
        subject_type=IncidentSubject.ITEM,
        item_id=item_id,
        source=Source.TELEGRAM,
        language="en",
        risk_score=risk,
        severity=severity,
        threat_types=["violent_threat"],
        explanation="test incident",
        scoring_config_version=1,
        merged_into_id=merged_into_id,
    )
    session.add(incident)
    session.flush()
    session.add(IncidentVip(incident_id=incident.id, vip_id=vip_id))
    session.flush()
    return incident


@pytest.fixture
def client(pg_engine) -> Iterator[TestClient]:
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
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def context(pg_engine) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    with Session(pg_engine) as session:
        users = UserService(session)
        created: dict[str, User] = {}
        for role in (UserRole.ADMIN, UserRole.LEAD, UserRole.ANALYST, UserRole.VIEWER):
            created[role.value] = users.create_user(
                email=f"{role.value}-{suffix}@example.test",
                password="password",
                role=role,
            )
        vip_a = VIP(name=f"Vip A {suffix}")
        vip_b = VIP(name=f"Vip B {suffix}")
        session.add_all([vip_a, vip_b])
        session.flush()
        users.set_scope(created["analyst"].id, vip_a.id)
        session.commit()

        tokens = {role: create_access_token(created[role].id, role) for role in ("admin", "lead", "analyst", "viewer")}
        return {
            "tokens": tokens,
            "user_ids": {role: str(user.id) for role, user in created.items()},
            "vip_a": str(vip_a.id),
            "vip_b": str(vip_b.id),
            "vip_a_uuid": vip_a.id,
            "vip_b_uuid": vip_b.id,
            "suffix": suffix,
        }


def _auth(context: dict[str, Any], role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {context['tokens'][role]}"}


@DB_REQUIRED
def test_list_filters_and_vip_scope(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        item_a = _create_item(session, "I will kill him tomorrow", seed=71)
        item_b = _create_item(session, "different item text", seed=72)
        incident_a = _create_incident(session, item_a, context["vip_a_uuid"], severity=Severity.CRITICAL, risk=0.95)
        _create_incident(session, item_b, context["vip_b_uuid"], severity=Severity.LOW, risk=0.35)
        session.commit()
        incident_a_id = str(incident_a.id)

    analyst = client.get("/incidents", headers=_auth(context, "analyst"))
    assert analyst.status_code == 200
    assert [row["id"] for row in analyst.json()["items"]] == [incident_a_id]

    lead = client.get("/incidents", headers=_auth(context, "lead"))
    assert lead.status_code == 200
    assert len(lead.json()["items"]) == 2

    filtered = client.get("/incidents", params={"severity": ["critical"]}, headers=_auth(context, "lead"))
    assert [row["id"] for row in filtered.json()["items"]] == [incident_a_id]

    denied = client.get(f"/incidents/{incident_a_id}", headers=_auth(context, "analyst"))
    assert denied.status_code == 200


@DB_REQUIRED
def test_detail_hides_incidents_outside_scope(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        item_b = _create_item(session, "out of scope item", seed=73)
        incident_b = _create_incident(session, item_b, context["vip_b_uuid"])
        session.commit()
        incident_b_id = str(incident_b.id)

    response = client.get(f"/incidents/{incident_b_id}", headers=_auth(context, "analyst"))
    assert response.status_code == 404


@DB_REQUIRED
def test_keyset_pagination(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        for index in range(3):
            item = _create_item(session, f"pagination item {index} alpha", seed=80 + index)
            _create_incident(session, item, context["vip_a_uuid"], risk=0.4 + index / 100)
        session.commit()

    first = client.get("/incidents", params={"limit": 2}, headers=_auth(context, "lead")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]

    second = client.get(
        "/incidents",
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=_auth(context, "lead"),
    ).json()
    assert len(second["items"]) == 1
    ids = [row["id"] for row in first["items"]] + [row["id"] for row in second["items"]]
    assert len(set(ids)) == 3


@DB_REQUIRED
def test_status_workflow_rules(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        item = _create_item(session, "workflow item text", seed=90)
        incident = _create_incident(session, item, context["vip_a_uuid"])
        session.commit()
        incident_id = str(incident.id)

    viewer = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review"},
        headers=_auth(context, "viewer"),
    )
    assert viewer.status_code == 403

    review = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review"},
        headers=_auth(context, "analyst"),
    )
    assert review.status_code == 200
    assert review.json()["status"] == "under_review"

    missing_outcome = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers=_auth(context, "analyst"),
    )
    assert missing_outcome.status_code == 422

    resolved = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "resolved", "outcome": "no_action_needed"},
        headers=_auth(context, "analyst"),
    )
    assert resolved.status_code == 200
    assert resolved.json()["outcome"] == "no_action_needed"

    analyst_reopen = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review", "reason": "new evidence"},
        headers=_auth(context, "analyst"),
    )
    assert analyst_reopen.status_code == 409

    lead_reopen_no_reason = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review"},
        headers=_auth(context, "lead"),
    )
    assert lead_reopen_no_reason.status_code == 409

    lead_reopen = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review", "reason": "new evidence"},
        headers=_auth(context, "lead"),
    )
    assert lead_reopen.status_code == 200

    with Session(pg_engine) as session:
        events = session.execute(
            select(func.count())
            .select_from(IncidentEvent)
            .where(IncidentEvent.event_type == IncidentEventType.STATUS_CHANGE)
        ).scalar_one()
    assert events >= 3


@DB_REQUIRED
def test_false_positive_creates_label(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        item = _create_item(session, "false positive candidate", seed=91)
        incident = _create_incident(session, item, context["vip_a_uuid"])
        session.commit()
        incident_id = str(incident.id)

    client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "under_review"},
        headers=_auth(context, "analyst"),
    )
    response = client.post(
        f"/incidents/{incident_id}/status",
        json={"status": "false_positive"},
        headers=_auth(context, "analyst"),
    )
    assert response.status_code == 200

    with Session(pg_engine) as session:
        label_count = session.execute(select(func.count()).select_from(Label)).scalar_one()
    assert label_count == 1


@DB_REQUIRED
def test_merged_incident_is_read_only(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        item_a = _create_item(session, "account incident placeholder", seed=92)
        account_incident = _create_incident(session, item_a, context["vip_a_uuid"])
        item_b = _create_item(session, "merged item placeholder", seed=93)
        merged = _create_incident(
            session,
            item_b,
            context["vip_a_uuid"],
            merged_into_id=account_incident.id,
        )
        session.commit()
        merged_id = str(merged.id)

    response = client.post(
        f"/incidents/{merged_id}/status",
        json={"status": "under_review"},
        headers=_auth(context, "lead"),
    )
    assert response.status_code == 409

    note = client.post(
        f"/incidents/{merged_id}/notes",
        json={"body": "still allowed"},
        headers=_auth(context, "analyst"),
    )
    assert note.status_code == 201


@DB_REQUIRED
def test_assign_note_and_bulk(client: TestClient, context: dict[str, Any], pg_engine) -> None:
    with Session(pg_engine) as session:
        incident_ids = []
        for index in range(2):
            item = _create_item(session, f"bulk item {index} text", seed=100 + index)
            incident = _create_incident(session, item, context["vip_a_uuid"])
            incident_ids.append(str(incident.id))
        session.commit()

    assigned = client.post(
        f"/incidents/{incident_ids[0]}/assign",
        json={"assignee_id": context["user_ids"]["analyst"]},
        headers=_auth(context, "lead"),
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee_id"] == context["user_ids"]["analyst"]

    note = client.post(
        f"/incidents/{incident_ids[0]}/notes",
        json={"body": "reviewed"},
        headers=_auth(context, "analyst"),
    )
    assert note.status_code == 201

    bulk = client.post(
        "/incidents/bulk/status",
        json={"incident_ids": incident_ids, "status": "under_review"},
        headers=_auth(context, "lead"),
    )
    assert bulk.status_code == 200
    assert bulk.json()["applied"] == 2

    detail = client.get(f"/incidents/{incident_ids[0]}", headers=_auth(context, "analyst")).json()
    assert len(detail["history"]) >= 3
    assert len(detail["notes"]) == 1

    with Session(pg_engine) as session:
        note_rows = session.execute(select(func.count()).select_from(IncidentNote)).scalar_one()
    assert note_rows == 1
