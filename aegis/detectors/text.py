"""Stage 1 text detection: lexicons plus optional multilingual toxicity."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from aegis.common.config import get_settings
from aegis.common.models.enums import InputVariant
from aegis.detectors.lexicons import LEXICON_VERSION, LexiconResult, score_lexicon
from aegis.detectors.toxicity import TOXICITY_DETECTOR, ToxicityScorer, score_toxicity

TEXT_LEXICON_DETECTOR = "text_lexicon"
DEFAULT_STAGE1_THRESHOLD = 0.35


@dataclass(frozen=True)
class DetectionDraft:
    """One detector's output, ready to persist or score."""

    detector: str
    model_version: str
    score: float
    label: str | None = None
    spans: list[dict[str, object]] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)
    input_variant: InputVariant = InputVariant.TEXT


@dataclass(frozen=True)
class Stage1Result:
    detections: list[DetectionDraft]
    passes: bool
    threat_class: bool


def lexicon_detection(result: LexiconResult) -> DetectionDraft | None:
    if not result.hits:
        return None
    return DetectionDraft(
        detector=TEXT_LEXICON_DETECTOR,
        model_version=LEXICON_VERSION,
        score=result.score,
        label=result.label,
        spans=result.spans(),
        details={
            "threat_class": result.threat_class,
            "categories": sorted({hit.category for hit in result.hits}),
        },
    )


def toxicity_detection(text: str, scorer: ToxicityScorer | None) -> DetectionDraft | None:
    score = score_toxicity(text, scorer)
    if score is None:
        return None
    return DetectionDraft(
        detector=TOXICITY_DETECTOR,
        model_version=str(getattr(scorer, "model_version", "unknown")),
        score=round(score, 4),
        label="toxic" if score >= 0.5 else "not_toxic",
        spans=[],
        details={},
    )


def run_stage1(
    text: str,
    language: str | None = None,
    *,
    toxicity_scorer: ToxicityScorer | None = None,
    threshold: float | None = None,
    input_variant: InputVariant = InputVariant.TEXT,
) -> Stage1Result:
    """Run the cheap detectors and decide whether later stages are needed."""

    settings = get_settings()
    effective_threshold = settings.stage1_threshold if threshold is None else threshold
    text = text or ""

    lexicon = score_lexicon(text, language)
    detections: list[DetectionDraft] = []
    lexicon_draft = lexicon_detection(lexicon)
    if lexicon_draft is not None:
        detections.append(replace(lexicon_draft, input_variant=input_variant))
    toxicity_draft = toxicity_detection(text, toxicity_scorer)
    if toxicity_draft is not None:
        detections.append(replace(toxicity_draft, input_variant=input_variant))

    top_score = max((draft.score for draft in detections), default=0.0)
    return Stage1Result(
        detections=detections,
        passes=top_score >= effective_threshold,
        threat_class=lexicon.threat_class,
    )
