"""Smoke tests for the health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

import aegis.common.health as health_module
from aegis.api.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_readiness_ready(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "check_database", lambda: True)
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "check_database", lambda: False)
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
