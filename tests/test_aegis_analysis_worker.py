"""Analysis worker integration tests (Postgres)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.models.collected import Account, Item
from aegis.common.models.enums import AliasKind
from aegis.common.models.incidents import Detection, Incident
from aegis.common.models.ops import Outbox
from aegis.common.models.reference import VIP, VipAlias
from aegis.detectors.mentions import resolve_for_item
from aegis.detectors.text import DetectionDraft
from aegis.pipeline.analysis import finalize_analysis, prepare_analysis
from aegis.pipeline.normalizer import Normalizer

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)

THREAT_TEXT = "I will shoot asha example with a gun tomorrow"


class FakeToxicityScorer:
    model_version = "fake-toxicity"

    def __init__(self, score: float) -> None:
        self._score = score

    def score(self, text: str) -> float:
        return self._score


def _payload(text: str) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=71,
            campaign_accounts=1,
            impersonators=0,
            leaks=0,
            hinglish_threats=0,
            criticism=0,
        )
    )[0]
    payload = json.loads(item.model_dump_json())
    payload["content"]["text"] = text
    return payload


def _setup(db_session, text: str, *, followers: int = 0) -> tuple[VIP, Item]:
    vip = VIP(name="Vip Analysis")
    db_session.add(vip)
    db_session.flush()
    db_session.add(VipAlias(vip_id=vip.id, alias="asha example", kind=AliasKind.NAME, is_ambiguous=False))
    db_session.flush()

    normalized = Normalizer().normalize(db_session, _payload(text))
    item = db_session.get(Item, uuid.UUID(normalized.item_id))
    assert item is not None
    if item.account_id and followers:
        account = db_session.get(Account, item.account_id)
        assert account is not None
        account.followers = followers
        db_session.flush()
    resolve_for_item(db_session, item)
    db_session.flush()
    return vip, item


def _detection_count(db_session, item_id: uuid.UUID) -> int:
    return db_session.execute(
        select(func.count()).select_from(Detection).where(Detection.item_id == item_id)
    ).scalar_one()


@DB_REQUIRED
def test_prepare_resolves_mentions_and_persists_stage1(db_session) -> None:
    vip, item = _setup(db_session, THREAT_TEXT)
    context = prepare_analysis(db_session, {"item_id": str(item.id)})

    assert context is not None
    assert context.item_id == item.id
    assert context.links[0].vip_id == vip.id
    assert context.links[0].match_confidence == 1.0
    assert context.stage1_passes is True
    detectors = set(db_session.execute(select(Detection.detector).where(Detection.item_id == item.id)).scalars())
    assert detectors == {"text_lexicon"}


@DB_REQUIRED
def test_finalize_creates_incident_with_outbox(db_session) -> None:
    vip, item = _setup(db_session, THREAT_TEXT, followers=100_000)
    context = prepare_analysis(db_session, {"item_id": str(item.id)})
    assert context is not None

    outcome = finalize_analysis(
        db_session,
        context,
        stage2_detection=DetectionDraft(
            detector="text_intent_llm",
            model_version="fake:1",
            score=0.9,
            label="violent_threat",
            details={"specificity": {"time": "tomorrow"}},
        ),
    )
    assert outcome.created is True
    assert outcome.incident_id is not None
    assert outcome.severity == "critical"
    assert outcome.stage2 is True
    assert _detection_count(db_session, item.id) == 2

    incident = db_session.get(Incident, outcome.incident_id)
    assert incident is not None
    assert incident.item_id == item.id
    created = db_session.execute(
        select(func.count())
        .select_from(Outbox)
        .where(Outbox.event_type == "incident.created")
        .where(Outbox.payload["item_id"].astext == str(item.id))
    ).scalar_one()
    assert created == 1


@DB_REQUIRED
def test_degraded_finalize_marks_stage1_detections(db_session) -> None:
    _, item = _setup(db_session, THREAT_TEXT, followers=100_000)
    context = prepare_analysis(db_session, {"item_id": str(item.id)})
    assert context is not None

    outcome = finalize_analysis(db_session, context, degraded=True)
    assert outcome.degraded is True
    assert outcome.incident_id is not None
    details = db_session.execute(select(Detection.details).where(Detection.item_id == item.id)).scalars()
    assert all(row.get("degraded") is True for row in details)


@DB_REQUIRED
def test_criticism_only_is_clamped(db_session) -> None:
    _, item = _setup(db_session, "asha example's policies are disappointing", followers=1_000_000)
    context = prepare_analysis(
        db_session,
        {"item_id": str(item.id)},
        toxicity_scorer=FakeToxicityScorer(0.95),
    )
    assert context is not None

    outcome = finalize_analysis(db_session, context)
    assert outcome.risk_score == 0.54
    assert outcome.severity == "low"


@DB_REQUIRED
def test_unmentioned_item_is_skipped(db_session) -> None:
    _, item = _setup(db_session, "nobody here to worry about")
    assert prepare_analysis(db_session, {"item_id": str(item.id)}) is None
    assert _detection_count(db_session, item.id) == 0
