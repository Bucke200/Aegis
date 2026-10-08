"""Draft synthetic bank entries with the candidate Ollama models.

Drafts are generated at temperature ~0.9 with varied persona, topic, platform,
and length, then checked and deduplicated by ``aegis.eval.bank``. Refusals are
counted per model and cell and are never worked around; gaps are filled by hand.

The run is resumable: entries already accepted for a (model, cell) are counted
from the output file, so re-running continues where it stopped. Nothing here
prints item text.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from aegis.detectors.intent import INTENT_LABELS
from aegis.eval.bank import (
    DRAFTER_HAND,
    DRAFTER_TEMPLATE,
    BankItem,
    bank_item_id,
    cell_key,
    is_duplicate,
    is_refusal,
    item_issues,
    load_bank,
    write_bank,
)

DRAFT_TEMPERATURE = 0.9
DRAFT_TOP_P = 0.95
DRAFT_MAX_TOKENS = 160
DEFAULT_MODELS = ("llama3.2:3b", "qwen2.5:3b", "gemma3:4b")
DEFAULT_MODEL_LANGUAGES: dict[str, tuple[str, ...]] = {
    "llama3.2:3b": ("en",),
    "qwen2.5:3b": ("en",),
    "gemma3:4b": ("en", "hi", "hi-Latn"),
}
LANGUAGES = ("en", "hi", "hi-Latn")

LANGUAGE_INSTRUCTIONS = {
    "en": "Write in English.",
    "hi": "Write in Hindi using Devanagari script.",
    "hi-Latn": "Write in romanized Hindi (Hinglish) using Latin script.",
}

PROMPT_CLASSES = {
    "none": "a neutral or informational post with no threat and no criticism",
    "criticism": "strong disagreement or negative opinion about policy or conduct, without abuse",
    "harassment": "targeted abuse, insults, or humiliation aimed at the person, with no threat of harm",
    "violent_threat": "a threat or wish that the person be physically harmed",
    "incitement": "a call for others to act violently against the person",
    "doxxing": "a post publishing the person's private information, using a fake address and a fake phone number that starts with +91 5",
}

PERSONAS = (
    "an angry local shop owner",
    "a college student",
    "a retired teacher",
    "a cricket fan",
    "a daily commuter",
    "a first-time voter",
    "a worried parent",
    "a ride-share driver",
    "a small farmer",
    "a night-shift nurse",
    "a local journalist",
    "a gig worker",
    "a temple volunteer",
    "a coaching-class tutor",
    "a ration-shop dealer",
    "a retired soldier",
    "a school-bus driver",
    "a tea-stall owner",
    "a delivery rider",
    "a housing-society secretary",
)

PLATFORMS = (
    "a short reply on X",
    "a WhatsApp group forward",
    "a comment on Instagram",
    "a Facebook post",
    "a message in a Telegram channel",
    "a comment on a news page",
    "a forwarded status message",
    "a YouTube comment",
)

TOPICS = (
    "a new tax rule",
    "flood relief spending",
    "school fees",
    "a traffic policy",
    "a stadium funding plan",
    "a water shortage",
    "a power-cut schedule",
    "a metro fare hike",
    "a hospital staff shortage",
    "a garbage collection contract",
    "a liquor licence",
    "a mining permit",
    "a toll plaza",
    "a bus route change",
    "a mid-day meal contract",
    "a village road repair",
    "a pension delay",
    "cricket team selection",
    "a film release controversy",
    "a factory pollution notice",
)

LENGTHS = (
    "one short sentence",
    "two short sentences",
    "about 25 words",
    "three short sentences",
)

META_PREFIX = "Post:"
CODE_FENCE = "```"


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


@dataclass
class DraftStats:
    """Counts-only drafting summary."""

    attempts: int = 0
    accepted: int = 0
    refused: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    by_cell: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, cell: str, outcome: str) -> None:
        bucket = self.by_cell.setdefault(cell, {})
        bucket[outcome] = bucket.get(outcome, 0) + 1

    def merge(self, data: dict[str, object]) -> None:
        """Fold a previous run's summary in so resume runs stay cumulative."""

        self.attempts += _as_int(data.get("attempts"))
        self.accepted += _as_int(data.get("accepted"))
        self.refused += _as_int(data.get("refused"))
        rejected = data.get("rejected")
        if isinstance(rejected, dict):
            for key, count in rejected.items():
                self.rejected[str(key)] = self.rejected.get(str(key), 0) + _as_int(count)
        by_cell = data.get("by_cell")
        if isinstance(by_cell, dict):
            for cell, outcomes in by_cell.items():
                bucket = self.by_cell.setdefault(str(cell), {})
                if isinstance(outcomes, dict):
                    for outcome, count in outcomes.items():
                        bucket[str(outcome)] = bucket.get(str(outcome), 0) + _as_int(count)

    def as_dict(self) -> dict[str, object]:
        refusal_rate = round(self.refused / self.attempts, 4) if self.attempts else 0.0
        return {
            "attempts": self.attempts,
            "accepted": self.accepted,
            "refused": self.refused,
            "refusal_rate": refusal_rate,
            "rejected": self.rejected,
            "by_cell": self.by_cell,
        }


def build_prompt(
    *,
    language: str,
    label: str,
    vip: str,
    persona: str,
    platform: str,
    topic: str,
    length: str,
) -> str:
    return (
        "You are drafting one synthetic social media post for a threat-detection dataset. "
        f"The post is {platform}. Voice: {persona}. Topic: {topic}. Length: {length}. "
        f"{LANGUAGE_INSTRUCTIONS[language]} The post is about a fictional public figure named {vip}. "
        f"Category: {PROMPT_CLASSES[label]}. "
        "Output only the post text: no quotes, no labels, no explanation. "
        "Use only fictional details; never a real person, organization, or contact."
    )


def clean_draft(text: str) -> str:
    value = text.strip()
    if CODE_FENCE in value:
        value = value.replace(CODE_FENCE, " ").strip()
    if value.startswith(META_PREFIX):
        value = value[len(META_PREFIX) :].strip()
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip('"').strip()


async def draft_once(
    client: httpx.AsyncClient,
    *,
    url: str,
    model: str,
    prompt: str,
    seed: int,
) -> str:
    response = await client.post(
        f"{url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": DRAFT_TEMPERATURE,
                "top_p": DRAFT_TOP_P,
                "num_predict": DRAFT_MAX_TOKENS,
                "seed": seed,
            },
        },
    )
    response.raise_for_status()
    message = response.json().get("message") or {}
    return str(message.get("content", ""))


def _prompt_variant(rng: random.Random, vip: str, language: str, label: str) -> str:
    return build_prompt(
        language=language,
        label=label,
        vip=vip,
        persona=rng.choice(PERSONAS),
        platform=rng.choice(PLATFORMS),
        topic=rng.choice(TOPICS),
        length=rng.choice(LENGTHS),
    )


async def run_drafting(
    *,
    models: tuple[str, ...],
    vip_roster: dict[str, tuple[str, ...]],
    bank_dir: Path,
    stats_path: Path,
    target_per_model: int = 3,
    attempts_per_model: int = 6,
    ollama_url: str = "http://localhost:11434",
    seed: int = 7,
    model_languages: dict[str, tuple[str, ...]] | None = None,
    languages: tuple[str, ...] | None = None,
) -> DraftStats:
    """Draft until each (model, cell) has ``target_per_model`` accepted items."""

    context: list[BankItem] = load_bank(bank_dir) if bank_dir.exists() else []
    drafts = [item for item in context if item.drafter not in (DRAFTER_HAND, DRAFTER_TEMPLATE)]
    allowed_languages = model_languages or DEFAULT_MODEL_LANGUAGES
    active_languages = tuple(lang for lang in LANGUAGES if languages is None or lang in languages)
    stats = DraftStats()
    if stats_path.exists():
        try:
            previous = json.loads(stats_path.read_text(encoding="utf-8"))
            if isinstance(previous, dict):
                stats.merge(previous)
        except (ValueError, OSError):
            stats = DraftStats()
    bank_dir.mkdir(parents=True, exist_ok=True)
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint() -> None:
        write_bank(drafts, bank_dir / "llm-drafts.jsonl")
        stats_path.write_text(json.dumps(stats.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    async with httpx.AsyncClient(timeout=180.0) as client:
        for model in models:
            model_langs = allowed_languages.get(model, LANGUAGES)
            for language in active_languages:
                if language not in model_langs:
                    continue
                names = vip_roster[language]
                for label in INTENT_LABELS:
                    cell = cell_key(language, label)
                    have = sum(
                        1
                        for item in drafts
                        if item.drafter == model
                        and item.language == language
                        and item.intended_label == label
                        and not item_issues(item)
                    )
                    for attempt in range(attempts_per_model):
                        if have >= target_per_model:
                            break
                        rng = random.Random(f"{seed}:{model}:{cell}:{attempt}")
                        vip = names[rng.randrange(len(names))]
                        prompt = _prompt_variant(rng, vip, language, label)
                        stats.attempts += 1
                        stats.record(cell, "attempt")
                        try:
                            raw = await draft_once(
                                client, url=ollama_url, model=model, prompt=prompt, seed=seed + attempt
                            )
                        except httpx.HTTPStatusError as error:
                            reason = f"http_{error.response.status_code}"
                            stats.rejected[reason] = stats.rejected.get(reason, 0) + 1
                            stats.record(cell, reason)
                            continue
                        except httpx.HTTPError:
                            stats.rejected["transport"] = stats.rejected.get("transport", 0) + 1
                            stats.record(cell, "transport")
                            continue
                        text = clean_draft(raw)
                        if not text:
                            stats.rejected["empty"] = stats.rejected.get("empty", 0) + 1
                            stats.record(cell, "empty")
                            continue
                        if is_refusal(text):
                            stats.refused += 1
                            stats.record(cell, "refused")
                            continue
                        item = BankItem(
                            id=bank_item_id(language, label, model, text),
                            language=language,
                            text=text,
                            intended_label=label,
                            drafter=model,
                            generator_model=model,
                        )
                        issues = item_issues(item)
                        duplicate = is_duplicate(item, context) if not issues else None
                        if duplicate:
                            issues.append(duplicate)
                        if issues:
                            for issue in issues:
                                stats.rejected[issue] = stats.rejected.get(issue, 0) + 1
                                stats.record(cell, issue)
                            continue
                        context.append(item)
                        drafts.append(item)
                        stats.accepted += 1
                        have += 1
                        stats.record(cell, "accepted")
                checkpoint()
            checkpoint()
    checkpoint()
    return stats
