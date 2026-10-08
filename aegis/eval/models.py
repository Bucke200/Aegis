"""Evaluation data models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from aegis.detectors.intent import INTENT_LABELS


class GoldenItem(BaseModel):
    """One labelled item in the golden evaluation set.

    Legacy smoke items only carry ``labels``/``intent``. Blind-labelled items
    add provenance and review fields; ``final_label`` holds the canonical
    intent class and ``labels`` carries the binary threat labels the detector
    adapters gate on.
    """

    id: str
    language: str
    text: str
    labels: dict[str, bool]
    intent: str | None = None
    source: str = "synthetic"
    notes: str = ""
    provenance: str = "synthetic"
    intended_label: str | None = None
    blind_label: str | None = None
    final_label: str | None = None
    annotator: str | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None
    edge_case: str | None = None
    generator_model: str | None = None
    guideline_version: str | None = None

    @field_validator("intent", "intended_label", "final_label")
    @classmethod
    def _validate_labels(cls, value: str | None) -> str | None:
        if value is not None and value not in INTENT_LABELS:
            raise ValueError(f"unknown intent label {value!r}")
        return value

    @field_validator("blind_label")
    @classmethod
    def _validate_blind_label(cls, value: str | None) -> str | None:
        if value is not None and value not in (*INTENT_LABELS, "ambiguous"):
            raise ValueError(f"unknown blind label {value!r}")
        return value

    @property
    def effective_label(self) -> str | None:
        return self.final_label or self.intent


def validation_summary(error: ValueError) -> str:
    """Describe a validation error without echoing the offending input.

    Pydantic embeds the input value in ``str(error)``; for golden items and
    caches that input can be private text, so messages destined for logs must
    use only the field locations and reasons.
    """

    errors = getattr(error, "errors", None)
    if not callable(errors):
        return "invalid value"
    parts: list[str] = []
    for item in errors():
        location = ".".join(str(piece) for piece in item.get("loc", ())) or "<root>"
        parts.append(f"{location}: {item.get('msg', 'invalid')}")
    return "; ".join(parts) if parts else "invalid value"


class Metrics(BaseModel):
    """Confusion-matrix counts and derived metrics for one detector/language."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    support: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


class ClassBreakdown(BaseModel):
    """Expected-vs-predicted counts for label-predicting detectors.

    Report-only: the CI gate checks the binary aggregate metrics, because a
    100-item cell per class and language is too small to gate on reliably.
    """

    matrix: dict[str, dict[str, int]] = Field(default_factory=dict)


class EvalReport(BaseModel):
    """Per-detector, per-language evaluation report."""

    generated_at: str
    golden_path: str
    item_count: int
    detectors: dict[str, dict[str, Metrics]]
    per_class: dict[str, dict[str, ClassBreakdown]] = Field(default_factory=dict)
