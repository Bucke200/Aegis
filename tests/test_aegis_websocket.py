"""Tests for the WebSocket incident gateway."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from aegis.api.main import app
from aegis.api.security import create_access_token
from aegis.api.services.users import UserService
from aegis.api.websocket import ConnectionManager
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.reference import VIP

try:
    from starlette.websockets import WebSocketDenialResponse

    DENIAL_ERRORS: tuple[type[Exception], ...] = (WebSocketDisconnect, WebSocketDenialResponse)
except ImportError:  # pragma: no cover
    DENIAL_ERRORS = (WebSocketDisconnect,)

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)
RABBITMQ_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_RABBITMQ_URL"),
    reason="AEGIS_TEST_RABBITMQ_URL is not set",
)

VIP_A = uuid.uuid4()
VIP_B = uuid.uuid4()


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail = False

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(payload)


def test_broadcast_filters_by_vip_scope() -> None:
    manager = ConnectionManager()
    scoped_a = FakeWebSocket()
    scoped_b = FakeWebSocket()
    unscoped = FakeWebSocket()
    manager.register(uuid.uuid4(), {VIP_A}, scoped_a)  # type: ignore[arg-type]
    manager.register(uuid.uuid4(), {VIP_B}, scoped_b)  # type: ignore[arg-type]
    manager.register(uuid.uuid4(), None, unscoped)  # type: ignore[arg-type]

    event = {
        "incident_id": "inc-1",
        "severity": "high",
        "risk_score": 0.8,
        "vip_ids": [str(VIP_A)],
    }
    sent = asyncio.run(manager.broadcast("incident.created", event))

    assert sent == 2
    assert len(scoped_a.sent) == 1
    assert scoped_a.sent[0]["type"] == "created"
    assert scoped_b.sent == []
    assert len(unscoped.sent) == 1


def test_dead_connection_is_dropped() -> None:
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    websocket.fail = True
    manager.register(uuid.uuid4(), None, websocket)  # type: ignore[arg-type]

    sent = asyncio.run(manager.broadcast("incident.updated", {"incident_id": "x", "vip_ids": []}))
    assert sent == 0
    assert manager.connections == []


def test_merged_payload_carries_target() -> None:
    payload = ConnectionManager().event_payload(
        "incident.merged",
        {"incident_id": "a", "vip_ids": [], "merged_into_id": "b"},
    )
    assert payload["type"] == "merged"
    assert payload["merged_into_id"] == "b"


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
    app.state.event_consumer_enabled = bool(os.environ.get("AEGIS_TEST_RABBITMQ_URL"))
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def context(pg_engine) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    with Session(pg_engine) as session:
        service = UserService(session)
        admin = service.create_user(
            email=f"ws-admin-{suffix}@example.test",
            password="password",
            role=UserRole.ADMIN,
        )
        analyst = service.create_user(
            email=f"ws-analyst-{suffix}@example.test",
            password="password",
            role=UserRole.ANALYST,
        )
        vip_a = VIP(name=f"Vip WS A {suffix}")
        vip_b = VIP(name=f"Vip WS B {suffix}")
        session.add_all([vip_a, vip_b])
        session.flush()
        service.set_scope(analyst.id, vip_a.id)
        session.commit()
        return {
            "admin_token": create_access_token(admin.id, admin.role.value),
            "analyst_token": create_access_token(analyst.id, analyst.role.value),
            "vip_a": str(vip_a.id),
            "vip_b": str(vip_b.id),
        }


@DB_REQUIRED
def test_websocket_rejects_invalid_token(client: TestClient) -> None:
    with pytest.raises(DENIAL_ERRORS), client.websocket_connect("/ws/incidents?token=not-a-token"):
        pass


def _receive_with_timeout(websocket: Any, timeout: float = 10.0) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def _receive() -> None:
        result["message"] = websocket.receive_json()

    thread = threading.Thread(target=_receive, daemon=True)
    thread.start()
    thread.join(timeout)
    assert "message" in result, "no websocket message within timeout"
    return result["message"]


@DB_REQUIRED
@RABBITMQ_REQUIRED
def test_end_to_end_incident_push_is_vip_scoped(client: TestClient, context: dict[str, Any]) -> None:
    app.state.event_consumer_enabled = True

    async def publish_event(vip_ids: list[str], incident_id: str) -> None:
        from aegis.common.messaging import Producer, broker_channel
        from aegis.common.outbox import INCIDENT_CREATED
        from aegis.common.topology import EVENTS_INCIDENTS, declare_topology

        async with broker_channel() as channel:
            await declare_topology(channel)
            exchange = await channel.declare_exchange(EVENTS_INCIDENTS, "topic", durable=True)
            await Producer(channel).publish(
                exchange,
                INCIDENT_CREATED,
                {
                    "incident_id": incident_id,
                    "severity": "high",
                    "risk_score": 0.8,
                    "vip_ids": vip_ids,
                },
                headers={"event_type": INCIDENT_CREATED},
                message_id=incident_id,
            )

    token = context["analyst_token"]
    with client.websocket_connect(f"/ws/incidents?token={token}") as websocket:
        assert _receive_with_timeout(websocket)["type"] == "ready"
        asyncio.run(publish_event([context["vip_b"]], "out-of-scope"))
        asyncio.run(publish_event([context["vip_a"]], "in-scope"))
        message = _receive_with_timeout(websocket)
        assert message["incident_id"] == "in-scope"
        assert message["type"] == "created"
