"""Detector adapters that make the real detectors evaluable.

``text_lexicon`` runs directly (core dependency). ``text_intent_llm`` and
``text_toxicity`` read the private caches in ``data/private/caches/`` (the
``Aegis-data`` checkout, cloned by ``make data``) so CI can evaluate them without
a GPU or model weights; a missing entry fails the run loudly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.detectors.intent import PROMPT_VERSION, THREAT_LABELS
from aegis.detectors.lexicons import score_lexicon
from aegis.eval.caches import (
    DEFAULT_LLM_CACHE,
    DEFAULT_TOXICITY_CACHE,
    load_llm_cache,
    load_toxicity_cache,
    text_sha256,
)
from aegis.eval.detectors import Detector, Prediction, get_detectors
from aegis.eval.models import GoldenItem

TEXT_INTENT_DETECTOR = "text_intent_llm"
TEXT_LEXICON_DETECTOR = "text_lexicon"
TEXT_TOXICITY_DETECTOR = "text_toxicity"
THREAT_PROBABILITY_THRESHOLD = 0.5
TOXICITY_THRESHOLD = 0.5


def threat_probability(probabilities: dict[str, Any]) -> float:
    """P(harassment) + P(violent_threat) + P(incitement) + P(doxxing)."""

    return round(sum(float(probabilities.get(label, 0.0)) for label in THREAT_LABELS), 4)


def lexicon_detector(item: GoldenItem) -> Prediction:
    result = score_lexicon(item.text, item.language)
    return Prediction(fired=result.threat_class)


def make_llm_detector(
    cache_path: Path = DEFAULT_LLM_CACHE,
    *,
    prompt_version: str = PROMPT_VERSION,
    threshold: float = THREAT_PROBABILITY_THRESHOLD,
) -> Detector:
    entries = load_llm_cache(cache_path)

    def detector(item: GoldenItem) -> Prediction:
        entry = entries.get(text_sha256(item.text))
        if entry is None:
            raise LookupError(f"no cached LLM output for {item.id}; run `aegis.eval cache --llm`")
        if entry.prompt_version != prompt_version:
            raise ValueError(f"cached prompt version {entry.prompt_version!r} does not match {prompt_version!r}")
        probabilities = entry.classification.get("intent_probs") or {}
        label = entry.classification.get("intent")
        return Prediction(
            fired=threat_probability(probabilities) >= threshold,
            label=str(label) if label else None,
        )

    return detector


def make_toxicity_detector(
    cache_path: Path = DEFAULT_TOXICITY_CACHE,
    *,
    threshold: float = TOXICITY_THRESHOLD,
) -> Detector:
    entries = load_toxicity_cache(cache_path)

    def detector(item: GoldenItem) -> Prediction:
        entry = entries.get(text_sha256(item.text))
        if entry is None:
            raise LookupError(f"no cached toxicity score for {item.id}; run `aegis.eval cache --toxicity`")
        return Prediction(fired=entry.score >= threshold)

    return detector


def build_detectors(
    *,
    llm_cache: Path = DEFAULT_LLM_CACHE,
    toxicity_cache: Path = DEFAULT_TOXICITY_CACHE,
) -> dict[str, Detector]:
    """Reference plus real detectors; cache-backed ones only when present."""

    detectors = get_detectors()
    detectors[TEXT_LEXICON_DETECTOR] = lexicon_detector
    if Path(llm_cache).exists():
        detectors[TEXT_INTENT_DETECTOR] = make_llm_detector(llm_cache)
    if Path(toxicity_cache).exists():
        detectors[TEXT_TOXICITY_DETECTOR] = make_toxicity_detector(toxicity_cache)
    return detectors
