"""Incident building, re-scoring, and suppression checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from aegis.common.models.collected import Item
from aegis.common.models.enums import IncidentEventType, IncidentSubject, Severity
from aegis.common.models.incidents import Incident, IncidentEvent, IncidentVip
from aegis.common.models.incidents import ScoringConfig as ScoringConfigRow
from aegis.common.models.ops import SuppressionRule
from aegis.common.outbox import INCIDENT_CREATED, INCIDENT_UPDATED, enqueue
from aegis.pipeline.scoring import (
    DEFAULT_BANDS,
    INCIDENT_THRESHOLD,
    DetectorScore,
    ScoringConfig,
    ScoringResult,
    incident_vip_ids,
    threat_types_for,
)


@dataclass(frozen=True)
class IncidentBuild:
    incident: Incident | None
    created: bool
    capture_required: bool
    rescored: bool = False


def load_scoring_config(session: Session) -> ScoringConfig:
    """Load the newest scoring configuration, falling back to the v1 defaults."""

    row = session.execute(
        select(ScoringConfigRow).order_by(ScoringConfigRow.version.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return ScoringConfig()
    overrides: dict[str, Any] = row.overrides or {}
    return ScoringConfig(
        version=row.version,
        weights=dict(row.weights or {}),
        bands=dict(row.bands or DEFAULT_BANDS),
        capture_severity=str(overrides.get("capture_severity", "medium")),
    )


def is_suppressed(
    session: Session,
    *,
    text: str | None,
    account_id: uuid.UUID | None,
) -> bool:
    """Check active suppression rules before creating an incident."""

    rules = session.execute(
        select(SuppressionRule).where(
            or_(
                SuppressionRule.expires_at.is_(None),
                SuppressionRule.expires_at > func.now(),
            )
        )
    ).scalars()
    haystack = (text or "").lower()
    for rule in rules:
        match = rule.match or {}
        if match.get("account_id") and account_id is not None and str(match["account_id"]) == str(account_id):
            return True
        keyword = match.get("keyword")
        if keyword and str(keyword).lower() in haystack:
            return True
        domain = match.get("domain")
        if domain and str(domain).lower() in haystack:
            return True
    return False


def _sync_incident_vips(session: Session, incident: Incident, vip_ids: list[uuid.UUID]) -> None:
    existing = {
        row.vip_id
        for row in session.execute(select(IncidentVip).where(IncidentVip.incident_id == incident.id)).scalars()
    }
    for vip_id in vip_ids:
        if vip_id not in existing:
            session.add(IncidentVip(incident_id=incident.id, vip_id=vip_id))


def upsert_item_incident(
    session: Session,
    item: Item,
    result: ScoringResult,
    config: ScoringConfig,
    *,
    detections: list[DetectorScore],
    trigger: str | None = None,
) -> IncidentBuild:
    """Create or update the item's incident; idempotent per item."""

    existing = session.execute(
        select(Incident).where(Incident.subject_type == IncidentSubject.ITEM).where(Incident.item_id == item.id)
    ).scalar_one_or_none()

    vip_ids = incident_vip_ids(result)
    if result.item_risk < INCIDENT_THRESHOLD or not vip_ids:
        return IncidentBuild(existing, False, False)
    if is_suppressed(session, text=item.text, account_id=item.account_id):
        return IncidentBuild(existing, False, False)

    threat_types = threat_types_for(result, detections)

    if existing is None:
        incident = Incident(
            subject_type=IncidentSubject.ITEM,
            item_id=item.id,
            source=item.source,
            language=item.language,
            risk_score=result.item_risk,
            severity=Severity(result.severity),
            threat_types=threat_types,
            explanation=result.explanation,
            scoring_config_version=config.version,
        )
        session.add(incident)
        session.flush()
        for vip_id in vip_ids:
            session.add(IncidentVip(incident_id=incident.id, vip_id=vip_id))
        enqueue(
            session,
            INCIDENT_CREATED,
            {
                "incident_id": str(incident.id),
                "item_id": str(item.id),
                "severity": result.severity,
                "risk_score": result.item_risk,
                "vip_ids": [str(vip_id) for vip_id in vip_ids],
            },
        )
        return IncidentBuild(incident, True, result.capture_required)

    old_score = existing.risk_score
    old_severity = existing.severity
    existing.risk_score = result.item_risk
    if not existing.severity_manual:
        existing.severity = Severity(result.severity)
    existing.explanation = result.explanation
    existing.threat_types = threat_types
    existing.scoring_config_version = config.version
    _sync_incident_vips(session, existing, vip_ids)

    rescored = trigger is not None
    if rescored:
        session.add(
            IncidentEvent(
                incident_id=existing.id,
                event_type=IncidentEventType.RESCORE,
                from_value={"risk_score": old_score, "severity": old_severity.value},
                to_value={
                    "risk_score": existing.risk_score,
                    "severity": existing.severity.value,
                },
                reason=trigger,
            )
        )
    enqueue(
        session,
        INCIDENT_UPDATED,
        {
            "incident_id": str(existing.id),
            "item_id": str(item.id),
            "severity": existing.severity.value,
            "risk_score": existing.risk_score,
            "vip_ids": [str(vip_id) for vip_id in vip_ids],
        },
    )
    return IncidentBuild(existing, False, result.capture_required, rescored=rescored)


def detector_scores(session: Session, item_id: uuid.UUID) -> list[DetectorScore]:
    """Load the item's persisted detections as scorer inputs."""

    from aegis.common.models.incidents import Detection

    rows = session.execute(select(Detection).where(Detection.item_id == item_id)).scalars()
    return [
        DetectorScore(
            detector=row.detector,
            score=row.score,
            label=row.label,
            details=row.details or {},
            vip_id=row.vip_id,
        )
        for row in rows
    ]
