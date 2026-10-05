"""Evaluation data models."""

from __future__ import annotations

from pydantic import BaseModel


class GoldenItem(BaseModel):
    """One labelled item in the golden evaluation set."""

    id: str
    language: str
    text: str
    labels: dict[str, bool]
    intent: str | None = None
    source: str = "synthetic"
    notes: str = ""


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


class EvalReport(BaseModel):
    """Per-detector, per-language evaluation report."""

    generated_at: str
    golden_path: str
    item_count: int
    detectors: dict[str, dict[str, Metrics]]
