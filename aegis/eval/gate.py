"""Compare an evaluation report against the committed baseline."""

from __future__ import annotations

from aegis.eval.models import EvalReport

WATCHED_METRICS = ("precision", "recall")


def compare_reports(
    baseline: EvalReport,
    current: EvalReport,
    tolerance: float,
) -> list[str]:
    """Return the regressions between baseline and current, if any."""

    regressions: list[str] = []
    for detector, baseline_languages in sorted(baseline.detectors.items()):
        current_languages = current.detectors.get(detector)
        if current_languages is None:
            regressions.append(f"detector '{detector}' is missing from the current report")
            continue
        for language, baseline_metrics in sorted(baseline_languages.items()):
            current_metrics = current_languages.get(language)
            if current_metrics is None:
                regressions.append(f"{detector}/{language} is missing from the current report")
                continue
            for metric in WATCHED_METRICS:
                baseline_value = getattr(baseline_metrics, metric)
                current_value = getattr(current_metrics, metric)
                if current_value < baseline_value - tolerance:
                    regressions.append(
                        f"{detector}/{language} {metric} dropped from {baseline_value:.4f} to {current_value:.4f}"
                    )
    return regressions
