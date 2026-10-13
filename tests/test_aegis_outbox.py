"""Unit tests for the transactional outbox helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from aegis.common.messaging import event_id_of
from aegis.common.models.ops import Outbox
from aegis.common.outbox import (
    CONFIG_CHANGED,
    EVIDENCE_CAPTURE_REQUESTED,
    INCIDENT_CREATED,
    INCIDENT_MERGED,
    INCIDENT_UPDATED,
    UnknownEventTypeError,
    enqueue,
    route_for,
)
from aegis.common.topology import EVENTS_CONFIG, EVENTS_INCIDENTS, EVIDENCE_CAPTURE
from aegis.pipeline import outbox_publisher
from aegis.pipeline.outbox_publisher import publish_once


def test_incident_events_route_to_the_incident_exchange() -> None:
    for event_type in (INCIDENT_CREATED, INCIDENT_UPDATED, INCIDENT_MERGED):
        assert route_for(event_type) == (EVENTS_INCIDENTS, event_type)


def test_capture_events_route_through_the_default_exchange() -> None:
    assert route_for(EVIDENCE_CAPTURE_REQUESTED) == ("", EVIDENCE_CAPTURE)


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


def test_publish_once_uses_the_default_exchange_for_capture_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    default = object()
    published: list[tuple[object, str, str | None]] = []
    marked: list[list[str]] = []

    class FakeProducer:
        def __init__(self, channel: object) -> None:
            self.channel = channel

        async def publish(
            self,
            exchange: object,
            routing_key: str,
            payload: dict[str, object],
            **kwargs: object,
        ) -> None:
            message_id = kwargs.get("message_id")
            published.append((exchange, routing_key, str(message_id) if message_id is not None else None))

    async def fake_fetch_batch(limit: int = 100) -> list[tuple[str, str, dict[str, object]]]:
        return [("row-1", EVIDENCE_CAPTURE_REQUESTED, {"marker": "capture"})]

    async def fake_mark_published(ids: list[str]) -> None:
        marked.append(ids)

    channel = AsyncMock()
    channel.default_exchange = default
    monkeypatch.setattr(outbox_publisher, "fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(outbox_publisher, "mark_published", fake_mark_published)
    monkeypatch.setattr(outbox_publisher, "Producer", FakeProducer)

    count = asyncio.run(publish_once(channel))

    assert count == 1
    assert published == [(default, EVIDENCE_CAPTURE, "row-1")]
    assert marked == [["row-1"]]
    channel.declare_queue.assert_awaited_once()
