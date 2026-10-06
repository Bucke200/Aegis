"""Persist detection drafts with the unique-key upsert rule.

The unique key is ``(item_id, detector, model_version, input_variant)`` for
item-scoped detections and ``(account_id, detector, model_version,
input_variant)`` for account-scoped ones, so re-running a detector never
double-counts in the scorer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.common.models.enums import DetectionScope
from aegis.common.models.incidents import Detection
from aegis.detectors.text import DetectionDraft


def upsert_detection(
    session: Session,
    draft: DetectionDraft,
    *,
    scope: DetectionScope = DetectionScope.ITEM,
    item_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    vip_id: uuid.UUID | None = None,
) -> Detection:
    """Insert or update the detector row for this item/account and variant."""

    conditions = [
        Detection.detector == draft.detector,
        Detection.model_version == draft.model_version,
        Detection.input_variant == draft.input_variant,
    ]
    if scope is DetectionScope.ITEM:
        conditions.append(Detection.item_id == item_id)
    else:
        conditions.append(Detection.account_id == account_id)

    existing = session.execute(select(Detection).where(*conditions)).scalar_one_or_none()
    if existing is None:
        existing = Detection(
            scope=scope,
            item_id=item_id,
            account_id=account_id,
            vip_id=vip_id,
            detector=draft.detector,
            model_version=draft.model_version,
            input_variant=draft.input_variant,
            score=draft.score,
            label=draft.label,
            spans=draft.spans,
            details=draft.details,
        )
        session.add(existing)
    else:
        existing.score = draft.score
        existing.label = draft.label
        existing.spans = draft.spans
        existing.details = draft.details
        if vip_id is not None:
            existing.vip_id = vip_id
    session.flush()
    return existing
