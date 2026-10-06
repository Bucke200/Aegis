"""FastAPI application factory and the ``aegis-api`` entrypoint."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aegis import __version__
from aegis.api.routers.vips import router as vips_router
from aegis.api.services.vips import DuplicateVipConfigError, VipNotFoundError
from aegis.common.config import get_settings
from aegis.common.fingerprints import InvalidFingerprintError
from aegis.common.health import router as health_router
from aegis.common.images import InvalidImageError
from aegis.common.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI application."""

    settings = get_settings()
    configure_logging()
    app = FastAPI(title="Aegis", version=__version__)
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(vips_router)

    @app.exception_handler(VipNotFoundError)
    async def _vip_not_found(request: Request, exc: VipNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DuplicateVipConfigError)
    async def _vip_conflict(request: Request, exc: DuplicateVipConfigError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

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
