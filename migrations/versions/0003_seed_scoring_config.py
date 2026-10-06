"""Seed scoring_configs v1.

Revision ID: 0003_scoring_config
Revises: 0002_initial_schema
Create Date: 2026-10-05

"""

from __future__ import annotations

import json

from alembic import op

revision = "0003_scoring_config"
down_revision = "0002_initial_schema"
branch_labels = None
depends_on = None

WEIGHTS = {
    "text_lexicon": 0.45,
    "text_toxicity": 0.55,
    "text_intent_llm": 0.80,
    "impersonation": 0.85,
    "solicitation": 0.90,
    "repurposed_media": 0.65,
    "leak_pattern": 0.70,
    "leak_fingerprint_match": 1.00,
    "campaign_member": 0.50,
    "synthetic_media": 0.30,
}
BANDS = {"low": 0.30, "medium": 0.55, "high": 0.75, "critical": 0.90}
OVERRIDES = {"capture_severity": "medium"}


def upgrade() -> None:
    op.execute(
        "INSERT INTO scoring_configs (version, weights, bands, overrides) VALUES ("
        f"1, '{json.dumps(WEIGHTS)}'::jsonb, '{json.dumps(BANDS)}'::jsonb, "
        f"'{json.dumps(OVERRIDES)}'::jsonb) ON CONFLICT (version) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM scoring_configs WHERE version = 1")
