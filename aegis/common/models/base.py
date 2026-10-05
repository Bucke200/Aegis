"""Shared ORM mixins and column helpers."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key generated in Python."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """Adds a server-defaulted ``created_at`` timestamp."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UpdatedAtMixin:
    """Adds server-defaulted ``created_at``/``updated_at`` timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def enum_column(enum_cls: type[enum.Enum], *, name: str, length: int = 32) -> sa.Enum:
    """A VARCHAR-backed enum with a check constraint and value-based storage."""

    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def jsonb_object() -> postgresql.JSONB:
    """A JSONB column defaulting to an empty object."""

    return postgresql.JSONB(astext_type=sa.Text())
