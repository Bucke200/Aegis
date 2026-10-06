"""Versioned threat/abuse lexicons for English, Hindi, and Hinglish.

Category weights feed a noisy-OR within the detector; the three threat
categories are what make an item threat-class (abuse alone is not).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LEXICON_VERSION = "2026.10.1"

CATEGORY_WEIGHTS: dict[str, float] = {
    "threat_verbs": 0.45,
    "weapons": 0.40,
    "specificity": 0.25,
    "abuse": 0.20,
}
THREAT_CATEGORIES = frozenset({"threat_verbs", "weapons", "specificity"})

LEXICONS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "threat_verbs": (
            "kill",
            "murder",
            "shoot",
            "stab",
            "hang",
            "behead",
            "burn down",
            "burn him",
            "burn her",
            "attack",
            "bomb",
            "destroy",
            "end him",
            "end her",
        ),
        "weapons": ("gun", "rifle", "pistol", "knife", "grenade", "acid attack"),
        "specificity": (
            "tomorrow",
            "tonight",
            "at his house",
            "at her house",
            "at the office",
            "at the rally",
            "at the temple",
            "at the mosque",
        ),
        "abuse": ("idiot", "stupid", "scum", "trash", "bastard", "moron"),
    },
    "hi": {
        "threat_verbs": (
            "\u092e\u093e\u0930",
            "\u0915\u0924\u094d\u0932",
            "\u0917\u094b\u0932\u0940",
            "\u092b\u093e\u0902\u0938\u0940",
            "\u091c\u0932\u093e",
            "\u0939\u092e\u0932\u093e",
            "\u092c\u092e",
            "\u0916\u0924\u092e",
        ),
        "weapons": (
            "\u092c\u0902\u0926\u0942\u0915",
            "\u092a\u093f\u0938\u094d\u091f\u0932",
            "\u091a\u093e\u0915\u0942",
            "\u0917\u094d\u0930\u0947\u0928\u0947\u0921",
            "\u0924\u0932\u0935\u093e\u0930",
        ),
        "specificity": (
            "\u0915\u0932",
            "\u0906\u091c \u0930\u093e\u0924",
            "\u0918\u0930",
            "\u0926\u092b\u094d\u0924\u0930",
            "\u0930\u0948\u0932\u0940",
            "\u092e\u0902\u0926\u093f\u0930",
            "\u092e\u0938\u094d\u091c\u093f\u0926",
        ),
        "abuse": (
            "\u092c\u0947\u0935\u0915\u0942\u092b",
            "\u0915\u092e\u0940\u0928\u093e",
            "\u0917\u0902\u0926\u093e",
        ),
    },
    "hi-Latn": {
        "threat_verbs": (
            "maar",
            "maaro",
            "katl",
            "goli",
            "phansi",
            "jala",
            "hamla",
            "bomb",
            "khatam",
            "end kar",
        ),
        "weapons": ("bandook", "pistol", "chaku", "grenade", "talwar"),
        "specificity": (
            "kal",
            "aaj raat",
            "ghar",
            "daftar",
            "rally",
            "mandir",
            "masjid",
        ),
        "abuse": ("bewakoof", "kameena", "gandu", "nalayak"),
    },
}


@dataclass(frozen=True)
class LexiconHit:
    category: str
    matched_text: str
    start: int
    end: int
    weight: float


@dataclass(frozen=True)
class LexiconResult:
    hits: list[LexiconHit] = field(default_factory=list)

    @property
    def score(self) -> float:
        score = 0.0
        for category in {hit.category for hit in self.hits}:
            score = 1 - (1 - score) * (1 - CATEGORY_WEIGHTS[category])
        return round(score, 4)

    @property
    def label(self) -> str | None:
        if not self.hits:
            return None
        return max(
            {hit.category for hit in self.hits},
            key=lambda category: CATEGORY_WEIGHTS[category],
        )

    @property
    def threat_class(self) -> bool:
        return any(hit.category in THREAT_CATEGORIES for hit in self.hits)

    def spans(self) -> list[dict[str, object]]:
        return [
            {
                "start": hit.start,
                "end": hit.end,
                "text": hit.matched_text,
                "category": hit.category,
            }
            for hit in self.hits
        ]


def _pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(" ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


_PATTERNS: dict[str, dict[str, list[re.Pattern[str]]]] = {
    language: {
        category: [_pattern(term) for term in LEXICONS[language][category]]
        for category in ("threat_verbs", "weapons", "specificity", "abuse")
    }
    for language in LEXICONS
}


def score_lexicon(text: str, language: str | None = None) -> LexiconResult:
    """Find lexicon hits in one language (or every supported language)."""

    normalized = unicodedata.normalize("NFKC", text or "")
    if not normalized.strip():
        return LexiconResult()
    languages = [language] if language in _PATTERNS else list(_PATTERNS)
    hits: list[LexiconHit] = []
    for current in languages:
        for category, patterns in _PATTERNS[current].items():
            for pattern in patterns:
                for match in pattern.finditer(normalized):
                    hits.append(
                        LexiconHit(
                            category=category,
                            matched_text=match.group(0),
                            start=match.start(),
                            end=match.end(),
                            weight=CATEGORY_WEIGHTS[category],
                        )
                    )
    return LexiconResult(hits=hits)
