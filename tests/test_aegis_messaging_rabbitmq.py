"""RabbitMQ integration tests.

These run only when AEGIS_TEST_RABBITMQ_URL points at a disposable broker.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from aegis.common.messaging import (
    Producer,
    QueueConsumer,
    RetryPolicy,
    attempts_of,
    broker_channel,
)
from aegis.common.topology import QUORUM, dead_letter_queue, retry_queue

pytestmark = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_RABBITMQ_URL"),
    reason="AEGIS_TEST_RABBITMQ_URL is not set",
)


def _url() -> str:
    return os.environ["AEGIS_TEST_RABBITMQ_URL"]


async def _wait_until(predicate: Any, timeout: float = 15.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(0.2)
    return False


async def _declare_test_queue(channel: AbstractChannel, name: str) -> None:
    await channel.declare_queue(name, durable=True, arguments=dict(QUORUM))
    await channel.declare_queue(dead_letter_queue(name), durable=True, arguments=dict(QUORUM))
    await channel.declare_queue(
        retry_queue(name),
        durable=True,
        arguments={
            **QUORUM,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": name,
        },
    )


async def _get_dlq_message(channel: AbstractChannel, name: str) -> AbstractIncomingMessage | None:
    dlq = await channel.declare_queue(dead_letter_queue(name), durable=True, arguments=dict(QUORUM))
    return await dlq.get(fail=False, timeout=0.5)


async def test_round_trip() -> None:
    name = f"test.roundtrip.{uuid.uuid4().hex[:12]}"
    async with broker_channel(_url()) as channel:
        await _declare_test_queue(channel, name)
        producer = Producer(channel)
        await producer.publish_raw(name, b'{"hello": "world"}')

        received: list[dict[str, Any]] = []

        async def handler(payload: dict[str, Any]) -> None:
            received.append(payload)

        consumer = QueueConsumer(channel, name, handler, arguments=dict(QUORUM))
        await consumer.start()

        assert await _wait_until(lambda: asyncio.sleep(0, result=bool(received)))
        assert received == [{"hello": "world"}]


async def test_poison_message_lands_in_dlq_after_retries() -> None:
    name = f"test.poison.{uuid.uuid4().hex[:12]}"
    async with broker_channel(_url()) as channel:
        await _declare_test_queue(channel, name)
        producer = Producer(channel)
        await producer.publish_raw(name, b'{"poison": true}')

        attempts_seen: list[int] = []

        async def failing_handler(payload: dict[str, Any]) -> None:
            attempts_seen.append(len(attempts_seen) + 1)
            raise RuntimeError("poison")

        consumer = QueueConsumer(
            channel,
            name,
            failing_handler,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.1, max_delay_seconds=1),
            arguments=dict(QUORUM),
        )
        await consumer.start()

        dead_lettered: dict[str, AbstractIncomingMessage] = {}

        async def fetch() -> bool:
            message = await _get_dlq_message(channel, name)
            if message is None:
                return False
            dead_lettered["message"] = message
            return True

        assert await _wait_until(fetch)
        assert attempts_of(dead_lettered["message"]) == 2
