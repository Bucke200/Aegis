"""Incident list, detail, workflow, assignment, notes, and bulk actions."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.dependencies import get_current_user, require_role
from aegis.api.services.incidents import IncidentFilters, IncidentService
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User

router = APIRouter(prefix="/incidents", tags=["incidents"])

AnalystOrAbove = Depends(require_role(UserRole.ANALYST, UserRole.LEAD, UserRole.ADMIN))


def get_incident_service(session: Session = Depends(get_session)) -> IncidentService:
    return IncidentService(session)


@router.get("", response_model=schemas.IncidentListResponse)
def list_incidents(
    user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
    severity: list[str] = Query(default=[]),
    incident_status: list[str] = Query(default=[], alias="status"),
    source: list[str] = Query(default=[]),
    language: list[str] = Query(default=[]),
    vip_id: list[uuid.UUID] = Query(default=[]),
    assignee_id: list[uuid.UUID] = Query(default=[]),
    campaign_id: uuid.UUID | None = None,
    threat_type: list[str] = Query(default=[]),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    include_merged: bool = False,
    sort: str = Query(default="time", pattern="^(time|severity)$"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> schemas.IncidentListResponse:
    filters = IncidentFilters(
        severity=severity,
        status=incident_status,
        source=source,
        language=language,
        vip_ids=vip_id,
        assignee_ids=assignee_id,
        campaign_id=campaign_id,
        threat_types=threat_type,
        created_from=created_from,
        created_to=created_to,
        include_merged=include_merged,
    )
    rows, next_cursor = service.list_incidents(user, filters, sort=sort, cursor=cursor, limit=limit)
    return schemas.IncidentListResponse(
        items=[schemas.IncidentRead.model_validate(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post("/bulk/status", response_model=schemas.BulkStatusResponse)
def bulk_status(
    payload: schemas.BulkStatusRequest,
    user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
) -> schemas.BulkStatusResponse:
    applied, errors = service.bulk_transition(
        user,
        payload.incident_ids,
        payload.status,
        reason=payload.reason,
        outcome=payload.outcome,
    )
    return schemas.BulkStatusResponse(applied=applied, errors=errors)


@router.get("/{incident_id}", response_model=schemas.IncidentDetailResponse)
def get_incident(
    incident_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
) -> schemas.IncidentDetailResponse:
    detail = service.detail(user, incident_id)
    return schemas.IncidentDetailResponse(
        incident=schemas.IncidentRead.model_validate(detail["incident"]),
        detections=[schemas.DetectionRead.model_validate(row) for row in detail["detections"]],
        account=(schemas.AccountSummary.model_validate(detail["account"]) if detail["account"] else None),
        campaign=(schemas.CampaignSummary.model_validate(detail["campaign"]) if detail["campaign"] else None),
        history=[schemas.IncidentEventRead.model_validate(row) for row in detail["history"]],
        notes=[schemas.IncidentNoteRead.model_validate(row) for row in detail["notes"]],
        evidence=[schemas.EvidenceArtifactRead.model_validate(row) for row in detail["evidence"]],
    )


@router.post("/{incident_id}/status", response_model=schemas.IncidentRead)
def change_status(
    incident_id: uuid.UUID,
    payload: schemas.StatusChangeRequest,
    user: User = AnalystOrAbove,
    service: IncidentService = Depends(get_incident_service),
) -> schemas.IncidentRead:
    incident = service.transition_status(
        user,
        incident_id,
        payload.status,
        reason=payload.reason,
        outcome=payload.outcome,
    )
    return schemas.IncidentRead.model_validate(incident)


@router.post("/{incident_id}/assign", response_model=schemas.IncidentRead)
def assign_incident(
    incident_id: uuid.UUID,
    payload: schemas.AssignRequest,
    user: User = AnalystOrAbove,
    service: IncidentService = Depends(get_incident_service),
) -> schemas.IncidentRead:
    incident = service.assign(user, incident_id, payload.assignee_id)
    return schemas.IncidentRead.model_validate(incident)


@router.post(
    "/{incident_id}/notes",
    response_model=schemas.IncidentNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    incident_id: uuid.UUID,
    payload: schemas.NoteCreate,
    user: User = AnalystOrAbove,
    service: IncidentService = Depends(get_incident_service),
) -> schemas.IncidentNoteRead:
    note = service.add_note(user, incident_id, payload.body)
    return schemas.IncidentNoteRead.model_validate(note)
