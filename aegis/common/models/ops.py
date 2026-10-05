"""Evidence, custody, alerting, feedback, access control, and outbox tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aegis.common.db import Base
from aegis.common.models.base import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column
from aegis.common.models.enums import (
    AlertChannel,
    AlertDeliveryStatus,
    AlertScope,
    CustodyAction,
    CustodyTargetType,
    EvidenceKind,
    LabelKind,
    Severity,
    SuppressionScope,
    UserRole,
)


class EvidenceArtifact(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "evidence_artifacts"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[EvidenceKind] = mapped_column(
        enum_column(EvidenceKind, name="evidence_kind"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvidenceManifest(Base):
    __tablename__ = "evidence_manifests"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    manifest_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    prev_manifest_sha256: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tsa_token: Mapped[str | None] = mapped_column(Text)


class CustodyLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "custody_log"
    __table_args__ = (
        CheckConstraint(
            "(target_type = 'artifact' AND artifact_id IS NOT NULL "
            "AND manifest_incident_id IS NULL AND manifest_version IS NULL) "
            "OR (target_type = 'manifest' AND artifact_id IS NULL "
            "AND manifest_incident_id IS NOT NULL AND manifest_version IS NOT NULL)",
            name="ck_custody_log_target",
        ),
    )

    target_type: Mapped[CustodyTargetType] = mapped_column(
        enum_column(CustodyTargetType, name="custody_target_type"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="CASCADE"), nullable=True
    )
    manifest_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    manifest_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[CustodyAction] = mapped_column(
        enum_column(CustodyAction, name="custody_action"), nullable=False
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertRule(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "alert_rules"

    scope: Mapped[AlertScope] = mapped_column(
        enum_column(AlertScope, name="alert_scope"), nullable=False
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    min_severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, name="alert_min_severity"), nullable=False, default=Severity.MEDIUM
    )
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    escalation_after: Mapped[int | None] = mapped_column(Integer)
    secondary_recipient: Mapped[str | None] = mapped_column(Text)


class Alert(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "alerts"

    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )
    incident_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class AlertDelivery(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "alert_deliveries"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[AlertChannel] = mapped_column(
        enum_column(AlertChannel, name="alert_channel"), nullable=False
    )
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertDeliveryStatus] = mapped_column(
        enum_column(AlertDeliveryStatus, name="alert_delivery_status"),
        nullable=False,
        default=AlertDeliveryStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Label(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "labels"
    __table_args__ = (
        CheckConstraint(
            "(item_id IS NOT NULL AND account_id IS NULL) "
            "OR (item_id IS NULL AND account_id IS NOT NULL)",
            name="ck_labels_subject",
        ),
    )

    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    labeller_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[LabelKind] = mapped_column(
        enum_column(LabelKind, name="label_kind"), nullable=False
    )
    value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SuppressionRule(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "suppression_rules"

    scope: Mapped[SuppressionScope] = mapped_column(
        enum_column(SuppressionScope, name="suppression_scope"), nullable=False
    )
    match: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class User(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, name="user_role"), nullable=False, default=UserRole.VIEWER
    )
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    totp_secret: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserVipScope(Base):
    __tablename__ = "user_vip_scopes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    vip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True
    )
    can_reveal_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", "at"),)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Outbox(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_unpublished", "created_at", postgresql_where="published_at IS NULL"),
    )

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavedSearch(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "saved_searches"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
