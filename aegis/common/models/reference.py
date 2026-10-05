"""VIPs, aliases, official accounts, reference media, and fingerprints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from aegis.common.db import Base
from aegis.common.models.base import (
    CreatedAtMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)
from aegis.common.models.enums import (
    AliasKind,
    FingerprintKind,
    ReferenceMediaKind,
    Sensitivity,
    Source,
)


class VIP(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "vips"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    sensitivity: Mapped[Sensitivity] = mapped_column(
        enum_column(Sensitivity, name="sensitivity"), nullable=False, default=Sensitivity.NORMAL
    )
    monitoring_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scoring_config_version: Mapped[int | None] = mapped_column(ForeignKey("scoring_configs.version"), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VipAlias(Base):
    __tablename__ = "vip_aliases"

    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True)
    alias: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[AliasKind] = mapped_column(enum_column(AliasKind, name="alias_kind"), primary_key=True)
    is_ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VipContextKeyword(Base):
    __tablename__ = "vip_context_keywords"

    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True)
    keyword: Mapped[str] = mapped_column(Text, primary_key=True)


class OfficialAccount(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "official_accounts"
    __table_args__ = (
        UniqueConstraint("source", "platform_account_id"),
        Index(
            "ix_official_accounts_avatar_embedding_hnsw",
            "avatar_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"avatar_embedding": "vector_cosine_ops"},
        ),
    )

    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[Source] = mapped_column(enum_column(Source, name="official_source"), nullable=False)
    platform_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    bio_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    avatar_object_key: Mapped[str | None] = mapped_column(Text)
    avatar_phash: Mapped[str | None] = mapped_column(Text)
    avatar_embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    verification_evidence: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReferenceMedia(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "reference_media"
    __table_args__ = (
        Index(
            "ix_reference_media_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[ReferenceMediaKind] = mapped_column(
        enum_column(ReferenceMediaKind, name="reference_media_kind"), nullable=False
    )
    phash: Mapped[str | None] = mapped_column(Text)
    dhash: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SensitiveFingerprint(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sensitive_fingerprints"

    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[FingerprintKind] = mapped_column(enum_column(FingerprintKind, name="fingerprint_kind"), nullable=False)
    salted_hash: Mapped[str] = mapped_column(Text, nullable=False)
    salt_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
