"""Tests for eval adapters, caches, benchmark scoring, and the Ollama provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import respx

from aegis.common.config import Settings
from aegis.detectors.intent import THREAT_LABELS, IntentClassification, IntentClassifier
from aegis.eval.adapters import (
    TEXT_INTENT_DETECTOR,
    TEXT_LEXICON_DETECTOR,
    build_detectors,
    lexicon_detector,
    make_llm_detector,
    make_toxicity_detector,
    threat_probability,
)
from aegis.eval.benchmark import BenchmarkRun, render_markdown, run_classifications, score_predictions, write_benchmark
from aegis.eval.caches import (
    LlmCacheEntry,
    ToxicityCacheEntry,
    fetch_ollama_digest,
    load_llm_cache,
    refresh_llm_cache,
    refresh_toxicity_cache,
    text_sha256,
    write_entries,
)
from aegis.eval.detectors import Prediction
from aegis.eval.models import GoldenItem
from aegis.eval.report import render_markdown as render_eval_markdown
from aegis.eval.runner import evaluate


def _item(item_id: str, text: str, label: str, *, language: str = "en") -> GoldenItem:
    return GoldenItem(
        id=item_id,
        language=language,
        text=text,
        labels={"text_intent_llm": label in THREAT_LABELS, "text_lexicon": label in THREAT_LABELS},
        intent=label,
        final_label=label,
    )


def _classification(intent: str, probabilities: dict[str, float]) -> IntentClassification:
    return IntentClassification(
        intent=intent,
        intent_probs=probabilities,
        solicitation="none",
        rationale="test",
    )


def test_threat_probability_sums_threat_labels_only() -> None:
    probabilities = {"harassment": 0.2, "violent_threat": 0.3, "incitement": 0.1, "doxxing": 0.05, "none": 0.3}
    assert threat_probability(probabilities) == 0.65
    assert threat_probability({"criticism": 1.0}) == 0.0


def test_lexicon_detector_flags_threat_terms() -> None:
    threat = _item("t1", "I will shoot him tomorrow", "violent_threat")
    benign = _item("t2", "I disagree with his policies", "criticism")
    assert lexicon_detector(threat).fired is True
    assert lexicon_detector(benign).fired is False
    assert lexicon_detector(threat).label is None


def test_llm_detector_reads_cache(tmp_path: Path) -> None:
    threat = _item("t1", "I will shoot him tomorrow", "violent_threat")
    criticism = _item("t2", "I disagree with his policies", "criticism")
    cache = tmp_path / "llm.jsonl"
    write_entries(
        [
            LlmCacheEntry(
                text_sha256=text_sha256(threat.text),
                model_id="aegis-intent",
                model_digest="digest-1",
                prompt_version="intent-v1",
                classification=_classification("violent_threat", {"violent_threat": 0.9, "none": 0.1}).model_dump(),
                created_at="2026-10-07T00:00:00+00:00",
            ),
            LlmCacheEntry(
                text_sha256=text_sha256(criticism.text),
                model_id="aegis-intent",
                model_digest="digest-1",
                prompt_version="intent-v1",
                classification=_classification("criticism", {"criticism": 0.9, "none": 0.1}).model_dump(),
                created_at="2026-10-07T00:00:00+00:00",
            ),
        ],
        cache,
    )

    detector = make_llm_detector(cache)
    threat_prediction = detector(threat)
    assert threat_prediction.fired is True
    assert threat_prediction.label == "violent_threat"
    assert detector(criticism).fired is False

    missing = _item("t3", "not cached", "none")
    with pytest.raises(LookupError, match="no cached LLM output"):
        detector(missing)

    stale = tmp_path / "stale.jsonl"
    write_entries(
        [
            LlmCacheEntry(
                text_sha256=text_sha256(threat.text),
                model_id="aegis-intent",
                model_digest="digest-1",
                prompt_version="intent-v0",
                classification=_classification("violent_threat", {"violent_threat": 1.0}).model_dump(),
                created_at="2026-10-07T00:00:00+00:00",
            )
        ],
        stale,
    )
    with pytest.raises(ValueError, match="prompt version"):
        make_llm_detector(stale)(threat)


def test_toxicity_detector_reads_cache(tmp_path: Path) -> None:
    item = _item("t1", "toxic text", "harassment")
    cache = tmp_path / "toxicity.jsonl"
    write_entries(
        [
            ToxicityCacheEntry(
                text_sha256=text_sha256(item.text),
                model_version="fake-toxicity",
                score=0.9,
                created_at="2026-10-07T00:00:00+00:00",
            )
        ],
        cache,
    )
    assert make_toxicity_detector(cache)(item).fired is True
    with pytest.raises(LookupError, match="no cached toxicity score"):
        make_toxicity_detector(cache)(_item("t2", "other", "none"))


def test_build_detectors_registers_lexicon_and_optional_caches(tmp_path: Path) -> None:
    detectors = build_detectors(llm_cache=tmp_path / "none.jsonl", toxicity_cache=tmp_path / "none.jsonl")
    assert TEXT_LEXICON_DETECTOR in detectors
    assert TEXT_INTENT_DETECTOR not in detectors

    cache = tmp_path / "llm.jsonl"
    write_entries([], cache)
    detectors = build_detectors(llm_cache=cache, toxicity_cache=tmp_path / "none.jsonl")
    assert TEXT_INTENT_DETECTOR in detectors


def test_per_class_confusion_matrix(tmp_path: Path) -> None:
    items = [
        _item("a", "shoot him", "violent_threat"),
        _item("b", "disagree", "criticism"),
        _item("c", "disagree too", "criticism"),
    ]

    def detector(item: GoldenItem) -> Prediction:
        return Prediction(fired=True, label="violent_threat" if item.id == "a" else "criticism")

    report = evaluate(items, {"text_intent_llm": detector}, "test")
    matrix = report.per_class["text_intent_llm"]["en"].matrix
    assert matrix["violent_threat"]["violent_threat"] == 1
    assert matrix["criticism"]["criticism"] == 2

    markdown = render_eval_markdown(report)
    assert "Per-class confusion" in markdown


def test_refresh_llm_and_toxicity_caches(tmp_path: Path) -> None:
    class FakeClassifier:
        def __init__(self) -> None:
            self.calls = 0

        async def classify(self, text: str, vip_names: list[str]) -> IntentClassification:
            self.calls += 1
            return _classification("criticism", {"criticism": 0.7, "none": 0.3})

    class FakeScorer:
        model_version = "fake-toxicity"

        def score(self, text: str) -> float:
            return 0.4

    items = [_item("a", "one", "criticism"), _item("b", "two", "none")]
    llm_cache = tmp_path / "llm.jsonl"
    classifier = FakeClassifier()
    written = asyncio.run(
        refresh_llm_cache(
            items,
            classifier=classifier,  # type: ignore[arg-type]
            model_id="aegis-intent",
            model_digest="digest-1",
            path=llm_cache,
        )
    )
    assert written == 2
    assert classifier.calls == 2
    assert len(load_llm_cache(llm_cache)) == 2

    again = asyncio.run(
        refresh_llm_cache(
            items,
            classifier=classifier,  # type: ignore[arg-type]
            model_id="aegis-intent",
            model_digest="digest-1",
            path=llm_cache,
        )
    )
    assert again == 0
    assert classifier.calls == 2

    toxicity_cache = tmp_path / "toxicity.jsonl"
    assert refresh_toxicity_cache(items, scorer=FakeScorer(), path=toxicity_cache) == 2
    assert refresh_toxicity_cache(items, scorer=FakeScorer(), path=toxicity_cache) == 0


@respx.mock
def test_fetch_ollama_digest() -> None:
    respx.get("http://localhost:11434/api/tags").respond(
        json={"models": [{"name": "aegis-intent:latest", "digest": "abc123"}]}
    )
    assert fetch_ollama_digest("http://localhost:11434", "aegis-intent") == "abc123"
    with pytest.raises(LookupError):
        fetch_ollama_digest("http://localhost:11434", "missing-model")


def test_benchmark_scoring_and_render(tmp_path: Path) -> None:
    items = [
        _item("a", "shoot him", "violent_threat"),
        _item("b", "disagree", "criticism"),
    ]
    predictions = [
        _classification("violent_threat", {"violent_threat": 0.9, "none": 0.1}),
        None,
    ]
    result = score_predictions("model-x", items, BenchmarkRun(predictions=predictions, elapsed_seconds=1.0))
    assert result.valid_json == 1
    assert result.invalid_json == 1
    assert result.threat_recall == 1.0
    assert result.exact_accuracy == 0.5
    assert result.items_per_second == 2.0

    json_path, markdown_path = write_benchmark([result], [], tmp_path)
    assert json_path.exists()
    assert "model-x" in markdown_path.read_text(encoding="utf-8")
    assert "model-x" in render_markdown([result], [])


def test_run_classifications_counts_failures() -> None:
    class FlakyClassifier:
        async def classify(self, text: str, vip_names: list[str]) -> IntentClassification:
            if text == "bad":
                raise RuntimeError("invalid JSON")
            return _classification("none", {"none": 1.0})

    items = [_item("a", "good", "none"), _item("b", "bad", "none")]
    run = asyncio.run(run_classifications(FlakyClassifier(), items))  # type: ignore[arg-type]
    assert run.predictions[0] is not None
    assert run.predictions[1] is None


def test_build_classifier_provider_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    from aegis.pipeline import analysis

    def settings(**kwargs: Any) -> Settings:
        return Settings(**kwargs)

    monkeypatch.setattr(
        analysis,
        "get_settings",
        lambda: settings(llm_provider="ollama", llm_model="aegis-intent", llm_api_key=""),
    )
    assert analysis.build_classifier() is not None

    monkeypatch.setattr(
        analysis,
        "get_settings",
        lambda: settings(llm_provider="openai", llm_model="gpt", llm_api_key=""),
    )
    assert analysis.build_classifier() is None

    monkeypatch.setattr(
        analysis,
        "get_settings",
        lambda: settings(llm_provider="openai", llm_model="gpt", llm_api_key="secret"),
    )
    assert analysis.build_classifier() is not None

    monkeypatch.setattr(analysis, "get_settings", lambda: settings(llm_provider="ollama", llm_model=""))
    assert analysis.build_classifier() is None


def test_detection_details_mark_identity_calibration() -> None:
    class FakeClient:
        model_version = "fake"

        async def complete_json(self, system: str, user: str) -> dict[str, Any]:
            return {}

    classifier = IntentClassifier(FakeClient())  # type: ignore[arg-type]
    detection = classifier.to_detection(_classification("criticism", {"criticism": 1.0}))
    assert detection.details["calibration"] == "identity"


def test_default_detector_registry_has_no_llm_without_cache() -> None:
    from aegis.eval.detectors import get_detectors

    assert "text_intent_llm" not in get_detectors()
