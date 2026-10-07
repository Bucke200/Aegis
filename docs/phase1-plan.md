# Phase 1 Plan and Handoff

Status: living document. Last updated 2026-10-07 on branch `phase1-setup`.
Purpose: carry the Phase 1 decisions, workstreams, and machine setup across the
Windows-to-WSL migration. The authoritative task list remains `docs/tasks.md`.

## 1. Scope

Phase 1 is the vertical slice. Phase 1 closure means: the durability test passes,
the reviewed gate set exists, eval adapters run against it, and the identity
calibrator is wired. Calibrator fitting and the real-text reality set are
explicitly deferred until a real LLM provider is chosen.

## 2. Decision register

| ID | Decision | Choice |
|---|---|---|
| Q1 | Golden-set sourcing | `Q1-A` for the gate set only: AI-drafted synthetic candidates, 100% human-confirmed. Calibration gets a separate real-text reality set later. |
| Q2 | Second review | `Q2-A` with blind labelling: labels are assigned cold (generator's intended label hidden). Generator label and blind label are independent; agreement keeps the item. Disagreements, ambiguous items, and a 25% random sample go to a second (Hindi-fluent) reviewer. Cohen's kappa target >= 0.7. If no reviewer: relabel 25% after a week's gap and record it as a known weakness. |
| Q3 | Pilot | `Q3-A`: 180-item pilot (10 per class per language). Exit criteria: measured seconds per item, kappa >= 0.7, and a written rule for each hard boundary (criticism/harassment, harassment/violent_threat, incitement/violent_threat, quoted or reported threats). If guidelines change materially, relabel the pilot before counting it. |
| Q4 | Annotators | `Q4-D`: AI drafts, the main annotator confirms blind, plus one Hindi-fluent person for the review slice. Capacity estimate ~20 s/item: ~10 h per 1,800 items for the annotator, 3-4 h for the reviewer. Sessions capped at ~200 items. |
| Q5 | Real data | `Q5-A` for private data, plus public research datasets when calibration comes up (HASOC, TRAC, Jigsaw; check each licence and relabel into the six canonical classes). |
| Q6 | Dev provider | `Q6-A` with a local Ollama model and no fitting. Keep the identity calibrator; tag every detection `calibration: identity`. |
| Q7 | Durability test | `Q7-A`, starting now, plus a nightly CI run. Publish 1,000 confirmed messages, restart RabbitMQ mid-consume, assert exactly-once by dedup key. Add the worker-killed-mid-batch case (SIGKILL, not SIGTERM). |

### Two sets with different jobs (Q1/Q5)

- **Gate set** (committed under `data/golden/`): 1,800 synthetic, human-confirmed
  items, plus mechanically labelled synthetic impersonation and leak sets.
  Doxxing items use fake PII. Synthetic text is acceptable here because the gate
  only detects drift.
- **Reality set** (not committed): real text, ~300 items to start, used to fit
  the calibrator and report honest precision and recall. Sources: public research
  datasets now, analyst-labelled items later.

AI-written text is cleaner and more prototypical than real posts; a calibrator
fitted on it would be overconfident on real ones, however the labels were
confirmed. That is why the two sets are separate.

### Section C defaults (accepted, with additions)

1. Schema: `GoldenItem` gains `provenance`, `intended_label`, `blind_label`,
   `final_label`, `annotator`, `reviewer`, `reviewed_at`, `edge_case`,
   `generator_model`, `guideline_version`; existing smoke set stays loadable.
2. Layout: `data/golden/intent/{en,hi,hi-Latn}.jsonl`, `data/golden/impersonation/`,
   `data/golden/leaks/`; work products in gitignored `data/labelling/`.
3. Tooling: `python -m aegis.eval {generate,sheet,import,stats,sample,merge}`.
   `sheet` hides the intended label, shuffles rows, and writes UTF-8 with a BOM
   so Excel renders Devanagari. See `docs/annotation-guidelines.md` for the
   full workflow.
4. Metrics: per-class confusion matrix per language and binary threat/non-threat
   precision and recall (what the scorer consumes) are mandatory. The gate checks
   aggregates per detector per language only; per-class numbers are report-only,
   because a 100-item cell has roughly +/-8 noise.
5. Smoke set: keep `synthetic_v1.jsonl` for harness tests; golden v2 lands beside it.
6. Calibration artifact (when fitting): store model ID, prompt version, fit-set
   hash, and assumed class prior. Fall back to identity if the model or prompt
   version does not match. Reweight to a realistic prior when fitting; a balanced
   six-class set is about 67% threats, far above production prevalence, so the 0.5
   threshold would over-fire without reweighting.
7. Gate caching: run the LLM at temperature 0 and cache outputs by model digest,
   prompt version, and text hash. Toxicity outputs are cached the same way and
   produced on CPU.

## 3. The four workstreams

### Workstream 1 - Durability and exactly-once

Status: implemented on `phase1-durability`; validated by the Integration
workflow on pull requests touching queue code and nightly on `master`.

- `tests/test_aegis_durability.py`, gated by `AEGIS_INTEGRATION=1` (normal pytest skips).
  - Broker restart: publish 1,000 confirmed messages; the consumer writes to
    Postgres keyed by dedup key with `ON CONFLICT DO NOTHING`; `docker restart
    aegis_rabbitmq` mid-consume; assert 1,000 rows, no DLQ messages, consumer reconnected.
  - Worker killed mid-batch with `proc.kill()` (SIGKILL) -> restart -> items and
    incidents exactly once by dedup key.
- `make integration` target; compose Postgres + RabbitMQ only.
- `.github/workflows/nightly.yml`: schedule, dispatch, and path-filtered pull
  requests touching queue code; runs the integration suite, uploads service logs,
  tears the stack down. Not triggered on every push.
- Done when: both scenarios pass locally and nightly; task 3.1's durability
  Done-when is closed.

### Workstream 2 - Annotation infrastructure and blind pilot

Status: tooling implemented on `phase1-annotation` (guidelines, `GoldenItem` v2,
candidate generator, annotate CLI, agreement stats, merge validation, tests).
The 180-item pilot itself is a human labelling step and is pending.

- `docs/annotation-guidelines.md`: six classes, the four hard-boundary drafts to
  ratify in the pilot, satire/quote/news handling, doxxing fake-PII rule, blind
  protocol, capacity cap, review and adjudication process.
- `GoldenItem` v2 per section C1, including `blind_label` allowing `ambiguous`.
- `aegis/eval/candidates.py`: seeded generator, 6 classes x 3 languages,
  template banks, edge-case quotas, fake PII for doxxing.
- `python -m aegis.eval {generate,sheet,import,stats,sample,merge}` per
  section C3; `load_golden` reads only `data/golden/`.
- Pilot: 180 items, blind labels, second pass as designed, exit report in
  `reports/labelling/pilot.md` (produced by the annotator lead).
- Reword `docs/tasks.md` task 4.3 to describe this two-set, blind, kappa-gated
  process (no deviation log).

### Workstream 3 - Scale to 1,800 and commit the gate set

- Generate 1,800 balanced candidates; blind-label in <=200-item sessions.
- Reviewer takes disagreements, ambiguous items, and a 25% random sample;
  adjudicate to `final_label` or discard unusable items.
- Commit the gate set and the synthetic impersonation/leak sets. No real text in
  the repo.
- Secret scanning: leak-set fake credentials must match detector patterns but not
  real provider key formats; verify GitHub push protection locally before pushing,
  and consider making the repository private before threat-text sets go in.

### Workstream 4 - Adapters, Ollama dev provider, identity calibrator, baseline

Status: tooling implemented on `phase1-eval-adapters` (per-class metrics,
adapters, commits caches, cache/benchmark CLI, Ollama provider, identity
marker). Caches, model choice, and the new baseline wait for the pilot labels
and the WSL Ollama setup.

- Metrics per section C4: `EvalReport.per_class` carries a per-language
  confusion matrix; the gate still checks only the aggregate table.
- Detector adapters (`aegis/eval/adapters.py`): `text_lexicon` runs directly;
  `text_intent_llm` and `text_toxicity` read committed caches
  (`aegis/eval/caches.py`, section C7). A missing cache entry fails the run.
- Refresh and benchmark:
  `python -m aegis.eval cache --llm --toxicity --model aegis-intent` and
  `python -m aegis.eval benchmark --models llama3.2:3b,qwen2.5:3b,gemma3:4b`.
- Provider: `AEGIS_LLM_PROVIDER=ollama` works with an empty API key; keep
  `json_object` + Pydantic validation + one retry; fall back to the native
  `/api/chat` schema mode only if the invalid JSON rate is high. Detections
  carry `calibration: "identity"`.
- Model benchmark after the pilot: compare valid-JSON rate, threat/non-threat
  F1 per language, items per second, and `ollama ps` GPU share; switch only on
  evidence.
- Regenerate `reports/eval/baseline.json`; `make eval` / `make eval-gate`
  exercise it. Mark task 4.3 done; Phase 1 closes here.

## 4. RTX 3050 (4 GB) settings

- Model: start with `llama3.2:3b` (2.0 GB, comfortable; Hindi officially supported).
  `qwen2.5:3b` is a fallback but research-only licensed; `gemma3:4b` is tight.
- Pin the config in `deploy/ollama/Modelfile.aegis-intent` (committed):
  `FROM llama3.2:3b`, `PARAMETER num_ctx 2048`, `PARAMETER temperature 0`,
  `PARAMETER seed 42`; then `ollama create aegis-intent -f ...`.
- One model, one request at a time: `OLLAMA_NUM_PARALLEL=1`,
  `OLLAMA_MAX_LOADED_MODELS=1`; run cache refresh sequentially.
- Cache key uses the model digest from `/api/tags`, not the tag.
- Timing estimate: 2-4 s per item, so 1-2 h for the 1,800-item refresh; measure
  on the pilot.
- Phase 2 warning: OpenCLIP, PaddleOCR, and the bio-embedding model each fit in
  4 GB alone but not beside a loaded LLM. Run the media worker on CPU in dev or
  unload the LLM first.

## 5. Machine setup and migration runbook

Verified on the host (2026-10-07): RTX 3050 Laptop 4 GB, driver 617.14; WSL2 with
`Ubuntu-22.04` and `docker-desktop` distros; 15.4 GB RAM; Ollama installed
Windows-side but with zero models. Target: repo and all tooling inside WSL2 ext4.

Windows side (done):

- [x] Ignored-file audit; only `frontend/src/lib/format.ts` was wrongly ignored.
- [x] `.gitignore` anchored, `.gitattributes` added, `data/labelling/` ignored.
- [x] Branch `phase1-setup` with two commits (ignore fix, 9.4 work).
- [ ] Push branch and open a PR; let CI run; merge to master. (`gh` is not
      installed on Windows; open the PR in the browser or push master directly.)
- [ ] After the WSL smoke test passes, rename `C:\projects\Aegis` to
      `C:\projects\Aegis.old` and delete it a week later.

WSL2 side (pending):

1. `%UserProfile%\.wslconfig`: `memory=10GB`, `swap=4GB`; then `wsl --shutdown`.
2. Docker Desktop -> Settings -> Resources -> WSL integration -> `Ubuntu-22.04`.
3. Install toolchain: `git`, `make`/`build-essential`, `curl`, `gh`, `uv`
   (`uv python install 3.12`), Node 22 via nvm or NodeSource, `opencode` CLI.
4. Clone the remote into `~/projects/Aegis`; confirm `legacy/v0`, tag `legacy-v0`,
   and that `frontend/src/lib/format.ts` exists.
5. Git config: `core.autocrlf input`; credentials via `gh auth`.
6. Recreate `.venv` with `uv sync` and `frontend/node_modules` with `npm ci`.
   Hand-copy nothing today: no `.env`, `data/labelling/`, or `models/` exist on
   the Windows copy.
7. Create `.env` with dev LLM values: `AEGIS_LLM_PROVIDER=ollama`,
   `AEGIS_LLM_BASE_URL=http://localhost:11434/v1`, `AEGIS_LLM_MODEL=aegis-intent`,
   empty key.
8. Ollama: install inside Ubuntu (enable systemd in `/etc/wsl.conf` or run
   `ollama serve` manually); confirm `nvidia-smi` sees the 3050; pull `llama3.2:3b`;
   create `aegis-intent`; confirm `ollama ps` shows 100% GPU after one request.
9. Smoke test: `make up` -> `make migrate` -> `make test` -> `make integration`
   (needs Docker) -> frontend `npm ci && npm test && npm run build`; one real
   classification call through the app to `aegis-intent`; open the dashboard from
   the Windows browser.
10. Start the coding agent inside Ubuntu (`cd ~/projects/Aegis && opencode`) and
    log in to the model provider again; Windows credentials do not carry over.

Keep LLM-calling workers as local processes in dev so `localhost:11434` resolves;
inside a compose container `localhost` is the container itself and the URL must
be revisited.

Fallback: if the agent cannot run in WSL, test a read/write/edit through
`\\wsl.localhost\Ubuntu-22.04\home\<user>\projects\Aegis`; if that fails, fall
back to a Windows-resident repo with `UV_PROJECT_ENVIRONMENT=~/.venvs/aegis`.

## 6. Deferred and known weaknesses

- Reality set (~300 real items) and calibrator fitting wait for the real provider.
- A 3B model's self-reported probabilities are coarse: this baseline is a
  plumbing and drift check, not an accuracy claim; regenerate when the real
  provider is chosen.
- Licences: `qwen2.5:3b` is research-only; `llama3.2` and `gemma3` have community
  terms. Fine for dev benchmarking; production self-hosting needs review.
- `docs/data-protection.md` (task 19.3) does not exist yet; real text must stay
  out of the repository until retention and PII handling are documented.
- Task 6.2's media fork stays in Phase 2; it needs the real media worker (14.1/14.2).

## 7. References

- `docs/tasks.md` - authoritative task list (task 4.3, 7.2, 18.2 are the Phase 1 anchors).
- `docs/design.md` - text detection cascade and calibrator rules (sections
  "Text Threat Detection", "Testing and Evaluation Strategy").
- `docs/requirements.md` - Requirements 5, 11, 16.
