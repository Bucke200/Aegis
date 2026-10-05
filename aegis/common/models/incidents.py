"""Detections, incidents, scoring configs, campaigns, and the interaction graph."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.common.db import Base
from aegis.common.models.base import UUIDPrimaryKeyMixin, enum_column
from aegis.common.models.enums import (
    CampaignMemberType,
    CampaignStatus,
    DetectionScope,
    EdgeType,
    IncidentEventType,
    IncidentOutcome,
    IncidentStatus,
    IncidentSubject,
    InputVariant,
    Severity,
    Source,
)


class ScoringConfig(Base):
    __tablename__ = "scoring_configs"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    bands: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Detection(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "detections"
    __table_args__ = (
        UniqueConstraint("item_id", "detector", "model_version", "input_variant"),
        CheckConstraint(
            "(scope = 'item' AND item_id IS NOT NULL AND account_id IS NULL) "
            "OR (scope = 'account' AND account_id IS NOT NULL)",
            name="ck_detections_scope",
        ),
        Index("ix_detections_detector_created", "detector", "created_at"),
        Index("ix_detections_item_id", "item_id"),
        Index("ix_detections_account_vip", "account_id", "vip_id"),
    )

    scope: Mapped[DetectionScope] = mapped_column(
        enum_column(DetectionScope, name="detection_scope"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    vip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vips.id", ondelete="CASCADE"), nullable=True
    )
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_variant: Mapped[InputVariant] = mapped_column(
        enum_column(InputVariant, name="input_variant"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    spans: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Incident(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'item' AND item_id IS NOT NULL AND account_id IS NULL "
            "AND subject_vip_id IS NULL) "
            "OR (subject_type = 'account' AND account_id IS NOT NULL "
            "AND subject_vip_id IS NOT NULL AND item_id IS NULL)",
            name="ck_incidents_subject",
        ),
        CheckConstraint(
            "merged_into_id IS NULL OR subject_type = 'item'",
            name="ck_incidents_merged_into",
        ),
        Index(
            "uq_incidents_item",
            "item_id",
            unique=True,
            postgresql_where="subject_type = 'item'",
        ),
        Index(
            "uq_incidents_open_account",
            "account_id",
            "subject_vip_id",
            unique=True,
            postgresql_where="subject_type = 'account' AND status NOT IN ('resolved', 'false_positive')",
        ),
        Index("ix_incidents_severity_created", "severity", "created_at"),
        Index("ix_incidents_status_assignee", "status", "assignee_id"),
        Index("ix_incidents_campaign_id", "campaign_id"),
        Index("ix_incidents_source", "source"),
        Index("ix_incidents_language", "language"),
        Index(
            "ix_incidents_default_feed",
            "created_at",
            postgresql_where="merged_into_id IS NULL",
        ),
    )

    subject_type: Mapped[IncidentSubject] = mapped_column(
        enum_column(IncidentSubject, name="incident_subject"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    subject_vip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vips.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Source] = mapped_column(enum_column(Source, name="incident_source"), nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, name="incident_severity"), nullable=False, default=Severity.LOW
    )
    severity_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threat_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_column(IncidentStatus, name="incident_status"),
        nullable=False,
        default=IncidentStatus.NEW,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    scoring_config_version: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_configs.version"), nullable=True
    )
    outcome: Mapped[IncidentOutcome | None] = mapped_column(
        enum_column(IncidentOutcome, name="incident_outcome"), nullable=True
    )
    source_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    below_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IncidentVip(Base):
    __tablename__ = "incident_vips"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    vip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True
    )


class IncidentItem(Base):
    __tablename__ = "incident_items"
    __table_args__ = (Index("ix_incident_items_item_id", "item_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    item_risk: Mapped[float | None] = mapped_column(Float)


class IncidentEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_events"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[IncidentEventType] = mapped_column(
        enum_column(IncidentEventType, name="incident_event_type"), nullable=False
    )
    from_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    to_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)


class IncidentNote(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_notes"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Campaign(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "campaigns"

    vip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vips.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[CampaignStatus] = mapped_column(
        enum_column(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.OPEN,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    account_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coordination_score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)


class CampaignMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "campaign_members"
    __table_args__ = (
        CheckConstraint(
            "(member_type = 'account' AND account_id IS NOT NULL AND item_id IS NULL) "
            "OR (member_type = 'item' AND item_id IS NOT NULL AND account_id IS NULL)",
            name="ck_campaign_members_member_type",
        ),
        UniqueConstraint("campaign_id", "item_id"),
        UniqueConstraint("campaign_id", "account_id"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    member_type: Mapped[CampaignMemberType] = mapped_column(
        enum_column(CampaignMemberType, name="campaign_member_type"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )


class AccountEdge(Base):
    __tablename__ = "account_edges"

    src_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    dst_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    edge_type: Mapped[EdgeType] = mapped_column(
        enum_column(EdgeType, name="edge_type"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
