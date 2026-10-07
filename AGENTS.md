# AGENTS.md

Guidance for coding agents working in this repository.

## Current phase

The active plan and handoff is `docs/phase1-plan.md`. Read it before starting
work; it carries the Phase 1 decision register, workstreams, and the WSL2 /
RTX 3050 setup. The authoritative task list is `docs/tasks.md`.

## Environment

- The project runs inside WSL2 (Ubuntu 22.04) on the dev machine; repo lives at
  `~/projects/Aegis`. Ollama runs in the same distro (`localhost:11434`).
- Python 3.12 managed by `uv`; Node 22 + npm for the dashboard.
- Docker via Docker Desktop WSL integration (`docker compose`).

## Commands

```bash
uv sync                 # install core + dev dependencies
make lint               # ruff check, ruff format --check, mypy aegis
make test               # pytest (Postgres/RabbitMQ tests skip without env)
make up / make down     # local stack (Postgres, RabbitMQ, MinIO, api, workers, frontend)
make migrate            # Alembic migrations
make eval / make eval-gate
make frontend-install / frontend-test / frontend-build
make e2e                # Playwright (API must be running)
```

Frontend lives in `frontend/` (Vite + React + TypeScript, Vitest, Playwright);
use `npm` from that directory.

## Conventions

- ruff: line length 120, rules `E,F,W,I,UP,B,SIM,C4,PT`; mypy strict on `aegis`.
- Tests in `tests/`; database tests use the `DB_REQUIRED` skip pattern and
  `AEGIS_TEST_DATABASE_URL`; RabbitMQ tests use `AEGIS_TEST_RABBITMQ_URL`.
- Do not add comments unless asked. Follow existing patterns in neighboring files.
- Never commit secrets or `.env`; never commit real personal data or real
  threat text (the golden reality set stays local-only).
- Do not commit unless the user explicitly asks.

## Key layout

- `aegis/common` - config, db, queue base classes, storage, schemas
- `aegis/collectors` - replay, synthetic generator
- `aegis/pipeline` - normalizer, analysis worker, media worker, scoring, incidents, outbox
- `aegis/detectors` - mentions, text, intent, persistence, toxicity
- `aegis/evidence`, `aegis/alerting` - later phases
- `aegis/api` - FastAPI app, services, routers, admin CLI
- `aegis/eval` - golden-set harness, report, gate
- `frontend/` - dashboard SPA
- `migrations/`, `deploy/`, `data/golden/`, `reports/eval/`, `docs/`
