"""Publishes committed outbox rows to RabbitMQ.

At-least-once: a row is marked published only after its message is confirmed,
so a crash between publish and mark causes a duplicate, never a loss. Consumers
deduplicate on the event id carried in the message id.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from typing import Any

from aio_pika.abc import AbstractChannel
from sqlalchemy import func, select, update

from aegis.common.db import session_scope
from aegis.common.logging import configure_logging, get_logger
from aegis.common.messaging import Producer, broker_channel
from aegis.common.models.ops import Outbox
from aegis.common.outbox import route_for
from aegis.common.topology import EVENTS_CONFIG, EVENTS_INCIDENTS

BATCH_SIZE = 100
DEFAULT_INTERVAL_SECONDS = 2.0


def _fetch_batch(limit: int) -> list[tuple[str, str, dict[str, Any]]]:
    with session_scope() as session:
        rows = session.execute(
            select(Outbox.id, Outbox.event_type, Outbox.payload)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(limit)
        ).all()
    return [(str(row.id), row.event_type, row.payload) for row in rows]


def _mark_published(ids: list[uuid.UUID]) -> None:
    with session_scope() as session:
        session.execute(update(Outbox).where(Outbox.id.in_(ids)).values(published_at=func.now()))


async def fetch_batch(limit: int = BATCH_SIZE) -> list[tuple[str, str, dict[str, Any]]]:
    """Fetch unpublished rows without holding a transaction open while publishing."""

    return await asyncio.to_thread(_fetch_batch, limit)


async def mark_published(ids: list[str]) -> None:
    """Mark rows published after their messages were confirmed."""

    await asyncio.to_thread(_mark_published, [uuid.UUID(value) for value in ids])


async def publish_once(channel: AbstractChannel, limit: int = BATCH_SIZE) -> int:
    """Publish one batch of unpublished rows and mark them published."""

    rows = await fetch_batch(limit)
    if not rows:
        return 0

    incidents = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
    config = await channel.declare_exchange(EVENTS_CONFIG, "fanout", durable=True)
    exchanges = {EVENTS_INCIDENTS: incidents, EVENTS_CONFIG: config}

    producer = Producer(channel)
    published: list[str] = []
    for event_id, event_type, payload in rows:
        exchange_name, routing_key = route_for(event_type)
        await producer.publish(
            exchanges[exchange_name],
            routing_key,
            payload,
            headers={"event_id": event_id, "event_type": event_type},
            message_id=event_id,
        )
        published.append(event_id)

    await mark_published(published)
    return len(published)


async def run_forever(interval: float = DEFAULT_INTERVAL_SECONDS) -> None:
    """Poll the outbox until the process is stopped."""

    configure_logging()
    log = get_logger("outbox-publisher")
    async with broker_channel() as channel:
        while True:
            count = await publish_once(channel)
            if count:
                log.info("outbox_batch_published", count=count)
            await asyncio.sleep(0.0 if count else interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis.pipeline.outbox_publisher",
        description="Publish committed outbox rows to RabbitMQ",
    )
    parser.add_argument("--once", action="store_true", help="publish one batch and exit")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    return parser


async def _publish_once_and_report() -> int:
    async with broker_channel() as channel:
        return await publish_once(channel)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.once:
        print(f"published {asyncio.run(_publish_once_and_report())} events")
        return 0
    asyncio.run(run_forever(args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
