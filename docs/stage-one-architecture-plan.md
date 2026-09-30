# Stage One — Architecture Plan

Sample DB backend: a small, teachable HTTP API backed by a relational database. This document covers **components, interactions, and connections only**. No data model, no implementation, no scaffolding.

---

## 1. Purpose / scope

**Purpose:** Demonstrate a clean, minimal backend that exposes CRUD-style resources over HTTP, persists them in PostgreSQL, and manages schema via versioned migrations. Suitable for teaching, demos, and as a starting slice for later features.

**In scope (eventual build):**
- HTTP JSON API (list / get / create / update / delete)
- PostgreSQL as the system of record
- Versioned SQL migrations
- Env-based configuration and a health check
- Clear empty, not-found, and error responses

**Out of scope for early stages:**
- Auth / multi-tenant isolation
- Background jobs, queues, websockets
- Separate admin UI or frontend app
- Caching layers, search engines, object storage

**Assumptions:**
- Single service process + one Postgres instance (Supabase-hosted Postgres)
- Synchronous request/response (no async workers in the first build)
- **Locked stack:** Python + FastAPI HTTP API + PostgreSQL via Supabase connection string
- Local-first for the API process; Supabase Free for managed Postgres in demos; cloud host for the API is optional later

---

## 2. Components

| Component | Owns | Does not own |
| --- | --- | --- |
| **HTTP API** | Routes, request validation, response shaping, status codes | Schema DDL, connection pooling internals |
| **Domain / service layer** | Business rules, orchestration of reads/writes | Raw SQL transport, env loading |
| **Persistence** | Queries, parameterized statements, mapping rows → domain | HTTP concerns, migration history |
| **Migrations** | Versioned schema changes, apply/rollback order | Runtime query logic |
| **Config** | Env parsing, defaults, fail-fast on missing required vars | Business logic |
| **Database (Postgres)** | Data durability, constraints, indexes | Application routing |

Optional later (not required for the first build): auth middleware, observability exporters, a thin admin/read-only UI.

---

## 3. Interactions

**Happy path (sync):**
1. Client → HTTP API (JSON)
2. API validates input → service layer
3. Service → persistence (parameterized query)
4. Persistence → Postgres → row(s) back
5. API returns JSON + appropriate status (`200` / `201`)

**Empty / not found:**
- List with no rows → `200` + empty collection
- Missing resource by id → `404`

**Error paths (high level):**
- Invalid input → `400` with field-level messages
- Constraint / conflict (e.g. unique) → `409`
- Unexpected failure → `500`; log server-side, do not leak internals

**Health:**
- `GET /health` checks process liveness; optionally probes DB connectivity (degraded vs down distinguished at a high level)

No message bus or async pipeline in the baseline design; all mutating work completes inside the request transaction boundary.

---

## 4. Connections

```
[Client] --HTTP/JSON--> [API process]
                           |
                           |-- config from env (DATABASE_URL, PORT, LOG_LEVEL, …)
                           |
                           +-- TCP pool --> [PostgreSQL]
                           |
                           Migrations run as a separate CLI/step against the same DB
```

**Boundaries:**
- API talks to Postgres only through the persistence layer (no ad-hoc SQL in route handlers)
- Config is env-only for runtime; secrets never hardcoded
- External deps kept minimal: HTTP framework, DB driver/client, migration runner

**Not wired in stage one / early build:** auth providers, Redis, object storage, third-party APIs. Those remain optional later stages if needed.

---

## 5. Staged delivery

| Stage | Deliverable | Status |
| --- | --- | --- |
| **1** | Overall plan: components, interactions, connections | **Done** (this document) |
| **2** | Verify the plan for functions; compute possible costs of running | **Done** — see [stage-two-function-and-cost.md](./stage-two-function-and-cost.md) |
| **3** | Plans for DevOps delivery processes, plus testing and QA process | After stage 2 |
| **4** | Initial repo framework + design-plan docs for all implementation (Markdown; SQL/JSON for data model / schema) | After stage 3 |
| **5** | Evaluate tooling (plugins, addons, extensions) for the dev pipeline and the app; suggest delivery-pipeline and application-performance optimizations | After stage 4 |
| **6** | Rethink stages 1–5 with all gathered information; produce final plans for build agents to implement the application | After stage 5 |
| — | Full feature build by build agents (implements stage 6 final plans) | After stage 6; input to stage 7 |
| **7** | Deploy the application; apply any DB data updates; engagement of deployment agents to put the release online and start testing it | After build-agent implementation |
| **8** | Test and evaluate the newly deployed application; provide monitoring setup changes; version numbering, changelog, and PR version-promotion updates | After stage 7 |
| **9** | Watch billing; provide cost-of-running estimations; suggest financial optimization improvements for tokens and other hosting costs | After stage 8 |

**No build for stages 1–3.** Stage 4 introduces the repo framework and design docs (including data model / schema artifacts). Stage 5 is planning/analysis — tooling evaluation and optimization suggestions — not necessarily implementing those optimizations unless a later step says so. Stage 6 consolidates everything into final implementation plans. Build agents implement from those plans after stage 6; stage 7 is deploy + DB data updates + online release + start testing via deployment agents. Stage 8 covers post-deploy test/eval, monitoring changes, and version/changelog/PR promotion. Stage 9 covers billing watch, running-cost estimates, and financial optimization suggestions.

---

## 6. Open decisions / assumptions

**Locked (do not reopen without user change):**
1. **Stack** — Python + FastAPI application.
2. **Database** — PostgreSQL via Supabase connection (project used as Postgres; Auth/Storage/Realtime unused unless a later stage adds them).

**Still open (non-blocking for stage 3):**
3. **Deployment target for the API** — Local process first; optional cheap host (e.g. Railway / Fly / Render) when online demo is needed. Supabase hosts Postgres.
4. **Domain theme** — Sample resources (e.g. notes, inventory, bookmarks) chosen at the data-model stage; not fixed yet.
5. **Auth** — Deferred; add only if a later stage requires protected routes.
6. **Cost posture** — Prefer Supabase Free + local FastAPI for demos; Pro (~$25/mo org) only if inactivity pause or quotas become a problem. Detail in stage-two cost section.
