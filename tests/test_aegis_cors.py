"""CORS preflight behavior for the dashboard origin."""

from __future__ import annotations

from fastapi.testclient import TestClient

from aegis.api.main import app


def test_preflight_allows_the_dashboard_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/incidents",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_rejects_an_unknown_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/incidents",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
