"""Normalizer worker: consumes ``items.raw`` and publishes ``items.normalized``.

Validates against schema v1 (invalid items are dead-lettered immediately),
upserts the account and item, detects language and script, records engagement
snapshots and text edits, and flags items whose reach grew enough to need a
re-score.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from aegis.common.db import session_scope
from aegis.common.language import detect_language
from aegis.common.logging import configure_logging, get_logger
from aegis.common.messaging import (
    PermanentMessageError,
    Producer,
    QueueConsumer,
    broker_channel,
)
from aegis.common.models.collected import (
    Account,
    Item,
    ItemEngagementSnapshot,
    ItemVersion,
)
from aegis.common.models.enums import (
    DiscoveredVia,
    IncidentStatus,
    ItemChangeType,
    Source,
)
from aegis.common.models.incidents import Incident
from aegis.common.schemas import ItemV1, compute_dedup_key, load_item
from aegis.common.topology import ITEMS_NORMALIZED, ITEMS_RAW, declare_topology

HIGH_PRIORITY = 2
NORMAL_PRIORITY = 1
RESCORE_FACTOR = 10
RESCORE_FLOOR = 10
OPEN_STATUSES = (IncidentStatus.NEW, IncidentStatus.UNDER_REVIEW, IncidentStatus.ESCALATED)


def _engagement_total(engagement: dict[str, Any]) -> int:
    return sum(value for value in engagement.values() if isinstance(value, int))


def _profile_hash(item: ItemV1) -> str:
    author = item.author
    material = json.dumps(
        {
            "handle": author.handle,
            "display_name": author.display_name,
            "bio": author.bio,
            "followers": author.followers,
            "following": author.following,
            "verified": author.verified,
            "self_labels": [label.value for label in author.self_labels],
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class NormalizedItem:
    item_id: str
    dedup_key: str
    source: str
    account_id: str | None
    language: str | None
    script: str | None
    created: bool
    edited: bool
    rescore: bool
    priority: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "dedup_key": self.dedup_key,
            "source": self.source,
            "account_id": self.account_id,
            "language": self.language,
            "script": self.script,
            "created": self.created,
            "rescore": self.rescore,
        }


class Normalizer:
    """Applies the schema-v1 normalizer rules inside one transaction."""

    def normalize(self, session: Session, payload: dict[str, Any]) -> NormalizedItem:
        try:
            item_data = load_item(payload)
        except (ValidationError, ValueError) as error:
            raise PermanentMessageError(f"schema validation failed: {error}") from error

        account = self._upsert_account(session, item_data)
        item, created, edited, rescore = self._upsert_item(session, item_data, account)

        detected = detect_language(item_data.content.text)
        item.language = detected.language
        item.script = detected.script
        session.flush()
        self._update_search_vector(session, item.id)

        priority = NORMAL_PRIORITY
        if item_data.source is Source.MANUAL or self._has_open_incident(session, account):
            priority = HIGH_PRIORITY

        return NormalizedItem(
            item_id=str(item.id),
            dedup_key=item.dedup_key,
            source=item_data.source.value,
            account_id=str(account.id),
            language=item.language,
            script=item.script,
            created=created,
            edited=edited,
            rescore=rescore,
            priority=priority,
        )

    def _upsert_account(self, session: Session, item_data: ItemV1) -> Account:
        author = item_data.author
        account = session.execute(
            select(Account)
            .where(Account.source == item_data.source)
            .where(Account.platform_account_id == author.platform_account_id)
        ).scalar_one_or_none()
        profile_hash = _profile_hash(item_data)
        if account is None:
            account = Account(
                source=item_data.source,
                platform_account_id=author.platform_account_id,
                handle=author.handle,
                display_name=author.display_name,
                bio=author.bio,
                created_at_platform=author.created_at,
                followers=author.followers,
                following=author.following,
                verified=author.verified,
                self_labels=[label.value for label in author.self_labels],
                discovered_via=DiscoveredVia.AUTHORED_ITEM,
                profile_hash=profile_hash,
            )
            session.add(account)
            session.flush()
            return account

        if account.profile_hash != profile_hash:
            account.handle = author.handle
            account.display_name = author.display_name
            account.bio = author.bio
            account.created_at_platform = author.created_at
            account.followers = author.followers
            account.following = author.following
            account.verified = author.verified
            account.self_labels = [label.value for label in author.self_labels]
            account.profile_hash = profile_hash
            session.flush()
        return account

    def _upsert_item(
        self,
        session: Session,
        item_data: ItemV1,
        account: Account,
    ) -> tuple[Item, bool, bool, bool]:
        dedup_key = compute_dedup_key(item_data.source, item_data.platform_item_id)
        item = session.execute(select(Item).where(Item.dedup_key == dedup_key)).scalar_one_or_none()
        engagement = item_data.engagement.model_dump()

        if item is None:
            item = Item(
                dedup_key=dedup_key,
                source=item_data.source,
                platform_item_id=item_data.platform_item_id,
                account_id=account.id,
                item_type=item_data.item_type,
                url=item_data.url,
                posted_at=item_data.posted_at,
                collected_at=item_data.collected_at,
                text=item_data.content.text,
                engagement=engagement,
                relations=item_data.relations.model_dump(),
                raw=item_data.raw,
                schema_version=item_data.schema_version,
            )
            session.add(item)
            session.flush()
            return item, True, False, False

        rescore = False
        if engagement != (item.engagement or {}):
            session.add(ItemEngagementSnapshot(item_id=item.id, engagement=engagement))
            item.engagement = engagement
            current_reach = (account.followers or 0) + _engagement_total(engagement)
            threshold = RESCORE_FACTOR * max(item.scored_reach or 0, RESCORE_FLOOR)
            if current_reach >= threshold:
                rescore = True

        edited = False
        if item_data.content.text != item.text:
            session.add(
                ItemVersion(
                    item_id=item.id,
                    text=item.text,
                    change_type=ItemChangeType.EDIT,
                )
            )
            item.text = item_data.content.text
            edited = True

        session.flush()
        return item, False, edited, rescore

    @staticmethod
    def _has_open_incident(session: Session, account: Account) -> bool:
        found = session.execute(
            select(Incident.id)
            .where(Incident.account_id == account.id)
            .where(Incident.status.in_(OPEN_STATUSES))
            .limit(1)
        ).first()
        return found is not None

    @staticmethod
    def _update_search_vector(session: Session, item_id: Any) -> None:
        session.execute(
            update(Item)
            .where(Item.id == item_id)
            .values(tsv=func.to_tsvector("simple", func.concat_ws(" ", Item.text, Item.ocr_text)))
        )


def _normalize_in_session(normalizer: Normalizer, payload: dict[str, Any]) -> NormalizedItem:
    with session_scope() as session:
        return normalizer.normalize(session, payload)


async def run_worker() -> None:
    """Consume items.raw until stopped."""

    configure_logging()
    log = get_logger("normalizer")
    normalizer = Normalizer()
    async with broker_channel() as channel:
        await declare_topology(channel)
        producer = Producer(channel)

        async def handler(payload: dict[str, Any]) -> None:
            result = await asyncio.to_thread(_normalize_in_session, normalizer, payload)
            await producer.publish_raw(
                ITEMS_NORMALIZED,
                json.dumps(result.to_payload()).encode(),
                priority=result.priority,
            )

        consumer = QueueConsumer(channel, ITEMS_RAW, handler)
        await consumer.start()
        log.info("normalizer_started")
        await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
