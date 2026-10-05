"""Run detectors over the golden set and compute per-language metrics."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from aegis.eval.detectors import Detector
from aegis.eval.models import EvalReport, GoldenItem, Metrics

ALL_LANGUAGES = "all"


def compute_metrics(pairs: list[tuple[bool, bool]]) -> Metrics:
    """Compute metrics from (expected, predicted) pairs."""

    tp = sum(1 for expected, predicted in pairs if expected and predicted)
    fp = sum(1 for expected, predicted in pairs if not expected and predicted)
    fn = sum(1 for expected, predicted in pairs if expected and not predicted)
    tn = sum(1 for expected, predicted in pairs if not expected and not predicted)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return Metrics(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        support=tp + fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
    )


def evaluate(
    items: list[GoldenItem],
    detectors: dict[str, Detector],
    golden_path: str,
) -> EvalReport:
    """Evaluate every detector that the golden set labels."""

    by_detector: dict[str, dict[str, Metrics]] = {}
    for name, detector in detectors.items():
        labelled = [item for item in items if name in item.labels]
        if not labelled:
            continue
        grouped: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
        for item in labelled:
            expected = bool(item.labels[name])
            predicted = bool(detector(item))
            grouped[item.language].append((expected, predicted))
            grouped[ALL_LANGUAGES].append((expected, predicted))
        by_detector[name] = {language: compute_metrics(pairs) for language, pairs in sorted(grouped.items())}

    return EvalReport(
        generated_at=datetime.now(tz=UTC).isoformat(),
        golden_path=golden_path,
        item_count=len(items),
        detectors=by_detector,
    )
