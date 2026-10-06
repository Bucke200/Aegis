"""Multilingual toxicity scoring for Stage 1.

The real scorer loads a transformers toxicity model lazily, so the lean API
image and the core test suite never import torch. Call ``get_toxicity_scorer``
and treat ``None`` as "toxicity unavailable".
"""

from __future__ import annotations

from typing import Any, Protocol

from aegis.common.config import get_settings
from aegis.common.logging import get_logger

TOXICITY_DETECTOR = "text_toxicity"
DEFAULT_TOXICITY_MODEL = "unitary/multilingual-toxic-xlm-roberta"

_log = get_logger(__name__)
_scorer: TransformersToxicityScorer | None = None
_scorer_loaded = False


class ToxicityScorer(Protocol):
    """Anything that returns a 0-1 toxicity probability for text."""

    model_version: str

    def score(self, text: str) -> float: ...


class TransformersToxicityScorer:
    """toxicity probability from a transformers text-classification pipeline."""

    def __init__(self, model: str | None = None) -> None:
        from transformers import pipeline

        settings = get_settings()
        self.model_version = model or settings.toxicity_model or DEFAULT_TOXICITY_MODEL
        self._pipeline = pipeline("text-classification", model=self.model_version, top_k=None)

    def score(self, text: str) -> float:
        results = self._pipeline(text[:2000])
        if results and isinstance(results[0], list):
            results = results[0]
        for entry in results or []:
            label = str(entry.get("label", "")).lower()
            if "toxic" in label:
                return float(entry["score"])
        if results:
            return float(results[0]["score"])
        return 0.0


def get_toxicity_scorer() -> ToxicityScorer | None:
    """Load the toxicity model once; return None when it is unavailable."""

    global _scorer, _scorer_loaded
    if _scorer_loaded:
        return _scorer
    _scorer_loaded = True
    settings = get_settings()
    if not settings.toxicity_enabled:
        _log.info("toxicity_disabled")
        return None
    try:
        _scorer = TransformersToxicityScorer()
        _log.info("toxicity_model_loaded", model=_scorer.model_version)
    except Exception as error:
        _log.warning("toxicity_unavailable", error=str(error))
        _scorer = None
    return _scorer


def reset_toxicity_scorer() -> None:
    """Forget the cached scorer (tests and config reloads)."""

    global _scorer, _scorer_loaded
    _scorer = None
    _scorer_loaded = False


def score_toxicity(text: str, scorer: ToxicityScorer | None) -> float | None:
    """Score text with the given scorer, or return None when absent."""

    if scorer is None:
        return None
    return max(0.0, min(1.0, scorer.score(text)))


def scorer_metadata(scorer: ToxicityScorer | None) -> dict[str, Any]:
    return {"model_version": getattr(scorer, "model_version", None)}
