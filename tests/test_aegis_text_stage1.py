"""Tests for Stage 1 text detection."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.models.collected import Item
from aegis.common.models.incidents import Detection
from aegis.detectors.lexicons import LEXICON_VERSION, score_lexicon
from aegis.detectors.persistence import upsert_detection
from aegis.detectors.text import TEXT_LEXICON_DETECTOR, run_stage1
from aegis.detectors.toxicity import TOXICITY_DETECTOR
from aegis.pipeline.normalizer import Normalizer

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


class FakeToxicityScorer:
    model_version = "fake-toxicity-1"

    def __init__(self, value: float) -> None:
        self.value = value

    def score(self, text: str) -> float:
        return self.value


def _payload(text: str) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=41,
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


def test_lexicon_threat_hit_is_threat_class() -> None:
    result = score_lexicon("I will kill him tomorrow", "en")
    assert result.score >= 0.45
    assert result.threat_class is True
    assert result.label in {"threat_verbs", "specificity"}
    assert result.spans()


def test_abuse_alone_is_not_threat_class() -> None:
    result = score_lexicon("you are an idiot", "en")
    assert [hit.category for hit in result.hits] == ["abuse"]
    assert result.threat_class is False
    assert result.score == 0.2


def test_hinglish_and_hindi_hits() -> None:
    assert score_lexicon("usko maar dunga", "hi-Latn").hits
    assert score_lexicon("\u0917\u094b\u0932\u0940 \u092e\u093e\u0930 \u0926\u094b", "hi").hits


def test_word_boundaries_prevent_false_positives() -> None:
    assert score_lexicon("killer content marketing", "en").hits == []
    assert score_lexicon("attacking the problem politely", "en").hits == []


def test_stage1_passes_on_threat_and_stops_on_criticism() -> None:
    threat = run_stage1("I will kill him tomorrow", "en")
    assert threat.passes is True
    assert threat.threat_class is True
    assert threat.detections[0].detector == TEXT_LEXICON_DETECTOR
    assert threat.detections[0].model_version == LEXICON_VERSION

    criticism = run_stage1("I disagree with his policies", "en")
    assert criticism.passes is False
    assert criticism.detections == []


def test_stage1_uses_toxicity_scorer() -> None:
    result = run_stage1("harsh words", "en", toxicity_scorer=FakeToxicityScorer(0.8))
    assert result.passes is True
    toxicity = [d for d in result.detections if d.detector == TOXICITY_DETECTOR]
    assert len(toxicity) == 1
    assert toxicity[0].score == 0.8
    assert result.threat_class is False


def test_stage1_respects_threshold_and_variant() -> None:
    from aegis.common.models.enums import InputVariant

    result = run_stage1(
        "you are an idiot",
        "en",
        threshold=0.1,
        input_variant=InputVariant.OCR_TEXT,
    )
    assert result.passes is True
    assert result.threat_class is False
    assert result.detections[0].input_variant is InputVariant.OCR_TEXT


@DB_REQUIRED
def test_upsert_detection_is_idempotent(db_session) -> None:
    normalized = Normalizer().normalize(db_session, _payload("I will kill him tomorrow"))
    item = db_session.get(Item, uuid.UUID(normalized.item_id))
    assert item is not None

    stage1 = run_stage1(item.text or "", item.language)
    first = upsert_detection(db_session, stage1.detections[0], item_id=item.id)
    second = upsert_detection(db_session, replace(stage1.detections[0], score=0.99), item_id=item.id)

    assert first.id == second.id
    assert second.score == 0.99
    assert db_session.execute(select(func.count()).select_from(Detection)).scalar_one() == 1
