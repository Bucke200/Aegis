"""Committed detector caches for reproducible, cheap evaluation.

CI has no GPU and no model weights, so ``text_intent_llm`` and
``text_toxicity`` are evaluated from committed caches. The LLM cache key is the
model digest (read from Ollama's ``/api/tags``), the prompt version, and the
text hash. A missing entry fails the run loudly.

Refresh (local, once per model or prompt change):

    python -m aegis.eval cache --golden data/golden --llm --toxicity \
        --model aegis-intent --ollama-url http://localhost:11434
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from aegis.detectors.intent import PROMPT_VERSION, IntentClassifier
from aegis.eval.models import GoldenItem

DEFAULT_LLM_CACHE = Path("data/golden/llm_cache.jsonl")
DEFAULT_TOXICITY_CACHE = Path("data/golden/toxicity_cache.jsonl")


class CachedEntry(BaseModel):
    """Base for cache entries keyed by the item text hash."""

    text_sha256: str


class LlmCacheEntry(CachedEntry):
    """One cached structured LLM classification."""

    model_id: str
    model_digest: str
    prompt_version: str
    classification: dict[str, Any]
    created_at: str


class ToxicityCacheEntry(CachedEntry):
    """One cached toxicity score."""

    model_version: str
    score: float
    created_at: str


class ToxicityScorerLike(Protocol):
    model_version: str

    def score(self, text: str) -> float: ...


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_entries[EntryT: CachedEntry](path: Path, model: type[EntryT]) -> dict[str, EntryT]:
    if not path.exists():
        return {}
    entries: dict[str, EntryT] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = model.model_validate_json(line)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: invalid cache entry: {error}") from error
        entries[entry.text_sha256] = entry
    return entries


def write_entries[EntryT: CachedEntry](entries: Iterable[EntryT], path: Path) -> Path:
    ordered = sorted(entries, key=lambda entry: entry.text_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(entry.model_dump_json() for entry in ordered) + "\n",
        encoding="utf-8",
    )
    return path


def load_llm_cache(path: Path = DEFAULT_LLM_CACHE) -> dict[str, LlmCacheEntry]:
    return _load_entries(path, LlmCacheEntry)


def load_toxicity_cache(path: Path = DEFAULT_TOXICITY_CACHE) -> dict[str, ToxicityCacheEntry]:
    return _load_entries(path, ToxicityCacheEntry)


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def fetch_ollama_digest(ollama_url: str, model: str) -> str:
    """Return the model digest from the Ollama tags API."""

    response = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=10.0)
    response.raise_for_status()
    for entry in response.json().get("models", []):
        name = str(entry.get("name", ""))
        if name == model or name.startswith(f"{model}:"):
            digest = entry.get("digest")
            if digest:
                return str(digest)
    raise LookupError(f"model {model!r} not found at {ollama_url}")


async def refresh_llm_cache(
    items: list[GoldenItem],
    *,
    classifier: IntentClassifier,
    model_id: str,
    model_digest: str,
    path: Path = DEFAULT_LLM_CACHE,
    prompt_version: str = PROMPT_VERSION,
    force: bool = False,
) -> int:
    """Classify every labelled item and write entries for missing keys."""

    entries = {} if force else load_llm_cache(path)
    written = 0
    for item in items:
        if not item.effective_label:
            continue
        key = text_sha256(item.text)
        existing = entries.get(key)
        if existing is not None and existing.model_digest == model_digest and existing.prompt_version == prompt_version:
            continue
        classification = await classifier.classify(item.text, [])
        entries[key] = LlmCacheEntry(
            text_sha256=key,
            model_id=model_id,
            model_digest=model_digest,
            prompt_version=prompt_version,
            classification=classification.model_dump(),
            created_at=_now(),
        )
        written += 1
    write_entries(entries.values(), path)
    return written


def refresh_toxicity_cache(
    items: list[GoldenItem],
    *,
    scorer: ToxicityScorerLike,
    path: Path = DEFAULT_TOXICITY_CACHE,
    force: bool = False,
) -> int:
    """Score every labelled item and write entries for missing keys."""

    entries = {} if force else load_toxicity_cache(path)
    written = 0
    for item in items:
        if not item.effective_label:
            continue
        key = text_sha256(item.text)
        existing = entries.get(key)
        if existing is not None and existing.model_version == scorer.model_version:
            continue
        entries[key] = ToxicityCacheEntry(
            text_sha256=key,
            model_version=scorer.model_version,
            score=round(float(scorer.score(item.text)), 6),
            created_at=_now(),
        )
        written += 1
    write_entries(entries.values(), path)
    return written
