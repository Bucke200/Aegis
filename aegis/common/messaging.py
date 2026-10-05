"""RabbitMQ producer and consumer base classes.

Consumers acknowledge a message only after the handler returns, so a handler
that commits to Postgres before returning gives ack-after-commit semantics.
Failures are re-published to a delayed-retry queue and, once the retry policy
is exhausted, to the queue's dead-letter queue.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractRobustConnection,
)

from aegis.common.config import get_settings
from aegis.common.logging import get_logger
from aegis.common.topology import (
    dead_letter_queue,
    retry_delay_seconds,
    retry_queue,
    work_queue_arguments,
)

ATTEMPTS_HEADER = "x-aegis-attempts"
REDRIVEN_HEADER = "x-aegis-redriven"

Handler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retries with exponential backoff before the DLQ."""

    max_attempts: int = 5
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0

    def delay_for(self, attempt: int) -> float:
        return retry_delay_seconds(
            attempt,
            base_delay_seconds=self.base_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
        )

    def exhausted(self, attempt: int) -> bool:
        return attempt >= self.max_attempts


def encode_message(payload: dict[str, Any], headers: dict[str, Any] | None = None) -> Message:
    """Encode a JSON payload as a persistent AMQP message."""

    return Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        headers=dict(headers or {}),
    )


def decode_message(message: AbstractIncomingMessage) -> dict[str, Any]:
    """Decode an AMQP message body as JSON."""

    decoded = json.loads(message.body.decode())
    if not isinstance(decoded, dict):
        raise ValueError("message body must be a JSON object")
    return decoded


def attempts_of(message: AbstractIncomingMessage) -> int:
    """Return how many times a message has been attempted."""

    headers = message.headers or {}
    return int(cast("int | str", headers.get(ATTEMPTS_HEADER, 0)))


def event_id_of(message: AbstractIncomingMessage) -> str | None:
    """Return the outbox event id used by consumers to deduplicate."""

    if message.message_id:
        return str(message.message_id)
    headers = message.headers or {}
    event_id = headers.get("event_id")
    return str(event_id) if event_id is not None else None


def default_exchange(channel: AbstractChannel) -> AbstractExchange:
    """Return the channel's default (nameless) exchange."""

    exchange = getattr(channel, "default_exchange", None)
    if exchange is None:
        raise RuntimeError("channel does not expose a default exchange")
    return cast(AbstractExchange, exchange)


@asynccontextmanager
async def broker_channel(
    url: str | None = None,
    *,
    publisher_confirms: bool = True,
) -> AsyncIterator[AbstractChannel]:
    """Open a robust channel; publisher confirms are on by default."""

    settings = get_settings()
    connection: AbstractRobustConnection = await aio_pika.connect_robust(url or settings.rabbitmq_url)
    try:
        yield await connection.channel(publisher_confirms=publisher_confirms)
    finally:
        await connection.close()


class Producer:
    """Publishes persistent messages with publisher confirms."""

    def __init__(self, channel: AbstractChannel) -> None:
        self.channel = channel

    async def publish(
        self,
        exchange: AbstractExchange | str,
        routing_key: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, Any] | None = None,
        priority: int | None = None,
        message_id: str | None = None,
    ) -> None:
        message = encode_message(payload, headers)
        if priority is not None:
            message.priority = priority
        if message_id is not None:
            message.message_id = message_id
        if isinstance(exchange, str):
            exchange = await self.channel.get_exchange(exchange)
        await exchange.publish(message, routing_key=routing_key)

    async def publish_raw(
        self,
        queue_name: str,
        body: bytes,
        *,
        headers: dict[str, Any] | None = None,
        priority: int | None = None,
        expiration_seconds: int | None = None,
    ) -> None:
        message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers=dict(headers or {}),
        )
        if priority is not None:
            message.priority = priority
        if expiration_seconds is not None:
            message.expiration = expiration_seconds
        await default_exchange(self.channel).publish(message, routing_key=queue_name)


class QueueConsumer:
    """Consumes one queue with ack-after-handler and DLQ fallback."""

    def __init__(
        self,
        channel: AbstractChannel,
        queue_name: str,
        handler: Handler,
        *,
        retry_policy: RetryPolicy | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        self.channel = channel
        self.queue_name = queue_name
        self.handler = handler
        self.retry_policy = retry_policy or RetryPolicy()
        self.arguments = arguments if arguments is not None else work_queue_arguments(queue_name)
        self.producer = Producer(channel)
        self.log = get_logger(__name__)

    async def start(self) -> None:
        """Declare the queue (if needed) and begin consuming."""

        queue = await self.channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments=cast(Any, self.arguments),
        )
        await queue.consume(self._on_message)

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        try:
            await self.handler(decode_message(message))
        except Exception as error:
            await self._handle_failure(message, error)
        else:
            await message.ack()

    async def _handle_failure(
        self,
        message: AbstractIncomingMessage,
        error: Exception,
    ) -> None:
        attempt = attempts_of(message) + 1
        headers = {**dict(message.headers or {}), ATTEMPTS_HEADER: attempt}
        self.log.warning(
            "message_failed",
            queue=self.queue_name,
            attempt=attempt,
            error=str(error),
        )
        if self.retry_policy.exhausted(attempt):
            await self.producer.publish_raw(
                dead_letter_queue(self.queue_name),
                message.body,
                headers=headers,
                priority=message.priority,
            )
            self.log.error("message_dead_lettered", queue=self.queue_name, attempt=attempt)
        else:
            await self.producer.publish_raw(
                retry_queue(self.queue_name),
                message.body,
                headers=headers,
                priority=message.priority,
                expiration_seconds=int(self.retry_policy.delay_for(attempt)),
            )
        await message.ack()
