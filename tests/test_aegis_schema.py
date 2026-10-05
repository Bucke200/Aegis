"""Postgres-backed migration and constraint tests for the data model.

These run only when AEGIS_TEST_DATABASE_URL is set to a disposable database.
Each test commits its prerequisites, then asserts that a single commit is
rejected with the expected database error.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from aegis.common.models.collected import Account, Item
from aegis.common.models.enums import (
    CampaignMemberType,
    CustodyAction,
    CustodyTargetType,
    DetectionScope,
    DiscoveredVia,
    EvidenceKind,
    IncidentStatus,
    IncidentSubject,
    InputVariant,
    ItemType,
    Source,
)
from aegis.common.models.incidents import Campaign, CampaignMember, Detection, Incident
from aegis.common.models.ops import CustodyLog, EvidenceArtifact
from aegis.common.models.reference import VIP


def make_vip(session: Session) -> VIP:
    vip = VIP(name=f"VIP-{uuid.uuid4().hex[:8]}")
    session.add(vip)
    session.flush()
    return vip


def make_account(session: Session) -> Account:
    account = Account(
        source=Source.TELEGRAM,
        platform_account_id=uuid.uuid4().hex,
        discovered_via=DiscoveredVia.AUTHORED_ITEM,
    )
    session.add(account)
    session.flush()
    return account


def make_item(session: Session) -> Item:
    item = Item(
        source=Source.TELEGRAM,
        platform_item_id=uuid.uuid4().hex,
        dedup_key=uuid.uuid4().hex,
        item_type=ItemType.POST,
    )
    session.add(item)
    session.flush()
    return item


def new_item_incident(item: Item) -> Incident:
    return Incident(
        subject_type=IncidentSubject.ITEM,
        item_id=item.id,
        source=Source.TELEGRAM,
    )


def new_account_incident(account: Account, vip: VIP) -> Incident:
    return Incident(
        subject_type=IncidentSubject.ACCOUNT,
        account_id=account.id,
        subject_vip_id=vip.id,
        source=Source.TELEGRAM,
    )


def test_schema_objects_exist(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection:
        extension_names = {row[0] for row in connection.execute(text("SELECT extname FROM pg_extension"))}
        assert {"vector", "pg_trgm"} <= extension_names

        table_count = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        ).scalar_one()
        assert table_count == 39

        index_names = {
            row[0] for row in connection.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        }
        for expected in (
            "uq_incidents_item",
            "uq_incidents_open_account",
            "ix_media_embedding_hnsw",
            "ix_items_tsv",
            "ix_accounts_handle_trgm",
        ):
            assert expected in index_names


def test_item_dedup_key_unique(db_session: Session) -> None:
    first = make_item(db_session)
    db_session.commit()

    duplicate = Item(
        source=Source.TELEGRAM,
        platform_item_id=uuid.uuid4().hex,
        dedup_key=first.dedup_key,
        item_type=ItemType.POST,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_item_incident_per_item(db_session: Session) -> None:
    item = make_item(db_session)
    db_session.add(new_item_incident(item))
    db_session.commit()

    db_session.add(new_item_incident(item))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_open_account_incident_per_account_vip(db_session: Session) -> None:
    vip = make_vip(db_session)
    account = make_account(db_session)
    first = new_account_incident(account, vip)
    db_session.add(first)
    db_session.commit()

    db_session.add(new_account_incident(account, vip))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    first.status = IncidentStatus.RESOLVED
    db_session.commit()

    db_session.add(new_account_incident(account, vip))
    db_session.commit()


def test_incident_subject_check(db_session: Session) -> None:
    vip = make_vip(db_session)
    account = make_account(db_session)
    db_session.commit()

    bad = Incident(
        subject_type=IncidentSubject.ITEM,
        item_id=None,
        account_id=account.id,
        subject_vip_id=vip.id,
        source=Source.TELEGRAM,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_detection_scope_check(db_session: Session) -> None:
    account = make_account(db_session)
    db_session.commit()

    db_session.add(
        Detection(
            scope=DetectionScope.ITEM,
            account_id=account.id,
            detector="text_lexicon",
            model_version="v1",
            input_variant=InputVariant.TEXT,
            score=0.5,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        Detection(
            scope=DetectionScope.ACCOUNT,
            detector="impersonation",
            model_version="v1",
            input_variant=InputVariant.MEDIA,
            score=0.5,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_detection_input_variant_uniqueness(db_session: Session) -> None:
    item = make_item(db_session)
    common = {
        "scope": DetectionScope.ITEM,
        "item_id": item.id,
        "detector": "text_lexicon",
        "model_version": "v1",
        "score": 0.5,
    }
    db_session.add(Detection(**common, input_variant=InputVariant.TEXT))
    db_session.commit()

    db_session.add(Detection(**common, input_variant=InputVariant.TEXT))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(Detection(**common, input_variant=InputVariant.OCR_TEXT))
    db_session.commit()


def test_below_threshold_default(db_session: Session) -> None:
    vip = make_vip(db_session)
    account = make_account(db_session)
    incident = new_account_incident(account, vip)
    db_session.add(incident)
    db_session.commit()
    assert incident.below_threshold is False


def test_merged_into_trigger_and_check(db_session: Session) -> None:
    vip = make_vip(db_session)
    account = make_account(db_session)
    account_incident = new_account_incident(account, vip)
    item_one = make_item(db_session)
    item_two = make_item(db_session)
    first_item_incident = new_item_incident(item_one)
    second_item_incident = new_item_incident(item_two)
    db_session.add_all([account_incident, first_item_incident, second_item_incident])
    db_session.commit()

    second_item_incident.merged_into_id = account_incident.id
    db_session.commit()

    first_item_incident.merged_into_id = second_item_incident.id
    with pytest.raises(DBAPIError):
        db_session.commit()
    db_session.rollback()

    account_incident.merged_into_id = account_incident.id
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_custody_log_exactly_one_target(db_session: Session) -> None:
    item = make_item(db_session)
    incident = new_item_incident(item)
    db_session.add(incident)
    db_session.flush()

    artifact = EvidenceArtifact(
        incident_id=incident.id,
        kind=EvidenceKind.SCREENSHOT,
        object_key="evidence/x.png",
        sha256="a" * 64,
        size=123,
    )
    db_session.add(artifact)
    db_session.commit()

    db_session.add(
        CustodyLog(
            target_type=CustodyTargetType.ARTIFACT,
            artifact_id=artifact.id,
            manifest_incident_id=incident.id,
            manifest_version=1,
            action=CustodyAction.VIEW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        CustodyLog(
            target_type=CustodyTargetType.MANIFEST,
            manifest_incident_id=incident.id,
            manifest_version=1,
            action=CustodyAction.EXPORT,
        )
    )
    db_session.commit()


def test_campaign_members_exactly_one_member(db_session: Session) -> None:
    vip = make_vip(db_session)
    account = make_account(db_session)
    item = make_item(db_session)
    campaign = Campaign(vip_id=vip.id)
    db_session.add(campaign)
    db_session.commit()

    db_session.add(
        CampaignMember(
            campaign_id=campaign.id,
            member_type=CampaignMemberType.ACCOUNT,
            account_id=account.id,
            item_id=item.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_enum_check_constraint(db_session: Session) -> None:
    statement = text(
        "INSERT INTO items (id, dedup_key, source, platform_item_id, item_type, "
        "engagement, scored_reach, relations, raw, legal_hold, schema_version) "
        "VALUES (gen_random_uuid(), :dedup, 'not-a-source', 'p', 'post', "
        "'{}'::jsonb, 0, '{}'::jsonb, '{}'::jsonb, false, '1.0')"
    )
    with pytest.raises(IntegrityError):
        db_session.execute(statement, {"dedup": uuid.uuid4().hex})
    db_session.rollback()


def test_audit_log_is_insert_only(db_session: Session) -> None:
    db_session.execute(
        text("INSERT INTO audit_log (id, action, details) VALUES (gen_random_uuid(), 'test', '{}'::jsonb)")
    )
    db_session.commit()

    db_session.execute(text("SET ROLE aegis_app"))
    with pytest.raises(DBAPIError):
        db_session.execute(text("UPDATE audit_log SET action = 'tampered'"))
    db_session.rollback()

    db_session.execute(text("SET ROLE aegis_app"))
    with pytest.raises(DBAPIError):
        db_session.execute(text("DELETE FROM audit_log"))
    db_session.rollback()


def test_migration_round_trip(test_database_url: str) -> None:
    env = {**os.environ, "AEGIS_DATABASE_URL": test_database_url}

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    engine = create_engine(test_database_url)
    try:
        with engine.connect() as connection:
            exists = connection.execute(text("SELECT to_regclass('public.incidents') IS NOT NULL")).scalar_one()
            assert exists is True
    finally:
        engine.dispose()
