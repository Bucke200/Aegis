"""The registry of periodic jobs run by ``aegis-scheduler``.

Later work packages append their jobs here. Each job names its target as a
dotted path, so the scheduler imports the module only when the job runs.
"""

from __future__ import annotations

from aegis.common.logging import get_logger
from aegis.common.scheduler import Every, Job

HEARTBEAT_INTERVAL_SECONDS = 60.0


def heartbeat() -> None:
    """Log one heartbeat; the runner records the run in ``job_runs``."""

    get_logger("scheduler").info("scheduler_heartbeat")


JOBS: tuple[Job, ...] = (
    Job(
        name="scheduler.heartbeat",
        schedule=Every(HEARTBEAT_INTERVAL_SECONDS),
        target="aegis.common.jobs.heartbeat",
    ),
)
