# Implementation Plan

Ordering principle: build a thin end-to-end slice first. The slice is replay data flowing through normalization, mention resolution, text detection, scoring, incidents, a live dashboard, and alerts. Sources and detectors are widened after that. Every task ships with its own tests; the "Done when" line is the acceptance check for the task.

**MVP = Phases 0–3.** Phase 1 (the vertical slice) is an internal milestone, not a release. The MVP release happens after task 21. Everything under "Post-MVP Backlog" is out of scope for it.

---

## Phase 0: Foundations

- [ ] 1. Project skeleton and developer environment
  - Apply the migration stance from the design: tag `legacy-v0` and branch `legacy/v0`, then delete the legacy packages, their tests, `main.py`, `start.py`, `scripts/`, `.flake8`, and `.env.template` from `master`
  - Create the modular-monolith package layout (`aegis/common`, `collectors`, `pipeline`, `detectors`, `evidence`, `alerting`, `api`, `eval`), plus `frontend/`, `migrations/`, `deploy/`, `docs/`, `data/golden/`, `reports/eval/`
  - Retarget `pyproject.toml` and `uv.lock`: `package = true` with a hatchling backend and `[project.scripts]` entrypoints (`aegis-api`, `aegis-normalizer`, `aegis-worker`, `aegis-media-worker`, `aegis-capture`, `aegis-admin`, `aegis-eval`); core dependencies only, with optional dependency groups (`collectors`, `analysis`, `media`, `capture`, `dev`) added by the tasks that need them. Declare compatible ranges, not exact pins, and use `uv sync --frozen` everywhere.
  - Write the `Dockerfile` on `python:3.12-slim` with four role targets (`api`, `analysis`, `media`, `capture`) and retarget `.dockerignore`, `Makefile`, `README.md`, `.env.example`, and pytest config to `aegis/`
  - Write `docker-compose.yml` at the repository root with Postgres 16 + pgvector (`pgvector/pgvector:pg16`), RabbitMQ, MinIO, `api`, and `worker` services, plus `capture` and `clamav` behind a compose profile; the frontend service is added in task 9.4
  - Add a root `alembic.ini` pointing at `migrations/`; the first migration enables the `vector` and `pg_trgm` extensions
  - Load configuration with pydantic-settings; commit `.env.example`; keep secrets out of the repository
  - Pin Python 3.12: `requires-python = ">=3.12,<3.13"` in `pyproject.toml`, `python:3.12-slim` images, and the same version in CI
  - Set up structured logging (structlog JSON) and `/health` endpoints from day one
  - Set up CI: ruff, mypy, pytest, and pip-audit; include a smoke test so the suite is never empty. Retarget `cd.yml` to build the four role targets and run only after CI is green. The frontend checks and the eval gate are added when tasks 9.4 and 18.2 land.
  - Done when: `docker compose up` brings every service up healthy and CI passes on the skeleton
  - _Requirements: 19.3, 19.4_

- [ ] 2. Data model and storage
- [ ] 2.1 Create database schema and migrations
  - Implement every table in the design data model (VIPs and reference data, accounts/items/media, connector cursors and source health, detections/incidents/events/notes, campaigns/edges, evidence/custody, alerts, labels/suppressions, users/scopes, audit log, outbox, scoring configs, saved searches, LLM budget usage)
  - Write Alembic migrations that first run `CREATE EXTENSION IF NOT EXISTS vector, pg_trgm`, then create UUID primary keys, the composite and UUID keys listed under "Keys" in the design, and unique and search indexes (dedup key, GIN tsvector, trigram, HNSW vectors)
  - Make `audit_log` insert-only at the database grant level
  - Implement incident subjects (`item` and `account`) with their check constraints and partial unique indexes, `incident_items`, `account_vip_scores`, detection scope constraints, `detections.input_variant` with its `(item_id, detector, model_version, input_variant)` unique index, the `custody_log` target check constraint, `incidents.merged_into_id` (self-FK, only allowed on item incidents pointing at an account incident, enforced by a check plus trigger), `incidents.below_threshold`, `incidents.legal_hold` and `items.legal_hold`, `campaign_members.member_type` with its check constraint and unique indexes, `vips.scoring_config_version` (FK to `scoring_configs.version`), the `incidents.threat_types` taxonomy values, and the `rescore`/`item_attached`/`merged_into`/`campaign_linked` event types, all as described in the design
  - Tests: migration up/down; constraint tests (dedup uniqueness, one item incident per item, one open account incident per (account, VIP), detection scope rules and the input-variant uniqueness, the `merged_into_id` item-to-account rule including the trigger, `below_threshold` semantics, the `custody_log` exactly-one-target rule, and `campaign_members` exactly-one-member rule)
  - Done when: migrations apply cleanly on an empty database and the constraint tests pass
  - _Requirements: 1.1, 1.2, 3.3, 6.8, 10.6, 13.2, 15.2, 17.3_

- [ ] 2.2 Define common item schema v1
  - Write Pydantic models for item, author, media, relations, and engagement; export JSON Schema; implement version handling (current and previous major version)
  - Build fixture files per planned source for contract tests
  - Tests: valid/invalid fixtures; round-trip serialization
  - Done when: every fixture validates and invalid fixtures produce readable errors
  - _Requirements: 2.8, 3.1, 3.2_

- [ ] 2.3 Configure object storage
  - Write a MinIO client wrapper that uploads with a computed SHA-256 and handles download and presigned URLs
  - Configure the evidence bucket with versioning and object lock in governance mode (configurable retention), the media bucket separately, and a dedicated retention role that can bypass the lock before expiry with separate credentials; every bypass writes to `audit_log`
  - Tests: upload/download, hash correctness, a normal credential cannot delete a locked object or overwrite a version, and a bypass through the retention role succeeds and is audited
  - Done when: an evidence object cannot be overwritten or deleted inside its retention period except through the audited retention role
  - _Requirements: 13.3_

- [ ] 3. Messaging backbone
- [ ] 3.1 Set up RabbitMQ topology and worker base classes
  - Declare quorum queues `items.raw`, `items.normalized`, `media.analyze`, `media.analyzed`, `evidence.capture`, `analysis.account_embedded`; the `events.incidents` and `events.accounts` topic exchanges and the `events.config` fanout exchange (per-instance exclusive queues for cache invalidation plus the shared durable `config.recompute` queue); delayed-retry queues; a DLQ per queue; priority on `items.normalized` with `x-max-priority: 2`
  - Implement producer (publisher confirms) and consumer (ack after DB commit, bounded retries with backoff, then DLQ) base classes
  - Build a DLQ inspection and re-drive CLI
  - Tests: poison message lands in DLQ after N retries; messages survive a broker restart
  - Done when: killing a worker mid-batch loses no items and creates no duplicates
  - _Requirements: 3.2, 19.3_

- [ ] 3.2 Build the transactional outbox and incident events
  - Write the outbox row in the same transaction as incident and VIP-configuration changes; implement a publisher that routes each committed row by `event_type` to `events.incidents` or `events.config` and marks rows published
  - Tests: a rolled-back transaction publishes nothing; a publisher crash causes no event loss (at-least-once delivery, idempotent consumers)
  - Done when: every committed incident change produces at least one consumable event, and consumers deduplicate by event ID so each change takes effect exactly once
  - _Requirements: 11.1, 14.1_

- [ ] 4. Test data and evaluation harness (build early; everything downstream depends on it)
- [ ] 4.1 Build the replay source and synthetic generator
  - Replay JSONL into `items.raw` at real or accelerated speed, preserving relative timing
  - Generate synthetic data: coordinated campaigns (N accounts, shared text with variations), homoglyph impersonators, leaks containing fake PII, Hinglish threats, and benign criticism
  - Done when: the generator produces a reproducible dataset (seeded) and replay drives the pipeline at a configurable rate
  - _Requirements: 2.2, 19.1_

- [ ] 4.2 Build the evaluation harness and synthetic golden set
  - Build the eval CLI in `aegis/eval`: `python -m aegis.eval run --golden data/golden/ --out reports/eval/` writes a per-detector, per-language report (JSON and Markdown), and `python -m aegis.eval gate --baseline reports/eval/baseline.json --tolerance 0.02` exits non-zero on a regression; add `make eval` and `make eval-gate` as wrappers
  - Seed `data/golden/` with a small reproducible synthetic set so the CLI and gate are exercised before real detectors exist; commit the first report as `reports/eval/baseline.json`
  - Done when: `make eval` produces a report from the synthetic set and `make eval-gate` fails on a seeded regression and passes otherwise
  - _Requirements: 16.2_

- [ ] 4.3 Build the labelled golden set (starts now; must complete before task 7.2 tunes the calibrator)
  - Write annotation guidelines covering intent classes, severity examples, and edge cases (satire, quotes, news reporting of threats); name the labellers and their weekly capacity
  - Label an initial set: 300+ items per threat class per language across English, Hindi, and Hinglish (six canonical intent classes, up to ~5,400 items) plus synthetic impersonation and leak sets
  - Have a second reviewer check each labelled item before it enters the set
  - Done when: `make eval` reports per-detector, per-language precision and recall from the reviewed set, and the set is complete enough to fit the isotonic calibrator (task 7.2) and to gate CI (task 18.2)
  - _Requirements: 16.2, 16.3_

---

## Phase 1: Vertical slice (internal milestone)

- [ ] 5. VIP management
- [ ] 5.1 Implement VIP CRUD and configuration
  - Build an API and service for VIPs, aliases (name/nickname/transliteration/handle/hashtag, with an ambiguity flag), context keywords, official accounts with verification evidence and profile data (display name, bio, avatar; refreshed daily where the source allows, otherwise entered by an Admin), sensitivity, and the monitoring on/off switch
  - Pausing monitoring stops new incidents within 5 minutes (config cache TTL); all changes are written to the audit log
  - Tests: CRUD, pause behavior, audit entries
  - Done when: a VIP can be fully configured over the API and every change appears in the audit log
  - _Requirements: 1.1, 1.2, 1.5, 1.6_

- [ ] 5.2 Implement reference media upload
  - Upload reference images and compute pHash/dHash; embeddings are added once 14.2 lands (reuse that module)
  - Done when: uploaded references have stored hashes and are queryable per VIP
  - _Requirements: 1.3_

- [ ] 5.3 Implement sensitive-data fingerprint registration
  - Normalize phones (E.164), emails, and address tokens; store salted hashes only, with salt rotation support
  - Tests: plaintext never reaches the database or logs (assert on captured logs)
  - Done when: registered values can be matched but not recovered
  - _Requirements: 1.4_

- [ ] 6. Normalization, deduplication, and mention resolution
- [ ] 6.1 Build the normalizer worker
  - Validate against the schema (invalid items go to the DLQ); compute the dedup key; upsert account and item; keep the raw payload; track edits and deletions in `item_versions`
  - Detect language and script with `lingua-language-detector`, including romanized-Hindi detection (fastText is not used: it has no Python 3.12 wheels)
  - On engagement updates, append to `item_engagement_snapshots`, keep `items.engagement` as the latest value, and trigger a re-score when reach reaches 10 × max(`scored_reach`, 10)
  - Tests: duplicate items update engagement only and append a snapshot; an edit creates a version row
  - Done when: replaying the same dataset twice creates no new items or incidents
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 6.2 Build VIP mention resolution and the media fork
  - Build an Aho-Corasick automaton from aliases; match original, confusables-normalized, and transliterated text (IndicXlit); match handles and hashtags
  - Apply context-keyword disambiguation for ambiguous aliases; record match confidence per the design's match-confidence table; support multiple VIPs per item
  - Fork **every** item that carries media to `media.analyze`, whether or not the item already has a text VIP link, and consume `media.analyzed` in the analysis worker to run text detection on OCR output and re-score the item
  - Tests: Hinglish and Devanagari variants, homoglyph-obfuscated names, common-name collisions; an item with a VIP-referencing image but no VIP text mention reaches the media worker and gains a `match_source = media` VIP link
  - Done when: mention recall and precision on the golden set meet the agreed targets, and the media fork is exercised end-to-end
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 7. Text threat detection cascade
- [ ] 7.1 Implement Stage 1: lexicons and multilingual toxicity
  - Curate versioned threat/abuse/specificity lexicons for English, Hindi, and Hinglish; integrate the multilingual toxicity model into the analysis image (weights baked or cached per the design); apply the stage-1 threshold to skip later stages
  - Record detector name, model version, `input_variant`, score, and spans on every detection
  - _Requirements: 5.2, 5.3, 5.5_

- [ ] 7.2 Implement Stage 2: LLM threat-intent classifier (depends on the reviewed golden set from 4.3)
  - Build the structured-output prompt and JSON schema (intent using the six canonical labels, solicitation, target, specificity, confidence, rationale, spans) with schema validation and retry on malformed output
  - Run it on every VIP-linked item that passes Stage 1 (no uncertainty-band gating at MVP)
  - Request per-class `intent_probs`; compute `threat_prob` (harassment + violent_threat + incitement + doxxing) and calibrate it with an isotonic calibrator fitted on the reviewed golden set; store the label and the calibrated `threat_prob` as the detection score, and refit the calibrator whenever the prompt or model changes
  - Enforce the daily token budget through the shared `llm_budget_usage` table so all worker instances see one total; fall back to Stage 1 scores and set `detections.details.degraded = true` when the budget is exhausted or the provider fails
  - Done when: intent-classification precision and recall on the golden set meet targets, and criticism-only items never score above low
  - _Requirements: 5.1, 5.4, 5.5, 5.6_

- [ ] 8. Scoring and incident creation
- [ ] 8.1 Build the scoring engine
  - Implement noisy-OR combination, reach and VIP multipliers, half-open severity bands (`[0.30, 0.55)`, `[0.55, 0.75)`, `[0.75, 0.90)`, `≥ 0.90`), critical overrides, the threat-class-based criticism cap (toxicity alone never lifts it), and suppression-rule checks
  - Seed `scoring_config` v1 with the detector reliability weights from the design and a default capture severity of medium
  - Score each item once per linked VIP (VIP-scoped detections plus null-VIP detections, with `mention_mult` from match confidence) and take the max; apply the criticism clamp to the score (`min(risk, 0.54)`), not only the severity
  - Consume one detection per `(item_id, detector, model_version, input_variant)`, relying on the unique index from 2.1 so a detector re-run after OCR never double-counts
  - Implement re-scoring: triggered by the reach rule from 6.1 now, by `media.analyzed` (media analysis complete) once 14.3 lands, by campaign membership once 16.3 lands, and by item attachment once 13.4 lands; never change a severity marked `severity_manual`; write a `rescore` incident event with the trigger and old/new values, and update `scored_reach`
  - Version the scoring config; generate the explanation from a template
  - Tests: table-driven cases for each band including the inclusive lower and exclusive upper bounds, each override, the clamp (a high-confidence criticism item with high toxicity stays at ≤ 0.54), a media-completion re-score, and re-scoring with and without a manual severity; an ambiguous-mention item scoring lower than an exact-mention one
  - _Requirements: 5.6, 10.1, 10.2, 10.3, 10.5, 10.6, 10.7_

- [ ] 8.2 Build the incident builder (item incidents)
  - Create one item incident per item grouping all item-scoped detections and inserting an `incident_vips` row for every VIP with risk ≥ 0.30; make creation idempotent; write the outbox event in the same transaction; enqueue evidence capture above the capture threshold
  - Call the scorer as an in-process library from the analysis and media workers; the incident and its outbox row are written in the calling worker's transaction
  - Account incidents are built in 13.4; the schema from 2.1 already supports them
  - Done when: replaying the synthetic text dataset yields the expected item incidents and severities in Postgres
  - _Requirements: 10.4, 13.1_

- [ ] 9. Backend API and dashboard (completes the vertical slice)
- [ ] 9.1 Build API foundations and access control
  - Set up FastAPI with JWT access tokens and rotating refresh tokens, Argon2id hashing, and TOTP MFA for admins
  - Enforce RBAC (Admin/Lead/Analyst/Viewer) with a per-VIP scope dependency applied to every query; add audit middleware and an in-process per-user rate limiter (single API instance at MVP)
  - Implement the per-VIP `can_reveal_sensitive` permission: Admin-only grant and revoke, never assignable to Viewers, audited
  - User CRUD, scope assignment, and the admin bootstrap CLI are built in 9.5
  - Tests: an analyst cannot read incidents for an unassigned VIP through any endpoint; an unauthenticated request is rejected on every route
  - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [ ] 9.2 Build incident endpoints
  - List with structured filters (AND across filters, OR within a filter), keyset pagination, and sort by time or severity
  - Detail endpoint returning detections, account, campaign, history, notes, and evidence links
  - Status transitions following the workflow table in the design (including Lead-only reopen) with reasons and history; resolution outcome required; notes; assignment with notification; bulk actions
  - _Requirements: 11.3, 12.1, 12.3, 15.1, 15.2, 15.3, 15.4, 15.5, 15.7_

- [ ] 9.3 Build the WebSocket gateway
  - Consume `events.incidents` and push to connections filtered by VIP scope; handle reconnect and resync (client refetches since its last-seen event)
  - Done when: a new incident appears on a connected dashboard within 10 seconds, and never on a dashboard outside the VIP's scope
  - _Requirements: 11.1_

- [ ] 9.4 Build the dashboard frontend
  - Set up React + TypeScript + Vite, React Router, TanStack Query, and Tailwind
  - Build the login flow (with MFA), a live incident feed with filter sidebar, incident cards with all required fields, and an incident detail view (detections with highlighted spans, account panel, history, notes, status/assign/resolve controls)
  - Build VIP admin screens; make the layout responsive at tablet and desktop widths
  - Tests: Vitest component tests; a Playwright end-to-end test of login → live incident → assign → note → resolve
  - Done when: the replayed dataset produces live incidents an analyst can triage end-to-end
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.6, 15.1, 15.3, 15.4_

- [ ] 9.5 Build user provisioning and the admin bootstrap
  - Implement `/auth` (login, refresh, logout, MFA enrol and verify) and the Admin-only `/users` endpoints for user CRUD, VIP-scope assignment, and `can_reveal_sensitive` grant/revoke; every change is audited
  - Provide an `aegis-admin` CLI to create the first admin (and reset credentials) so a fresh deployment is never locked out
  - Tests: a fresh database can bootstrap an admin and log in; a Lead cannot grant reveal permission; a Viewer can never hold it
  - Done when: an Admin can provision a user, scope them to VIPs, and grant or revoke reveal permission over the API
  - _Requirements: 17.1, 17.2, 17.3_

- [ ] 10. Evidence capture
- [ ] 10.1 Build the sandboxed capture service
  - Add the `capture` Compose service (the `capture` image target) plus the egress proxy, both behind a Compose profile until this task lands
  - Run Playwright (Python) in an isolated container with a fresh context per capture, a timeout, and an egress proxy that blocks private and metadata ranges
  - Capture raw payload, full-page screenshot, HTML, original media, and an account snapshot for item incidents; build the account-incident capture path now (profile page screenshot and HTML, avatar, account snapshot at creation, then each attached item as it arrives), exercised end-to-end once 13.4 lands; retry with backoff; record final failures on the incident
  - _Requirements: 13.1, 13.6_

- [ ] 10.2 Build manifests, custody log, and export
  - Hash every artifact and write a versioned manifest whose file content includes `version` and `prev_manifest_sha256`; each later capture for the same incident writes a new version chained to the previous one; store manifest hashes in Postgres; log every view, download, and export to the custody log (exactly one of artifact or manifest per row)
  - Export a ZIP containing a PDF summary, artifacts, every manifest version, and `VERIFY.md` explaining how to check artifact hashes and walk the manifest chain
  - Tests: tampering with any exported artifact, or with any earlier manifest version, fails verification
  - _Requirements: 13.2, 13.3, 13.4, 13.5_

- [ ] 10.3 Implement source-removed checks
  - Re-fetch high-or-above incidents at 1 hour, 24 hours, and 7 days; mark them `source_removed`; keep the evidence accessible
  - _Requirements: 13.7_

- [ ] 11. Alerting (email and Slack)
- [ ] 11.1 Build the alert rules engine
  - Consume incident events and evaluate per-VIP and per-user rules (minimum severity, channels, quiet hours that never suppress critical)
  - Group related incidents within the grouping window; produce digests for digest-only severities
  - Ensure alerts never include unmasked sensitive values
  - _Requirements: 14.3, 14.4, 14.6_

- [ ] 11.2 Build delivery channels and tracking
  - Implement SMTP email and a Slack app with an Acknowledge button that calls `POST /alerts/{id}/acknowledge`; track delivery state; retry with backoff; escalate unacknowledged critical alerts to the secondary recipient
  - Done when: a critical incident from replay produces a Slack alert within 2 minutes of `collected_at` (p95 measured under load in task 20.3)
  - _Requirements: 14.1, 14.2, 14.5_

- [ ] 12. First real sources
- [ ] 12.1 Build manual URL submission
  - Implement SSRF-safe fetching (DNS resolution check, redirect re-check, scheme allowlist); use platform extractors where possible; otherwise fall back to screenshot capture plus analyst-entered text
  - Route submissions through the normal pipeline at high priority
  - Accept profile URLs as well as post URLs; a profile submission creates or updates the account (`discovered_via = manual_profile`) and queues it for impersonation scoring
  - Tests: SSRF suite (private IPs, DNS rebinding, redirects to internal hosts)
  - _Requirements: 2.5, 2.6_

- [ ] 12.2 Build the Telegram collector
  - Implement a Telethon (MTProto) client on a dedicated monitoring account, with a configurable channel list and cursors stored in Postgres
  - Honor FloodWait; report staleness and auth failures to source health
  - _Requirements: 2.1, 2.2, 2.4, 2.7_

- [ ] 12.3 Build the GitHub code search collector
  - Use the authenticated REST code search API, with queries generated from VIP keywords and org domains; implement a rate-limit-aware scheduler
  - Written fresh under `aegis/collectors/github.py`; the legacy BeautifulSoup scraper lives only on `legacy/v0`
  - _Requirements: 2.1, 2.2, 2.4, 2.7_

---

## Phase 2: Broaden detection

- [ ] 13. Impersonation detection (depends on 14.1 for the media worker and 14.2 for the shared pHash and OpenCLIP embedding code; build both before 13.2)
- [ ] 13.1 Implement handle and name normalization and similarity
  - Apply NFKC, a UTS #39 confusables skeleton, lowercasing, separator stripping, a leetspeak map, and filler-token stripping
  - Compute Jaro-Winkler and normalized Levenshtein similarity
  - Tests: a synthetic homoglyph and look-alike set (e.g., Cyrillic/Latin swaps, `_official` suffixes)
  - _Requirements: 6.2_

- [ ] 13.2 Build the two-phase profile scorer
  - Generate candidates (authors of VIP-linked items, plus accounts known only from their profile whose handle or display name contains an alias token)
  - Pre-screen in the analysis worker (handle, display name, metadata); record state in `account_vip_scores`; enqueue an `account_profile` job on `media.analyze` when the pre-screen is ≥ 0.35 or an alias token matches
  - Handle `account_profile` jobs in the media worker (avatar pHash and OpenCLIP embedding, multilingual bio embedding), for suspect and official accounts alike; publish `account.embedded`
  - On `account.embedded` (consumed from `analysis.account_embedded`), complete scoring (adding avatar and bio components); after failure or a 10-minute timeout, score with those components at 0 and mark `partial`; rescore on profile change
  - Invalidate on VIP configuration change using `vips.config_version`, consuming `config.recompute` (one consumer per event, a per-VIP Postgres advisory lock, idempotent on `vip_config_version`, plus an hourly sweeper for VIPs left behind): re-evaluate against the new threshold for threshold-only changes; mark rows `stale` and batch-recompute from stored embeddings for alias, official-account, or reference-media changes
  - Tests: two workers receiving the same config event run the batch once; a lost event is picked up by the sweeper
  - Apply the parody/fan discount and per-VIP thresholds; exclude official accounts; emit an account-scoped `impersonation` detection with component scores as evidence
  - Build the solicitation detector (Stage 2 `solicitation` field plus patterns: UPI handle suffix list, crypto wallets, bank account plus IFSC, OTP/password lexicon, non-official domains); store its detections inert on every VIP-linked item
  - Done when: impersonation precision and recall on the synthetic and golden sets meet targets, and the analysis worker's throughput is unchanged with impersonation enabled
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.7, 1.2_

- [ ] 13.3 Generate the report package
  - Produce a PDF plus artifacts showing the official and suspect profiles side by side, available after an analyst confirms
  - _Requirements: 6.6_

- [ ] 13.4 Build account incidents end-to-end
  - Create or update one open account incident per (account, VIP) from `impersonation` detections, inserting its `incident_vips` row in the same transaction; attach the account's VIP-linked items from the last 30 days, then each later one, via `incident_items` with their `item_risk`
  - Reconcile items that already have their own incident, following the design's merge table: set `merged_into_id`, freeze scoring, hide from the default feed, carry the assignee, take `item_risk` from the item incident (0 if it was False Positive), write `merged_into` and `item_attached` events, and make merged incidents read-only apart from notes
  - Implement account-incident scoring (impersonation risk combined with the worst attached item's stored `item_risk`), the solicitation and violent-threat overrides, re-scoring on attachment, the Resolved → new linked incident rule, and the 90-day suppression rule on False Positive
  - Handle accounts that fall below a raised threshold: auto-resolve with the system outcome `below_threshold` only when the incident is untouched, not critical, and has no attached item at medium or above; otherwise keep it open and flag `below_threshold`
  - Make merged incidents consistent everywhere: exclude them from default search and add the "include merged" filter; push `{type: "merged", incident_id, merged_into_id}` over the WebSocket and have the client drop the card; move the campaign link to the account incident when it has none; resolve campaign members to live incidents in the campaign view and bulk actions
  - Render account incidents in the dashboard: suspect profile on the feed card; side-by-side profiles, component scores, and an attached-item timeline in the detail view; "impersonation check pending" on item incidents whose author is still being scored
  - Tests: an account incident whose score does not rise as more capped items attach but goes critical on a solicitation item; an item whose own incident was created before its author was flagged ends up merged, appears once in the default feed, and feeds only the account incident; a previously False-Positive item attaches with `item_risk` 0; a raised threshold auto-resolves an untouched low-risk account incident but only flags one an analyst is working on; a merged incident never reappears in search or on a connected dashboard
  - Done when: a synthetic impersonator posting several items (some processed before the account is flagged) yields exactly one live account incident, which becomes critical when one of its items contains a UPI ID
  - _Requirements: 6.8, 6.9, 6.10, 10.1, 10.3, 10.4, 10.7, 11.2, 11.4, 12.2, 13.1, 15.5, 15.7_

- [ ] 14. Media analysis
- [ ] 14.1 Build the media worker and safe download
  - Add the `clamav` Compose service; install `ffmpeg` in the `media` image; add the `models` volume and `make fetch-models` so OpenCLIP, PaddleOCR, and sentence-embedding weights are present at first use
  - Enforce size and type limits, MIME sniffing, ClamAV scanning over TCP, and SHA-256 dedup before storage
  - _Requirements: 7.1, 13.1_

- [ ] 14.2 Implement fingerprinting and matching
  - Compute pHash/dHash and OpenCLIP embeddings stored in pgvector (and backfill reference media from 5.2)
  - Match against reference media and prior media; a reference match writes an `item_vips` link (`match_source = media`), not a detection; track first-seen occurrences; emit `repurposed_media` detections showing the earliest occurrence
  - _Requirements: 1.3, 7.1, 7.2_

- [ ] 14.3 Implement OCR and video keyframes
  - Run PaddleOCR (English and Devanagari) into `items.ocr_text` and re-run text detection on it, writing detections with `input_variant = ocr_text`
  - Extract ffmpeg scene-change keyframes (capped per video) and analyze them as images
  - Publish `media.analyzed` when an item's media jobs finish so the analysis worker re-scores it (the trigger wired in 8.1)
  - _Requirements: 7.3, 7.4_

- [ ] 14.4 Integrate reverse image search
  - Integrate TinEye or Cloud Vision Web Detection behind a provider interface; run only for high-or-above incidents; enforce a daily quota; store results as detection details
  - _Requirements: 7.5_

- [ ] 15. Leak and PII detection
- [ ] 15.1 Build pattern detectors with validators
  - Detect Indian mobile numbers, emails, Aadhaar (with Verhoeff checksum), PAN, address heuristics, and secrets (gitleaks rule set)
  - _Requirements: 8.1_

- [ ] 15.2 Implement fingerprint matching and leak incidents
  - Normalize and hash detected values with active salts and compare them to VIP fingerprints; a match emits a `leak_fingerprint_match` detection that the scorer's override makes critical; non-matching PII near a VIP mention emits a `leak_pattern` detection scored normally
  - _Requirements: 8.2, 8.3_

- [ ] 15.3 Implement masking and reveal
  - Build the application-level encryption key service here (versioned keys, rotation), encrypt detected values with it, return masked values from the API and UI, restrict reveal to permitted roles, audit every reveal, and scrub values from logs and alerts
  - Tests: no raw value appears in any API response, alert payload, or log line; a rotated key can still decrypt older values
  - _Requirements: 8.4, 14.3_

- [ ] 16. Coordinated campaign detection
- [ ] 16.1 Implement near-duplicate clustering
  - Normalize and shingle text; use MinHash LSH (datasketch) at Jaccard 0.7; add media near-duplicate edges; take connected components over a sliding window
  - _Requirements: 9.1_

- [ ] 16.2 Implement volume anomaly detection
  - Use a per-VIP same-hour-of-week median/MAD baseline and robust z-score with a minimum count; route spikes to campaign candidate review
  - Until a VIP has 4 weeks of history, fall back to a global cross-VIP same-hour-of-week baseline and lower the confidence, per the design's cold-start rule
  - _Requirements: 9.3_

- [ ] 16.3 Assemble campaigns
  - Apply per-VIP N/W thresholds; exclude allowlisted accounts; compute the coordination score from account signals; record members, timeline, and `account_edges`; merge candidates into open campaigns on overlap
  - Emit a `campaign_member` detection for each item joining a confirmed campaign and trigger re-scoring
  - Done when: the synthetic campaigns are detected and organic news resharing in the golden set is not flagged
  - _Requirements: 9.2, 9.4, 9.5, 9.6, 10.7_

- [ ] 16.4 Build graph analysis and the campaign view
  - Run NetworkX Louvain communities and centrality; expose a campaign graph endpoint returning Cytoscape.js JSON
  - Build a campaign page with graph and timeline; support bulk triage of campaign incidents
  - _Requirements: 9.5, 15.7_

- [ ] 17. Search
- [ ] 17.1 Implement full-text search
  - Index text and OCR text with a `simple`-config tsvector; search account handles, display names, and bios via `accounts.tsv` plus trigram similarity, matching item incidents through `items.account_id` and account incidents through `incidents.account_id`; highlight with `ts_headline` for text fields and frontend substring highlighting for fuzzy handle matches; combine search with filters (account incidents have a null language)
  - _Requirements: 12.2, 12.3, 12.4_

- [ ] 17.2 Implement saved searches
  - Add the saved-search API and UI presets
  - _Requirements: 12.6_

- [ ] 17.3 Benchmark search
  - Generate one year of synthetic volume and measure p95 latency; open an Elasticsearch/OpenSearch migration task only if p95 exceeds 1 second
  - _Requirements: 12.5_

- [ ] 18. Feedback loop and quality gates
- [ ] 18.1 Capture labels and suppression rules
  - Turn False Positive marks and type/severity corrections into labels linked to every detection that fired (for account incidents, keyed by incident and account with a null item); support suppression and allowlist rules with expiry and audit entries
  - _Requirements: 16.1, 16.5_

- [ ] 18.2 Add the evaluation CI gate
  - Run `make eval-gate` (`python -m aegis.eval gate --baseline reports/eval/baseline.json`) on any change to detectors, models, lexicons, or scoring config; fail CI when precision or recall drops beyond tolerance; sample reviewed labels weekly and add them to the golden set after a second review
  - _Requirements: 16.2, 16.3_

- [ ] 18.3 Build quality and workflow metrics
  - Show detector false-positive rate over time, time to acknowledge, time to resolve, and outcome distribution per VIP and team, with per-analyst views restricted to leads
  - _Requirements: 15.6, 16.4_

---

## Phase 3: Hardening

- [ ] 19. Data protection and retention
- [ ] 19.1 Implement retention and offboarding jobs
  - Delete unlinked items after 30 days (cascading to their detections, `item_vips`, engagement snapshots, versions, labels, and campaign members; deleting a `media` row only with its last referencing item) and incidents/evidence after 1 year, skipping rows with `legal_hold`; delete accounts with no VIP link, no incident, and no refresh for 1 year; implement VIP offboarding deletion; make all periods configurable
  - Delete pre-expiry evidence only through the audited retention role from 2.3, so DPDP erasure and offboarding work while every bypass is logged
  - _Requirements: 18.1, 18.2, 18.4_

- [ ] 19.2 Implement encryption
  - Enable TLS between services; encrypt Postgres volumes; enable MinIO server-side encryption; wire in the application-level key service built in 15.3
  - _Requirements: 18.3_

- [ ] 19.3 Write data protection documentation
  - Write `docs/data-protection.md` covering purpose, lawful basis (DPDP Act, 2023), data categories, retention, LLM provider handling, and a per-source ToS review; disable any source whose terms prohibit automated collection
  - _Requirements: 2.5, 18.5_

- [ ] 20. Observability and operations
- [ ] 20.1 Set up metrics and dashboards
  - Add Prometheus metrics (ingest rate, queue depth, stage latency, end-to-end processing latency, detector errors, alert delivery, LLM tokens); build Grafana dashboards
  - _Requirements: 19.4_

- [ ] 20.2 Add operational alerts and source health
  - Alert on backlog, connector staleness, DLQ growth, disk usage, and LLM budget; show source health on the dashboard
  - _Requirements: 2.7, 11.5, 19.5_

- [ ] 20.3 Run load and latency tests
  - At the sustained design rate (10 items/s), assert the p95 processing-latency targets (60 seconds text-only, 5 minutes with media) and the critical-alert latency target (2 minutes or less); these targets are defined at the sustained rate, not at 2×
  - At 2× the sustained rate (20 items/s), assert no queue growth over 30 minutes and record how latency degrades; size the worker pools from the result
  - Size the media path for **every** media-bearing item (the all-media fork from 6.2), and record the measured media share; if the 10-minute drain target cannot be met, apply the design's fallback gate before launch
  - Replay the burst profile (50 items/s for 15 minutes) and assert all queues drain within 10 minutes after it ends; keep the design target of 35 items/s on the text path
  - _Requirements: 14.1, 19.1, 19.2_

- [ ] 20.4 Implement backup and restore
  - Automate Postgres backups and MinIO replication, write the restore runbook in `docs/`, and run a timed restore into a fresh environment
  - Done when: a documented, timed restore meets the agreed recovery-point and recovery-time objectives (Req 19.6)
  - _Requirements: 19.3, 19.6_

- [ ] 21. Security review
  - Run authorization tests across all endpoints (role boundaries and VIP scope), the SSRF suite, masked-value leakage tests, dependency scanning, and a secrets audit; fix findings before the MVP release
  - _Requirements: 13.6, 17.2, 8.4_

---

## Post-MVP Backlog (not scheduled)

- [ ] 22. Additional sources (each needs a connector, fixtures, contract tests, and a ToS review)
  - X API v2 connector (requires a paid tier)
  - Facebook Pages and Instagram Business owned-account comments and mentions, plus Instagram hashtag search
  - YouTube Data API comments connector
  - Discord bot for invited servers
  - Pastebin Scraping API (PRO account plus whitelisted IP)
  - _Requirements: 2.3_

- [ ] 23. Detection upgrades
  - Fine-tune a MuRIL/XLM-R threat-intent classifier on analyst plus LLM labels; keep the LLM only for the uncertainty band
  - Add synthetic-media detection as a labelled signal only
  - Add RFC 3161 trusted timestamps for evidence manifests
  - Support additional Indic languages
  - _Requirements: 5.4, 7.6, 13.2_

- [ ] 24. Platform upgrades (only when the documented triggers are hit)
  - SMS alert channel
  - OpenSearch/Elasticsearch for search
  - Neo4j for graph queries
  - OpenTelemetry tracing and Loki logs
  - Redis-backed rate limiting when the API runs more than one instance
  - Kubernetes deployment with HA and backups/disaster recovery
  - _Requirements: 14.2, 12.5, 19.4_
