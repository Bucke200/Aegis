"""Tests for user provisioning (API and CLI)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api.admin import build_parser, main
from aegis.api.main import app
from aegis.api.security import create_access_token
from aegis.api.services.users import UserService
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User, UserVipScope
from aegis.common.models.reference import VIP

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


def test_parser_accepts_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(["create-user", "--email", "a@example.test", "--password", "secret123"])
    assert args.command == "create-user"
    assert args.role == "viewer"
    with pytest.raises(SystemExit):
        parser.parse_args(["create-user"])


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
def context(pg_engine) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    with Session(pg_engine) as session:
        service = UserService(session)
        admin = service.create_user(
            email=f"admin-{suffix}@example.test",
            password="admin-password",
            role=UserRole.ADMIN,
        )
        analyst = service.create_user(
            email=f"analyst-{suffix}@example.test",
            password="analyst-password",
            role=UserRole.ANALYST,
        )
        vip = VIP(name=f"Vip Users {suffix}")
        session.add(vip)
        session.flush()
        session.commit()
        return {
            "admin": str(admin.id),
            "analyst": str(analyst.id),
            "admin_email": admin.email,
            "analyst_email": analyst.email,
            "analyst_token": create_access_token(analyst.id, analyst.role.value),
            "admin_token": create_access_token(admin.id, admin.role.value),
            "vip": str(vip.id),
        }


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@DB_REQUIRED
def test_admin_user_crud_scope_and_reveal_downgrade(client: TestClient, context: dict[str, str], pg_engine) -> None:
    admin = _auth(context["admin_token"])
    new_email = f"new-{uuid.uuid4().hex[:8]}@example.test"

    created = client.post(
        "/users",
        json={"email": new_email, "password": "new-password", "role": "analyst"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    listed = client.get("/users", headers=admin)
    assert listed.status_code == 200
    assert any(row["id"] == user_id for row in listed.json())

    duplicate = client.post(
        "/users",
        json={"email": new_email, "password": "new-password", "role": "analyst"},
        headers=admin,
    )
    assert duplicate.status_code == 409

    granted = client.put(f"/users/{user_id}/vips/{context['vip']}/reveal", headers=admin)
    assert granted.status_code == 200
    assert granted.json()["can_reveal_sensitive"] is True

    downgraded = client.patch(f"/users/{user_id}", json={"role": "viewer"}, headers=admin)
    assert downgraded.status_code == 200
    assert downgraded.json()["role"] == "viewer"

    with Session(pg_engine) as session:
        scope = session.get(UserVipScope, (uuid.UUID(user_id), uuid.UUID(context["vip"])))
        assert scope is not None
        assert scope.can_reveal_sensitive is False

    removed = client.delete(f"/users/{user_id}/vips/{context['vip']}", headers=admin)
    assert removed.status_code == 204


@DB_REQUIRED
def test_non_admins_cannot_manage_users(client: TestClient, context: dict[str, str]) -> None:
    analyst = _auth(context["analyst_token"])
    assert client.get("/users", headers=analyst).status_code == 403
    assert (
        client.post(
            "/users",
            json={
                "email": f"x-{uuid.uuid4().hex[:8]}@example.test",
                "password": "password123",
                "role": "viewer",
            },
            headers=analyst,
        ).status_code
        == 403
    )


@DB_REQUIRED
def test_cli_bootstraps_an_admin_who_can_log_in(client: TestClient, pg_engine) -> None:
    email = f"bootstrap-{uuid.uuid4().hex[:8]}@example.test"
    assert main(["create-admin", "--email", email, "--password", "bootstrap-pass"]) == 0
    assert main(["list-users"]) == 0

    with Session(pg_engine) as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        assert user.role is UserRole.ADMIN

    login = client.post("/auth/login", json={"email": email, "password": "bootstrap-pass"})
    assert login.status_code == 200
    assert login.json()["role"] == "admin"


@DB_REQUIRED
def test_directory_is_available_to_analysts(client: TestClient, context: dict[str, str]) -> None:
    directory = client.get("/users/directory", headers=_auth(context["analyst_token"]))
    assert directory.status_code == 200, directory.text
    rows = {row["id"]: row for row in directory.json()}
    assert context["analyst"] in rows
    assert rows[context["analyst"]]["role"] == "analyst"

    assert client.get("/users/directory").status_code == 401
