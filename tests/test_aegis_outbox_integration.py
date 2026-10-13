"""Outbox integration tests.

These run only when both AEGIS_TEST_DATABASE_URL and AEGIS_TEST_RABBITMQ_URL
are set to disposable services.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from aegis.common.messaging import broker_channel, event_id_of
from aegis.common.outbox import EVIDENCE_CAPTURE_REQUESTED, INCIDENT_CREATED, enqueue
from aegis.common.topology import EVENTS_INCIDENTS, EVIDENCE_CAPTURE, work_queue_arguments
from aegis.pipeline import outbox_publisher
from aegis.pipeline.outbox_publisher import publish_once

pytestmark = pytest.mark.skipif(
    not (os.environ.get("AEGIS_TEST_DATABASE_URL") and os.environ.get("AEGIS_TEST_RABBITMQ_URL")),
    reason="AEGIS_TEST_DATABASE_URL and AEGIS_TEST_RABBITMQ_URL are required",
)


def _broker_url() -> str:
    return os.environ["AEGIS_TEST_RABBITMQ_URL"]


def _count_rows_with_marker(engine: Engine, marker: str) -> int:
    with Session(engine) as session:
        return session.execute(
            text("SELECT count(*) FROM outbox WHERE payload->>'marker' = :marker"),
            {"marker": marker},
        ).scalar_one()


def _published_at(engine: Engine, row_id: str) -> Any:
    with Session(engine) as session:
        return session.execute(text("SELECT published_at FROM outbox WHERE id = :id"), {"id": row_id}).scalar_one()


async def _next_matching(
    queue: Any,
    row_id: str,
    count: int = 1,
    timeout: float = 15.0,
) -> list[AbstractIncomingMessage]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    matched: list[AbstractIncomingMessage] = []
    while len(matched) < count and loop.time() < deadline:
        message = await queue.get(fail=False, timeout=0.5)
        if message is not None and event_id_of(message) == row_id:
            matched.append(message)
    return matched


def test_rolled_back_transaction_publishes_nothing(pg_engine: Engine) -> None:
    marker = uuid.uuid4().hex
    with Session(pg_engine) as session:
        enqueue(session, INCIDENT_CREATED, {"marker": marker})
        session.rollback()

    assert _count_rows_with_marker(pg_engine, marker) == 0


async def test_committed_row_is_published_and_marked(pg_engine: Engine) -> None:
    marker = uuid.uuid4().hex
    with Session(pg_engine) as session:
        row = enqueue(session, INCIDENT_CREATED, {"marker": marker})
        session.commit()
        row_id = str(row.id)

    async with broker_channel(_broker_url()) as channel:
        exchange = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
        queue = await channel.declare_queue(f"test.outbox.{marker}", durable=False, exclusive=True, auto_delete=True)
        await queue.bind(exchange, "incident.#")

        published = await publish_once(channel)
        assert published >= 1

        messages = await _next_matching(queue, row_id)
        assert len(messages) == 1
        assert messages[0].headers["event_type"] == INCIDENT_CREATED

    assert _published_at(pg_engine, row_id) is not None


async def test_failed_marking_republishes_at_least_once(pg_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = uuid.uuid4().hex
    with Session(pg_engine) as session:
        row = enqueue(session, INCIDENT_CREATED, {"marker": marker})
        session.commit()
        row_id = str(row.id)

    async def _skip_marking(ids: list[str]) -> None:
        return None

    monkeypatch.setattr(outbox_publisher, "mark_published", _skip_marking)

    async with broker_channel(_broker_url()) as channel:
        exchange = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
        queue = await channel.declare_queue(
            f"test.outbox.redeliver.{marker}", durable=False, exclusive=True, auto_delete=True
        )
        await queue.bind(exchange, "incident.#")

        await publish_once(channel)
        await publish_once(channel)

        messages = await _next_matching(queue, row_id, count=2)
        assert len(messages) == 2

    assert _published_at(pg_engine, row_id) is None


async def test_publisher_routes_each_event_type_with_the_outbox_id_as_message_id(pg_engine: Engine) -> None:
    marker = uuid.uuid4().hex
    with Session(pg_engine) as session:
        incident_row = enqueue(session, INCIDENT_CREATED, {"marker": marker})
        capture_row = enqueue(session, EVIDENCE_CAPTURE_REQUESTED, {"marker": marker})
        session.commit()
        incident_row_id = str(incident_row.id)
        capture_row_id = str(capture_row.id)

    async with broker_channel(_broker_url()) as channel:
        exchange = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
        incident_queue = await channel.declare_queue(
            f"test.outbox.routing.{marker}", durable=False, exclusive=True, auto_delete=True
        )
        await incident_queue.bind(exchange, "incident.#")
        capture_queue = await channel.declare_queue(
            EVIDENCE_CAPTURE,
            durable=True,
            arguments=work_queue_arguments(EVIDENCE_CAPTURE),
        )
        await capture_queue.purge()

        published = await publish_once(channel)
        assert published >= 2

        incident_messages = await _next_matching(incident_queue, incident_row_id)
        assert len(incident_messages) == 1
        assert incident_messages[0].message_id == incident_row_id
        assert incident_messages[0].headers["event_type"] == INCIDENT_CREATED

        capture_messages = await _next_matching(capture_queue, capture_row_id)
        assert len(capture_messages) == 1
        assert capture_messages[0].message_id == capture_row_id
        assert capture_messages[0].headers["event_type"] == EVIDENCE_CAPTURE_REQUESTED
        await capture_messages[0].ack()

    assert _published_at(pg_engine, incident_row_id) is not None
    assert _published_at(pg_engine, capture_row_id) is not None
