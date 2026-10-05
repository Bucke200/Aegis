"""Request and response models for the API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from aegis.common.models.enums import AliasKind, Sensitivity, Source


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
