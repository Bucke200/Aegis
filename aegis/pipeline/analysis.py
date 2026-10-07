"""Analysis worker: consumes ``items.normalized`` and runs the detection cascade.

For every VIP-linked item the worker resolves mentions, runs Stage 1 detection,
optionally escalates to the Stage 2 LLM (within the shared daily token budget),
persists every detection, scores the item once per linked VIP, and creates or
updates its item incident. Stage 1 detections are persisted even when Stage 2
degrades, so the scorer always has a signal to fall back to.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.common.config import get_settings
from aegis.common.db import session_scope
from aegis.common.llm_budget import BudgetExhaustedError, charge_tokens
from aegis.common.logging import configure_logging, get_logger
from aegis.common.messaging import PermanentMessageError, QueueConsumer, broker_channel
from aegis.common.models.collected import Account, Item, ItemVip
from aegis.common.models.enums import DetectionScope
from aegis.common.models.incidents import Detection
from aegis.common.models.reference import VIP
from aegis.common.topology import ITEMS_NORMALIZED, declare_topology
from aegis.detectors.intent import IntentClassifier, OpenAICompatibleClient, run_stage2
from aegis.detectors.mentions import resolve_for_item
from aegis.detectors.persistence import upsert_detection
from aegis.detectors.text import DetectionDraft, run_stage1
from aegis.detectors.toxicity import ToxicityScorer, get_toxicity_scorer
from aegis.pipeline.incidents import (
    IncidentBuild,
    detector_scores,
    load_scoring_config,
    upsert_item_incident,
)
from aegis.pipeline.scoring import VipLink, score_item


@dataclass(frozen=True)
class AnalysisContext:
    """Everything Stage 2 and the finalizer need after Stage 1 has run."""

    item_id: uuid.UUID
    text: str
    vip_names: list[str]
    links: list[VipLink]
    followers: int
    engagement_total: int
    rescore: bool
    stage1_passes: bool


@dataclass(frozen=True)
class AnalysisOutcome:
    """The finalizer's result, for logging and tests."""

    item_id: uuid.UUID
    incident_id: uuid.UUID | None
    created: bool
    severity: str | None
    risk_score: float
    degraded: bool
    skipped: bool = False
    stage2: bool = False


def _engagement_total(engagement: dict[str, Any] | None) -> int:
    return sum(value for value in (engagement or {}).values() if isinstance(value, int))


def _load_item(session: Session, item_id: uuid.UUID) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise PermanentMessageError(f"item {item_id} not found")
    return item


def _vip_links(session: Session, item_id: uuid.UUID) -> list[VipLink]:
    links: list[VipLink] = []
    rows = session.execute(select(ItemVip).where(ItemVip.item_id == item_id)).scalars()
    for row in rows:
        vip = session.get(VIP, row.vip_id)
        if vip is None:
            continue
        links.append(
            VipLink(
                vip_id=vip.id,
                sensitivity=vip.sensitivity.value,
                match_confidence=row.match_confidence,
                name=vip.name,
            )
        )
    return links


def prepare_analysis(
    session: Session,
    payload: dict[str, Any],
    *,
    toxicity_scorer: ToxicityScorer | None = None,
) -> AnalysisContext | None:
    """Resolve mentions and persist Stage 1 detections, or return None to skip."""

    item_id_value = payload.get("item_id")
    if not item_id_value:
        raise PermanentMessageError("normalized payload is missing item_id")
    item = _load_item(session, uuid.UUID(str(item_id_value)))

    matches = resolve_for_item(session, item)
    links = _vip_links(session, item.id)
    if not links and not matches:
        return None

    stage1 = run_stage1(item.text or "", item.language, toxicity_scorer=toxicity_scorer)
    for draft in stage1.detections:
        upsert_detection(session, draft, scope=DetectionScope.ITEM, item_id=item.id)

    account = session.get(Account, item.account_id) if item.account_id else None
    return AnalysisContext(
        item_id=item.id,
        text=item.text or "",
        vip_names=[link.name or str(link.vip_id) for link in links],
        links=links,
        followers=account.followers if account and account.followers else 0,
        engagement_total=_engagement_total(item.engagement),
        rescore=bool(payload.get("rescore")),
        stage1_passes=stage1.passes,
    )


def _mark_degraded(session: Session, item_id: uuid.UUID) -> None:
    rows = session.execute(select(Detection).where(Detection.item_id == item_id)).scalars()
    for row in rows:
        row.details = {**(row.details or {}), "degraded": True}
    session.flush()


def finalize_analysis(
    session: Session,
    context: AnalysisContext,
    *,
    stage2_detection: DetectionDraft | None = None,
    degraded: bool = False,
    trigger: str | None = None,
) -> AnalysisOutcome:
    """Persist Stage 2 (or its degraded marker), score, and upsert the incident."""

    item = _load_item(session, context.item_id)
    if stage2_detection is not None:
        upsert_detection(session, stage2_detection, scope=DetectionScope.ITEM, item_id=item.id)
    if degraded:
        _mark_degraded(session, item.id)

    scores = detector_scores(session, item.id)
    config = load_scoring_config(session)
    result = score_item(
        config,
        scores,
        context.links,
        followers=context.followers,
        engagement_total=context.engagement_total,
    )
    build: IncidentBuild = upsert_item_incident(
        session,
        item,
        result,
        config,
        detections=scores,
        trigger=trigger,
    )
    return AnalysisOutcome(
        item_id=item.id,
        incident_id=build.incident.id if build.incident else None,
        created=build.created,
        severity=build.incident.severity.value if build.incident else None,
        risk_score=result.item_risk,
        degraded=degraded,
        stage2=stage2_detection is not None,
    )


class AnalysisWorker:
    """Orchestrates prepare -> (Stage 2) -> finalize across short transactions."""

    def __init__(
        self,
        *,
        toxicity_scorer: ToxicityScorer | None = None,
        classifier: IntentClassifier | None = None,
        trigger: str = "engagement_reach",
    ) -> None:
        self.toxicity_scorer = toxicity_scorer
        self.classifier = classifier
        self.trigger = trigger

    async def handle(self, payload: dict[str, Any]) -> AnalysisOutcome:
        context = await asyncio.to_thread(self._prepare, payload)
        if context is None:
            return AnalysisOutcome(
                item_id=uuid.UUID(str(payload["item_id"])),
                incident_id=None,
                created=False,
                severity=None,
                risk_score=0.0,
                degraded=False,
                skipped=True,
            )

        stage2_detection: DetectionDraft | None = None
        degraded = False
        if context.stage1_passes:
            if self.classifier is None:
                degraded = True
            else:
                outcome = await run_stage2(
                    self.classifier,
                    context.text,
                    context.vip_names,
                    charge_budget=self._charge_budget,
                )
                stage2_detection = outcome.detection
                degraded = outcome.degraded

        trigger = self.trigger if context.rescore else None
        return await asyncio.to_thread(
            self._finalize,
            context,
            stage2_detection,
            degraded,
            trigger,
        )

    def _prepare(self, payload: dict[str, Any]) -> AnalysisContext | None:
        with session_scope() as session:
            return prepare_analysis(session, payload, toxicity_scorer=self.toxicity_scorer)

    def _finalize(
        self,
        context: AnalysisContext,
        stage2_detection: DetectionDraft | None,
        degraded: bool,
        trigger: str | None,
    ) -> AnalysisOutcome:
        with session_scope() as session:
            return finalize_analysis(
                session,
                context,
                stage2_detection=stage2_detection,
                degraded=degraded,
                trigger=trigger,
            )

    async def _charge_budget(self) -> bool:
        settings = get_settings()
        try:
            await asyncio.to_thread(self._charge_tokens, settings.llm_reserved_tokens_per_call)
        except BudgetExhaustedError:
            return False
        return True

    @staticmethod
    def _charge_tokens(tokens: int) -> None:
        settings = get_settings()
        with session_scope() as session:
            charge_tokens(session, tokens, budget=settings.llm_daily_token_budget)


def build_classifier() -> IntentClassifier | None:
    """Build the Stage 2 classifier when an LLM is configured, else None."""

    settings = get_settings()
    if not settings.llm_model:
        return None
    provider = settings.llm_provider.strip().lower()
    if provider != "ollama" and not settings.llm_api_key.get_secret_value():
        return None
    return IntentClassifier(OpenAICompatibleClient())


async def run_worker() -> None:
    """Consume ``items.normalized`` until stopped."""

    configure_logging()
    log = get_logger("analysis-worker")
    classifier = build_classifier()
    if classifier is None:
        log.warning("stage2_disabled", reason="no LLM model or API key configured")
    worker = AnalysisWorker(
        toxicity_scorer=get_toxicity_scorer(),
        classifier=classifier,
    )

    async def handle(payload: dict[str, Any]) -> None:
        outcome = await worker.handle(payload)
        if not outcome.skipped:
            log.info(
                "item_analyzed",
                item_id=str(outcome.item_id),
                incident_id=str(outcome.incident_id) if outcome.incident_id else None,
                severity=outcome.severity,
                degraded=outcome.degraded,
            )

    async with broker_channel() as channel:
        await declare_topology(channel)
        consumer = QueueConsumer(channel, ITEMS_NORMALIZED, handle)
        await consumer.start()
        log.info("analysis_worker_started")
        await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
