"""Tests for VIP mention resolution."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.models.collected import Item, ItemVip
from aegis.common.models.enums import AliasKind, MatchSource
from aegis.common.models.reference import VIP, VipAlias
from aegis.detectors.mentions import (
    MentionResolver,
    VipAliasConfig,
    VipConfig,
    collapse_doubles,
    load_vip_configs,
    normalize_text,
    resolve_for_item,
    skeleton,
    transliterate_devanagari,
)
from aegis.pipeline.normalizer import Normalizer

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)

VIP_A = uuid.uuid4()
VIP_B = uuid.uuid4()


def _alias(
    vip_id: uuid.UUID,
    alias: str,
    kind: AliasKind = AliasKind.NAME,
    ambiguous: bool = False,
) -> VipAliasConfig:
    return VipAliasConfig(vip_id=vip_id, alias=alias, kind=kind, is_ambiguous=ambiguous)


def _resolver(*configs: VipConfig) -> MentionResolver:
    return MentionResolver(list(configs))


def _payload(**overrides: Any) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=31,
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


def _loaded_item(session: Any, item_id: str) -> Item:
    item = session.get(Item, uuid.UUID(item_id))
    assert item is not None
    return item


def test_normalization_helpers() -> None:
    assert normalize_text("Vip_Sharma") == "vipsharma"
    assert skeleton("v\u0456p") == "vip"
    assert collapse_doubles("maar") == "mar"
    assert transliterate_devanagari("\u092e\u093e\u0930") == "mar"


def test_exact_alias_match() -> None:
    config = VipConfig(VIP_A, (_alias(VIP_A, "Vip Sharma"),), frozenset())
    matches = _resolver(config).resolve("I saw Vip Sharma today")
    assert len(matches) == 1
    assert matches[0].match_confidence == 1.0
    assert matches[0].match_source == MatchSource.ALIAS


def test_homoglyph_match_uses_normalized_confidence() -> None:
    config = VipConfig(VIP_A, (_alias(VIP_A, "vip_sharma"),), frozenset())
    matches = _resolver(config).resolve("follow v\u0456p_sharma now")
    assert matches[0].match_confidence == 0.9


def test_devanagari_alias_matches_romanized_and_devanagari_text() -> None:
    config = VipConfig(VIP_A, (_alias(VIP_A, "\u092e\u093e\u0930"),), frozenset())
    resolver = _resolver(config)
    romanized = resolver.resolve("maar dunga dekh lena")
    assert romanized[0].match_confidence == 0.9
    devanagari = resolver.resolve("\u092e\u093e\u0930 \u0926\u0942\u0902\u0917\u093e")
    assert devanagari[0].match_confidence == 1.0


def test_ambiguous_alias_requires_context() -> None:
    config = VipConfig(VIP_A, (_alias(VIP_A, "vk", ambiguous=True),), frozenset({"cricket"}))
    resolver = _resolver(config)
    assert resolver.resolve("vk said hello")[0].match_confidence == 0.4
    assert resolver.resolve("vk cricket practice")[0].match_confidence == 0.8


def test_handle_and_hashtag_matches() -> None:
    handle_config = VipConfig(VIP_A, (_alias(VIP_A, "vip_sharma", kind=AliasKind.HANDLE),), frozenset())
    by_handle = _resolver(handle_config).resolve("nothing here", mentions=["@vip_sharma"])
    assert by_handle[0].match_source == MatchSource.HANDLE
    assert by_handle[0].match_confidence == 1.0

    tag_config = VipConfig(VIP_B, (_alias(VIP_B, "vipsharma", kind=AliasKind.HASHTAG),), frozenset())
    by_tag = _resolver(tag_config).resolve("trending", hashtags=["#vipsharma"])
    assert by_tag[0].match_source == MatchSource.HASHTAG


def test_multiple_vips_are_matched() -> None:
    configs = [
        VipConfig(VIP_A, (_alias(VIP_A, "alpha"),), frozenset()),
        VipConfig(VIP_B, (_alias(VIP_B, "alpha"),), frozenset()),
    ]
    matches = _resolver(*configs).resolve("alpha is trending")
    assert {match.vip_id for match in matches} == {VIP_A, VIP_B}


@DB_REQUIRED
def test_resolve_for_item_links_item_vips(db_session) -> None:
    vip = VIP(name="Vip Integration")
    db_session.add(vip)
    db_session.flush()
    db_session.add(VipAlias(vip_id=vip.id, alias="vip sharma", kind=AliasKind.NAME, is_ambiguous=False))
    db_session.flush()

    normalized = Normalizer().normalize(db_session, _payload())
    matches = resolve_for_item(db_session, _loaded_item(db_session, normalized.item_id))
    assert [match.vip_id for match in matches] == [vip.id]

    link = db_session.get(ItemVip, (uuid.UUID(normalized.item_id), vip.id))
    assert link is not None
    assert link.match_confidence == 1.0
    assert link.match_source is MatchSource.ALIAS


@DB_REQUIRED
def test_paused_vip_is_not_matched(db_session) -> None:
    vip = VIP(name="Vip Paused", monitoring_active=False)
    db_session.add(vip)
    db_session.flush()
    db_session.add(VipAlias(vip_id=vip.id, alias="vip sharma", kind=AliasKind.NAME, is_ambiguous=False))
    db_session.flush()

    normalized = Normalizer().normalize(db_session, _payload())
    assert resolve_for_item(db_session, _loaded_item(db_session, normalized.item_id)) == []
    assert load_vip_configs(db_session) == []
