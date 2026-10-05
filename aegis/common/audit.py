"""Audit log helpers.

Every configuration change appends an ``audit_log`` row inside the same
transaction as the change, so the log cannot drift from the data.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from aegis.common.models.ops import AuditLog


def record(
    session: Session,
    *,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
) -> AuditLog:
    """Append an audit row to the caller's transaction."""

    row = AuditLog(
        actor_id=actor_id,
        action=action,
        target=target,
        details=details or {},
    )
    session.add(row)
    return row
