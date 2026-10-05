"""Shared helpers for service entrypoints."""

from __future__ import annotations

import signal
import threading

from aegis.common.logging import configure_logging, get_logger


def run_until_stopped(service: str, note: str) -> None:
    """Run the skeleton heartbeat for a service until SIGTERM or SIGINT."""

    configure_logging()
    log = get_logger(service)
    log.warning("skeleton_service_started", service=service, note=note)

    stop = threading.Event()

    def _handle(signum: int, frame: object) -> None:
        log.info("stop_signal_received", signal=signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    stop.wait()
    log.info("skeleton_service_stopped", service=service)
