"""Collected accounts, items, media, engagement, and source state."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from aegis.common.db import Base
from aegis.common.models.base import UUIDPrimaryKeyMixin, enum_column
from aegis.common.models.enums import (
    DiscoveredVia,
    ItemChangeType,
    ItemType,
    MatchSource,
    MediaType,
    ScoreState,
    Source,
    SourceHealthStatus,
)


class Account(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("source", "platform_account_id"),
        Index("ix_accounts_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_accounts_handle_trgm",
            "handle",
            postgresql_using="gin",
            postgresql_ops={"handle": "gin_trgm_ops"},
        ),
        Index(
            "ix_accounts_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_accounts_avatar_embedding_hnsw",
            "avatar_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"avatar_embedding": "vector_cosine_ops"},
        ),
    )

    source: Mapped[Source] = mapped_column(enum_column(Source, name="account_source"), nullable=False)
    platform_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    bio_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    avatar_object_key: Mapped[str | None] = mapped_column(Text)
    avatar_phash: Mapped[str | None] = mapped_column(Text)
    avatar_embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    created_at_platform: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followers: Mapped[int | None] = mapped_column(Integer)
    following: Mapped[int | None] = mapped_column(Integer)
    verified: Mapped[bool | None] = mapped_column(Boolean)
    self_labels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    discovered_via: Mapped[DiscoveredVia] = mapped_column(
        enum_column(DiscoveredVia, name="discovered_via"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    profile_hash: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)


class Item(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_tsv", "tsv", postgresql_using="gin"),
        Index("ix_items_language", "language"),
    )

    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[Source] = mapped_column(enum_column(Source, name="item_source"), nullable=False)
    platform_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    item_type: Mapped[ItemType] = mapped_column(enum_column(ItemType, name="item_type"), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    engagement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    scored_reach: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    relations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False, default="1.0")


class ItemEngagementSnapshot(Base):
    __tablename__ = "item_engagement_snapshots"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    engagement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AccountVipScore(Base):
    __tablename__ = "account_vip_scores"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[ScoreState] = mapped_column(enum_column(ScoreState, name="score_state"), nullable=False)
    prescreen_score: Mapped[float | None] = mapped_column()
    score: Mapped[float | None] = mapped_column()
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    profile_hash: Mapped[str | None] = mapped_column(Text)
    vip_config_version: Mapped[int | None] = mapped_column(Integer)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "item_versions"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    change_type: Mapped[ItemChangeType] = mapped_column(
        enum_column(ItemChangeType, name="item_change_type"), nullable=False
    )


class ItemVip(Base):
    __tablename__ = "item_vips"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    vip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vips.id", ondelete="CASCADE"), primary_key=True)
    match_confidence: Mapped[float] = mapped_column(nullable=False)
    match_source: Mapped[MatchSource] = mapped_column(enum_column(MatchSource, name="match_source"), nullable=False)
    matched_value: Mapped[str | None] = mapped_column(Text)


class Media(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "media"
    __table_args__ = (
        Index(
            "ix_media_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=True)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[MediaType] = mapped_column(enum_column(MediaType, name="media_type"), nullable=False)
    phash: Mapped[str | None] = mapped_column(Text)
    dhash: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    first_seen_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )


class ConnectorCursor(Base):
    __tablename__ = "connector_cursors"

    source: Mapped[Source] = mapped_column(enum_column(Source, name="cursor_source"), primary_key=True)
    cursor: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_after_seconds: Mapped[int | None] = mapped_column(Integer)


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[Source] = mapped_column(enum_column(Source, name="health_source"), primary_key=True)
    status: Mapped[SourceHealthStatus] = mapped_column(
        enum_column(SourceHealthStatus, name="source_health_status"), nullable=False
    )
    last_item_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LlmBudgetUsage(Base):
    __tablename__ = "llm_budget_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    tokens_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
