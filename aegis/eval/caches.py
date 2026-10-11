"""Private detector caches for reproducible, cheap evaluation.

CI has no GPU and no model weights, so ``text_intent_llm`` and ``text_toxicity``
are evaluated from caches stored in the private ``Aegis-data`` checkout
(``data/private/caches/``, cloned by ``make data``). The LLM cache key is the
model digest (read from Ollama's ``/api/tags``), the prompt version, and the
text hash. A missing entry fails the run loudly.

Refresh (local, once per model or prompt change):

    python -m aegis.eval cache --golden data/private/golden --llm --toxicity \
        --model aegis-intent --ollama-url http://localhost:11434

Refresh is fault-tolerant and incremental: a model output that fails to
validate is logged, counted, and left uncached so a re-run retries it, and the
cache file is checkpointed every few new entries so an interrupted run keeps
its progress.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from aegis.common.logging import get_logger
from aegis.detectors.intent import PROMPT_VERSION, IntentClassifier
from aegis.eval.models import GoldenItem, validation_summary

DEFAULT_LLM_CACHE = Path("data/private/caches/llm_cache.jsonl")
DEFAULT_TOXICITY_CACHE = Path("data/private/caches/toxicity_cache.jsonl")
CHECKPOINT_EVERY = 10

_log = get_logger(__name__)


@dataclass
class RefreshResult:
    """Outcome of one cache refresh; ``failed`` holds item ids left uncached."""

    cached: int = 0
    kept: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        line = f"cached {self.cached}, kept {self.kept}, skipped {self.skipped}, failed {len(self.failed)}"
        if self.failed:
            line += f" ({', '.join(self.failed)})"
        return line


def _failure_reason(error: Exception) -> str:
    """Describe a failure without echoing model payloads or item text."""

    if isinstance(error, ValueError) and callable(getattr(error, "errors", None)):
        return f"{type(error).__name__}: {validation_summary(error)}"
    return f"{type(error).__name__}: {error}"


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
            raise ValueError(f"{path}:{line_number}: invalid cache entry: {validation_summary(error)}") from None
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
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> RefreshResult:
    """Classify every labelled item and write entries for missing keys.

    Items whose classification fails (invalid model output or an unexpected
    error) are logged with their id, counted, and skipped, so one bad item
    cannot abort a long refresh. New entries are checkpointed to ``path`` every
    ``checkpoint_every`` results and once more at the end.
    """

    entries = {} if force else load_llm_cache(path)
    result = RefreshResult()
    pending_checkpoint = 0
    for item in items:
        if not item.effective_label:
            result.skipped += 1
            continue
        key = text_sha256(item.text)
        existing = entries.get(key)
        if existing is not None and existing.model_digest == model_digest and existing.prompt_version == prompt_version:
            result.kept += 1
            continue
        try:
            classification = await classifier.classify(item.text, [])
        except Exception as error:
            result.failed.append(item.id)
            _log.warning("llm_cache_item_failed", item_id=item.id, error=_failure_reason(error))
            continue
        entries[key] = LlmCacheEntry(
            text_sha256=key,
            model_id=model_id,
            model_digest=model_digest,
            prompt_version=prompt_version,
            classification=classification.model_dump(),
            created_at=_now(),
        )
        result.cached += 1
        pending_checkpoint += 1
        if checkpoint_every > 0 and pending_checkpoint >= checkpoint_every:
            write_entries(entries.values(), path)
            pending_checkpoint = 0
    write_entries(entries.values(), path)
    return result


def refresh_toxicity_cache(
    items: list[GoldenItem],
    *,
    scorer: ToxicityScorerLike,
    path: Path = DEFAULT_TOXICITY_CACHE,
    force: bool = False,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> RefreshResult:
    """Score every labelled item and write entries for missing keys.

    Individual scoring failures are logged and skipped, and new entries are
    checkpointed to ``path`` every ``checkpoint_every`` results and at the end,
    matching the LLM refresh behaviour.
    """

    entries = {} if force else load_toxicity_cache(path)
    result = RefreshResult()
    pending_checkpoint = 0
    for item in items:
        if not item.effective_label:
            result.skipped += 1
            continue
        key = text_sha256(item.text)
        existing = entries.get(key)
        if existing is not None and existing.model_version == scorer.model_version:
            result.kept += 1
            continue
        try:
            score = scorer.score(item.text)
        except Exception as error:
            result.failed.append(item.id)
            _log.warning("toxicity_cache_item_failed", item_id=item.id, error=_failure_reason(error))
            continue
        entries[key] = ToxicityCacheEntry(
            text_sha256=key,
            model_version=scorer.model_version,
            score=round(float(score), 6),
            created_at=_now(),
        )
        result.cached += 1
        pending_checkpoint += 1
        if checkpoint_every > 0 and pending_checkpoint >= checkpoint_every:
            write_entries(entries.values(), path)
            pending_checkpoint = 0
    write_entries(entries.values(), path)
    return result
