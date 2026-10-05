"""Smoke tests for the database layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text

import aegis.common.db as db


def test_check_database_true(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    assert db.check_database() is True


def test_check_database_false_on_failure(monkeypatch) -> None:
    class BrokenEngine:
        def connect(self) -> Any:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "get_engine", lambda: BrokenEngine())
    assert db.check_database() is False


def test_session_scope_round_trip(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setattr(db, "_session_factory", None)
    with db.session_scope() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_reset_engine_disposes(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_session_factory", "sentinel")
    db.reset_engine()
    assert db._engine is None
    assert db._session_factory is None
