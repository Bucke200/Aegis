"""Seeded synthetic item generator.

Produces schema-v1 items for every scenario the pipeline must handle:
coordinated campaigns, homoglyph impersonators, leaks with fake PII,
Hinglish threats, and benign criticism. Deterministic for a given seed.
"""

from __future__ import annotations

import argparse
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aegis.common.models.enums import ItemType, Source
from aegis.common.schemas import ItemV1, compute_dedup_key

NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
CONFUSABLES = {"o": "\u043e", "a": "\u0430", "e": "\u0435", "i": "\u0456", "p": "\u0440"}
FAKE_UPI = "vip.payments@fakeupi"
FAKE_PHONE = "+91 50000 00001"
FAKE_AADHAAR = "1111 2222 3333"


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = 7
    campaign_accounts: int = 12
    impersonators: int = 3
    leaks: int = 3
    hinglish_threats: int = 5
    criticism: int = 5
    vip_name: str = "Asha Example"
    official_handle: str = "asha_example"
    base_time: datetime = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _homoglyph(handle: str, index: int) -> str:
    """Replace one Latin character with a confusable, deterministically."""

    available = [(char, CONFUSABLES[char]) for char in dict.fromkeys(handle) if char in CONFUSABLES]
    if not available:
        return handle + "_official"
    char, replacement = available[index % len(available)]
    return handle.replace(char, replacement, 1)


def _item(
    *,
    source: Source,
    platform_item_id: str,
    text: str,
    handle: str,
    display_name: str,
    collected_at: datetime,
    item_type: ItemType = ItemType.POST,
    self_labels: list[str] | None = None,
    engagement: int = 0,
) -> dict[str, Any]:
    author_id = f"acct-{platform_item_id}"
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "source": source.value,
        "platform_item_id": platform_item_id,
        "dedup_key": compute_dedup_key(source, platform_item_id),
        "item_type": item_type.value,
        "url": f"https://example.test/{source.value}/{platform_item_id}",
        "posted_at": collected_at.isoformat(),
        "collected_at": collected_at.isoformat(),
        "author": {
            "platform_account_id": author_id,
            "handle": handle,
            "display_name": display_name,
            "bio": f"Fan page about {display_name}",
            "avatar_url": None,
            "created_at": None,
            "followers": engagement,
            "following": 10,
            "verified": False,
            "self_labels": self_labels or [],
        },
        "content": {"text": text, "language": None, "script": None},
        "media": [],
        "relations": {
            "reply_to": None,
            "repost_of": None,
            "quote_of": None,
            "mentions": [handle],
            "hashtags": [],
        },
        "engagement": {"likes": engagement, "shares": 0, "replies": 0, "views": None},
        "collection": {
            "connector": "synthetic",
            "connector_version": "0.1.0",
            "query": None,
        },
        "raw": {"synthetic": True},
    }
    return payload


def _stable_id(config: SyntheticConfig, kind: str, index: int) -> str:
    return f"syn-{kind}-{uuid.uuid5(NAMESPACE, f'{config.seed}:{kind}:{index}').hex[:12]}"


def generate(config: SyntheticConfig | None = None) -> list[ItemV1]:
    """Generate a deterministic, schema-valid synthetic dataset."""

    config = config or SyntheticConfig()
    rng = random.Random(config.seed)
    items: list[dict[str, Any]] = []

    base_text = f"We must act against {config.vip_name} now"
    variations = ["", " !", " please", " today", " #justice", " friends", " now"]
    for index in range(config.campaign_accounts):
        handle = f"campaign_{config.seed}_{index}"
        items.append(
            _item(
                source=Source.REPLAY,
                platform_item_id=_stable_id(config, "campaign", index),
                text=base_text + rng.choice(variations),
                handle=handle,
                display_name=f"Campaign {index}",
                collected_at=config.base_time + timedelta(seconds=index * 20),
                engagement=rng.randint(5, 500),
            )
        )

    for index in range(config.impersonators):
        handle = "@" + _homoglyph(config.official_handle, index)
        items.append(
            _item(
                source=Source.MANUAL,
                platform_item_id=_stable_id(config, "impersonator", index),
                text=f"Official {config.vip_name} updates and giveaways",
                handle=handle,
                display_name=config.vip_name,
                collected_at=config.base_time + timedelta(minutes=5 + index),
                self_labels=["parody"] if index == 0 else [],
                engagement=rng.randint(1, 50),
            )
        )

    leak_texts = [
        f"processing {FAKE_UPI} for {config.vip_name}",
        f"call {FAKE_PHONE} or pay {FAKE_UPI}",
        f"records {FAKE_AADHAAR} and {FAKE_PHONE}",
    ]
    for index in range(config.leaks):
        items.append(
            _item(
                source=Source.PASTEBIN,
                platform_item_id=_stable_id(config, "leak", index),
                text=leak_texts[index % len(leak_texts)],
                handle=f"leaker_{config.seed}_{index}",
                display_name="Leaker",
                collected_at=config.base_time + timedelta(minutes=10 + index),
                item_type=ItemType.PASTE,
            )
        )

    hinglish = [
        "usko maar dunga dekh lena",
        "goli maaro usko",
        "bomb rakh denge uske ghar",
        "uska end kar denge",
        "khatam kar do usko",
    ]
    for index in range(config.hinglish_threats):
        items.append(
            _item(
                source=Source.TELEGRAM,
                platform_item_id=_stable_id(config, "hinglish", index),
                text=f"{hinglish[index % len(hinglish)]} {config.vip_name}",
                handle=f"threat_{config.seed}_{index}",
                display_name="Angry User",
                collected_at=config.base_time + timedelta(minutes=15 + index),
                item_type=ItemType.MESSAGE,
            )
        )

    criticism = [
        f"{config.vip_name}'s policies are disappointing",
        f"I disagree with {config.vip_name} on every issue",
        f"Poor leadership from {config.vip_name}",
        f"{config.vip_name} should answer questions",
        f"Not impressed by {config.vip_name}",
    ]
    for index in range(config.criticism):
        items.append(
            _item(
                source=Source.TELEGRAM,
                platform_item_id=_stable_id(config, "criticism", index),
                text=criticism[index % len(criticism)],
                handle=f"critic_{config.seed}_{index}",
                display_name="Critic",
                collected_at=config.base_time + timedelta(minutes=20 + index),
                item_type=ItemType.MESSAGE,
            )
        )

    return [ItemV1.model_validate(item) for item in items]


def write_jsonl(items: Sequence[ItemV1], path: Path) -> Path:
    """Write items as JSONL, one object per line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [item.model_dump_json() for item in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis.collectors.synthetic",
        description="Generate a seeded synthetic item dataset",
    )
    parser.add_argument("--seed", type=int, default=SyntheticConfig.seed)
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/dataset.jsonl"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    items = generate(SyntheticConfig(seed=args.seed))
    write_jsonl(items, args.out)
    print(f"wrote {len(items)} items to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
