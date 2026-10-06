"""Stage 2: LLM threat-intent classification with structured output.

The LLM returns the six canonical intent labels with per-class probabilities.
The detection score is the calibrated probability that the item is threatening
(sum of the four threat classes), so a confident ``criticism`` contributes
nothing.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from aegis.common.config import get_settings
from aegis.common.models.enums import InputVariant
from aegis.detectors.text import DetectionDraft

INTENT_DETECTOR = "text_intent_llm"
PROMPT_VERSION = "intent-v1"

INTENT_LABELS: tuple[str, ...] = (
    "none",
    "criticism",
    "harassment",
    "violent_threat",
    "incitement",
    "doxxing",
)
THREAT_LABELS: tuple[str, ...] = ("harassment", "violent_threat", "incitement", "doxxing")
SOLICITATION_VALUES: tuple[str, ...] = ("none", "money", "credentials", "personal_info")

SYSTEM_PROMPT = (
    "You are a threat-intent classifier. Return strict JSON with keys: "
    "intent (one of none, criticism, harassment, violent_threat, incitement, doxxing), "
    "intent_probs (an object with all six labels mapping to probabilities summing to 1), "
    "solicitation (none, money, credentials, or personal_info), "
    "target_vip (the named target or null), "
    "specificity (an object with location, time, and method, each a string or null), "
    "rationale (one sentence), and spans (a list of the triggering text fragments). "
    "Sentiment is irrelevant; judge intent only."
)


class LLMOutputError(RuntimeError):
    """Raised when the model fails to return a valid classification."""


class IntentClassification(BaseModel):
    intent: str
    intent_probs: dict[str, float] = Field(default_factory=dict)
    solicitation: str = "none"
    target_vip: str | None = None
    specificity: dict[str, str | None] = Field(default_factory=dict)
    rationale: str = ""
    spans: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("intent")
    @classmethod
    def _validate_intent(cls, value: str) -> str:
        if value not in INTENT_LABELS:
            raise ValueError(f"intent must be one of {INTENT_LABELS}")
        return value

    @field_validator("solicitation")
    @classmethod
    def _validate_solicitation(cls, value: str) -> str:
        if value not in SOLICITATION_VALUES:
            raise ValueError(f"solicitation must be one of {SOLICITATION_VALUES}")
        return value

    @model_validator(mode="after")
    def _validate_probabilities(self) -> IntentClassification:
        for label, probability in self.intent_probs.items():
            if label not in INTENT_LABELS:
                raise ValueError(f"unknown intent label {label!r}")
            if not 0.0 <= probability <= 1.0:
                raise ValueError(f"probability for {label} out of range")
        return self

    @property
    def threat_prob(self) -> float:
        total = sum(self.intent_probs.get(label, 0.0) for label in THREAT_LABELS)
        return round(min(max(total, 0.0), 1.0), 4)


class LLMClient(Protocol):
    model_version: str

    async def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


class Calibrator(Protocol):
    def __call__(self, probability: float) -> float: ...


def identity_calibrator(probability: float) -> float:
    return probability


class IntentClassifier:
    """Calls the LLM and validates its structured output, retrying once."""

    def __init__(
        self,
        client: LLMClient,
        *,
        calibrator: Calibrator = identity_calibrator,
        max_attempts: int = 2,
    ) -> None:
        self.client = client
        self.calibrator = calibrator
        self.max_attempts = max_attempts

    def build_prompt(self, text: str, vip_names: list[str]) -> str:
        targets = ", ".join(vip_names) if vip_names else "unknown"
        return f"Monitored VIPs: {targets}\n\nItem text:\n{text}"

    async def classify(self, text: str, vip_names: list[str]) -> IntentClassification:
        prompt = self.build_prompt(text, vip_names)
        last_error: Exception | None = None
        for _ in range(self.max_attempts):
            payload = await self.client.complete_json(SYSTEM_PROMPT, prompt)
            try:
                return IntentClassification.model_validate(payload)
            except ValidationError as error:
                last_error = error
        raise LLMOutputError(f"model returned invalid classification: {last_error}")

    def to_detection(
        self,
        classification: IntentClassification,
        *,
        input_variant: InputVariant = InputVariant.TEXT,
    ) -> DetectionDraft:
        return DetectionDraft(
            detector=INTENT_DETECTOR,
            model_version=f"{self.client.model_version}:{PROMPT_VERSION}",
            score=self.calibrator(classification.threat_prob),
            label=classification.intent,
            spans=classification.spans,
            details={
                "rationale": classification.rationale,
                "intent_probs": classification.intent_probs,
                "solicitation": classification.solicitation,
                "specificity": classification.specificity,
                "target_vip": classification.target_vip,
                "degraded": False,
            },
            input_variant=input_variant,
        )


@dataclass(frozen=True)
class Stage2Outcome:
    detection: DetectionDraft | None
    degraded: bool
    reason: str | None = None


async def run_stage2(
    classifier: IntentClassifier,
    text: str,
    vip_names: list[str],
    *,
    charge_budget: Callable[[], Awaitable[bool]] | None = None,
    input_variant: InputVariant = InputVariant.TEXT,
) -> Stage2Outcome:
    """Classify one item, degrading to Stage 1 on budget or provider failure."""

    if charge_budget is not None:
        allowed = await charge_budget()
        if not allowed:
            return Stage2Outcome(detection=None, degraded=True, reason="budget_exhausted")
    try:
        classification = await classifier.classify(text, vip_names)
    except Exception as error:
        return Stage2Outcome(detection=None, degraded=True, reason=f"provider_failure: {error}")
    return Stage2Outcome(
        detection=classifier.to_detection(classification, input_variant=input_variant),
        degraded=False,
    )


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible chat client using httpx."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key.get_secret_value()
        self.model_version = model or settings.llm_model or "unknown"
        self.timeout = timeout or settings.llm_timeout_seconds

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        import httpx

        payload: dict[str, Any] = {
            "model": self.model_version,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        decoded = json.loads(content)
        if not isinstance(decoded, dict):
            raise LLMOutputError("model did not return a JSON object")
        return decoded
