# Stage Two — Function Verification & Running-Cost Estimates

Maps the stage-one architecture onto the locked stack (**Python + FastAPI** + **PostgreSQL via Supabase**), checks planned functions are covered, and gives ballpark monthly costs. No implementation.

**Pricing sources:** [supabase.com/pricing](https://supabase.com/pricing) and public billing docs, checked **2026-09-30**. Figures change; treat ranges as planning estimates, not quotes.

---

## 1. Function verification

### Component → FastAPI + Supabase mapping

| Stage-1 component | Concrete responsibility (this stack) | Covered? |
| --- | --- | --- |
| **HTTP API** | FastAPI routers, Pydantic request/response models, status codes | Yes |
| **Domain / service layer** | Python service modules orchestrating CRUD; no SQL in route handlers | Yes |
| **Persistence** | async/sync Postgres driver (e.g. `asyncpg` / `psycopg`) + pool against Supabase `DATABASE_URL` (direct or pooler) | Yes |
| **Migrations** | Versioned SQL via Alembic or a SQL migration runner, applied as a CLI/step against the same Supabase DB | Yes |
| **Config** | Env (`DATABASE_URL`, `PORT`, `LOG_LEVEL`, …); fail-fast on missing required vars | Yes |
| **Database (Postgres)** | Supabase-hosted Postgres (project as DB-only; Auth/Storage/Realtime unused) | Yes |

### Interaction → responsibility coverage

| Planned function | How it is covered | Gap / note |
| --- | --- | --- |
| **CRUD** (list / get / create / update / delete) | FastAPI routes → service → parameterized queries → Supabase Postgres | None for baseline; domain resource chosen in stage 4 |
| **Empty / not-found** | List → `200` + `[]`; missing id → `404` | None |
| **Validation errors** | Pydantic → `400`/`422` with field messages | Align status convention in stage 4 design docs (`400` vs FastAPI default `422`) |
| **Constraint / conflict** | Map unique/FK violations → `409` | Needs explicit exception mapping in persistence |
| **Unexpected errors** | Global exception handler → `500`; log server-side | None |
| **Health** | `GET /health` process liveness; optional DB probe (e.g. `SELECT 1`) for degraded vs down | None |
| **Config** | Env-only secrets; no hardcoded connection strings | Document SSL / pooler vs direct URL for Supabase |
| **Migrations** | Separate apply step against Supabase connection (not on every request) | Choose tool in stage 4/5; not a functional gap |
| **Connections** | Client → FastAPI over HTTP; FastAPI → Postgres over TCP (Supabase pooler recommended for serverless/short-lived, direct OK for long-lived API process) | Prefer transaction/session pooler settings when hosting API ephemerally |

### Out-of-scope (stage 1) — still out

Auth, queues, websockets, admin UI, caching, object storage — not required for function completeness of the baseline plan.

**Verdict:** Every in-scope stage-1 function maps cleanly onto FastAPI + Supabase Postgres. Only soft gaps are design choices (validation status code, migration tool, pooler vs direct), not missing capabilities.

---

## 2. Running-cost estimates

### Assumptions

- Low demo/teach traffic: sparse CRUD, well under Free egress/DB size.
- Supabase used as **Postgres only** (no Auth MAUs, Storage, Realtime, Edge Functions billed usage beyond idle project).
- FastAPI runs **locally** for day-to-day work; optional cheap host only for a public demo.
- One Supabase project; no branching, PITR, custom domains, or Team/Enterprise.
- Agent/token costs for Cursor build agents are **out of scope until stage 9**; not included in monthly hosting totals below.

### Supabase (Postgres) — Free vs Pro

| Item | Free | Pro (typical single project) |
| --- | --- | --- |
| Plan | **$0 / mo** | **~$25 / mo** org plan (includes $10 compute credits → one Micro instance) |
| DB size included | 500 MB | 8 GB disk / project |
| Egress included | 5 GB | 250 GB (then ~$0.09/GB) |
| API requests | Unlimited | Unlimited |
| Inactivity | **Paused after ~1 week** | No pause |
| Active projects | Max **2** free active | Per-project compute beyond credits |
| Backups | None automatic | Daily, 7-day retention |

**Demo / local-first path:** Supabase Free + local FastAPI → **~$0 / mo** hosting, with the caveat that Free projects pause after inactivity (wake on demand; awkward for always-on demos).

**Always-on / shared demo path:** Supabase Pro Micro → **~$25 / mo** for the DB side alone (spend cap on by default for overages). Extra egress or disk rarely matters at sample-app scale.

Team ($599+) and Enterprise are unnecessary for this project.

### FastAPI process hosting

| Where API runs | Ballpark monthly | Notes |
| --- | --- | --- |
| Local (dev / teaching laptop) | **$0** | Default for stages until deploy |
| Cheap PaaS (Railway / Fly / Render hobby-class) | **~$0–10** if free tier available; else **~$5–15** for a small always-on container | Plus Supabase DB cost above; watch egress between regions |
| Same machine as agents / CI only | **$0** incremental | Ephemeral; Free Supabase pause still applies between uses |

### Combined rough monthly ranges

| Scenario | Rough total |
| --- | --- |
| A. Local FastAPI + Supabase Free | **$0** (pause risk) |
| B. Cheap hosted FastAPI + Supabase Free | **~$0–15** (pause + free-tier limits) |
| C. Cheap hosted FastAPI + Supabase Pro | **~$30–40** |
| D. Local FastAPI + Supabase Pro | **~$25** |

No fake precision: actual PaaS bills depend on sleep policies, regions, and idle compute. Sample CRUD traffic should stay inside Free/Pro included egress.

### Stage 9 note (tokens / agents)

Cursor agent and token spend for later build/deploy stages is **not** estimated here. Stage 9 owns billing watch and financial optimization for tokens + hosting.

---

## 3. Risks / gaps

1. **Free-tier pause** — Supabase Free pauses after ~1 week idle; breaks “always-on” demos unless someone wakes the project or upgrades to Pro.
2. **Connection mode** — Wrong URL (direct vs pooler) or missing SSL can cause flaky pools when the API is hosted; document in stage 4.
3. **Validation status convention** — FastAPI/Pydantic defaults to `422`; stage-1 plan said `400`. Pick one in design docs.
4. **Migration discipline** — Applying migrations against a shared Supabase project needs a clear process (stage 3 DevOps) so demos do not clobber schema.
5. **RLS / Data API surface** — Even if the app uses only the Postgres connection, tables in `public` can be exposed via Supabase Data API unless locked down; stage 4/5 should note RLS or schema exposure hygiene.
6. **Region / egress** — Hosting FastAPI far from the Supabase region burns Free’s 5 GB egress faster under careless bulk tests.

---

## 4. Recommendation

**Go** to stage 3 (DevOps + testing/QA process planning).

No architecture adjust needed: FastAPI + Supabase Postgres covers all planned functions. Prefer scenario A (local API + Supabase Free) until an always-on demo forces Pro or a cheap API host. Carry forward the soft choices (migration tool, `400` vs `422`, pooler URL, Free pause awareness) into stage 3/4 without blocking.
