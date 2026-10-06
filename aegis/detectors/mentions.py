"""VIP mention resolution.

Builds an Aho-Corasick automaton over every alias in three normal forms
(as-is, confusables/leet skeleton, Devanagari-transliterated) and matches text,
handles, and hashtags. Match confidence follows the design's table; ambiguous
aliases require a context keyword.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

import ahocorasick
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.common.models.collected import Item, ItemVip
from aegis.common.models.enums import AliasKind, MatchSource
from aegis.common.models.reference import VIP, VipAlias, VipContextKeyword

CONFUSABLE_MAP = str.maketrans(
    {
        "\u0430": "a",
        "\u0435": "e",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0445": "x",
        "\u0456": "i",
        "\u0458": "j",
        "\u0443": "y",
        "\u0455": "s",
        "\u03b1": "a",
        "\u03bf": "o",
        "\u03c1": "p",
        "\u03b5": "e",
        "\u03b9": "i",
        "\u03bd": "v",
        "\u03c4": "t",
        "\u03ba": "k",
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
    }
)
SEPARATORS = str.maketrans("", "", "_.-")
DEVANAGARI_MAP = str.maketrans(
    {
        "\u0905": "a",
        "\u0906": "aa",
        "\u0907": "i",
        "\u0908": "ii",
        "\u0909": "u",
        "\u090a": "uu",
        "\u090b": "ri",
        "\u090f": "e",
        "\u0910": "ai",
        "\u0913": "o",
        "\u0914": "au",
        "\u0915": "k",
        "\u0916": "kh",
        "\u0917": "g",
        "\u0918": "gh",
        "\u0919": "n",
        "\u091a": "ch",
        "\u091b": "chh",
        "\u091c": "j",
        "\u091d": "jh",
        "\u091e": "n",
        "\u091f": "t",
        "\u0920": "th",
        "\u0921": "d",
        "\u0922": "dh",
        "\u0923": "n",
        "\u0924": "t",
        "\u0925": "th",
        "\u0926": "d",
        "\u0927": "dh",
        "\u0928": "n",
        "\u092a": "p",
        "\u092b": "ph",
        "\u092c": "b",
        "\u092d": "bh",
        "\u092e": "m",
        "\u092f": "y",
        "\u0930": "r",
        "\u0932": "l",
        "\u0935": "v",
        "\u0936": "sh",
        "\u0937": "sh",
        "\u0938": "s",
        "\u0939": "h",
        "\u093e": "aa",
        "\u093f": "i",
        "\u0940": "ii",
        "\u0941": "u",
        "\u0942": "uu",
        "\u0943": "ri",
        "\u0947": "e",
        "\u0948": "ai",
        "\u094b": "o",
        "\u094c": "au",
        "\u0902": "n",
        "\u0901": "n",
        "\u0903": "h",
        "\u094d": "",
        "\u093c": "",
        "\u0964": " ",
        "\u0965": " ",
    }
)
_DOUBLED = re.compile(r"(.)\1+")

EXACT_CONFIDENCE = 1.0
NORMALIZED_CONFIDENCE = 0.9
AMBIGUOUS_WITH_CONTEXT = 0.8
AMBIGUOUS_WITHOUT_CONTEXT = 0.4

SOURCE_BY_KIND = {
    AliasKind.HANDLE: MatchSource.HANDLE,
    AliasKind.HASHTAG: MatchSource.HASHTAG,
}


def normalize_text(value: str) -> str:
    """NFKC, lowercase, and separator stripping."""

    return unicodedata.normalize("NFKC", value).lower().translate(SEPARATORS)


def skeleton(value: str) -> str:
    """Confusables and leetspeak folded to Latin."""

    return normalize_text(value).translate(CONFUSABLE_MAP)


def collapse_doubles(value: str) -> str:
    return _DOUBLED.sub(r"\1", value)


def transliterate_devanagari(value: str) -> str:
    """Rough Devanagari to Latin transliteration for alias matching."""

    return collapse_doubles(value.translate(DEVANAGARI_MAP).lower())


@dataclass(frozen=True)
class VipAliasConfig:
    vip_id: uuid.UUID
    alias: str
    kind: AliasKind
    is_ambiguous: bool


@dataclass(frozen=True)
class VipConfig:
    vip_id: uuid.UUID
    aliases: tuple[VipAliasConfig, ...]
    context_keywords: frozenset[str]


@dataclass(frozen=True)
class VipMatch:
    vip_id: uuid.UUID
    match_confidence: float
    match_source: MatchSource
    matched_value: str


def _alias_forms(value: str) -> list[str]:
    """Every form an alias is matched in."""

    forms = [
        normalize_text(value),
        skeleton(value),
        transliterate_devanagari(skeleton(value)),
    ]
    return list(dict.fromkeys(form for form in forms if form))


def _text_forms(value: str) -> list[tuple[str, float]]:
    """Normalized text forms with the confidence a match in each form earns."""

    forms = [
        (normalize_text(value), EXACT_CONFIDENCE),
        (skeleton(value), NORMALIZED_CONFIDENCE),
        (transliterate_devanagari(skeleton(value)), NORMALIZED_CONFIDENCE),
    ]
    seen: set[str] = set()
    unique: list[tuple[str, float]] = []
    for form, confidence in forms:
        if form and form not in seen:
            seen.add(form)
            unique.append((form, confidence))
    return unique


class MentionResolver:
    """Resolves text to VIPs using a per-deployment automaton."""

    def __init__(self, configs: list[VipConfig]) -> None:
        self.configs = {config.vip_id: config for config in configs}
        self.automaton: ahocorasick.Automaton | None = None
        entries: dict[str, list[tuple[uuid.UUID, VipAliasConfig]]] = {}
        for config in configs:
            for alias in config.aliases:
                for form in _alias_forms(alias.alias):
                    entries.setdefault(form, []).append((config.vip_id, alias))
        if not entries:
            return
        automaton = ahocorasick.Automaton()
        for form, values in entries.items():
            automaton.add_word(form, values)
        automaton.make_automaton()
        self.automaton = automaton

    def _source(self, alias: VipAliasConfig) -> MatchSource:
        return SOURCE_BY_KIND.get(alias.kind, MatchSource.ALIAS)

    def _confidence(self, config: VipConfig, alias: VipAliasConfig, base: float, text: str) -> float:
        if not alias.is_ambiguous:
            return base
        haystack = f"{normalize_text(text)} {skeleton(text)}"
        has_context = any(keyword and keyword in haystack for keyword in config.context_keywords)
        return AMBIGUOUS_WITH_CONTEXT if has_context else AMBIGUOUS_WITHOUT_CONTEXT

    def _consider(
        self,
        best: dict[uuid.UUID, VipMatch],
        config: VipConfig,
        alias: VipAliasConfig,
        base: float,
        text: str,
        source: MatchSource | None = None,
    ) -> None:
        confidence = self._confidence(config, alias, base, text)
        candidate = VipMatch(
            vip_id=config.vip_id,
            match_confidence=confidence,
            match_source=source or self._source(alias),
            matched_value=alias.alias,
        )
        current = best.get(config.vip_id)
        if current is None or candidate.match_confidence > current.match_confidence:
            best[config.vip_id] = candidate

    def _exact_token_matches(
        self,
        tokens: list[str],
        source: MatchSource,
        text: str,
        best: dict[uuid.UUID, VipMatch],
    ) -> None:
        if self.automaton is None:
            return
        for token in tokens:
            cleaned = token.lstrip("@#").strip()
            for form, base in _text_forms(cleaned):
                for vip_id, alias in self.automaton.get(form, []):
                    self._consider(best, self.configs[vip_id], alias, base, text, source)

    def resolve(
        self,
        text: str,
        mentions: list[str] | None = None,
        hashtags: list[str] | None = None,
    ) -> list[VipMatch]:
        best: dict[uuid.UUID, VipMatch] = {}
        if self.automaton is not None:
            for form, base in _text_forms(text):
                for _, values in self.automaton.iter(form):
                    for vip_id, alias in values:
                        self._consider(best, self.configs[vip_id], alias, base, text)
        self._exact_token_matches(mentions or [], MatchSource.HANDLE, text, best)
        self._exact_token_matches(hashtags or [], MatchSource.HASHTAG, text, best)
        return sorted(best.values(), key=lambda match: str(match.vip_id))


def load_vip_configs(session: Session) -> list[VipConfig]:
    """Load aliases and context keywords for every actively monitored VIP."""

    vip_ids = list(session.execute(select(VIP.id).where(VIP.monitoring_active.is_(True))).scalars())
    if not vip_ids:
        return []

    aliases: dict[uuid.UUID, list[VipAliasConfig]] = {vip_id: [] for vip_id in vip_ids}
    for row in session.execute(select(VipAlias).where(VipAlias.vip_id.in_(vip_ids))).scalars():
        aliases[row.vip_id].append(
            VipAliasConfig(
                vip_id=row.vip_id,
                alias=row.alias,
                kind=row.kind,
                is_ambiguous=row.is_ambiguous,
            )
        )

    keywords: dict[uuid.UUID, set[str]] = {vip_id: set() for vip_id in vip_ids}
    for keyword_row in session.execute(
        select(VipContextKeyword).where(VipContextKeyword.vip_id.in_(vip_ids))
    ).scalars():
        keywords[keyword_row.vip_id].add(normalize_text(keyword_row.keyword))

    return [
        VipConfig(
            vip_id=vip_id,
            aliases=tuple(aliases[vip_id]),
            context_keywords=frozenset(keywords[vip_id]),
        )
        for vip_id in vip_ids
        if aliases[vip_id]
    ]


def link_item_vips(session: Session, item_id: uuid.UUID, matches: list[VipMatch]) -> None:
    """Upsert the item's VIP links from resolved matches."""

    for match in matches:
        existing = session.get(ItemVip, (item_id, match.vip_id))
        if existing is None:
            session.add(
                ItemVip(
                    item_id=item_id,
                    vip_id=match.vip_id,
                    match_confidence=match.match_confidence,
                    match_source=match.match_source,
                    matched_value=match.matched_value,
                )
            )
        else:
            existing.match_confidence = match.match_confidence
            existing.match_source = match.match_source
            existing.matched_value = match.matched_value
    session.flush()


def resolve_for_item(
    session: Session,
    item: Item,
    configs: list[VipConfig] | None = None,
) -> list[VipMatch]:
    """Resolve, persist, and return the item's VIP mentions."""

    configs = configs if configs is not None else load_vip_configs(session)
    if not configs:
        return []
    resolver = MentionResolver(configs)
    relations = item.relations or {}
    matches = resolver.resolve(
        item.text or "",
        mentions=list(relations.get("mentions") or []),
        hashtags=list(relations.get("hashtags") or []),
    )
    link_item_vips(session, item.id, matches)
    return matches
