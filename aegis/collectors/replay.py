"""Replay JSONL items into ``items.raw``.

Preserves the relative timing of the original dataset, scaled by ``--speed``,
or emits at a fixed ``--rate`` items per second.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aegis.common.logging import configure_logging, get_logger
from aegis.common.messaging import Producer, broker_channel
from aegis.common.schemas import ItemV1, load_item
from aegis.common.topology import ITEMS_RAW


def load_items(path: Path) -> list[ItemV1]:
    """Load and validate a JSONL dataset."""

    items: list[ItemV1] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            items.append(load_item(json.loads(stripped)))
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}:{line_number}: invalid item: {error}") from error
    return items


@dataclass(frozen=True)
class ReplaySchedule:
    """Per-item delay before publishing each item."""

    delays: list[float]

    @classmethod
    def from_timestamps(
        cls,
        timestamps: Sequence[datetime],
        *,
        speed: float = 1.0,
        rate: float | None = None,
    ) -> ReplaySchedule:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        if rate is not None:
            if rate <= 0:
                raise ValueError("rate must be > 0")
            step = 1.0 / rate
            return cls([0.0] + [step] * (len(timestamps) - 1))
        delays = [0.0]
        for previous, current in zip(timestamps, timestamps[1:], strict=False):
            delays.append(max((current - previous).total_seconds(), 0.0) / speed)
        return cls(delays)

    def total_seconds(self) -> float:
        return sum(self.delays)


def schedule_for(
    items: Sequence[ItemV1],
    *,
    speed: float = 1.0,
    rate: float | None = None,
) -> ReplaySchedule:
    """Build a schedule from item timestamps."""

    return ReplaySchedule.from_timestamps([item.collected_at for item in items], speed=speed, rate=rate)


async def replay_items(
    items: Sequence[ItemV1],
    producer: Producer,
    *,
    queue_name: str = ITEMS_RAW,
    schedule: ReplaySchedule | None = None,
) -> int:
    """Publish items to the raw queue, sleeping between them per the schedule."""

    delays = schedule.delays if schedule else [0.0] * len(items)
    published = 0
    for item, delay in zip(items, delays, strict=True):
        if delay > 0:
            await asyncio.sleep(delay)
        await producer.publish_raw(
            queue_name,
            item.model_dump_json().encode(),
            headers={"replay": True, "source": item.source.value},
        )
        published += 1
    return published


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis.collectors.replay",
        description="Replay a JSONL item dataset into items.raw",
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--rate", type=float, default=None)
    parser.add_argument("--limit", type=int, default=None)
    return parser


async def _run(args: argparse.Namespace) -> int:
    configure_logging()
    log = get_logger("replay")
    items = load_items(args.file)
    if args.limit is not None:
        items = items[: args.limit]
    ordered = sorted(items, key=lambda item: item.collected_at)
    schedule = schedule_for(ordered, speed=args.speed, rate=args.rate)
    log.info("replay_started", items=len(ordered), seconds=round(schedule.total_seconds(), 2))
    async with broker_channel() as channel:
        count = await replay_items(ordered, Producer(channel), schedule=schedule)
    print(f"replayed {count} items into {ITEMS_RAW}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
