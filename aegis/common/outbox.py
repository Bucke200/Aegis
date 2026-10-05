"""Transactional outbox.

Callers write an outbox row with ``enqueue`` inside the same database
transaction as the change it describes. The outbox publisher picks committed
rows up afterwards, so a rolled-back transaction publishes nothing and a
publisher crash cannot lose an event.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from aegis.common.models.ops import Outbox
from aegis.common.topology import EVENTS_CONFIG, EVENTS_INCIDENTS

INCIDENT_CREATED = "incident.created"
INCIDENT_UPDATED = "incident.updated"
INCIDENT_MERGED = "incident.merged"
CONFIG_CHANGED = "config.changed"

INCIDENT_EVENT_TYPES: tuple[str, ...] = (
    INCIDENT_CREATED,
    INCIDENT_UPDATED,
    INCIDENT_MERGED,
)
CONFIG_EVENT_TYPES: tuple[str, ...] = (CONFIG_CHANGED,)


class UnknownEventTypeError(ValueError):
    """Raised when an outbox row has no exchange route."""


def enqueue(session: Session, event_type: str, payload: dict[str, Any]) -> Outbox:
    """Add an outbox row to the caller's transaction."""

    row = Outbox(event_type=event_type, payload=payload)
    session.add(row)
    return row


def route_for(event_type: str) -> tuple[str, str]:
    """Return the ``(exchange, routing_key)`` for an event type."""

    if event_type in INCIDENT_EVENT_TYPES:
        return EVENTS_INCIDENTS, event_type
    if event_type in CONFIG_EVENT_TYPES:
        return EVENTS_CONFIG, ""
    raise UnknownEventTypeError(f"no route for event type {event_type!r}")
