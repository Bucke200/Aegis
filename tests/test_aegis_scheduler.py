"""Tests for the periodic job scheduler."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from aegis.common import scheduler as scheduler_module
from aegis.common.models.ops import JobRun
from aegis.common.scheduler import (
    DailyAt,
    Every,
    HourlyAt,
    Job,
    SchedulerRunner,
    is_due,
    resolve_target,
)

DB_REQUIRED = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_DATABASE_URL"),
    reason="AEGIS_TEST_DATABASE_URL is not set",
)


@pytest.fixture
def job_name(pg_engine: Engine) -> Iterator[str]:
    name = f"test.scheduler.{uuid.uuid4().hex[:8]}"
    yield name
    with Session(pg_engine) as session:
        session.execute(text("DELETE FROM job_runs WHERE job LIKE 'test.scheduler.%'"))
        session.commit()


def _seed_last_start(engine: Engine, name: str, last_started_at: datetime) -> None:
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO job_runs (job, last_started_at, last_finished_at, last_status, last_error, run_count) "
                "VALUES (:job, :started, :started, 'ok', NULL, 0) "
                "ON CONFLICT (job) DO UPDATE SET last_started_at = EXCLUDED.last_started_at, "
                "last_finished_at = NULL, last_status = 'ok', last_error = NULL, run_count = 0"
            ),
            {"job": name, "started": last_started_at},
        )
        session.commit()


def _read_run(engine: Engine, name: str) -> dict[str, Any] | None:
    with Session(engine) as session:
        row = (
            session.execute(
                select(
                    JobRun.last_started_at,
                    JobRun.last_finished_at,
                    JobRun.last_status,
                    JobRun.last_error,
                    JobRun.run_count,
                ).where(JobRun.job == name)
            )
            .mappings()
            .one_or_none()
        )
    return dict(row) if row is not None else None


def _resolve(mapping: dict[str, Callable[[], Any]]) -> Callable[[str], Callable[[], Any]]:
    return lambda target: mapping[target]


def test_every_next_run_after_adds_the_interval() -> None:
    now = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert Every(90).next_run_after(now) == now + timedelta(seconds=90)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-10-13T09:30:00+00:00", "2026-10-13T10:00:00+00:00"),
        ("2026-10-13T10:00:00+00:00", "2026-10-13T11:00:00+00:00"),
        ("2026-10-13T10:00:00.500000+00:00", "2026-10-13T11:00:00+00:00"),
    ],
)
def test_hourly_at_next_run_after(moment: str, expected: str) -> None:
    assert HourlyAt(0).next_run_after(datetime.fromisoformat(moment)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-10-13T02:00:00+00:00", "2026-10-13T03:30:00+00:00"),
        ("2026-10-13T03:29:59+00:00", "2026-10-13T03:30:00+00:00"),
        ("2026-10-13T03:30:00+00:00", "2026-10-14T03:30:00+00:00"),
        ("2026-10-13T19:00:00+00:00", "2026-10-14T03:30:00+00:00"),
        ("2026-10-13T20:30:00+00:00", "2026-10-14T03:30:00+00:00"),
    ],
)
def test_daily_at_in_asia_kolkata_crosses_the_utc_date(moment: str, expected: str) -> None:
    schedule = DailyAt(9, 0, "Asia/Kolkata")
    assert schedule.next_run_after(datetime.fromisoformat(moment)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Every(0), "seconds"),
        (lambda: HourlyAt(60), "minute"),
        (lambda: DailyAt(24, 0, "UTC"), "hour"),
        (lambda: DailyAt(0, 60, "UTC"), "minute"),
        (lambda: DailyAt(0, 0, "Nowhere/Nope"), "time zone"),
    ],
)
def test_schedule_validation(build: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build()


def test_is_due_waits_for_the_next_occurrence() -> None:
    now = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert is_due(Every(60), now, now) is False
    assert is_due(Every(60), now - timedelta(seconds=30), now) is False


def test_is_due_when_the_next_occurrence_has_passed() -> None:
    now = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert is_due(Every(60), now - timedelta(minutes=5), now) is True


def test_is_due_collapses_a_backlog_of_daily_runs() -> None:
    schedule = DailyAt(9, 0, "Asia/Kolkata")
    last_started_at = datetime(2026, 10, 10, 3, 30, tzinfo=UTC)
    now = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    assert is_due(schedule, last_started_at, now) is True
    assert is_due(schedule, datetime(2026, 10, 13, 4, 0, tzinfo=UTC), now) is False


def test_resolve_target_imports_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "aegis.common.jobs", raising=False)
    job = Job(name="test.lazy", schedule=Every(60), target="aegis.common.jobs.heartbeat")
    assert "aegis.common.jobs" not in sys.modules
    assert callable(resolve_target(job.target))
    assert "aegis.common.jobs" in sys.modules


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("", ValueError),
        ("heartbeat", ValueError),
        (".x", ValueError),
        ("aegis.common.jobs.missing", AttributeError),
        ("aegis.missing.module", ModuleNotFoundError),
        ("aegis.common.scheduler.DEFAULT_POLL_SECONDS", TypeError),
    ],
)
def test_resolve_target_rejects_bad_paths(target: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        resolve_target(target)


def test_registry_starts_with_the_heartbeat_job() -> None:
    from aegis.common.jobs import JOBS, heartbeat

    assert [job.name for job in JOBS] == ["scheduler.heartbeat"]
    assert JOBS[0].schedule == Every(60.0)
    assert JOBS[0].timeout_seconds > 0
    assert resolve_target(JOBS[0].target) is heartbeat


@DB_REQUIRED
def test_two_runners_execute_a_due_job_once(pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []
    started = threading.Event()
    release = threading.Event()

    def target() -> None:
        calls.append(time.monotonic())
        started.set()
        assert release.wait(timeout=10)

    monkeypatch.setattr(scheduler_module, "resolve_target", _resolve({"test.blocking": target}))
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    job = Job(name=job_name, schedule=Every(60), target="test.blocking", timeout_seconds=30)
    first = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.05)
    second = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.05)

    passed: list[tuple[str, ...]] = []

    def run_pass(runner: SchedulerRunner) -> None:
        passed.append(runner.run_once())

    threads = [
        threading.Thread(target=run_pass, args=(runner,), name=f"runner-{index}")
        for index, runner in enumerate((first, second))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert started.is_set()
    release.set()
    first.drain()
    second.drain()

    assert len(calls) == 1
    assert [names for names in passed if names] == [(job_name,)]
    run = _read_run(pg_engine, job_name)
    assert run is not None
    assert run["run_count"] == 1
    assert run["last_status"] == "ok"


@DB_REQUIRED
def test_a_failing_job_records_error_and_does_not_stop_the_runner(
    pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    healthy_name = f"{job_name}.healthy"

    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "resolve_target", _resolve({"test.boom": boom, "test.ok": lambda: None}))
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    _seed_last_start(pg_engine, healthy_name, datetime.now(UTC) - timedelta(minutes=5))
    failing = Job(name=job_name, schedule=Every(60), target="test.boom", timeout_seconds=30)
    healthy = Job(name=healthy_name, schedule=Every(60), target="test.ok", timeout_seconds=30)
    runner = SchedulerRunner([failing, healthy], engine=pg_engine, poll_seconds=0.05)

    assert runner.run_once() == (job_name, healthy_name)
    runner.drain()

    failed = _read_run(pg_engine, job_name)
    assert failed is not None
    assert failed["last_status"] == "error"
    assert failed["last_error"] is not None
    assert "boom" in failed["last_error"]
    healthy_run = _read_run(pg_engine, healthy_name)
    assert healthy_run is not None
    assert healthy_run["last_status"] == "ok"

    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    assert runner.run_once() == (job_name,)
    runner.drain()


@DB_REQUIRED
def test_a_job_exceeding_its_timeout_records_timeout(
    pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    monkeypatch.setattr(scheduler_module, "resolve_target", _resolve({"test.slow": release.wait}))
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    job = Job(name=job_name, schedule=Every(60), target="test.slow", timeout_seconds=0.05)
    runner = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.01)

    assert runner.run_once() == (job_name,)
    run: dict[str, Any] | None = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        runner.run_once()
        run = _read_run(pg_engine, job_name)
        if run is not None and run["last_status"] == "timeout":
            break
        time.sleep(0.05)

    assert run is not None
    assert run["last_status"] == "timeout"
    assert run["last_error"] is not None
    assert "exceeded 0.05 seconds" in run["last_error"]
    assert runner.running_jobs == (job_name,)

    release.set()
    deadline = time.monotonic() + 5
    while runner.running_jobs and time.monotonic() < deadline:
        runner.run_once()
        time.sleep(0.01)
    assert runner.running_jobs == ()
    settled = _read_run(pg_engine, job_name)
    assert settled is not None
    assert settled["last_status"] == "timeout"
    assert settled["run_count"] == 1


@DB_REQUIRED
def test_missed_runs_collapse_into_one_catch_up(
    pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[float] = []
    monkeypatch.setattr(
        scheduler_module, "resolve_target", _resolve({"test.count": lambda: calls.append(time.monotonic())})
    )
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(hours=10))
    job = Job(name=job_name, schedule=Every(60), target="test.count", timeout_seconds=30)
    runner = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.01)

    assert runner.run_once() == (job_name,)
    runner.drain()
    assert len(calls) == 1

    assert runner.run_once() == ()
    runner.drain()
    assert len(calls) == 1

    run = _read_run(pg_engine, job_name)
    assert run is not None
    assert run["run_count"] == 1
    assert run["last_status"] == "ok"


@DB_REQUIRED
def test_a_job_without_history_waits_for_its_first_occurrence(
    pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[float] = []
    monkeypatch.setattr(
        scheduler_module, "resolve_target", _resolve({"test.first": lambda: calls.append(time.monotonic())})
    )
    job = Job(name=job_name, schedule=Every(0.2), target="test.first", timeout_seconds=30)
    runner = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.01)

    assert runner.run_once() == ()
    assert runner.run_once() == ()
    assert calls == []

    deadline = time.monotonic() + 5
    while not calls and time.monotonic() < deadline:
        runner.run_once()
        time.sleep(0.05)
    runner.drain()

    assert len(calls) == 1
    run = _read_run(pg_engine, job_name)
    assert run is not None
    assert run["run_count"] == 1
    assert run["last_status"] == "ok"


@DB_REQUIRED
def test_stop_lets_the_running_job_finish(pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    finished = threading.Event()

    def target() -> None:
        release.wait(timeout=10)
        finished.set()

    monkeypatch.setattr(scheduler_module, "resolve_target", _resolve({"test.stop": target}))
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    job = Job(name=job_name, schedule=Every(60), target="test.stop", timeout_seconds=10)
    runner = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.01)

    assert runner.run_once() == (job_name,)
    runner.stop()
    threading.Timer(0.2, release.set).start()
    runner.drain()

    assert finished.is_set()
    run = _read_run(pg_engine, job_name)
    assert run is not None
    assert run["last_status"] == "ok"


@DB_REQUIRED
def test_drain_gives_up_after_the_job_timeout(
    pg_engine: Engine, job_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    monkeypatch.setattr(scheduler_module, "resolve_target", _resolve({"test.hang": release.wait}))
    _seed_last_start(pg_engine, job_name, datetime.now(UTC) - timedelta(minutes=5))
    job = Job(name=job_name, schedule=Every(60), target="test.hang", timeout_seconds=0.05)
    runner = SchedulerRunner([job], engine=pg_engine, poll_seconds=0.01)

    assert runner.run_once() == (job_name,)
    started_at = time.monotonic()
    runner.stop()
    runner.drain()
    elapsed = time.monotonic() - started_at

    assert elapsed < 10
    run = _read_run(pg_engine, job_name)
    assert run is not None
    assert run["last_status"] == "timeout"
    release.set()


@DB_REQUIRED
@pytest.mark.skipif(sys.platform == "win32", reason="stopping the scheduler needs POSIX signals")
def test_entrypoint_records_a_run_and_stops_on_sigterm(test_database_url: str, pg_engine: Engine) -> None:
    name = "scheduler.heartbeat"
    _seed_last_start(pg_engine, name, datetime.now(UTC) - timedelta(minutes=5))
    repository = Path(__file__).resolve().parents[1]
    env = {**os.environ, "AEGIS_DATABASE_URL": test_database_url, "PYTHONPATH": str(repository)}
    process = subprocess.Popen(
        [sys.executable, "-m", "aegis.common.scheduler", "--poll-seconds", "0.2"],
        cwd=repository,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = ""
    try:
        run: dict[str, Any] | None = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and process.poll() is None:
            run = _read_run(pg_engine, name)
            if run is not None and run["last_status"] == "ok":
                started_at = run["last_started_at"]
                if datetime.now(UTC) - started_at < timedelta(minutes=1):
                    break
            time.sleep(0.2)

        assert process.poll() is None, process.stdout.read() if process.stdout is not None else ""
        assert run is not None
        assert run["last_status"] == "ok"
        assert run["last_finished_at"] is not None

        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if process.stdout is not None:
            output = process.stdout.read()

    assert "scheduler_heartbeat" in output
