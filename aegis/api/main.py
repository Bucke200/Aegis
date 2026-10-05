"""FastAPI application factory and the ``aegis-api`` entrypoint."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from aegis import __version__
from aegis.common.config import get_settings
from aegis.common.health import router as health_router
from aegis.common.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI application."""

    settings = get_settings()
    configure_logging()
    app = FastAPI(title="Aegis", version=__version__)
    app.include_router(health_router)
    app.state.settings = settings
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
