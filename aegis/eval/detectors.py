"""Detector registry and the reference detector.

The reference detector exists only to exercise the harness until the real
detectors land in tasks 5-16. Real detectors register here (or in a product
registry that this module imports) and are evaluated the same way.
"""

from __future__ import annotations

from collections.abc import Callable

from aegis.eval.models import GoldenItem

Detector = Callable[[GoldenItem], bool]

DETECTORS: dict[str, Detector] = {}

REFERENCE_KEYWORDS: tuple[str, ...] = (
    "kill",
    "murder",
    "bomb",
    "maar",
    "maaro",
    "goli",
    "मार",
    "बम",
    "गोली",
)


def keyword_smoke(item: GoldenItem) -> bool:
    """Flag items containing an obvious threat keyword."""

    text = item.text.casefold()
    return any(keyword in text for keyword in REFERENCE_KEYWORDS)


def register_detector(name: str) -> Callable[[Detector], Detector]:
    """Register a detector callable under a stable name."""

    def decorator(function: Detector) -> Detector:
        if name in DETECTORS:
            raise ValueError(f"detector already registered: {name}")
        DETECTORS[name] = function
        return function

    return decorator


def get_detectors() -> dict[str, Detector]:
    """Return the reference detector plus every registered detector."""

    return {"keyword_smoke": keyword_smoke, **DETECTORS}
