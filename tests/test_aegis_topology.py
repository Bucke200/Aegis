"""Unit tests for the RabbitMQ topology and messaging helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from aio_pika import DeliveryMode

from aegis.common.messaging import (
    ATTEMPTS_HEADER,
    RetryPolicy,
    attempts_of,
    decode_message,
    encode_message,
)
from aegis.common.topology import (
    ACCOUNT_EMBEDDED,
    ACCOUNT_EMBEDDED_ROUTING_KEY,
    CONFIG_RECOMPUTE,
    EVENTS_ACCOUNTS,
    EVENTS_CONFIG,
    EVENTS_INCIDENTS,
    ITEMS_NORMALIZED,
    ITEMS_RAW,
    PRIORITY_QUEUES,
    WORK_QUEUES,
    dead_letter_queue,
    retry_delay_seconds,
    retry_queue,
    retry_queue_arguments,
    work_queue_arguments,
)


def test_names_and_exchanges() -> None:
    assert ITEMS_RAW in WORK_QUEUES
    assert ITEMS_NORMALIZED in WORK_QUEUES
    assert ACCOUNT_EMBEDDED not in WORK_QUEUES
    assert retry_queue(ITEMS_RAW) == "items.raw.retry"
    assert dead_letter_queue(ITEMS_RAW) == "items.raw.dlq"
    assert (EVENTS_INCIDENTS, EVENTS_ACCOUNTS, EVENTS_CONFIG) == (
        "events.incidents",
        "events.accounts",
        "events.config",
    )
    assert ACCOUNT_EMBEDDED_ROUTING_KEY == "account.embedded"
    assert CONFIG_RECOMPUTE == "config.recompute"


def test_work_queue_arguments_include_priority() -> None:
    assert work_queue_arguments(ITEMS_RAW) == {"x-queue-type": "quorum"}
    assert work_queue_arguments(ITEMS_NORMALIZED)["x-max-priority"] == 2
    assert PRIORITY_QUEUES[ITEMS_NORMALIZED] == 2


def test_retry_queue_dead_letters_to_the_work_queue() -> None:
    arguments = retry_queue_arguments(ITEMS_RAW)
    assert arguments["x-dead-letter-exchange"] == ""
    assert arguments["x-dead-letter-routing-key"] == ITEMS_RAW


def test_retry_delay_is_exponential_and_capped() -> None:
    assert retry_delay_seconds(1) == 5
    assert retry_delay_seconds(2) == 10
    assert retry_delay_seconds(3) == 20
    assert retry_delay_seconds(10) == 300
    with pytest.raises(ValueError, match="attempt"):
        retry_delay_seconds(0)


def test_retry_policy() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.exhausted(3) is True
    assert policy.exhausted(2) is False
    assert policy.delay_for(2) == 10


def test_encode_message_is_persistent_json() -> None:
    message = encode_message({"a": 1}, {"kind": "test"})
    assert message.delivery_mode == DeliveryMode.PERSISTENT
    assert message.content_type == "application/json"
    assert message.headers == {"kind": "test"}


def test_attempts_header_default_and_set() -> None:
    message = Mock()
    message.headers = {}
    assert attempts_of(message) == 0
    message.headers = {ATTEMPTS_HEADER: 2}
    assert attempts_of(message) == 2


def test_decode_message_rejects_non_object() -> None:
    message = Mock()
    message.body = b"[1, 2]"
    with pytest.raises(ValueError, match="JSON object"):
        decode_message(message)
