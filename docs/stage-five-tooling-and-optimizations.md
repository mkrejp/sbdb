# Stage 5 — Tooling Evaluation & Optimizations

Evaluation only (locked stage plan). No parallel roadmap. Stack: **FastAPI** + **Supabase Postgres (`samplebackdb`)** + **GitHub Actions** + **Railway** + **NPÚ MapServer sync**. Free-tier hosting preferred; Cursor **current plan** capabilities are in scope for agent/review tooling.

**Inputs:** [agents-instructions](./agents-instructions.md) · [stage 1–4](./stage-one-architecture-plan.md) · [NPÚ sync](./npu-geoportal-sync.md) · genesis framework on `main` (Ruff, pytest, uv, `psycopg`, httpx, SQL migrations).

**Next stage:** 6 — rethink 1–5 → final build-agent plans (not implement yet).

---

## 1. Dev-pipeline tooling

| Tool | Role | Cost | Verdict |
| --- | --- | --- | --- |
| **uv** | Deps, lockfile, scripts (`sample-db-npu-sync`) | Free | **Keep** (already in CI) |
| **Ruff** | Lint + format | Free | **Keep**; add `ruff format --check` in CI |
| **pytest** (+ `pytest-asyncio`) | Unit / API / sync unit tests | Free | **Keep**; stub `DATABASE_URL` in CI (already) |
| **pre-commit** | Local Ruff (+ optional `uv lock --check`) | Free | **Do now** — short-circuits Actions minutes |
| **astral-sh/setup-uv@v5** | GHA UV + cache | Free | **Keep** |
| **actions/checkout@v4** | GHA | Free | **Keep** |
| **GHA `postgres` service** | Integration tests without Supabase egress | Free minutes | **Later** (when stub coverage is insufficient) |
| **Railway CLI** | Env, logs, one-off migrate/redeploy | Free | **Do now** for stage 7 prep |
| **Supabase CLI / MCP** | Status, advisors, SQL, migrations inspect | Free (project Free) | **Do now** for ops; avoid Data API exposure |
| **Alembic** | Migration runner | Free | **Skip** for sample — stick to versioned `psql -f migrations/*.sql` |
| **Dependabot / Renovate** | Dep bumps | Free (GH) | **Later** — quiet weekly PRs only |
| **Codecov / Coveralls** | Coverage SaaS | Free tier noise | **Skip** — local `pytest --cov` optional |
| **Sentry / paid APM** | Error SaaS | Paid | **Skip** until stage 8 needs it |

**CI shape (stay minute-cheap):** one Python version, lint then test, uv cache on, no matrix, no cron, no deploy-from-Actions (Railway Wait-for-CI autodeploy).

---

## 2. Application tooling

| Area | Recommend | Notes |
| --- | --- | --- |
| Framework | **FastAPI** + **Pydantic v2** + **pydantic-settings** | Keep; validation **422** (locked) |
| ASGI | **uvicorn[standard]** | Single worker on Railway Free (0.5 GB) |
| DB driver | **psycopg 3** (sync today) | Fits current `db.py`; upgrade path: `psycopg` async pool or **asyncpg** when concurrent load matters |
| HTTP (NPÚ) | **httpx** (already) | Keep timeouts + `User-Agent` / `Accept`; retries with backoff on 429/5xx |
| Geo / storage | **JSONB** GeoJSON + GIN (already) | **PostGIS later** only if spatial filters/`ST_*` needed |
| Migrations | Plain SQL under `migrations/` | Document apply order; no Alembic for sample |
| Observability (Free) | Structured **stdlib logging** + Railway logs + Supabase advisors | Skip paid APM |
| Optional libs | `geojson-pydantic` | Later if geometry validation churns; not required now |
| Storage refs | Supabase Storage paths in props | No BYTEA; upload helpers later if needed |

---

## 3. Cursor-plan tooling (in scope)

Use the **current Cursor subscription** for agent/review/watch workflow. Hosting (Railway / Supabase) stays free-tier by default — Cursor plan does not replace those.

| Capability | Use for this project | When |
| --- | --- | --- |
| **Project + Cloud Agents** | Stage docs → build/deploy workers after stage 6; keep `docs/agents-instructions.md` as standing brief | **Now** for stage planning; **stage 6+** for implement/deploy agents |
| **Origin** (`origin` CLI, draft PRs) | PR hygiene on private genesis; prefer draft PRs; watch checks via `origin pr checks` | **Now** on any code change |
| **Bugbot / agentic review** | Review PRs that touch migrations, NPÚ upsert, or `DATABASE_URL` handling | **Now** on non-trivial PRs; skip for doc-only |
| **Cursor rules / skills** | Repo rules: no secrets in git; free-tier defaults; NPÚ paging; SQL parameterized. Skills: Supabase, Railway, env-setup, subscriptions | **Do now** — thin `.cursor/rules` (or Project instructions) mirroring agents-instructions §3–6 |
| **Self-hosted workers** | Run NPÚ sync / migrate from a network that is **not WAF-blocked** (cloud agent IPs often blocked) | **Later** if cloud sync keeps failing; else run sync from user WSL |
| **Subscriptions MCP** | `subscribe_origin_ci` / `subscribe_origin_pr` while waiting on build/deploy PRs; avoid polling | **Stage 7–8** when PRs + CI matter |
| **Railway / Supabase MCP** | Inspect Free project, vars, advisors — not for paid upgrades | **Do now** as ops assist |

**Do not:** invent a second delivery track outside stages 1–9; burn Cloud Agent minutes on full NPÚ mirrors from blocked egress; auto-upgrade Railway Hobby / Supabase Pro from agents.

---

## 4. Delivery-pipeline optimizations

| Optimization | Why | Priority |
| --- | --- | --- |
| Keep CI stub-mode (`DATABASE_URL=""`) | Saves Actions minutes + Supabase **5 GB** egress | **Do now** |
| uv cache + single job chain | Already present; keep | **Do now** |
| pre-commit → fewer red CI runs | Local fail-fast | **Do now** |
| Railway **Wait for CI** + autodeploy `main` only | No token CD; no preview envs | **Stage 7** |
| Migrate as explicit step (Railway release cmd or one-off CLI) | Not per-request; wake Supabase Free first if paused | **Stage 7** |
| Supabase **pooler** URL + SSL on Railway | Stable pools from ephemeral/container hosts | **Stage 7** |
| Manual smoke (`curl /health`) | Zero Actions minutes | **Stage 7** |
| Tear down / stop Railway when idle | Protect **$1/mo** Free credit | **Ongoing** |
| GHA postgres service for real SQL tests | When stub lies about SQL | **Later** |
| Scheduled NPÚ sync in CI/Railway cron | Burns Free + WAF risk | **Skip** early; run CLI from WSL/self-hosted |

---

## 5. Application performance optimizations

Realistic for sample / Free — not a spatial platform rewrite.

| Optimization | Detail | Priority |
| --- | --- | --- |
| Indexes already in schema | FK indexes, GIN on `geometry`, unique `(layer_id, npu_objectid)` | **Keep** |
| NPÚ page ≤ `maxRecordCount` (≤2000), stream upsert | Never load whole layer in RAM | **Do now** (already designed) |
| Batch upserts per page | One transaction per page; avoid N+1 property/tag inserts where easy | **Do now** in build plans |
| List endpoints: `LIMIT` + keyset/offset | Cap GeoJSON payload size | **Do now** in API build |
| Prefer pooler for Railway | Session/transaction pooler per Supabase docs | **Stage 7** |
| Async DB (`psycopg` async / asyncpg) | Better under concurrent reads | **Later** if single sync worker is fine for demo |
| HTTP response caching / CDN | Overkill for sample API | **Skip** |
| Redis / Materialized views | Extra cost & ops | **Skip** |
| PostGIS / geography indexes | Only if bbox/intersects queries appear | **Later** |
| JSONB geometry stay | Correct Free choice until spatial ops needed | **Keep** |

---

## 6. Prioritized list

### Do now (stage 5 → feed stage 6 plans)

1. Keep **uv + Ruff + pytest** as the only required local/CI toolchain; add **pre-commit** + `ruff format --check`.
2. Codify Cursor **rules/skills** from agents-instructions (secrets, free tiers, NPÚ paging, 422).
3. Use **Bugbot/Origin draft PRs** for migration / sync code; **Project agents** for stage docs → stage 6 plans.
4. In build plans: paged NPÚ sync, batch upsert, API `LIMIT`, pooler `DATABASE_URL`, structured logging.
5. Prefer **Railway CLI + Supabase MCP/CLI** for ops readiness — still Free hosting.

### Later (stages 6–8)

- Async DB pool; optional GHA Postgres service; Dependabot quiet bumps.
- Self-hosted worker **or** user-WSL for live NPÚ sync if cloud WAF blocks.
- `subscribe_origin_ci` during deploy PRs; light monitoring from Railway/Supabase logs.
- PostGIS only if product needs spatial predicates.
- Railway Hobby / Supabase Pro **only** as escape hatches (pause / $1 credit / RAM).

### Skip (for this sample)

- Alembic, paid APM/Sentry, coverage SaaS, Redis, preview envs, Actions deploy matrices, FeatureServer-only assumptions, full-layer in-memory NPÚ pulls, inventing stages outside 1–9.

---

## 7. Blocking questions

None for stage 5. Soft carry-overs already locked or deferred:

- NPÚ live sync network: user WSL preferred (documented); ask only if stage 7 requires cloud sync and credentials/network still fail.
- Paid Railway/Supabase: ask only when Free hard-limits block a required always-on demo.

---

## 8. Handoff to stage 6

Stage 6 should **rethink 1–5** and produce **final build-agent plans** that implement: lean CI (this doc §1/§4), app libs (§2), Cursor agent/review workflow (§3), and perf defaults (§5) — without expanding into paid hosting or PostGIS unless the user changes locks.
