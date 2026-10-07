"""Inter-annotator agreement for the blind labelling workflow."""

from __future__ import annotations

from collections import Counter


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa for two raters over categorical labels.

    Returns 0.0 for an empty input and 1.0 when both raters agree on every
    item, including the degenerate single-label case.
    """

    total = len(pairs)
    if total == 0:
        return 0.0
    observed = sum(1 for first, second in pairs if first == second) / total
    first_counts = Counter(first for first, _ in pairs)
    second_counts = Counter(second for _, second in pairs)
    labels = set(first_counts) | set(second_counts)
    expected = sum((first_counts[label] / total) * (second_counts[label] / total) for label in labels)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return round((observed - expected) / (1.0 - expected), 4)


def per_class_agreement(pairs: list[tuple[str, str]], label: str) -> dict[str, int]:
    """Counts for one label: both, only first (intended), only second (blind)."""

    both = sum(1 for first, second in pairs if first == label and second == label)
    only_first = sum(1 for first, second in pairs if first == label and second != label)
    only_second = sum(1 for first, second in pairs if second == label and first != label)
    return {"both": both, "only_intended": only_first, "only_blind": only_second}
