"""Request and response models for the API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aegis.common.models.enums import (
    AliasKind,
    FingerprintKind,
    IncidentEventType,
    IncidentOutcome,
    IncidentStatus,
    IncidentSubject,
    InputVariant,
    ReferenceMediaKind,
    Sensitivity,
    Severity,
    Source,
    UserRole,
)


class VipCreate(BaseModel):
    name: str = Field(min_length=1)
    sensitivity: Sensitivity = Sensitivity.NORMAL
    monitoring_active: bool = True


class VipUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    sensitivity: Sensitivity | None = None
    monitoring_active: bool | None = None


class VipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sensitivity: Sensitivity
    monitoring_active: bool
    config_version: int
    created_at: datetime


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1)
    kind: AliasKind
    is_ambiguous: bool = False


class AliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vip_id: uuid.UUID
    alias: str
    kind: AliasKind
    is_ambiguous: bool


class ContextKeywordCreate(BaseModel):
    keyword: str = Field(min_length=1)


class ContextKeywordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vip_id: uuid.UUID
    keyword: str


class OfficialAccountCreate(BaseModel):
    source: Source
    platform_account_id: str = Field(min_length=1)
    handle: str | None = None
    display_name: str | None = None
    bio: str | None = None
    avatar_object_key: str | None = None
    verification_evidence: str | None = None


class OfficialAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vip_id: uuid.UUID
    source: Source
    platform_account_id: str
    handle: str | None
    display_name: str | None
    bio: str | None
    verification_evidence: str | None
    profile_refreshed_at: datetime | None
    verified_at: datetime | None


class ReferenceMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vip_id: uuid.UUID
    object_key: str
    kind: ReferenceMediaKind
    phash: str | None
    dhash: str | None
    created_at: datetime


class FingerprintCreate(BaseModel):
    kind: FingerprintKind
    value: str = Field(min_length=1)


class FingerprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vip_id: uuid.UUID
    kind: FingerprintKind
    salt_id: str
    created_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_type: IncidentSubject
    item_id: uuid.UUID | None
    account_id: uuid.UUID | None
    source: Source
    language: str | None
    risk_score: float
    severity: Severity
    threat_types: list[str]
    explanation: str | None
    status: IncidentStatus
    assignee_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    outcome: IncidentOutcome | None
    below_threshold: bool
    merged_into_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    detector: str
    model_version: str
    input_variant: InputVariant
    score: float
    label: str | None
    spans: list[Any]
    details: dict[str, Any]
    created_at: datetime


class IncidentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: IncidentEventType
    actor_id: uuid.UUID | None
    from_value: dict[str, Any] | None
    to_value: dict[str, Any] | None
    reason: str | None
    at: datetime


class IncidentNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    created_at: datetime


class EvidenceArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    object_key: str
    sha256: str
    size: int
    captured_at: datetime


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: Source
    platform_account_id: str
    handle: str | None
    display_name: str | None


class CampaignSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    coordination_score: float | None
    account_count: int
    item_count: int


class IncidentDetailResponse(BaseModel):
    incident: IncidentRead
    detections: list[DetectionRead]
    account: AccountSummary | None
    campaign: CampaignSummary | None
    history: list[IncidentEventRead]
    notes: list[IncidentNoteRead]
    evidence: list[EvidenceArtifactRead]


class IncidentListResponse(BaseModel):
    items: list[IncidentRead]
    next_cursor: str | None


class StatusChangeRequest(BaseModel):
    status: IncidentStatus
    reason: str | None = None
    outcome: IncidentOutcome | None = None


class AssignRequest(BaseModel):
    assignee_id: uuid.UUID


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)


class BulkStatusRequest(BaseModel):
    incident_ids: list[uuid.UUID] = Field(min_length=1)
    status: IncidentStatus
    reason: str | None = None
    outcome: IncidentOutcome | None = None


class BulkStatusResponse(BaseModel):
    applied: int
    errors: list[str]


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: UserRole
    display_name: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    role: UserRole
    mfa_enabled: bool
    is_active: bool
    created_at: datetime


class ScopeAssignRequest(BaseModel):
    can_reveal_sensitive: bool = False


class UserScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    vip_id: uuid.UUID
    can_reveal_sensitive: bool
