"""Tests for authentication, authorization, and middleware."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.api.main import app
from aegis.api.middleware import RateLimiter
from aegis.api.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp,
)
from aegis.api.services.users import UserService
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import AuditLog
from aegis.common.models.reference import VIP

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def test_password_hashing() -> None:
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_round_trip_and_type_check() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "analyst")
    payload = decode_token(token, "access")
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "analyst"
    with pytest.raises(TokenError):
        decode_token(token, "refresh")


def test_refresh_token_carries_jti() -> None:
    jti = uuid.uuid4()
    payload = decode_token(create_refresh_token(uuid.uuid4(), jti), "refresh")
    assert payload["jti"] == str(jti)


def test_totp_round_trip() -> None:
    secret = generate_totp_secret()
    assert verify_totp(secret, pyotp.TOTP(secret).now())
    assert not verify_totp(secret, "000000")


def test_rate_limiter_window() -> None:
    limiter = RateLimiter(per_minute=2)
    assert limiter.allow("key", now=0.0)
    assert limiter.allow("key", now=1.0)
    assert not limiter.allow("key", now=2.0)
    assert limiter.allow("key", now=61.5)
    assert limiter.allow("other", now=2.0)


@pytest.fixture
def client(pg_engine) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        session = Session(bind=pg_engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def identity(pg_engine) -> dict[str, str]:
    with Session(pg_engine) as session:
        service = UserService(session)
        admin = service.create_user(email="admin@example.test", password="admin-pass", role=UserRole.ADMIN)
        analyst = service.create_user(email="analyst@example.test", password="analyst-pass", role=UserRole.ANALYST)
        viewer = service.create_user(email="viewer@example.test", password="viewer-pass", role=UserRole.VIEWER)
        vip_a = VIP(name="Vip A")
        vip_b = VIP(name="Vip B")
        session.add_all([vip_a, vip_b])
        session.flush()
        service.set_scope(analyst.id, vip_a.id)
        session.commit()
        return {
            "admin": str(admin.id),
            "analyst": str(analyst.id),
            "viewer": str(viewer.id),
            "vip_a": str(vip_a.id),
            "vip_b": str(vip_b.id),
        }


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@DB_REQUIRED
def test_unauthenticated_requests_are_rejected(client: TestClient, identity: dict[str, str]) -> None:
    vip_a = identity["vip_a"]
    cases = [
        ("GET", "/vips", None),
        ("GET", f"/vips/{vip_a}", None),
        ("POST", "/vips", {"name": "No Auth"}),
        ("GET", f"/vips/{vip_a}/aliases", None),
        ("POST", f"/vips/{vip_a}/aliases", {"alias": "x", "kind": "name"}),
        (
            "PUT",
            f"/users/{identity['analyst']}/vips/{vip_a}/reveal",
            None,
        ),
    ]
    for method, path, body in cases:
        response = client.request(method, path, json=body)
        assert response.status_code == 401, (method, path, response.status_code)


@DB_REQUIRED
def test_analyst_cannot_read_an_unassigned_vip(client: TestClient, identity: dict[str, str]) -> None:
    token = _login(client, "analyst@example.test", "analyst-pass")

    allowed = client.get(f"/vips/{identity['vip_a']}", headers=_auth(token))
    assert allowed.status_code == 200

    denied = client.get(f"/vips/{identity['vip_b']}", headers=_auth(token))
    assert denied.status_code == 403

    listed = client.get("/vips", headers=_auth(token))
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [identity["vip_a"]]

    mutate = client.post("/vips", json={"name": "Nope"}, headers=_auth(token))
    assert mutate.status_code == 403


@DB_REQUIRED
def test_admin_flow_and_audit_middleware(client: TestClient, identity: dict[str, str], pg_engine) -> None:
    token = _login(client, "admin@example.test", "admin-pass")
    created = client.post("/vips", json={"name": "Vip Admin"}, headers=_auth(token))
    assert created.status_code == 201

    with Session(pg_engine) as session:
        middleware_rows = session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "POST /vips")
        ).scalar_one()
    assert middleware_rows >= 1


@DB_REQUIRED
def test_refresh_rotation_invalidates_the_old_token(client: TestClient, identity: dict[str, str]) -> None:
    login = client.post("/auth/login", json={"email": "admin@example.test", "password": "admin-pass"})
    assert login.status_code == 200
    original_cookie = login.cookies.get("aegis_refresh")
    assert original_cookie

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    client.cookies.set("aegis_refresh", original_cookie, path="/auth")
    reuse = client.post("/auth/refresh")
    assert reuse.status_code == 401


@DB_REQUIRED
def test_reveal_permission_is_admin_only_and_never_for_viewers(client: TestClient, identity: dict[str, str]) -> None:
    admin = _login(client, "admin@example.test", "admin-pass")
    analyst = _login(client, "analyst@example.test", "analyst-pass")

    denied = client.put(
        f"/users/{identity['analyst']}/vips/{identity['vip_a']}/reveal",
        headers=_auth(analyst),
    )
    assert denied.status_code == 403

    granted = client.put(
        f"/users/{identity['analyst']}/vips/{identity['vip_a']}/reveal",
        headers=_auth(admin),
    )
    assert granted.status_code == 200
    assert granted.json()["can_reveal_sensitive"] is True

    viewer_rejected = client.put(
        f"/users/{identity['viewer']}/vips/{identity['vip_a']}/reveal",
        headers=_auth(admin),
    )
    assert viewer_rejected.status_code == 400

    revoked = client.delete(
        f"/users/{identity['analyst']}/vips/{identity['vip_a']}/reveal",
        headers=_auth(admin),
    )
    assert revoked.status_code == 204
