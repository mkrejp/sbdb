# Stage 6 — Final Build-Agent Plans

Rethink of stages 1–5 into **actionable work packages** for build agents. **Do not implement or deploy from this stage** until the user approves. After approval, build agents implement; stages 7–8 own deploy / smoke / release hygiene.

**Standing brief:** [agents-instructions.md](./agents-instructions.md)  
**Inputs:** stages [1](./stage-one-architecture-plan.md)–[5](./stage-five-tooling-and-optimizations.md), [NPÚ sync](./npu-geoportal-sync.md), [DNS](./dns-sbdb-animarium-ai.md), [preferences](../preferences.md)

---

## 1. Confirmed architecture & stack locks

Do **not** reopen without user confirmation.

| Lock | Value |
| --- | --- |
| App | Python 3.12+ · FastAPI · Pydantic v2 · pydantic-settings · uvicorn[standard] |
| Package / tooling | `uv` · Ruff · pytest · entrypoints `sample-db-backend`, `sample-db-npu-sync` |
| DB | PostgreSQL via Supabase **samplebackdb** (`bsauzwsgiwghkwgehcid`, `eu-central-2`, Free) |
| Driver | **psycopg 3** (sync); pooler URL preferred on Railway |
| Migrations | Versioned SQL under `migrations/` via `psql -f` — **no Alembic** |
| Geometry | JSONB GeoJSON + GIN; PostGIS later only if spatial predicates appear |
| Image/binary props | Supabase Storage **refs** (never BYTEA) |
| Validation | HTTP **422** (FastAPI default) |
| CI | GitHub Actions: Ruff → pytest; stub `DATABASE_URL=""`; no matrix; no deploy-from-Actions |
| Host | Railway Free/Trial; **no** Railway Postgres; Wait-for-CI autodeploy `main` |
| Public hostname | `sbdb.animarium.ai` → Railway (CNAME; see DNS doc) |
| Cost | Free tiers default; Hobby/Pro only as escape hatches |
| Domain | GeoJSON map layers (`notes-for-data-model`): `map_layers`, `layer_objects`, `layer_object_properties`, `tags`, `layer_object_tags`, `layer_object_urls` |
| Auth / queues / UI / Redis / paid APM | **Out of scope** for this build slice |
| NPÚ fill | MapServer layer `…/Tematicke/CP_UAP_PVO/MapServer/0`; paged `resultOffset`; upsert on `(layer_id, npu_objectid)` |

**Architecture (unchanged from stage 1, grounded by 2–5):**

```
Client --HTTP/JSON--> FastAPI (routers → services → persistence)
                           |
                           +-- env (DATABASE_URL pooler, PORT, LOG_LEVEL, PUBLIC_HOSTNAME, NPU_*)
                           +-- TCP --> Supabase Postgres
CLI sample-db-npu-sync --> same DB (paged MapServer → upsert)
Migrations: explicit psql steps (not per-request)
```

---

## 2. What exists on genesis `main` vs remaining gaps

**Repo tip (as of stage-6 drafting):** `098c286` (agents-instructions #2) atop stage-4 framework `775339a` / NPÚ CP_UAP_PVO work.

### Already on `main` (do not rebuild)

| Area | Present |
| --- | --- |
| Package layout | `src/sample_db_backend/` — `main`, `config`, `db`, `schemas`, `routers/{health,layers}`, `services/layers`, `sync/npu_geoportal` |
| API surface | Health + layers/objects/properties/tags/urls CRUD aligned with `docs/api-design.json` |
| Stub mode | Empty `DATABASE_URL` → in-memory store (CI-friendly) |
| Migrations | `001_create_notes_for_data_model.sql`, `002_npu_sync_keys.sql` |
| Design docs | `docs/design-overview.md`, schema SQL/JSON, API JSON, NPÚ + DNS notes, agents-instructions |
| NPÚ sync CLI | Metadata → page GeoJSON → upsert layer/objects/props/tags/urls |
| CI | `.github/workflows/ci.yml` (uv cache, Ruff, pytest stub) |
| Tests | `tests/test_layers.py`, `tests/test_npu_sync.py` (unit / TestClient; no live NPÚ) |
| Supabase | Schema reported applied on **samplebackdb** (stage-4 handoff) |

### Gaps for build agents (implement these)

| Gap | Why it matters |
| --- | --- |
| **No Dockerfile / Railway start command** | Stage 7 cannot deploy without a Free-RAM-sized image + `uvicorn` start |
| **No pre-commit; CI lacks `ruff format --check`** | Stage-5 “do now” lean pipeline |
| **`.env.example` / README still say FeatureServer “placeholder”** | Layer is **locked** to CP_UAP_PVO MapServer/0 — docs/defaults must match |
| **Config defaults for `NPU_TAG_FIELDS` / `NPU_URL_FIELDS`** | Still generic (`TYP,KATEGORIE,…`); should default to CP_UAP_PVO mapping from NPÚ doc |
| **Layer HTTP models may omit `source_key` / `source_url`** | Sync writes them; API list/get should expose for ops/debug (read) |
| **No connection pool** | Short-lived `psycopg.connect` per call is OK for demo; document; optional thin pool later — not blocking if Railway single-worker |
| **NPÚ retries / backoff** | Stage-5: retry 429/5xx; keep timeouts + `User-Agent: YourSyncBot/1.0` |
| **Batch / transactional upsert per page** | Harden sync: one transaction per page; reduce N+1 where easy |
| **Structured logging** | stdlib logging with consistent fields for sync + request errors |
| **Conflict mapping completeness** | Ensure UniqueViolation → 409 on all write paths that need it |
| **List LIMIT already present** | Keep ≤100; verify objects list + GeoJSON payloads stay capped |
| **No `.cursor/rules`** | Thin rules mirroring agents-instructions §3–6 (secrets, free tier, NPÚ paging, 422) |
| **Deploy / DNS / live sync / monitoring** | **Stage 7–8** — plan only below; not build-agent scope |

**Not gaps:** inventing a new domain, Auth, PostGIS, Alembic, Sentry, preview envs, Actions deploy matrices.

---

## 3. Ordered work packages (build agents)

Execute **WP-A → WP-E** in order unless noted parallel. Prefer draft PRs via Origin; Bugbot on migration/sync/`DATABASE_URL` PRs. Stay free-tier. **Ask the user immediately** if `DATABASE_URL`, Railway login, or DNS credentials are missing when a package actually needs them — build packages below should work with stub mode + mocked NPÚ where possible.

### WP-A — Lock NPÚ defaults & doc hygiene

| | |
| --- | --- |
| **Owner** | Build agent (docs + config) |
| **Depends on** | User approval of stage 6 |
| **In scope** | Set `.env.example` `NPU_LAYER_URL` to locked MapServer/0; update README (remove “placeholder / FeatureServer-first”); align `config.py` default `NPU_TAG_FIELDS` / `NPU_URL_FIELDS` with [npu-geoportal-sync.md](./npu-geoportal-sync.md) CP_UAP_PVO mapping; fix stale FeatureServer comments in sync module docstring; ensure Context + repo `docs/npu-geoportal-sync.md` stay consistent |
| **Out of scope** | Live sync run; changing layer URL; WAF workarounds beyond docs |
| **Acceptance** | Grep shows locked URL in `.env.example` + agents-instructions; README points to MapServer/0; defaults match CP_UAP_PVO tag/URL/temporal fields; `uv run ruff check` + `pytest -q` green |

### WP-B — API/service hardening (productize framework)

| | |
| --- | --- |
| **Owner** | Build agent (API) |
| **Depends on** | WP-A optional (can parallel after approval) |
| **In scope** | Expose `source_key`/`source_url` on layer read schemas if missing; confirm all CRUD paths from `api-design.json`; empty list → `200`+`[]`; missing → `404`; validation → `422`; unique conflicts → `409`; keep `LIMIT` on list endpoints; health returns process + DB probe (`connected`/`skipped`/`unavailable`); structured logging on unexpected 500s; no SQL in routers |
| **Out of scope** | Auth, CORS sprawl, pagination cursors beyond simple limit, PostGIS filters, Storage upload helpers |
| **Acceptance** | TestClient covers happy/empty/404/422/409 for core resources; stub mode CI green; OpenAPI matches design endpoints |

### WP-C — NPÚ sync hardening

| | |
| --- | --- |
| **Owner** | Build agent (sync) |
| **Depends on** | WP-A (field defaults) |
| **In scope** | Keep page ≤ `maxRecordCount` (client cap ≤1000); stream page→upsert; **one DB transaction per page**; upsert `map_layers` by `source_key`, objects by `(layer_id, npu_objectid)`; map tags/URLs/temporal/text per locked field table; httpx timeouts; retries with backoff on 429/5xx; headers `User-Agent: YourSyncBot/1.0`, `Accept: application/json`; unit tests with mocked httpx (no live geoportal in CI) |
| **Out of scope** | Scheduled cron; full-layer in-memory load; FeatureServer-only assumptions; running sync from cloud agents known to be WAF-blocked |
| **Acceptance** | `tests/test_npu_sync.py` covers paging stop condition + upsert identity; CLI `--help` / main path documented; docs say **run live sync from user WSL** (`/home/cursor/dev/genesis`) when cloud IPs are blocked |

### WP-D — Tooling / CI polish

| | |
| --- | --- |
| **Owner** | Build agent (DX) |
| **Depends on** | None (parallel with B/C) |
| **In scope** | Add `.pre-commit-config.yaml` (Ruff lint + format); CI: `ruff format --check` + existing `ruff check` + pytest stub; thin `.cursor/rules` (no secrets, free-tier, NPÚ paging, 422, parameterized SQL); keep single Python, no matrix, no cron |
| **Out of scope** | Codecov, Dependabot (later), GHA postgres service (later), Alembic |
| **Acceptance** | `pre-commit run --all-files` passes locally; CI job still ≤ one lint + one test; Actions still uses stub `DATABASE_URL` |

### WP-E — Deployability artifacts (no live deploy)

| | |
| --- | --- |
| **Owner** | Build agent (packaging) |
| **Depends on** | WP-B green enough to run |
| **In scope** | Minimal **Dockerfile** (uv sync, non-root optional, single worker); document Railway start e.g. `uv run uvicorn sample_db_backend.main:app --host 0.0.0.0 --port $PORT`; stay within **0.5 GB** RAM; document migrate commands; document required Railway vars (`DATABASE_URL` pooler+SSL, `PORT`, `LOG_LEVEL`, `PUBLIC_HOSTNAME`, optional `NPU_*`); cross-link [dns-sbdb-animarium-ai.md](./dns-sbdb-animarium-ai.md); **do not** create Railway service or set secrets unless user expands into stage 7 |
| **Out of scope** | Actual Railway project wiring, DNS CNAME apply, Supabase wake automation, paid plan upgrades |
| **Acceptance** | `docker build` succeeds (or documented equivalent); README “Deploy prep” section lists start command + migrate + env; image/start sized for Free; no secrets committed |

### Optional WP-F — Repo mirror of stage docs

| | |
| --- | --- |
| **Owner** | Docs agent / same build agent |
| **In scope** | Copy this file (+ keep agents-instructions §10) into genesis `docs/` via draft PR if not already present |
| **Out of scope** | Rewriting stages 1–5 |

---

## 4. NPÚ sync / WAF / WSL notes

| Topic | Instruction for agents |
| --- | --- |
| Layer | `https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0` |
| Practices | Follow [npu-geoportal-sync.md](./npu-geoportal-sync.md) exactly — page with `resultOffset` / `resultRecordCount`; never assume one `where=1=1` returns all rows |
| WAF | Cloud agent / some datacenter IPs get blocked on `/query` — **do not burn agent minutes** retrying full mirrors from blocked egress |
| Preferred live sync | User **WSL** path `/home/cursor/dev/genesis` with `DATABASE_URL` + `NPU_LAYER_URL` set; `uv run sample-db-npu-sync` |
| Self-hosted workers | Stage-5 “later” option if WSL unavailable and cloud stays blocked |
| CI | Mock NPÚ only; never hit geoportal from Actions |
| Scheduling | Weekly/monthly cron → **stage 7 decision**, not default in build |

---

## 5. Deploy path handoff (stages 7–8) — plan only

Build agents stop when `main` is **deployable**. Deployment agents then:

### Stage 7 (deploy agents)

1. Wake Supabase Free if paused.  
2. Confirm migrations applied on **samplebackdb** (`001` then `002` if needed).  
3. Railway: Trial/Free service from GitHub; **verify GitHub** (avoid Limited Trial); **no** Railway Postgres; set pooler `DATABASE_URL` + app env; enable **Wait for CI** autodeploy on `main`.  
4. Deploy; manual smoke: `curl /health` then one read path.  
5. Optional: apply CNAME `sbdb` → Railway target per [dns-sbdb-animarium-ai.md](./dns-sbdb-animarium-ai.md); TLS via Railway.  
6. Optional initial fill: NPÚ sync from **WSL** (not from blocked cloud).  
7. Ask user immediately if Railway/DNS/Supabase password missing.

### Stage 8 (eval agents)

1. Live eval against Railway / `sbdb.animarium.ai`.  
2. Light monitoring: Railway logs + Supabase advisors (no paid APM).  
3. Version / changelog / PR promotion hygiene.  
4. Note Free pause + `$1/mo` credit risks for stage 9.

**Build agents must not:** buy Hobby/Pro, enable preview envs, put secrets in git, or treat stage 6 approval as deploy authorization.

---

## 6. Risks & “do not reopen” list

### Do not reopen

1. Stack: FastAPI + Supabase Postgres + GHA + Railway.  
2. Domain: GeoJSON map layers + typed props + tags + URL lists.  
3. Validation **422**.  
4. Migrations = plain SQL files.  
5. NPÚ = **MapServer** CP_UAP_PVO/0 with paging.  
6. Free-tier hosting defaults.  
7. No auth / no frontend / no PostGIS in this slice.  
8. Stages 1–9 sequence; no parallel “shadow” roadmap.

### Active risks (carry forward)

| Risk | Mitigation |
| --- | --- |
| Supabase Free **pause** (~1 week idle) | Wake before migrate/deploy/smoke; Pro only if always-on required |
| Railway Free **$1/mo** / **0.5 GB** | Single worker; stop when idle; Hobby only if hard-blocked |
| Limited Trial outbound | GitHub verify on Railway |
| Wrong `DATABASE_URL` (direct vs pooler / SSL) | Document pooler for Railway in WP-E |
| NPÚ WAF | Sync from WSL; mock in CI |
| Shared Free DB + CI egress | Keep stub CI; no live Supabase in Actions |
| Concurrent DDL on shared demo DB | Review migration PRs; never auto-reset demo DB |
| Secrets in chat/docs | Env only; rotate if pasted; never commit |

### Soft / deferred (not build blockers)

- Async DB pool when concurrency hurts.  
- GHA `postgres` service when stub lies about SQL.  
- Dependabot quiet bumps.  
- PostGIS if bbox/intersects product need appears.  
- Storage upload helpers for image/binary props.

---

## 7. Cursor / agent working style (for implementers)

- Read [agents-instructions.md](./agents-instructions.md) first; prefer `docs/` over chat history.  
- Speed; ask **only** blocking questions; ask **immediately** on missing credentials.  
- Draft PRs; watch CI with Origin / subscriptions MCP when waiting.  
- Bugbot on migration, sync, and secret-handling PRs; skip for pure doc typos.  
- Branch names: follow repo / cloud conventions (`cursor/…`).  
- **Start implementation only after user approves stage 6.**

---

## 8. Definition of done (build phase)

Build phase complete when:

1. WP-A–E merged (or explicitly waived by user).  
2. CI green on `main`.  
3. App runs locally stub + with `DATABASE_URL`.  
4. Dockerfile/start docs ready for Railway.  
5. NPÚ CLI documented for WSL live fill.  
6. No secrets in git.  
7. Handoff note points stage-7 agents at migrate → Railway → DNS → WSL sync → smoke.

Then stop and wait for stage-7 authorization.
