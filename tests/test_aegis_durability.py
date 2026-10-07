"""Durability integration tests: broker restart and worker crash.

These tests are excluded from the normal suite because they restart the broker
container and spawn real worker processes. Run them with:

    AEGIS_INTEGRATION=1 AEGIS_TEST_DATABASE_URL=... AEGIS_TEST_RABBITMQ_URL=... \
        uv run pytest tests/test_aegis_durability.py -v

The broker-restart test needs Docker and restarts the container named by
``AEGIS_TEST_RABBITMQ_CONTAINER`` (default ``aegis_rabbitmq``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import aio_pika
import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session

from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.messaging import Producer, QueueConsumer, broker_channel
from aegis.common.models.collected import Item
from aegis.common.models.enums import AliasKind, Source
from aegis.common.models.incidents import Incident
from aegis.common.models.reference import VIP, VipAlias
from aegis.common.schemas import compute_dedup_key
from aegis.common.topology import QUORUM, dead_letter_queue, declare_topology, retry_queue

pytestmark = [
    pytest.mark.skipif(os.environ.get("AEGIS_INTEGRATION") != "1", reason="AEGIS_INTEGRATION is not set"),
    pytest.mark.skipif(
        not os.environ.get("AEGIS_TEST_DATABASE_URL"),
        reason="AEGIS_TEST_DATABASE_URL is not set",
    ),
    pytest.mark.skipif(
        not os.environ.get("AEGIS_TEST_RABBITMQ_URL"),
        reason="AEGIS_TEST_RABBITMQ_URL is not set",
    ),
]

RECEIPT_TABLE = "durability_receipts"


def _sync_wait(predicate: Any, timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
    return False


async def _async_wait(predicate: Any, timeout: float = 120.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.5)
    return False


async def _connect_ready(
    url: str,
    *,
    attempts: int = 30,
    delay: float = 2.0,
) -> aio_pika.abc.AbstractRobustConnection:
    """Connect, retrying while RabbitMQ finishes restarting.

    A reset during the AMQP handshake makes the initial connect_robust call
    raise instead of retrying, so probe with our own retry loop.
    """

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as error:
            last_error = error
            await asyncio.sleep(delay)
    raise RuntimeError(f"broker did not become ready: {last_error}")


async def _probe_broker(url: str) -> None:
    connection = await _connect_ready(url)
    with contextlib.suppress(Exception):
        await connection.close()


def _insert_receipt(engine: Engine, dedup_key: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(f"INSERT INTO {RECEIPT_TABLE} (dedup_key) VALUES (:key) ON CONFLICT DO NOTHING"),
            {"key": dedup_key},
        )


def _receipt_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {RECEIPT_TABLE}")).scalar_one())


def _restart_broker(container: str) -> None:
    subprocess.run(["docker", "restart", container], check=True, capture_output=True, timeout=120)


def _docker_ready(container: str) -> bool:
    if shutil.which("docker") is None:
        return False
    inspect = subprocess.run(["docker", "inspect", container], capture_output=True, text=True)
    return inspect.returncode == 0


@pytest.mark.timeout(420)
def test_broker_restart_processes_each_message_once() -> None:
    container = os.environ.get("AEGIS_TEST_RABBITMQ_CONTAINER", "aegis_rabbitmq")
    if not _docker_ready(container):
        pytest.skip(f"docker container {container} is not available")

    engine = create_engine(os.environ["AEGIS_TEST_DATABASE_URL"], pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {RECEIPT_TABLE}"))
        connection.execute(
            text(
                f"CREATE TABLE {RECEIPT_TABLE} (dedup_key text PRIMARY KEY, seen_at timestamptz NOT NULL DEFAULT now())"
            )
        )

    queue_name = f"test.durability.{uuid.uuid4().hex[:12]}"
    total = 1000

    async def scenario() -> None:
        connection = await _connect_ready(os.environ["AEGIS_TEST_RABBITMQ_URL"])
        try:
            channel = await connection.channel(publisher_confirms=True)
            await channel.declare_queue(queue_name, durable=True, arguments=dict(QUORUM))
            await channel.declare_queue(dead_letter_queue(queue_name), durable=True, arguments=dict(QUORUM))
            await channel.declare_queue(
                retry_queue(queue_name),
                durable=True,
                arguments={**QUORUM, "x-dead-letter-exchange": "", "x-dead-letter-routing-key": queue_name},
            )

            producer = Producer(channel)
            for index in range(total):
                await producer.publish_raw(queue_name, json.dumps({"dedup_key": f"durability-{index}"}).encode())

            async def handler(payload: dict[str, Any]) -> None:
                await asyncio.to_thread(_insert_receipt, engine, str(payload["dedup_key"]))

            consumer = QueueConsumer(channel, queue_name, handler, arguments=dict(QUORUM))
            await consumer.start()

            await asyncio.sleep(1.0)
            await asyncio.to_thread(_restart_broker, container)

            reached = await _async_wait(lambda: _receipt_count(engine) >= total, timeout=300)
            assert reached, f"processed only {_receipt_count(engine)} of {total} messages"
        finally:
            with contextlib.suppress(Exception):
                await connection.close()

        connection = await _connect_ready(os.environ["AEGIS_TEST_RABBITMQ_URL"])
        try:
            channel = await connection.channel()
            dlq = await channel.declare_queue(dead_letter_queue(queue_name), durable=True, arguments=dict(QUORUM))
            assert await dlq.get(fail=False, timeout=1.0) is None
        finally:
            with contextlib.suppress(Exception):
                await connection.close()

    asyncio.run(scenario())
    assert _receipt_count(engine) == total
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {RECEIPT_TABLE}"))
    engine.dispose()


def _item_count(engine: Engine, run_id: str) -> int:
    with Session(engine) as session:
        return int(
            session.execute(
                select(func.count()).select_from(Item).where(Item.platform_item_id.like(f"durability-{run_id}-%"))
            ).scalar_one()
        )


def _incident_count(engine: Engine, run_id: str) -> int:
    with Session(engine) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(Incident)
                .join(Item, Incident.item_id == Item.id)
                .where(Item.platform_item_id.like(f"durability-{run_id}-%"))
            ).scalar_one()
        )


def _spawn(module: str, log_path: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    log = log_path.open("wb")  # noqa: SIM115
    return subprocess.Popen(
        [sys.executable, "-m", module],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def _dump_logs(tmp_path: Path) -> None:
    for name in ("normalizer.log", "worker-1.log", "worker-2.log"):
        path = tmp_path / name
        if path.exists():
            print(f"--- {name} ---")
            print(path.read_text(encoding="utf-8", errors="replace")[-4000:])


async def _publish_items(payloads: list[dict[str, Any]]) -> None:
    async with broker_channel() as channel:
        await declare_topology(channel)
        producer = Producer(channel)
        for payload in payloads:
            await producer.publish_raw("items.raw", json.dumps(payload).encode())


@pytest.mark.timeout(420)
def test_worker_killed_mid_batch_loses_and_duplicates_nothing(pg_engine: Engine, tmp_path: Path) -> None:
    run_id = uuid.uuid4().hex[:8]
    vip_name = f"Durability VIP {run_id}"
    with Session(pg_engine) as session:
        vip = VIP(name=vip_name)
        session.add(vip)
        session.flush()
        session.add(VipAlias(vip_id=vip.id, alias=vip_name, kind=AliasKind.NAME))
        session.commit()

    total = 150
    template = json.loads(
        generate(
            SyntheticConfig(
                seed=91,
                campaign_accounts=1,
                impersonators=0,
                leaks=0,
                hinglish_threats=0,
                criticism=0,
                vip_name=vip_name,
            )
        )[0].model_dump_json()
    )
    payloads: list[dict[str, Any]] = []
    for index in range(total):
        payload = deepcopy(template)
        platform_item_id = f"durability-{run_id}-{index}"
        payload["platform_item_id"] = platform_item_id
        payload["dedup_key"] = compute_dedup_key(Source.REPLAY, platform_item_id)
        payload["content"]["text"] = f"I will shoot {vip_name} with a gun tomorrow at his house"
        payload["author"]["platform_account_id"] = f"durability-account-{run_id}"
        payload["author"]["handle"] = f"durability_{run_id}"
        payload["author"]["followers"] = 1_000_000
        payload["relations"]["mentions"] = []
        payloads.append(payload)

    env = {**os.environ, "AEGIS_TOXICITY_ENABLED": "false"}
    asyncio.run(_probe_broker(os.environ["AEGIS_TEST_RABBITMQ_URL"]))
    normalizer = _spawn("aegis.pipeline.normalizer", tmp_path / "normalizer.log", env)
    worker: subprocess.Popen[bytes] | None = None
    try:
        time.sleep(3)
        worker = _spawn("aegis.pipeline.analysis", tmp_path / "worker-1.log", env)
        time.sleep(2)
        exited = []
        if normalizer.poll() is not None:
            exited.append(f"normalizer exit code {normalizer.returncode}")
        if worker.poll() is not None:
            exited.append(f"worker exit code {worker.returncode}")
        if exited:
            _dump_logs(tmp_path)
            pytest.fail(f"processes exited during startup: {', '.join(exited)}")

        asyncio.run(_publish_items(payloads))

        appeared = _sync_wait(lambda: _incident_count(pg_engine, run_id) >= 1, timeout=90)
        if not appeared:
            _dump_logs(tmp_path)
        assert appeared, "no incident appeared"

        worker.kill()
        worker.wait(timeout=30)

        worker = _spawn("aegis.pipeline.analysis", tmp_path / "worker-2.log", env)
        complete = _sync_wait(
            lambda: _item_count(pg_engine, run_id) == total and _incident_count(pg_engine, run_id) == total,
            timeout=300,
        )
        if not complete:
            _dump_logs(tmp_path)

        assert _item_count(pg_engine, run_id) == total
        assert _incident_count(pg_engine, run_id) == total
    finally:
        for process in (worker, normalizer):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
