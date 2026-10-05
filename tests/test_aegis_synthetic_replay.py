"""Tests for the synthetic generator and the replay source."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aegis.collectors.replay import ReplaySchedule, load_items, replay_items, schedule_for
from aegis.collectors.synthetic import SyntheticConfig, generate, write_jsonl
from aegis.common.messaging import Producer, broker_channel
from aegis.common.topology import ITEMS_RAW


def test_generation_is_deterministic() -> None:
    first = generate(SyntheticConfig(seed=11))
    second = generate(SyntheticConfig(seed=11))
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]

    other = generate(SyntheticConfig(seed=12))
    assert [item.platform_item_id for item in first] != [item.platform_item_id for item in other]


def test_generated_items_validate_and_have_unique_ids() -> None:
    config = SyntheticConfig(seed=3)
    items = generate(config)
    expected = (
        config.campaign_accounts + config.impersonators + config.leaks + config.hinglish_threats + config.criticism
    )
    assert len(items) == expected
    ids = [item.platform_item_id for item in items]
    assert len(set(ids)) == len(ids)
    assert all(item.dedup_key for item in items)


def test_categories_are_present() -> None:
    items = generate(SyntheticConfig(seed=5))
    texts = [item.content.text for item in items]
    assert any(text.startswith("We must act against") for text in texts)
    assert any("@fakeupi" in text for text in texts)
    assert any("+91" in text for text in texts)
    assert any("maar dunga" in text for text in texts)
    assert any("disappointing" in text for text in texts)


def test_impersonator_handles_are_confusable() -> None:
    config = SyntheticConfig(
        seed=5,
        campaign_accounts=0,
        leaks=0,
        hinglish_threats=0,
        criticism=0,
    )
    items = generate(config)
    assert len(items) == config.impersonators
    latin = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    for item in items:
        handle = (item.author.handle or "").lstrip("@")
        assert handle != config.official_handle
        assert any(char not in latin for char in handle)


def test_write_and_reload(tmp_path: Path) -> None:
    config = SyntheticConfig(
        seed=9,
        campaign_accounts=2,
        impersonators=0,
        leaks=0,
        hinglish_threats=0,
        criticism=0,
    )
    items = generate(config)
    path = write_jsonl(items, tmp_path / "dataset.jsonl")
    reloaded = load_items(path)
    assert [item.platform_item_id for item in reloaded] == [item.platform_item_id for item in items]


def test_load_items_reports_the_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"schema_version": "1.0"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad.jsonl:1"):
        load_items(path)


def test_replay_schedule_modes() -> None:
    start = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    timestamps = [start, start + timedelta(seconds=1), start + timedelta(seconds=3)]
    assert ReplaySchedule.from_timestamps(timestamps, speed=1).delays == [0.0, 1.0, 2.0]
    assert ReplaySchedule.from_timestamps(timestamps, speed=2).delays == [0.0, 0.5, 1.0]
    assert ReplaySchedule.from_timestamps(timestamps, rate=10).delays == [0.0, 0.1, 0.1]


def test_replay_schedule_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="speed"):
        ReplaySchedule.from_timestamps([], speed=0)
    with pytest.raises(ValueError, match="rate"):
        ReplaySchedule.from_timestamps([], rate=0)


def test_schedule_for_uses_item_timestamps() -> None:
    config = SyntheticConfig(
        seed=2,
        campaign_accounts=3,
        impersonators=0,
        leaks=0,
        hinglish_threats=0,
        criticism=0,
    )
    schedule = schedule_for(generate(config), speed=20)
    assert schedule.delays[0] == 0.0
    assert schedule.delays[1] == 1.0


@pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_RABBITMQ_URL"),
    reason="AEGIS_TEST_RABBITMQ_URL is not set",
)
async def test_replay_publishes_in_order() -> None:
    config = SyntheticConfig(
        seed=42,
        campaign_accounts=3,
        impersonators=0,
        leaks=0,
        hinglish_threats=0,
        criticism=0,
    )
    items = generate(config)

    async with broker_channel(os.environ["AEGIS_TEST_RABBITMQ_URL"]) as channel:
        count = await replay_items(
            items,
            Producer(channel),
            schedule=ReplaySchedule([0.0, 0.0, 0.0]),
        )
        assert count == 3

        queue = await channel.declare_queue(ITEMS_RAW, durable=True, arguments={"x-queue-type": "quorum"})
        received = []
        for _ in range(3):
            message = await queue.get(fail=False, timeout=5)
            assert message is not None
            received.append(json.loads(message.body)["platform_item_id"])
            await message.ack()

    assert received == [item.platform_item_id for item in items]
