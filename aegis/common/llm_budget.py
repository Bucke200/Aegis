"""Shared daily LLM token budget.

Every analysis worker instance charges the same ``llm_budget_usage`` row so the
configured daily budget is enforced across the fleet, not per process.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.common.models.collected import LlmBudgetUsage


class BudgetExhaustedError(RuntimeError):
    """Raised when a charge would exceed the day's token budget."""


def current_day() -> date:
    return datetime.now(tz=UTC).date()


def tokens_used(session: Session, day: date | None = None) -> int:
    target = day or current_day()
    row = session.execute(select(LlmBudgetUsage).where(LlmBudgetUsage.day == target)).scalar_one_or_none()
    return row.tokens_used if row else 0


def charge_tokens(
    session: Session,
    tokens: int,
    *,
    budget: int,
    day: date | None = None,
) -> int:
    """Add tokens to the day's usage or raise when the budget would be exceeded."""

    target_day = day or current_day()
    row = session.execute(
        select(LlmBudgetUsage).where(LlmBudgetUsage.day == target_day).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        row = LlmBudgetUsage(day=target_day, tokens_used=0)
        session.add(row)
        session.flush()
    if row.tokens_used + tokens > budget:
        raise BudgetExhaustedError(f"daily token budget {budget} exhausted: {row.tokens_used} used")
    row.tokens_used += tokens
    row.updated_at = datetime.now(tz=UTC)
    session.flush()
    return row.tokens_used


def budget_snapshot(session: Session, budget: int, day: date | None = None) -> dict[str, Any]:
    used = tokens_used(session, day)
    return {"day": str(day or current_day()), "tokens_used": used, "budget": budget}
