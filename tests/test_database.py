"""
Tests for database initialization helpers.
"""

import pytest

import storage.database as database


@pytest.mark.asyncio
async def test_init_database_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(database, "init_db", lambda: None)

    assert await database.init_database() is True


@pytest.mark.asyncio
async def test_init_database_returns_false_on_failure(monkeypatch):
    def failing_init():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(database, "init_db", failing_init)

    assert await database.init_database() is False
