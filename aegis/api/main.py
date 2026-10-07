"""FastAPI application factory and the ``aegis-api`` entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aegis import __version__
from aegis.api.middleware import AuditMiddleware, RateLimiter, RateLimitMiddleware
from aegis.api.routers.auth import router as auth_router
from aegis.api.routers.incidents import router as incidents_router
from aegis.api.routers.users import router as users_router
from aegis.api.routers.vips import router as vips_router
from aegis.api.services.incidents import (
    IncidentNotFoundError,
    InvalidTransitionError,
    MergeReadOnlyError,
    OutcomeRequiredError,
)
from aegis.api.services.users import (
    DuplicateUserError,
    RevealPermissionError,
    UserNotFoundError,
)
from aegis.api.services.vips import DuplicateVipConfigError, VipNotFoundError
from aegis.api.websocket import (
    ConnectionManager,
    websocket_consumer_lifespan,
)
from aegis.api.websocket import (
    router as websocket_router,
)
from aegis.common.config import get_settings
from aegis.common.fingerprints import InvalidFingerprintError
from aegis.common.health import router as health_router
from aegis.common.images import InvalidImageError
from aegis.common.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI application."""

    settings = get_settings()
    configure_logging()
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        consumer_enabled = bool(getattr(app.state, "event_consumer_enabled", False))
        async with websocket_consumer_lifespan(manager, consumer_enabled):
            yield

    app = FastAPI(title="Aegis", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.connection_manager = manager
    app.state.event_consumer_enabled = settings.event_consumer_enabled

    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(vips_router)
    app.include_router(incidents_router)
    app.include_router(websocket_router)

    @app.exception_handler(VipNotFoundError)
    async def _vip_not_found(request: Request, exc: VipNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UserNotFoundError)
    async def _user_not_found(request: Request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DuplicateVipConfigError)
    async def _vip_conflict(request: Request, exc: DuplicateVipConfigError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DuplicateUserError)
    async def _user_conflict(request: Request, exc: DuplicateUserError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(RevealPermissionError)
    async def _reveal_error(request: Request, exc: RevealPermissionError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(IncidentNotFoundError)
    async def _incident_not_found(request: Request, exc: IncidentNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(request: Request, exc: InvalidTransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(MergeReadOnlyError)
    async def _merge_read_only(request: Request, exc: MergeReadOnlyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(OutcomeRequiredError)
    async def _outcome_required(request: Request, exc: OutcomeRequiredError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InvalidImageError)
    async def _invalid_image(request: Request, exc: InvalidImageError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InvalidFingerprintError)
    async def _invalid_fingerprint(request: Request, exc: InvalidFingerprintError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return app


app = create_app()


def main() -> None:
    """Run the API server."""

    settings = get_settings()
    uvicorn.run(
        "aegis.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
