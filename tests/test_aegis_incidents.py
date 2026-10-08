"""Incident builder integration tests (Postgres)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.models.collected import Item
from aegis.common.models.enums import (
    AliasKind,
    IncidentEventType,
    Severity,
    SuppressionScope,
)
from aegis.common.models.incidents import Incident, IncidentEvent, IncidentVip
from aegis.common.models.ops import Outbox, SuppressionRule
from aegis.common.models.reference import VIP, VipAlias
from aegis.detectors.mentions import resolve_for_item
from aegis.detectors.persistence import upsert_detection
from aegis.detectors.text import DetectionDraft
from aegis.pipeline.incidents import (
    detector_scores,
    load_scoring_config,
    upsert_item_incident,
)
from aegis.pipeline.normalizer import Normalizer
from aegis.pipeline.scoring import VipLink, score_item

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def _payload(text: str) -> dict[str, Any]:
    item = generate(
        SyntheticConfig(
            seed=51,
            campaign_accounts=1,
            impersonators=0,
            leaks=0,
            hinglish_threats=0,
            criticism=0,
        )
    )[0]
    payload = json.loads(item.model_dump_json())
    payload["content"]["text"] = text
    return payload


def _setup(db_session, text: str) -> tuple[VIP, Item]:
    vip = VIP(name="Vip Incidents")
    db_session.add(vip)
    db_session.flush()
    db_session.add(VipAlias(vip_id=vip.id, alias="asha example", kind=AliasKind.NAME, is_ambiguous=False))
    db_session.flush()

    normalized = Normalizer().normalize(db_session, _payload(text))
    item = db_session.get(Item, uuid.UUID(normalized.item_id))
    assert item is not None
    resolve_for_item(db_session, item)
    return vip, item


def _score(db_session, item: Item, vip: VIP):
    drafts = [
        DetectionDraft(
            detector="text_lexicon",
            model_version="2026.10.1",
            score=0.9,
            label="threat_verbs",
            details={"threat_class": True},
        ),
        DetectionDraft(
            detector="text_intent_llm",
            model_version="fake:1",
            score=0.8,
            label="violent_threat",
            details={"specificity": {"time": "tomorrow"}},
        ),
    ]
    for draft in drafts:
        upsert_detection(db_session, draft, item_id=item.id, vip_id=vip.id)
    scores = detector_scores(db_session, item.id)
    config = load_scoring_config(db_session)
    result = score_item(
        config,
        scores,
        [VipLink(vip.id, sensitivity="normal", match_confidence=1.0, name=vip.name)],
        followers=1000,
    )
    return config, scores, result


@DB_REQUIRED
def test_incident_is_created_once_with_vips_and_outbox(db_session) -> None:
    vip, item = _setup(db_session, "I will kill him tomorrow")
    config, scores, result = _score(db_session, item, vip)
    assert result.override == "violent_threat_specificity"
    assert result.severity == "critical"

    build = upsert_item_incident(db_session, item, result, config, detections=scores)
    assert build.created is True
    assert build.capture_required is True
    assert (
        db_session.execute(select(func.count()).select_from(Incident).where(Incident.item_id == item.id)).scalar_one()
        == 1
    )
    assert (
        db_session.execute(
            select(func.count()).select_from(IncidentVip).where(IncidentVip.incident_id == build.incident.id)
        ).scalar_one()
        == 1
    )
    created = db_session.execute(
        select(func.count())
        .select_from(Outbox)
        .where(Outbox.event_type == "incident.created")
        .where(Outbox.payload["item_id"].astext == str(item.id))
    ).scalar_one()
    assert created == 1

    second = upsert_item_incident(db_session, item, result, config, detections=scores)
    assert second.created is False
    assert build.incident is not None
    assert second.incident is not None
    assert second.incident.id == build.incident.id
    assert (
        db_session.execute(select(func.count()).select_from(Incident).where(Incident.item_id == item.id)).scalar_one()
        == 1
    )


@DB_REQUIRED
def test_rescore_event_and_manual_severity_is_preserved(db_session) -> None:
    vip, item = _setup(db_session, "I will kill him tomorrow")
    config, scores, result = _score(db_session, item, vip)
    build = upsert_item_incident(db_session, item, result, config, detections=scores)
    assert build.incident is not None

    upsert_detection(
        db_session,
        DetectionDraft(
            detector="text_intent_llm",
            model_version="fake:1",
            score=0.02,
            label="criticism",
            details={},
        ),
        item_id=item.id,
        vip_id=vip.id,
    )
    weak_scores = detector_scores(db_session, item.id)
    weak_result = score_item(
        config,
        weak_scores,
        [VipLink(vip.id, match_confidence=1.0, name=vip.name)],
        followers=1000,
    )
    rescored = upsert_item_incident(db_session, item, weak_result, config, detections=weak_scores, trigger="rescore")
    assert rescored.rescored is True
    assert (
        db_session.execute(
            select(func.count()).select_from(IncidentEvent).where(IncidentEvent.event_type == IncidentEventType.RESCORE)
        ).scalar_one()
        == 1
    )
    assert build.incident.severity is not Severity.CRITICAL

    build.incident.severity = Severity.CRITICAL
    build.incident.severity_manual = True
    db_session.flush()
    upsert_item_incident(db_session, item, weak_result, config, detections=weak_scores, trigger="rescore")
    assert build.incident.severity is Severity.CRITICAL


@DB_REQUIRED
def test_suppression_rule_prevents_incident_creation(db_session) -> None:
    vip, item = _setup(db_session, "I will kill him tomorrow")
    config, scores, result = _score(db_session, item, vip)

    db_session.add(
        SuppressionRule(
            scope=SuppressionScope.KEYWORD,
            match={"keyword": "kill"},
            reason="known quote",
        )
    )
    db_session.flush()

    build = upsert_item_incident(db_session, item, result, config, detections=scores)
    assert build.created is False
    assert build.incident is None
    assert (
        db_session.execute(select(func.count()).select_from(Incident).where(Incident.item_id == item.id)).scalar_one()
        == 0
    )
