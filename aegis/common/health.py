"""Health and readiness endpoints shared by every service."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from aegis import __version__
from aegis.common.db import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up."""

    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, str]:
    """Readiness: the process can reach its dependencies."""

    if check_database():
        return {"status": "ready"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "not_ready", "detail": "database unavailable"}
