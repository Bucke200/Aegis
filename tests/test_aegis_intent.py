"""Tests for the Stage 2 LLM intent classifier and the shared token budget."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Any

import pytest
import respx

from aegis.common.llm_budget import BudgetExhaustedError, charge_tokens, tokens_used
from aegis.detectors.intent import (
    INTENT_DETECTOR,
    IntentClassifier,
    LLMOutputError,
    OpenAICompatibleClient,
    run_stage2,
)

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)

GOOD: dict[str, Any] = {
    "intent": "violent_threat",
    "intent_probs": {
        "none": 0.01,
        "criticism": 0.02,
        "harassment": 0.10,
        "violent_threat": 0.80,
        "incitement": 0.05,
        "doxxing": 0.02,
    },
    "solicitation": "none",
    "target_vip": "Asha Example",
    "specificity": {"location": "office", "time": "tomorrow", "method": None},
    "rationale": "Explicit threat with time and place",
    "spans": [{"text": "kill him tomorrow"}],
}

CRITICISM: dict[str, Any] = {
    "intent": "criticism",
    "intent_probs": {
        "none": 0.05,
        "criticism": 0.90,
        "harassment": 0.03,
        "violent_threat": 0.01,
        "incitement": 0.00,
        "doxxing": 0.01,
    },
    "solicitation": "none",
    "rationale": "Policy disagreement",
    "spans": [],
}


class FakeClient:
    model_version = "fake-llm-1"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_threat_prob_sums_only_threat_labels() -> None:
    classifier = IntentClassifier(FakeClient([GOOD]))
    classification = asyncio.run(classifier.classify("text", ["Asha Example"]))
    assert classification.threat_prob == pytest.approx(0.97)

    detection = classifier.to_detection(classification)
    assert detection.detector == INTENT_DETECTOR
    assert detection.label == "violent_threat"
    assert detection.score == pytest.approx(0.97)
    assert detection.details["solicitation"] == "none"
    assert detection.details["degraded"] is False
    assert "fake-llm-1" in detection.model_version


def test_confident_criticism_has_negligible_threat_prob() -> None:
    classification = asyncio.run(IntentClassifier(FakeClient([CRITICISM])).classify("text", []))
    assert classification.threat_prob == pytest.approx(0.05)


def test_malformed_output_is_retried() -> None:
    client = FakeClient([{"intent": "bogus"}, GOOD])
    classification = asyncio.run(IntentClassifier(client).classify("text", []))
    assert classification.intent == "violent_threat"
    assert client.calls == 2


def test_malformed_twice_raises() -> None:
    with pytest.raises(LLMOutputError):
        asyncio.run(IntentClassifier(FakeClient([{"intent": "bogus"}, {"intent": "bogus"}])).classify("text", []))


def test_calibrator_is_applied_to_the_score() -> None:
    outcome = asyncio.run(
        run_stage2(
            IntentClassifier(FakeClient([GOOD]), calibrator=lambda probability: 0.25),
            "text",
            [],
        )
    )
    assert outcome.degraded is False
    assert outcome.detection is not None
    assert outcome.detection.score == 0.25


def test_provider_failure_degrades() -> None:
    outcome = asyncio.run(run_stage2(IntentClassifier(FakeClient([RuntimeError("boom")])), "text", []))
    assert outcome.degraded is True
    assert outcome.detection is None
    assert outcome.reason is not None
    assert "provider_failure" in outcome.reason


def test_budget_refusal_degrades_without_calling_the_provider() -> None:
    client = FakeClient([GOOD])

    async def refuse() -> bool:
        return False

    outcome = asyncio.run(run_stage2(IntentClassifier(client), "text", [], charge_budget=refuse))
    assert outcome.degraded is True
    assert outcome.reason == "budget_exhausted"
    assert client.calls == 0


def test_string_spans_are_normalised_to_fragments() -> None:
    payload = {**GOOD, "spans": ["kill him tomorrow", {"text": "with a gun", "category": "weapons"}]}
    classifier = IntentClassifier(FakeClient([payload]))
    classification = asyncio.run(classifier.classify("text", ["Asha Example"]))

    assert classification.spans == [
        {"text": "kill him tomorrow"},
        {"text": "with a gun", "category": "weapons"},
    ]
    detection = classifier.to_detection(classification)
    assert detection.spans[0]["text"] == "kill him tomorrow"


@DB_REQUIRED
def test_token_budget_is_shared_and_enforced(db_session) -> None:
    day = date(2026, 10, 1)
    assert tokens_used(db_session, day) == 0
    assert charge_tokens(db_session, 500, budget=1000, day=day) == 500
    assert charge_tokens(db_session, 400, budget=1000, day=day) == 900
    with pytest.raises(BudgetExhaustedError):
        charge_tokens(db_session, 200, budget=1000, day=day)
    assert tokens_used(db_session, day) == 900


@respx.mock
def test_openai_client_omits_authorization_without_key() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "{}"}}]}
    )
    client = OpenAICompatibleClient(base_url="http://localhost:11434/v1", api_key="", model="aegis-intent")

    assert asyncio.run(client.complete_json("system", "user")) == {}
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
def test_openai_client_sends_authorization_with_key() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "{}"}}]}
    )
    client = OpenAICompatibleClient(base_url="http://localhost:11434/v1", api_key="secret", model="aegis-intent")

    asyncio.run(client.complete_json("system", "user"))
    assert route.calls.last.request.headers["authorization"] == "Bearer secret"
