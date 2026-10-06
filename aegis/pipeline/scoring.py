"""Severity scoring: noisy-OR, multipliers, bands, overrides, and the clamp.

Pure functions with no database access, so the full decision table is unit
testable. The scorer's caller passes detections once per ``(detector,
model_version, input_variant)`` and one link per VIP.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

SCORING_CONFIG_VERSION = 1
INCIDENT_THRESHOLD = 0.30
CRITICISM_CLAMP = 0.54

DEFAULT_WEIGHTS: dict[str, float] = {
    "text_lexicon": 0.45,
    "text_toxicity": 0.55,
    "text_intent_llm": 0.80,
    "impersonation": 0.85,
    "solicitation": 0.90,
    "repurposed_media": 0.65,
    "leak_pattern": 0.70,
    "leak_fingerprint_match": 1.00,
    "campaign_member": 0.50,
    "synthetic_media": 0.30,
}
DEFAULT_BANDS: dict[str, float] = {
    "low": 0.30,
    "medium": 0.55,
    "high": 0.75,
    "critical": 0.90,
}
DEFAULT_CAPTURE_SEVERITY = "medium"
SEVERITY_ORDER = ("low", "medium", "high", "critical")

VIP_MULTIPLIERS = {"low": 0.9, "normal": 1.0, "high": 1.15}
THREAT_CLASS_DETECTORS = frozenset(
    {
        "impersonation",
        "leak_pattern",
        "leak_fingerprint_match",
        "repurposed_media",
        "campaign_member",
    }
)


@dataclass(frozen=True)
class ScoringConfig:
    version: int = SCORING_CONFIG_VERSION
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    bands: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BANDS))
    capture_severity: str = DEFAULT_CAPTURE_SEVERITY

    def weight_for(self, detector: str) -> float:
        return self.weights.get(detector, 0.5)


@dataclass(frozen=True)
class DetectorScore:
    detector: str
    score: float
    label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    vip_id: uuid.UUID | None = None


@dataclass(frozen=True)
class VipLink:
    vip_id: uuid.UUID
    sensitivity: str = "normal"
    match_confidence: float = 1.0
    name: str | None = None


@dataclass(frozen=True)
class VipRisk:
    vip_id: uuid.UUID
    risk: float
    detection_score: float
    clamped: bool
    override: str | None


@dataclass(frozen=True)
class ScoringResult:
    item_risk: float
    severity: str
    threat_class: bool
    override: str | None
    explanation: str
    capture_required: bool
    vips: list[VipRisk]


def noisy_or(weighted_scores: list[float]) -> float:
    result = 0.0
    for score in weighted_scores:
        result = 1 - (1 - result) * (1 - max(0.0, min(1.0, score)))
    return result


def reach_multiplier(followers: int, engagement_total: int) -> float:
    raw = 0.8 + 0.08 * math.log10(1 + max(followers, 0) + max(engagement_total, 0))
    return min(max(raw, 0.8), 1.2)


def vip_multiplier(sensitivity: str) -> float:
    return VIP_MULTIPLIERS.get(sensitivity, 1.0)


def mention_multiplier(match_confidence: float) -> float:
    return 0.5 + 0.5 * min(max(match_confidence, 0.0), 1.0)


def severity_for(risk: float, bands: dict[str, float] | None = None) -> str:
    """Half-open bands; a value equal to a bound belongs to the band above."""

    thresholds = bands or DEFAULT_BANDS
    if risk >= thresholds["critical"]:
        return "critical"
    if risk >= thresholds["high"]:
        return "high"
    if risk >= thresholds["medium"]:
        return "medium"
    return "low"


def is_threat_class(detections: list[DetectorScore]) -> bool:
    """Whether any threat-class signal is present (abuse alone is not)."""

    for detection in detections:
        if detection.detector == "text_intent_llm" and detection.score >= 0.5:
            return True
        if detection.detector == "text_lexicon" and detection.details.get("threat_class"):
            return True
        if detection.detector in THREAT_CLASS_DETECTORS:
            return True
    return False


def critical_override(detections: list[DetectorScore]) -> str | None:
    for detection in detections:
        if detection.detector == "text_intent_llm" and detection.label == "violent_threat":
            specificity = detection.details.get("specificity") or {}
            if any(specificity.get(key) for key in ("location", "time", "method")):
                return "violent_threat_specificity"
        if detection.detector == "leak_fingerprint_match":
            return "leak_fingerprint_match"
    return None


def _detections_for_vip(detections: list[DetectorScore], vip_id: uuid.UUID) -> list[DetectorScore]:
    return [detection for detection in detections if detection.vip_id is None or detection.vip_id == vip_id]


def score_vip(
    config: ScoringConfig,
    link: VipLink,
    detections: list[DetectorScore],
    *,
    followers: int,
    engagement_total: int,
    threat_class: bool,
) -> VipRisk:
    relevant = _detections_for_vip(detections, link.vip_id)
    detection_score = noisy_or([config.weight_for(d.detector) * d.score for d in relevant])
    risk = detection_score * reach_multiplier(followers, engagement_total)
    risk *= vip_multiplier(link.sensitivity)
    risk *= mention_multiplier(link.match_confidence)

    clamped = False
    if not threat_class and risk > CRITICISM_CLAMP:
        risk = CRITICISM_CLAMP
        clamped = True

    override = critical_override(relevant)
    if override is not None:
        risk = 1.0
    return VipRisk(
        vip_id=link.vip_id,
        risk=round(min(risk, 1.0), 4),
        detection_score=round(detection_score, 4),
        clamped=clamped,
        override=override,
    )


def build_explanation(
    detections: list[DetectorScore],
    vips: list[VipLink],
    *,
    risk: float,
    severity: str,
    followers: int,
    engagement_total: int,
) -> str:
    parts: list[str] = []
    for detection in detections:
        label = f" {detection.label}" if detection.label else ""
        parts.append(f"{detection.detector}{label} ({detection.score:.2f})")
    names = ", ".join(link.name or str(link.vip_id) for link in vips) or "no VIP"
    reach = followers + engagement_total
    return f"{severity.capitalize()} risk {risk:.2f}; signals: {', '.join(parts)}; VIP: {names}; reach {reach}."


def score_item(
    config: ScoringConfig,
    detections: list[DetectorScore],
    links: list[VipLink],
    *,
    followers: int = 0,
    engagement_total: int = 0,
) -> ScoringResult:
    """Score one item once per linked VIP and take the max."""

    threat_class = is_threat_class(detections)
    risks = [
        score_vip(
            config,
            link,
            detections,
            followers=followers,
            engagement_total=engagement_total,
            threat_class=threat_class,
        )
        for link in links
    ]
    item_risk = max((risk.risk for risk in risks), default=0.0)
    severity = severity_for(item_risk, config.bands)
    override = next((risk.override for risk in risks if risk.override), None)
    explanation = build_explanation(
        detections,
        links,
        risk=item_risk,
        severity=severity,
        followers=followers,
        engagement_total=engagement_total,
    )
    return ScoringResult(
        item_risk=item_risk,
        severity=severity,
        threat_class=threat_class,
        override=override,
        explanation=explanation,
        capture_required=severity_rank(severity) >= severity_rank(config.capture_severity),
        vips=risks,
    )


def severity_rank(severity: str) -> int:
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return 0


def incident_vip_ids(result: ScoringResult) -> list[uuid.UUID]:
    return [risk.vip_id for risk in result.vips if risk.risk >= INCIDENT_THRESHOLD]


def threat_types_for(result: ScoringResult, detections: list[DetectorScore]) -> list[str]:
    types: set[str] = set()
    for detection in detections:
        if detection.detector == "text_intent_llm" and detection.label not in (None, "none", "criticism"):
            types.add(str(detection.label))
        if detection.detector == "leak_pattern" or detection.detector == "leak_fingerprint_match":
            types.add("leak")
        if detection.detector == "repurposed_media":
            types.add("repurposed_media")
        if detection.detector == "campaign_member":
            types.add("campaign")
        if detection.detector == "impersonation":
            types.add("impersonation")
        if detection.detector == "solicitation" and detection.score > 0:
            types.add("solicitation")
    return sorted(types)
