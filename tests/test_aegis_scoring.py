"""Unit tests for the scoring engine."""

from __future__ import annotations

import uuid

import pytest

from aegis.pipeline.scoring import (
    CRITICISM_CLAMP,
    DetectorScore,
    ScoringConfig,
    VipLink,
    incident_vip_ids,
    mention_multiplier,
    noisy_or,
    reach_multiplier,
    score_item,
    severity_for,
    threat_types_for,
    vip_multiplier,
)

VIP = uuid.uuid4()


def test_noisy_or_matches_the_worked_example() -> None:
    toxicity = 0.55 * 0.9
    llm = 0.80 * 0.05
    assert noisy_or([toxicity, llm]) == pytest.approx(0.5152, abs=1e-4)


def test_reach_multiplier_is_bounded_and_monotonic() -> None:
    assert reach_multiplier(0, 0) == 0.8
    assert reach_multiplier(10, 0) < reach_multiplier(1000, 0)
    assert reach_multiplier(99_999, 0) == pytest.approx(1.2, abs=0.01)


def test_mention_and_vip_multipliers() -> None:
    assert mention_multiplier(1.0) == 1.0
    assert mention_multiplier(0.4) == pytest.approx(0.7)
    assert vip_multiplier("low") == 0.9
    assert vip_multiplier("high") == 1.15


def test_severity_bands_are_half_open() -> None:
    assert severity_for(0.29) == "low"
    assert severity_for(0.30) == "low"
    assert severity_for(0.55) == "medium"
    assert severity_for(0.75) == "high"
    assert severity_for(0.90) == "critical"
    assert severity_for(0.5499) == "low"


def test_criticism_clamp_applies_to_the_score() -> None:
    detections = [
        DetectorScore("text_toxicity", 0.95),
        DetectorScore("text_intent_llm", 0.05, label="criticism"),
    ]
    links = [VipLink(VIP, sensitivity="high", match_confidence=1.0)]
    result = score_item(ScoringConfig(), detections, links, followers=50_000, engagement_total=10_000)
    assert result.threat_class is False
    assert result.item_risk <= CRITICISM_CLAMP
    assert result.severity == "low"


def test_threat_class_llm_lifts_the_clamp() -> None:
    detections = [DetectorScore("text_intent_llm", 0.9, label="violent_threat")]
    result = score_item(ScoringConfig(), detections, [VipLink(VIP)], followers=1000)
    assert result.threat_class is True
    assert result.item_risk > CRITICISM_CLAMP


def test_violent_threat_with_specificity_overrides_critical() -> None:
    detections = [
        DetectorScore(
            "text_intent_llm",
            0.6,
            label="violent_threat",
            details={"specificity": {"location": "the office"}},
        )
    ]
    result = score_item(ScoringConfig(), detections, [VipLink(VIP)])
    assert result.override == "violent_threat_specificity"
    assert result.severity == "critical"


def test_leak_fingerprint_match_overrides_critical() -> None:
    result = score_item(ScoringConfig(), [DetectorScore("leak_fingerprint_match", 1.0)], [VipLink(VIP)])
    assert result.severity == "critical"
    assert result.override == "leak_fingerprint_match"


def test_ambiguous_mention_lowers_risk() -> None:
    detections = [DetectorScore("text_intent_llm", 0.8, label="harassment")]
    exact = score_item(ScoringConfig(), detections, [VipLink(VIP, match_confidence=1.0)])
    ambiguous = score_item(ScoringConfig(), detections, [VipLink(VIP, match_confidence=0.4)])
    assert ambiguous.item_risk < exact.item_risk


def test_incident_vip_threshold_and_capture_severity() -> None:
    config = ScoringConfig()
    weak = score_item(
        config,
        [DetectorScore("text_lexicon", 0.1, details={"threat_class": True})],
        [VipLink(VIP)],
    )
    assert incident_vip_ids(weak) == []
    assert weak.capture_required is False

    strong = score_item(
        config,
        [DetectorScore("leak_fingerprint_match", 1.0)],
        [VipLink(VIP)],
    )
    assert incident_vip_ids(strong) == [VIP]
    assert strong.capture_required is True


def test_threat_types_taxonomy() -> None:
    detections = [
        DetectorScore("text_intent_llm", 0.8, label="violent_threat"),
        DetectorScore("leak_pattern", 0.5),
        DetectorScore("repurposed_media", 0.4),
        DetectorScore("solicitation", 1.0),
    ]
    result = score_item(ScoringConfig(), detections, [VipLink(VIP)])
    assert threat_types_for(result, detections) == [
        "leak",
        "repurposed_media",
        "solicitation",
        "violent_threat",
    ]
