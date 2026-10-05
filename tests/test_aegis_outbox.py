"""Unit tests for the transactional outbox helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from aegis.common.messaging import event_id_of
from aegis.common.models.ops import Outbox
from aegis.common.outbox import (
    CONFIG_CHANGED,
    INCIDENT_CREATED,
    INCIDENT_MERGED,
    INCIDENT_UPDATED,
    UnknownEventTypeError,
    enqueue,
    route_for,
)
from aegis.common.topology import EVENTS_CONFIG, EVENTS_INCIDENTS


def test_incident_events_route_to_the_incident_exchange() -> None:
    for event_type in (INCIDENT_CREATED, INCIDENT_UPDATED, INCIDENT_MERGED):
        assert route_for(event_type) == (EVENTS_INCIDENTS, event_type)


def test_config_event_routes_to_the_config_exchange() -> None:
    assert route_for(CONFIG_CHANGED) == (EVENTS_CONFIG, "")


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(UnknownEventTypeError, match="no route"):
        route_for("something.else")


def test_enqueue_adds_a_row_without_committing() -> None:
    session = Mock()
    row = enqueue(session, INCIDENT_CREATED, {"incident_id": "abc"})

    assert isinstance(row, Outbox)
    assert row.event_type == INCIDENT_CREATED
    assert row.payload == {"incident_id": "abc"}
    session.add.assert_called_once_with(row)
    session.commit.assert_not_called()


def test_event_id_prefers_message_id_then_header() -> None:
    message = Mock()
    message.message_id = None
    message.headers = {"event_id": "42"}
    assert event_id_of(message) == "42"

    message.message_id = "7"
    assert event_id_of(message) == "7"
