"""Shared pytest fixtures.

Postgres-backed integration tests only run when ``AEGIS_TEST_DATABASE_URL``
points at a disposable test database; otherwise they are skipped.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

TEST_DATABASE_URL_ENV = "AEGIS_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not set")
    return url


@pytest.fixture(scope="session")
def pg_engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        engine.dispose()
        pytest.skip("test database is not reachable")

    env = {**os.environ, "AEGIS_DATABASE_URL": test_database_url}
    for command in ("downgrade base", "upgrade head"):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *command.split()],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            engine.dispose()
            pytest.fail(f"alembic {command} failed:\n{result.stderr}")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(pg_engine: Engine) -> Iterator[Session]:
    session = Session(pg_engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
