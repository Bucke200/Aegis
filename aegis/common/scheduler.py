"""Periodic job scheduling with one advisory-locked run per job at a time.

The ``aegis-scheduler`` process owns a registry of :class:`Job` objects. Every
pass reads each job's last start from ``job_runs``, runs the jobs whose next
occurrence has passed, and records the outcome. A job with no recorded run is
anchored at the pass that first saw it, so it waits for its first scheduled
occurrence instead of running at every scheduler start. A run holds
``pg_try_advisory_lock(hashtext('aegis-job:' || name))`` on a dedicated
connection, so a job that another scheduler process is already running is
skipped rather than queued, and missed occurrences collapse into one catch-up
run.

Job targets are dotted paths resolved when the job runs, so the scheduler
process does not import heavy modules until a job actually needs them.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import signal
import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from aegis.common.db import get_engine
from aegis.common.logging import configure_logging, get_logger
from aegis.common.models.ops import JobRun

DEFAULT_JOB_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_SECONDS = 1.0
ADVISORY_LOCK = text("SELECT pg_try_advisory_lock(hashtext('aegis-job:' || :name))")
ADVISORY_UNLOCK = text("SELECT pg_advisory_unlock(hashtext('aegis-job:' || :name))")


class JobRunStatus(StrEnum):
    """Outcomes recorded in ``job_runs.last_status``."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class Schedule(Protocol):
    """A pure next-run computation over timezone-aware datetimes."""

    def next_run_after(self, moment: datetime) -> datetime:
        """Return the first scheduled occurrence strictly after ``moment``."""


def _require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("schedule arithmetic needs a timezone-aware datetime")
    return moment


@dataclass(frozen=True)
class Every:
    """Run at a fixed interval, measured from the previous run."""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError("seconds must be positive")

    def next_run_after(self, moment: datetime) -> datetime:
        return _require_aware(moment) + timedelta(seconds=self.seconds)


@dataclass(frozen=True)
class HourlyAt:
    """Run once an hour at ``minute`` minutes past the hour."""

    minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be between 0 and 59")

    def next_run_after(self, moment: datetime) -> datetime:
        aware = _require_aware(moment)
        candidate = aware.replace(minute=self.minute, second=0, microsecond=0)
        if candidate <= aware:
            candidate += timedelta(hours=1)
        return candidate


@dataclass(frozen=True)
class DailyAt:
    """Run once a day at ``hour:minute`` in the IANA time zone ``tz``."""

    hour: int
    minute: int
    tz: str

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= 23:
            raise ValueError("hour must be between 0 and 23")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be between 0 and 59")
        try:
            ZoneInfo(self.tz)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown time zone: {self.tz!r}") from exc

    def next_run_after(self, moment: datetime) -> datetime:
        zone = ZoneInfo(self.tz)
        local = _require_aware(moment).astimezone(zone)
        candidate = datetime.combine(local.date(), time(self.hour, self.minute), tzinfo=zone)
        if candidate <= local:
            candidate = datetime.combine(local.date() + timedelta(days=1), time(self.hour, self.minute), tzinfo=zone)
        return candidate.astimezone(UTC)


@dataclass(frozen=True)
class Job:
    """A named periodic job whose dotted-path target runs with a timeout."""

    name: str
    schedule: Schedule
    target: str
    timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS


def resolve_target(target: str) -> Callable[[], Any]:
    """Return the callable named by a ``module.attribute`` dotted path."""

    module_name, _, attribute = target.rpartition(".")
    if not module_name or not attribute:
        raise ValueError(f"job target must be a dotted path: {target!r}")
    resolved: object = getattr(importlib.import_module(module_name), attribute)
    if not callable(resolved):
        raise TypeError(f"job target is not callable: {target!r}")
    return cast("Callable[[], Any]", resolved)


def is_due(schedule: Schedule, last_started_at: datetime, now: datetime) -> bool:
    """Return True when the first occurrence after ``last_started_at`` has passed.

    A job whose next occurrence is already in the past runs once, so a backlog
    of missed occurrences collapses into a single catch-up run.
    """

    return schedule.next_run_after(last_started_at) <= now


async def _await(awaitable: Awaitable[Any]) -> None:
    await awaitable


def _seconds_since(moment: datetime) -> float:
    return (datetime.now(UTC) - moment).total_seconds()


@dataclass
class _Run:
    """One attempt at a job, kept until its outcome is recorded."""

    job: Job
    connection: Connection
    started_at: datetime
    done: threading.Event = field(default_factory=threading.Event)
    finished_at: datetime | None = None
    status: JobRunStatus | None = None
    error: str | None = None
    timed_out: bool = False
    recorded: bool = False


class SchedulerRunner:
    """Run the due jobs, one advisory-locked attempt per job at a time."""

    def __init__(
        self,
        jobs: Sequence[Job],
        *,
        engine: Engine | None = None,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        self._jobs = tuple(jobs)
        self._engine = engine if engine is not None else get_engine()
        self._poll_seconds = poll_seconds
        self._running: dict[str, _Run] = {}
        self._observed_since: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._log = get_logger("scheduler")

    @property
    def running_jobs(self) -> tuple[str, ...]:
        """Names of the jobs that are running right now."""

        return tuple(self._running)

    def run_once(self) -> tuple[str, ...]:
        """Record finished runs, then start every due job and return their names."""

        self._settle_all()
        now = datetime.now(UTC)
        anchors = self._load_anchors()
        started: list[str] = []
        for job in self._jobs:
            if job.name in self._running:
                continue
            anchor = anchors.get(job.name)
            if anchor is None:
                anchor = self._observed_since.setdefault(job.name, now)
            if not is_due(job.schedule, anchor, now):
                continue
            if self._start(job, now):
                started.append(job.name)
        return tuple(started)

    def run_forever(self) -> None:
        """Run passes until :meth:`stop`, then wait for the in-flight jobs."""

        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._poll_seconds)
        self.drain()

    def stop(self) -> None:
        """Ask the loop to stop starting jobs."""

        self._stop.set()

    def drain(self) -> None:
        """Wait for running jobs, up to each job's timeout, then return."""

        for name in sorted(self._running):
            run = self._running[name]
            remaining = run.job.timeout_seconds - _seconds_since(run.started_at)
            if run.finished_at is None and remaining > 0:
                run.done.wait(remaining)
            self._settle(run)

    def _start(self, job: Job, now: datetime) -> bool:
        connection = self._acquire(job)
        if connection is None:
            self._log.info("job_skipped_locked", job=job.name)
            return False
        run = _Run(job=job, connection=connection, started_at=now)
        self._running[job.name] = run
        threading.Thread(target=self._execute, args=(run,), name=f"aegis-job-{job.name}", daemon=True).start()
        self._log.info("job_started", job=job.name)
        return True

    def _execute(self, run: _Run) -> None:
        try:
            outcome = resolve_target(run.job.target)()
            if inspect.isawaitable(outcome):
                asyncio.run(_await(outcome))
        except Exception as exc:
            run.status = JobRunStatus.ERROR
            run.error = f"{type(exc).__name__}: {exc}"
        else:
            run.status = JobRunStatus.OK
        finally:
            run.finished_at = datetime.now(UTC)
            run.done.set()

    def _settle_all(self) -> None:
        for run in list(self._running.values()):
            self._settle(run)

    def _settle(self, run: _Run) -> None:
        job = run.job
        if run.finished_at is not None:
            self._record(run, run.status if run.status is not None else JobRunStatus.ERROR, run.error)
            self._release(run)
            self._running.pop(job.name, None)
            self._log.info(
                "job_finished",
                job=job.name,
                status=run.status.value if run.status is not None else None,
                timed_out=run.timed_out,
                duration_seconds=round((run.finished_at - run.started_at).total_seconds(), 3),
            )
            return
        if not run.timed_out and _seconds_since(run.started_at) >= job.timeout_seconds:
            run.timed_out = True
            self._record(run, JobRunStatus.TIMEOUT, f"exceeded {job.timeout_seconds:g} seconds")
            self._log.warning("job_timeout", job=job.name, timeout_seconds=job.timeout_seconds)

    def _record(self, run: _Run, status: JobRunStatus, error: str | None) -> None:
        if run.recorded:
            return
        finished_at = run.finished_at if run.finished_at is not None else datetime.now(UTC)
        self._write_run(run.job.name, run.started_at, finished_at, status, error)
        run.recorded = True

    def _acquire(self, job: Job) -> Connection | None:
        connection = self._engine.connect()
        try:
            acquired = bool(connection.execute(ADVISORY_LOCK, {"name": job.name}).scalar_one())
            if connection.in_transaction():
                connection.commit()
        except Exception:
            connection.close()
            raise
        if not acquired:
            connection.close()
            return None
        return connection

    def _release(self, run: _Run) -> None:
        try:
            run.connection.execute(ADVISORY_UNLOCK, {"name": run.job.name})
            if run.connection.in_transaction():
                run.connection.commit()
        except Exception:
            self._log.warning("advisory_lock_release_failed", job=run.job.name, exc_info=True)
            run.connection.invalidate()
        finally:
            run.connection.close()

    def _load_anchors(self) -> dict[str, datetime]:
        names = [job.name for job in self._jobs]
        if not names:
            return {}
        with self._engine.connect() as connection:
            rows = connection.execute(select(JobRun.job, JobRun.last_started_at).where(JobRun.job.in_(names))).all()
        return {row.job: row.last_started_at for row in rows}

    def _write_run(
        self,
        name: str,
        started_at: datetime,
        finished_at: datetime,
        status: JobRunStatus,
        error: str | None,
    ) -> None:
        statement = postgresql_insert(JobRun).values(
            job=name,
            last_started_at=started_at,
            last_finished_at=finished_at,
            last_status=status.value,
            last_error=error,
            run_count=1,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[JobRun.job],
            set_={
                "last_started_at": statement.excluded.last_started_at,
                "last_finished_at": statement.excluded.last_finished_at,
                "last_status": statement.excluded.last_status,
                "last_error": statement.excluded.last_error,
                "run_count": JobRun.run_count + 1,
            },
        )
        with self._engine.begin() as connection:
            connection.execute(statement)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis-scheduler",
        description="Run the Aegis periodic jobs",
    )
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    log = get_logger("scheduler")

    from aegis.common.jobs import JOBS

    runner = SchedulerRunner(JOBS, poll_seconds=args.poll_seconds)

    def _handle(signum: int, frame: object) -> None:
        log.info("stop_signal_received", signal=signum)
        runner.stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    log.info("scheduler_started", jobs=[job.name for job in JOBS])
    if args.once:
        started = runner.run_once()
        runner.stop()
        runner.drain()
        log.info("scheduler_pass_complete", started=list(started))
        return 0
    runner.run_forever()
    log.info("scheduler_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
