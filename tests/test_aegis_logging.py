"""Smoke tests for structured logging."""

from __future__ import annotations

from aegis.common.logging import configure_logging, get_logger


def test_configure_logging_and_emit() -> None:
    configure_logging("INFO")
    logger = get_logger("aegis.test")
    logger.info("smoke_test_event", answer=42)


def test_get_logger_without_name() -> None:
    logger = get_logger()
    assert logger is not None
