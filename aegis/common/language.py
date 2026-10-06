"""Language and script detection for normalized items.

Devanagari is detected by script; romanized Hindi is detected with a small
Hinglish marker heuristic because statistical detectors confuse it with
English; everything else falls back to lingua.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lingua import Language, LanguageDetectorBuilder

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
LATIN = re.compile(r"[A-Za-z]")

HINGLISH_MARKERS = frozenset(
    {
        "acha",
        "accha",
        "bhai",
        "denge",
        "dunga",
        "goli",
        "hai",
        "hoga",
        "kar",
        "karo",
        "khatam",
        "kya",
        "maar",
        "maaro",
        "nahi",
        "nhi",
        "tum",
        "tumhe",
        "usko",
    }
)

_DETECTOR = LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.HINDI).build()


@dataclass(frozen=True)
class DetectedLanguage:
    language: str | None
    script: str | None


def detect_language(text: str) -> DetectedLanguage:
    """Return ``(language, script)`` for item text."""

    stripped = text.strip()
    if not stripped:
        return DetectedLanguage(None, None)

    if DEVANAGARI.search(stripped):
        return DetectedLanguage("hi", "Devanagari")

    if not LATIN.search(stripped):
        return DetectedLanguage(None, None)

    tokens = {token.strip(".,!?#@").lower() for token in stripped.split()}
    if len(tokens & HINGLISH_MARKERS) >= 2:
        return DetectedLanguage("hi-Latn", "Latin")

    detected = _DETECTOR.detect_language_of(stripped)
    if detected is Language.HINDI:
        return DetectedLanguage("hi", "Devanagari")
    return DetectedLanguage("en", "Latin")
