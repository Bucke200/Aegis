"""Normalizer integration tests (Postgres)."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from sqlalchemy import func, select

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.messaging import PermanentMessageError
from aegis.common.models.collected import (
    Account,
    Item,
    ItemEngagementSnapshot,
    ItemVersion,
)
from aegis.common.models.enums import Source
from aegis.common.schemas import compute_dedup_key
from aegis.pipeline.normalizer import Normalizer

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def _payload(**overrides: Any) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=21,
            campaign_accounts=1,
            impersonators=0,
            leaks=0,
            hinglish_threats=0,
            criticism=0,
        )
    )[0]
    payload = json.loads(item.model_dump_json())
    payload.update(overrides)
    return payload


@DB_REQUIRED
def test_new_item_creates_account_and_item(db_session) -> None:
    payload = _payload()
    result = Normalizer().normalize(db_session, payload)

    assert result.created is True
    assert result.script == "Latin"
    item = db_session.execute(select(Item).where(Item.dedup_key == result.dedup_key)).scalar_one()
    account = db_session.execute(
        select(Account).where(Account.platform_account_id == payload["author"]["platform_account_id"])
    ).scalar_one()
    assert item.account_id == account.id
    assert result.language == "en"
    assert (
        db_session.execute(
            select(func.count()).select_from(ItemVersion).where(ItemVersion.item_id == item.id)
        ).scalar_one()
        == 0
    )


@DB_REQUIRED
def test_replaying_the_same_item_is_idempotent(db_session) -> None:
    normalizer = Normalizer()
    payload = _payload()
    first = normalizer.normalize(db_session, payload)
    second = normalizer.normalize(db_session, payload)

    assert second.created is False
    assert second.item_id == first.item_id
    assert (
        db_session.execute(select(func.count()).select_from(Item).where(Item.dedup_key == first.dedup_key)).scalar_one()
        == 1
    )
    assert (
        db_session.execute(
            select(func.count())
            .select_from(Account)
            .where(Account.platform_account_id == payload["author"]["platform_account_id"])
        ).scalar_one()
        == 1
    )


@DB_REQUIRED
def test_engagement_update_appends_snapshot_and_triggers_rescore(db_session) -> None:
    normalizer = Normalizer()
    normalizer.normalize(db_session, _payload())

    changed = _payload()
    changed["engagement"] = {"likes": 1000, "shares": 0, "replies": 0, "views": None}
    result = normalizer.normalize(db_session, changed)

    assert result.created is False
    assert result.rescore is True
    item = db_session.execute(select(Item).where(Item.dedup_key == result.dedup_key)).scalar_one()
    assert item.engagement["likes"] == 1000
    assert (
        db_session.execute(
            select(func.count()).select_from(ItemEngagementSnapshot).where(ItemEngagementSnapshot.item_id == item.id)
        ).scalar_one()
        == 1
    )


@DB_REQUIRED
def test_edit_creates_version_row(db_session) -> None:
    normalizer = Normalizer()
    payload = _payload()
    normalizer.normalize(db_session, payload)

    edited = _payload()
    edited["content"]["text"] = "edited text about the same item"
    result = normalizer.normalize(db_session, edited)

    assert result.edited is True
    item = db_session.execute(select(Item).where(Item.dedup_key == result.dedup_key)).scalar_one()
    version = db_session.execute(select(ItemVersion).where(ItemVersion.item_id == item.id)).scalar_one()
    assert version.change_type.value == "edit"
    assert version.text == payload["content"]["text"]
    assert item.text == "edited text about the same item"


@DB_REQUIRED
def test_invalid_payload_is_permanent(db_session) -> None:
    with pytest.raises(PermanentMessageError, match="schema validation failed"):
        Normalizer().normalize(db_session, {"schema_version": "1.0"})


@DB_REQUIRED
def test_manual_items_get_high_priority(db_session) -> None:
    payload = _payload()
    payload["source"] = "manual"
    payload["dedup_key"] = compute_dedup_key(Source.MANUAL, payload["platform_item_id"])
    result = Normalizer().normalize(db_session, payload)
    assert result.priority == 2
