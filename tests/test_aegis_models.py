"""Smoke tests for the ORM data model."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

import aegis.common.models  # noqa: F401
from aegis.common.db import Base
from aegis.common.models.enums import (
    DetectionScope,
    IncidentStatus,
    IncidentSubject,
    InputVariant,
)

EXPECTED_TABLES = {
    "accounts",
    "account_edges",
    "account_vip_scores",
    "alert_deliveries",
    "alert_rules",
    "alerts",
    "audit_log",
    "campaign_members",
    "campaigns",
    "connector_cursors",
    "custody_log",
    "detections",
    "evidence_artifacts",
    "evidence_manifests",
    "incident_events",
    "incident_items",
    "incident_notes",
    "incident_vips",
    "incidents",
    "item_engagement_snapshots",
    "item_versions",
    "item_vips",
    "items",
    "labels",
    "llm_budget_usage",
    "media",
    "official_accounts",
    "outbox",
    "reference_media",
    "refresh_tokens",
    "saved_searches",
    "scoring_configs",
    "sensitive_fingerprints",
    "source_health",
    "suppression_rules",
    "user_vip_scopes",
    "users",
    "vip_aliases",
    "vip_context_keywords",
    "vips",
}


def test_all_tables_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_enum_columns_store_values() -> None:
    assert IncidentStatus.RESOLVED.value == "resolved"
    assert IncidentSubject.ACCOUNT.value == "account"
    assert DetectionScope.ITEM.value == "item"
    assert InputVariant.OCR_TEXT.value == "ocr_text"


def test_items_use_jsonb_and_tsvector() -> None:
    items = Base.metadata.tables["items"]
    assert isinstance(items.c.engagement.type, JSONB)
    assert isinstance(items.c.raw.type, JSONB)
    assert isinstance(items.c.tsv.type, TSVECTOR)
    assert items.c.dedup_key.unique is True


def test_detections_uniqueness() -> None:
    detections = Base.metadata.tables["detections"]
    unique_columns = [
        {column.name for column in constraint.columns}
        for constraint in detections.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert {"item_id", "detector", "model_version", "input_variant"} in unique_columns


def test_incidents_partial_unique_indexes() -> None:
    incidents = Base.metadata.tables["incidents"]
    index_names = {index.name for index in incidents.indexes}
    assert "uq_incidents_item" in index_names
    assert "uq_incidents_open_account" in index_names


def test_composite_primary_keys() -> None:
    expected = {
        "vip_aliases": ["vip_id", "alias", "kind"],
        "vip_context_keywords": ["vip_id", "keyword"],
        "item_vips": ["item_id", "vip_id"],
        "incident_vips": ["incident_id", "vip_id"],
        "incident_items": ["incident_id", "item_id"],
        "item_engagement_snapshots": ["item_id", "observed_at"],
        "evidence_manifests": ["incident_id", "version"],
        "account_vip_scores": ["account_id", "vip_id"],
        "user_vip_scopes": ["user_id", "vip_id"],
        "account_edges": ["src_account_id", "dst_account_id", "edge_type"],
    }
    for table_name, columns in expected.items():
        table = Base.metadata.tables[table_name]
        assert [column.name for column in table.primary_key.columns] == columns, table_name
