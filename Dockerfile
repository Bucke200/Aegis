# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

FROM base AS deps-api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups

FROM base AS deps-analysis
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group collectors --group analysis

FROM base AS deps-media
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group media

FROM base AS deps-capture
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group capture

FROM base AS api
COPY --from=deps-api /app/.venv /app/.venv
COPY aegis ./aegis
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups
RUN useradd --create-home --uid 1000 aegis \
    && chown -R aegis:aegis /app
USER aegis
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
CMD ["aegis-api"]

FROM base AS analysis
COPY --from=deps-analysis /app/.venv /app/.venv
COPY aegis ./aegis
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --group collectors --group analysis
RUN useradd --create-home --uid 1000 aegis \
    && chown -R aegis:aegis /app
USER aegis
CMD ["aegis-worker"]

FROM base AS media
COPY --from=deps-media /app/.venv /app/.venv
COPY aegis ./aegis
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --group media
RUN useradd --create-home --uid 1000 aegis \
    && chown -R aegis:aegis /app
USER aegis
CMD ["aegis-media-worker"]

FROM base AS capture
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
COPY --from=deps-capture /app/.venv /app/.venv
COPY aegis ./aegis
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --group capture
RUN playwright install --with-deps chromium
RUN useradd --create-home --uid 1000 aegis \
    && chown -R aegis:aegis /app \
    && chmod -R a+rX /opt/ms-playwright
USER aegis
CMD ["aegis-capture"]
