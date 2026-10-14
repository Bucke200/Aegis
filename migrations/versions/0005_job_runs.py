"""Add the job_runs table for the periodic job scheduler.

Revision ID: 0005_job_runs
Revises: 0004_refresh_tokens
Create Date: 2026-10-13

The file number is a placeholder: the merge order assigns the final number
(docs/orchestration-plan.md section 3.5).

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_job_runs"
down_revision = "0004_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("job", sa.Text(), primary_key=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("run_count", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("last_status IN ('ok', 'error', 'timeout')", name="ck_job_runs_last_status"),
    )


def downgrade() -> None:
    op.drop_table("job_runs")
