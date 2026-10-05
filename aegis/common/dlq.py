"""Inspect and re-drive dead-letter queues.

Usage:
    python -m aegis.common.dlq list
    python -m aegis.common.dlq redrive --queue items.raw --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from aio_pika.abc import AbstractChannel

from aegis.common.messaging import (
    ATTEMPTS_HEADER,
    REDRIVEN_HEADER,
    Producer,
    broker_channel,
)
from aegis.common.topology import QUORUM, WORK_QUEUES, dead_letter_queue, declare_topology


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis.common.dlq",
        description="Inspect and re-drive Aegis dead-letter queues",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="show the dead-letter count for every work queue")
    redrive = subparsers.add_parser("redrive", help="move messages back to their work queue")
    redrive.add_argument("--queue", required=True, choices=list(WORK_QUEUES))
    redrive.add_argument("--limit", type=int, default=100)
    return parser


async def dead_letter_counts(channel: AbstractChannel) -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    for queue_name in WORK_QUEUES:
        queue = await channel.declare_queue(dead_letter_queue(queue_name), durable=True, arguments=dict(QUORUM))
        counts.append((queue_name, queue.declaration_result.message_count or 0))
    return counts


async def redrive_queue(channel: AbstractChannel, queue_name: str, limit: int) -> int:
    """Move messages from a DLQ back to its work queue, resetting attempts."""

    await declare_topology(channel)
    producer = Producer(channel)
    source = await channel.declare_queue(dead_letter_queue(queue_name), durable=True, arguments=dict(QUORUM))
    moved = 0
    while moved < limit:
        message = await source.get(fail=False, timeout=1)
        if message is None:
            break
        headers = {key: value for key, value in dict(message.headers or {}).items() if key != ATTEMPTS_HEADER}
        headers[REDRIVEN_HEADER] = True
        await producer.publish_raw(queue_name, message.body, headers=headers, priority=message.priority)
        await message.ack()
        moved += 1
    return moved


async def _run(args: argparse.Namespace) -> int:
    async with broker_channel() as channel:
        if args.command == "list":
            for queue_name, count in await dead_letter_counts(channel):
                print(f"{queue_name}: {count} dead-lettered")
            return 0
        moved = await redrive_queue(channel, args.queue, args.limit)
        print(f"re-drove {moved} messages from {dead_letter_queue(args.queue)}")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
