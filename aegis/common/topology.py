"""RabbitMQ topology: queues, exchanges, retries, and dead letters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from aio_pika.abc import AbstractChannel, AbstractExchange

ITEMS_RAW = "items.raw"
ITEMS_NORMALIZED = "items.normalized"
MEDIA_ANALYZE = "media.analyze"
MEDIA_ANALYZED = "media.analyzed"
EVIDENCE_CAPTURE = "evidence.capture"
ACCOUNT_EMBEDDED = "analysis.account_embedded"
CONFIG_RECOMPUTE = "config.recompute"

WORK_QUEUES: tuple[str, ...] = (
    ITEMS_RAW,
    ITEMS_NORMALIZED,
    MEDIA_ANALYZE,
    MEDIA_ANALYZED,
    EVIDENCE_CAPTURE,
)

PRIORITY_QUEUES: dict[str, int] = {ITEMS_NORMALIZED: 2}

EVENTS_INCIDENTS = "events.incidents"
EVENTS_ACCOUNTS = "events.accounts"
EVENTS_CONFIG = "events.config"

WS_INCIDENTS_QUEUE = "events.incidents.ws"
ALERTING_INCIDENTS_QUEUE = "events.incidents.alerting"
INCIDENT_ROUTING_KEYS: tuple[str, ...] = (
    "incident.created",
    "incident.updated",
    "incident.merged",
)
ACCOUNT_EMBEDDED_ROUTING_KEY = "account.embedded"

QUORUM = {"x-queue-type": "quorum"}


def retry_queue(queue_name: str) -> str:
    """Name of the delayed-retry queue for a work queue."""

    return f"{queue_name}.retry"


def dead_letter_queue(queue_name: str) -> str:
    """Name of the dead-letter queue for a work queue."""

    return f"{queue_name}.dlq"


def retry_delay_seconds(
    attempt: int,
    *,
    base_delay_seconds: float = 5.0,
    max_delay_seconds: float = 300.0,
) -> float:
    """Exponential backoff for a retry attempt (1-based)."""

    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = base_delay_seconds * (2 ** (attempt - 1))
    return float(min(delay, max_delay_seconds))


def work_queue_arguments(queue_name: str) -> dict[str, object]:
    """Declaration arguments for a work queue, including priority."""

    arguments: dict[str, object] = dict(QUORUM)
    if queue_name in PRIORITY_QUEUES:
        arguments["x-max-priority"] = PRIORITY_QUEUES[queue_name]
    return arguments


def retry_queue_arguments(queue_name: str) -> dict[str, object]:
    """Retry queues dead-letter back to their work queue after the TTL."""

    return {
        **QUORUM,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": queue_name,
    }


@dataclass(frozen=True)
class Topology:
    incidents: AbstractExchange
    accounts: AbstractExchange
    config: AbstractExchange


async def declare_topology(channel: AbstractChannel) -> Topology:
    """Declare every Aegis queue, exchange, and binding (idempotent)."""

    for queue_name in WORK_QUEUES:
        await channel.declare_queue(queue_name, durable=True, arguments=cast(Any, work_queue_arguments(queue_name)))
        await channel.declare_queue(dead_letter_queue(queue_name), durable=True, arguments=dict(QUORUM))
        await channel.declare_queue(
            retry_queue(queue_name),
            durable=True,
            arguments=cast(Any, retry_queue_arguments(queue_name)),
        )

    incidents = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
    for queue_name in (WS_INCIDENTS_QUEUE, ALERTING_INCIDENTS_QUEUE):
        queue = await channel.declare_queue(queue_name, durable=True, arguments=dict(QUORUM))
        for routing_key in INCIDENT_ROUTING_KEYS:
            await queue.bind(incidents, routing_key)

    accounts = await channel.declare_exchange(EVENTS_ACCOUNTS, "topic", durable=True)
    embedded_queue = await channel.declare_queue(ACCOUNT_EMBEDDED, durable=True, arguments=dict(QUORUM))
    await embedded_queue.bind(accounts, ACCOUNT_EMBEDDED_ROUTING_KEY)

    config = await channel.declare_exchange(EVENTS_CONFIG, "fanout", durable=True)
    recompute_queue = await channel.declare_queue(CONFIG_RECOMPUTE, durable=True, arguments=dict(QUORUM))
    await recompute_queue.bind(config)

    return Topology(incidents=incidents, accounts=accounts, config=config)
