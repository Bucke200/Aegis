"""Structured logging configuration built on structlog."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from aegis.common.config import check_insecure_defaults, get_settings


def configure_logging(level: str | None = None) -> None:
    """Configure structlog to emit JSON and set the root log level."""

    settings = get_settings()
    log_level = (level or settings.log_level).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(format="%(message)s", level=numeric_level, stream=sys.stdout)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    insecure = check_insecure_defaults(settings)
    if insecure:
        structlog.get_logger("aegis.config").warning(
            "insecure_default_secrets",
            fields=insecure,
            environment=settings.environment,
        )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger, optionally bound to a name."""

    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()
