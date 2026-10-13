"""Incident events and evidence capture requests.

``IncidentEvent`` is the version 2 contract shared by the outbox publisher, the
WebSocket gateway, and alerting (D-02); ``CaptureRequest`` is the job payload
for the capture service (D-01). Consumers must keep accepting version 1
incident payloads, which have no ``schema`` key and fewer fields, until every
producer is upgraded, so ``parse_incident_event`` defaults the missing fields to
``None``. Payloads never carry item text or sensitive values.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.common.models.collected import Item
from aegis.common.models.enums import IncidentStatus, IncidentSubject, Severity
from aegis.common.models.incidents import Incident, IncidentVip


class IncidentChange(StrEnum):
    CREATED = "created"
    RESCORED = "rescored"
    STATUS = "status"
    ASSIGNED = "assigned"
    NOTE = "note"
    MERGED = "merged"
    CAPTURE = "capture"
    SOURCE_REMOVED = "source_removed"


class CaptureTrigger(StrEnum):
    CREATED = "created"
    RESCORED = "rescored"
    ITEM_ATTACHED = "item_attached"
    RECAPTURE = "recapture"


class IncidentEvent(BaseModel):
    """Version 2 incident event; unknown keys from v1 payloads are preserved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: int = Field(default=2, alias="schema")
    incident_id: uuid.UUID | None = None
    subject_type: IncidentSubject | None = None
    item_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    vip_ids: list[uuid.UUID] = Field(default_factory=list)
    severity: Severity | None = None
    previous_severity: Severity | None = None
    risk_score: float | None = None
    status: IncidentStatus | None = None
    threat_types: list[str] = Field(default_factory=list)
    change: IncidentChange | None = None
    actor_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    merged_into_id: uuid.UUID | None = None


class CaptureRequest(BaseModel):
    """A capture job for the queue ``evidence.capture``."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema")
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    subject_type: IncidentSubject
    item_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    trigger: CaptureTrigger
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _account_id_for(session: Session, incident: Incident) -> uuid.UUID | None:
    if incident.account_id is not None:
        return incident.account_id
    if incident.item_id is None:
        return None
    return session.execute(select(Item.account_id).where(Item.id == incident.item_id)).scalar_one_or_none()


def _incident_vip_ids(session: Session, incident: Incident) -> list[uuid.UUID]:
    return list(
        session.execute(
            select(IncidentVip.vip_id).where(IncidentVip.incident_id == incident.id).order_by(IncidentVip.vip_id)
        ).scalars()
    )


def build_incident_event(
    session: Session,
    incident: Incident,
    change: IncidentChange,
    *,
    previous_severity: Severity | None = None,
    actor_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
) -> IncidentEvent:
    """Build the version 2 payload for an incident change."""

    return IncidentEvent(
        incident_id=incident.id,
        subject_type=incident.subject_type,
        item_id=incident.item_id,
        account_id=_account_id_for(session, incident),
        campaign_id=incident.campaign_id,
        vip_ids=_incident_vip_ids(session, incident),
        severity=incident.severity,
        previous_severity=previous_severity,
        risk_score=incident.risk_score,
        status=incident.status,
        threat_types=list(incident.threat_types or []),
        change=change,
        actor_id=actor_id,
        assignee_id=assignee_id,
        merged_into_id=incident.merged_into_id,
    )


def build_capture_request(session: Session, incident: Incident, trigger: CaptureTrigger) -> CaptureRequest:
    """Build a capture job for an incident that reached the capture severity."""

    return CaptureRequest(
        incident_id=incident.id,
        subject_type=incident.subject_type,
        item_id=incident.item_id,
        account_id=_account_id_for(session, incident),
        trigger=trigger,
    )


def parse_incident_event(payload: Mapping[str, Any]) -> IncidentEvent:
    """Parse a version 1 or version 2 payload, filling absent fields with None."""

    data = dict(payload)
    data.setdefault("schema", 1)
    return IncidentEvent.model_validate(data)
