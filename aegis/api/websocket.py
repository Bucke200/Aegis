"""WebSocket gateway: pushes incident events to dashboards filtered by VIP scope.

The gateway consumes ``events.incidents`` and forwards ``created``, ``updated``
and ``merged`` events to every connection whose VIP scope intersects the
event's VIPs. Clients then refetch details over REST, so permission checks stay
in one place; a reconnect simply refetches since the client's last-seen event.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from aegis.api.dependencies import scoped_vip_ids
from aegis.api.security import ACCESS_TOKEN_TYPE, TokenError, decode_token
from aegis.common.db import get_session
from aegis.common.logging import get_logger
from aegis.common.messaging import broker_channel, decode_message
from aegis.common.models.ops import User
from aegis.common.topology import QUORUM, WS_INCIDENTS_QUEUE, declare_topology

EVENT_TYPE_PREFIX = "incident."


@dataclass
class Connection:
    user_id: uuid.UUID
    vip_scope: set[uuid.UUID] | None
    websocket: WebSocket


class ConnectionManager:
    """Tracks live dashboard connections and fans events out by VIP scope."""

    def __init__(self) -> None:
        self.connections: list[Connection] = []

    def register(self, user_id: uuid.UUID, vip_scope: set[uuid.UUID] | None, websocket: WebSocket) -> Connection:
        connection = Connection(user_id=user_id, vip_scope=vip_scope, websocket=websocket)
        self.connections.append(connection)
        return connection

    def unregister(self, connection: Connection) -> None:
        with suppress(ValueError):
            self.connections.remove(connection)

    def event_payload(self, event_type: str, event: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": event_type.removeprefix(EVENT_TYPE_PREFIX),
            "incident_id": event.get("incident_id"),
            "severity": event.get("severity"),
            "risk_score": event.get("risk_score"),
            "vip_ids": event.get("vip_ids", []),
        }
        if event.get("merged_into_id"):
            payload["merged_into_id"] = event["merged_into_id"]
        return payload

    def visible_to(self, connection: Connection, event: dict[str, Any]) -> bool:
        if connection.vip_scope is None:
            return True
        event_vips = {uuid.UUID(str(value)) for value in event.get("vip_ids", [])}
        return bool(connection.vip_scope & event_vips)

    async def broadcast(self, event_type: str, event: dict[str, Any]) -> int:
        payload = self.event_payload(event_type, event)
        sent = 0
        for connection in list(self.connections):
            if not self.visible_to(connection, event):
                continue
            try:
                await connection.websocket.send_json(payload)
                sent += 1
            except Exception:
                self.unregister(connection)
        return sent


router = APIRouter()


def _user_from_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token, ACCESS_TOKEN_TYPE)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError):
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


@router.websocket("/ws/incidents")
async def incidents_websocket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> None:
    user = _user_from_token(session, token)
    if user is None:
        await websocket.close(code=1008)
        return

    manager: ConnectionManager = websocket.app.state.connection_manager
    await websocket.accept()
    connection = manager.register(user.id, scoped_vip_ids(session, user), websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(connection)


async def consume_incident_events(manager: ConnectionManager, url: str | None = None) -> None:
    """Consume events.incidents and broadcast them until cancelled."""

    async with broker_channel(url) as channel:
        await _consume(channel, manager)


async def _consume(channel: AbstractChannel, manager: ConnectionManager) -> None:
    await declare_topology(channel)
    queue = await channel.declare_queue(WS_INCIDENTS_QUEUE, durable=True, arguments=dict(QUORUM))
    async with queue.iterator() as messages:
        async for message in messages:
            await _handle_message(channel, message, manager)


async def _handle_message(
    channel: AbstractChannel, message: AbstractIncomingMessage, manager: ConnectionManager
) -> None:
    event_type = str((message.headers or {}).get("event_type", "incident.updated"))
    async with message.process():
        await manager.broadcast(event_type, decode_message(message))


@asynccontextmanager
async def websocket_consumer_lifespan(manager: ConnectionManager, enabled: bool) -> AsyncIterator[None]:
    """Run the incident consumer for the lifetime of the app."""

    log = get_logger("ws-gateway")
    task: asyncio.Task[None] | None = None
    if enabled:
        task = asyncio.create_task(_consume_safely(manager, log))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def _consume_safely(manager: ConnectionManager, log: Any) -> None:
    try:
        await consume_incident_events(manager)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        log.warning("ws_consumer_stopped", error=str(error))
