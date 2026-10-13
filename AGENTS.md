# AGENTS.md

Guidance for coding agents working in this repository.

## Current phase

The active plan is `docs/orchestration-plan.md`. Read sections 2-4 and your own
work-package section before starting work; it sequences the remaining Phase 1
closure-to-MVP work, carries the decision register, and defines the branch,
commit, merge, and review rules for delegated agents. The authoritative task
list is `docs/tasks.md`; `docs/phase1-plan.md` stays the Phase 1 handoff and
`docs/design.md` / `docs/requirements.md` stay authoritative for behaviour.

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
make data               # clone/update the private Aegis-data checkout (golden set, caches)
make eval / make eval-gate
make eval-smoke         # evaluation on the public smoke set
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
  threat text (golden sets, caches, and text-bearing reports live in the private
  `Aegis-data` repository, cloned to gitignored `data/private/` by `make data`).

## Commit and merge policy

Accepted at G-01 (2026-10-13); the full policy is section 3.4 of
`docs/orchestration-plan.md`.

- Agents dispatched by the orchestrator may commit to their work-package
  branch, push it, and open a PR.
- Agents never push to `master`, never force-push a branch someone else owns,
  never rewrite history, and never merge their own PR.
- Merges to `master` need a green CI run, an independent review (section 3.7),
  and the owner's approval for any work package tagged `[HUMAN]` or touching
  auth, evidence integrity, masking, or migrations. Other work packages may be
  merged by the orchestrator.

## Environment tags

Every work package lists the environment it needs (section 3.9 of
`docs/orchestration-plan.md`):

| Tag | Meaning |
|---|---|
| `[PY]` | Pure Python; runs in any sandbox with `uv sync` |
| `[STACK]` | Needs Postgres, RabbitMQ, and MinIO (Compose stack or CI services) |
| `[BROWSER]` | Needs Playwright Chromium (`uv sync --group capture`, `playwright install chromium`) |
| `[GPU]` | Needs the owner's RTX 3050 + Ollama in WSL2 |
| `[PRIV]` | Needs the private `Aegis-data` checkout |
| `[EXT]` | Needs real third-party credentials (Slack, SMTP, Telegram, GitHub) |
| `[HUMAN]` | Needs an owner decision, review, or manual step before or during the WP |

## Shared files

Work packages run in parallel, so read section 3.5 of
`docs/orchestration-plan.md` before touching `migrations/versions/`,
`aegis/common/models/*.py` or `enums.py`, `aegis/common/config.py` or
`.env.example`, `outbox.py` or `topology.py`, `docker-compose.yml`, the
`Makefile`, `pyproject.toml` or `uv.lock`, or `docs/tasks.md`. In short: one
migration per work package with `down_revision` reset to the head at merge time
(`tests/test_aegis_migration_heads.py` enforces a single head), append-only
changes elsewhere, and `docs/tasks.md` is restructured only by WP-00.

## Key layout

- `aegis/common` - config, db, queue base classes, storage, schemas
- `aegis/collectors` - replay, synthetic generator
- `aegis/pipeline` - normalizer, analysis worker, media worker, scoring, incidents, outbox
- `aegis/detectors` - mentions, text, intent, persistence, toxicity
- `aegis/evidence`, `aegis/alerting` - later phases
- `aegis/api` - FastAPI app, services, routers, admin CLI
- `aegis/eval` - golden-set harness, report, gate
- `frontend/` - dashboard SPA
- `migrations/`, `deploy/`, `data/smoke/`, `data/private/` (Aegis-data checkout), `docs/`
