# Stage Three — DevOps Delivery & Testing / QA Process

Plans only. No scaffolding, no app code, no real deploy. Locked stack: **Python + FastAPI**, **Postgres via Supabase**, **CI = GitHub Actions**, **API host = Railway**.

**Cost posture (user constraint):** stay on **free tiers by default**. Paid plans appear only as optional escape hatches when a free hard limit blocks demos. Prefer local FastAPI when Railway free credit is tight.

---

## 0. Free-tier defaults & hard limits

| Service | Default (free) | Hard limits to plan around | Paid escape (only if needed) |
| --- | --- | --- | --- |
| **GitHub Actions** | Free minutes on the repo’s GitHub plan | Private repos: ~**2,000 min/mo** (Free); public usually unlimited for standard runners. No OS/Python matrix — burns minutes. | Larger Actions packs / Team — avoid |
| **Railway** | **Free** plan: **$1** usage credit / mo after trial; Trial: one-time **$5** / ≤30 days then reverts to Free | Free: **0.5 GB RAM**, **1 vCPU**, **1 replica**, **$1/mo** compute budget (credit does not roll over). Trial network may be **Limited** until GitHub verify. Image retention **24h** on Free/Trial. | **Hobby $5/mo** (includes $5 usage) if Free credit/RAM is too tight for always-on |
| **Supabase** | **Free** Postgres project | **Paused after ~1 week** idle; **500 MB** DB; **5 GB** egress; max **2** free active projects; no automatic backups | **Pro ~$25/mo** only if pause/quotas break always-on demos |

**Default operating mode:** local FastAPI + Supabase Free for day-to-day; Railway Free/Trial for short public demos; keep deploys and CI sparse so credits/minutes last. Do **not** default to Railway Hobby or Supabase Pro.

---

## 1. DevOps delivery process

### Path (minimal, one production API)

```
feature branch → PR → GitHub Actions (lint + test) → merge to main
                                                      ↓
                              Railway GitHub autodeploy (Wait for CI)
                                                      ↓
                              migrate against Supabase Free (explicit step)
                                                      ↓
                              smoke check on Railway URL → green release
```

| Step | Who / what | Notes |
| --- | --- | --- |
| Branch | Developer / build agent | Short-lived `cursor/…` or `feature/…` off `main` |
| PR | GitHub | Required checks: lint + tests must pass |
| CI | GitHub Actions (free minutes) | No deploy from CI; keep jobs short (single Python version) |
| Deploy | Railway ← GitHub (Free/Trial) | Autodeploy `main` after CI green (**Wait for CI**). One service only — no Railway Postgres (saves Free credit). |
| Migrate | Controlled step against Supabase Free | Not on every request; not a second paid DB |
| Smoke | Manual curl preferred; optional light GHA | Prefer manual smoke to save Actions minutes |

**Environments — keep minimal (free-friendly):** one Supabase Free project + one Railway Free/Trial service. **No** Railway PR preview envs, **no** second Supabase project (Free allows only 2 active; previews burn credit). Local API + shared Supabase Free until a public demo needs Railway.

If Railway Free **$1/mo** credit is exhausted: fall back to **local-only API** for teaching; Hobby is optional, not automatic.

### Secrets / env

| Variable | Where set | Used by |
| --- | --- | --- |
| `DATABASE_URL` | Local `.env` (gitignored); GitHub Actions **secrets** (CI); Railway **service variables** (runtime) | API + migration CLI |
| `PORT` | Railway sets / app reads; local default e.g. `8000` | API bind |
| `LOG_LEVEL` | Optional; default `INFO` | API |
| Railway tokens | Avoid for baseline | Prefer GitHub↔Railway autodeploy (no token CI deploy) |

**Rules:** never commit connection strings; prefer Supabase **pooler** URL for hosted API (document SSL in stage 4); CI may reuse the same Free Supabase project (no paid CI DB). Watch Free **egress (5 GB)** if CI hits the remote DB often — prefer in-process/sqlite-less: use Supabase sparingly or a free `postgres` service container in Actions when that stays within free minutes.

### Migrations against Supabase Free

1. Author versioned SQL (tool chosen in stage 4/5).
2. Apply **locally** against Supabase Free when schema changes.
3. On release: apply to the **same** Free DB as a gated step (not mid-request).
4. One shared Free DB → PR-review migration files; avoid concurrent conflicting DDL.
5. **Never** automate destructive resets against the shared demo DB.
6. After Free **pause**: wake project in dashboard before migrate/deploy/smoke; treat wake latency as expected, not a pager event.

---

## 2. Integrations

### GitHub Actions (plan-level; conserve free minutes)

**Workflow A — `ci.yml` (on PR + push to `main`)**

| Job | Steps (plan) |
| --- | --- |
| `lint` | Checkout → setup Python → install deps → Ruff |
| `test` | Checkout → setup Python → install deps → `DATABASE_URL` from secrets **or** free `postgres` service container → migrate → `pytest` |

One workflow, one Python version, ubuntu-latest only — **no matrix**. Cache pip if cheap. Skip scheduled/cron workflows on free minutes.

**Workflow B — smoke (optional; prefer manual on Free)**

- Manual: curl Railway URL after deploy (zero Actions minutes).
- Optional later: GHA on Railway `deployment_status` success ([post-deploy actions](https://docs.railway.com/cli/deploying#github-actions)) — only if minutes budget allows.

### Railway (Free / Trial first)

| Integration | Plan |
| --- | --- |
| **Plan** | Start **Trial** ($5 one-time) → then **Free** ($1/mo credit). Connect GitHub and [verify](https://railway.com/verify) to avoid **Limited Trial** outbound/port restrictions (API must reach Supabase). |
| **GitHub connection** | One service = FastAPI app. **No** Railway-managed Postgres (DB on Supabase Free). |
| **Autodeploy** | `main` only. Enable **[Wait for CI](https://docs.railway.com/deployments/github-autodeploys#wait-for-ci)**. |
| **Variables** | `DATABASE_URL` + config in Railway env UI/CLI. |
| **Build / run** | Small image; single replica; start `uvicorn` (exact command stage 4/6). Stay within Free **0.5 GB RAM**. |
| **Domains** | Default `*.up.railway.app` (no custom domain cost). |
| **Spend control** | One always-on service max; tear down or stop when demo idle if credit is low; do not enable previews. |

**Hobby ($5/mo)** only if Free credit/RAM cannot sustain a needed always-on demo — document as escape hatch for stage 7/9, not default.

### What not to automate yet

- Multi-env promotion, blue/green, canaries
- Railway PR previews + Supabase branches (burns Free quotas)
- CD via `RAILWAY_TOKEN` from Actions
- Automated DB resets / PITR drills
- Paid APM / error SaaS
- Auth secret rotation (no auth in baseline)
- Cron-heavy Actions or multi-version test matrices

---

## 3. Testing & QA process

### Layers (lean; free-minute aware)

| Layer | What | Tools | When |
| --- | --- | --- | --- |
| **Unit** | Domain/service, error mapping | `pytest` | Local first; CI on PR/`main` |
| **Integration** | Persistence + SQL | `pytest` + Postgres | Local when touching DB; CI (prefer Actions `postgres` service over hammering Supabase Free egress) |
| **API** | HTTP contracts: CRUD, 404, validation, health | TestClient / httpx | Local + CI |
| **Smoke** | Live Railway URL | curl | After deploy; **manual default** on Free |

No browser E2E, load tests, or multi-Python matrix.

### Acceptance criteria — “green” release

1. PR CI lint + tests green (within free Actions minutes).
2. Railway deploy succeeded on Free/Trial (Wait for CI).
3. Migrations applied on Supabase Free (project **awake**, not paused).
4. Smoke: `GET /health` OK; one CRUD/read path not 5xx.
5. No P0 (data loss, wrong schema, secrets leaked).

If Supabase is paused or Railway Free credit is spent → release is **not** green until wake/credit recovery or temporary local-only demo; upgrading plans is optional, not required for “green.”

---

## 4. Roles for later agents (stages 6–8)

| Stage / agent | Owns | Does not own |
| --- | --- | --- |
| **Stage 6 — build-agent plans** | Final plans: app, migrations, lean CI, test layout, Railway start command sized for Free RAM | Live deploy, buying paid plans |
| **Build agents (post-6)** | Implement app, tests, Dockerfile/start, GHA files that stay minute-cheap | Creating paid Railway/Supabase subscriptions |
| **Stage 7 — deploy agents** | Railway Free/Trial + GitHub verify, env vars, deploy, migrate Supabase Free, wake-from-pause awareness, start smoke | Defaulting to Hobby/Pro without a hard free-tier blocker |
| **Stage 8 — eval agents** | Live eval, light monitoring, version/changelog hygiene | Greenfield features; billing optimization (stage 9) |

Handoff: build agents leave deployable `main` + migrate/start docs; deploy agents wire free-tier secrets and prove smoke green **without** paid upgrades unless a hard limit blocks.

---

## 5. Open risks / assumptions

| # | Item |
| --- | --- |
| 1 | **Assumption:** Default path = GitHub Actions free minutes + Railway Free/Trial + Supabase Free; paid only as escape hatches. |
| 2 | **Assumption:** Single Railway service + single Supabase Free project; no preview envs. |
| 3 | **Assumption:** Deploy = Railway GitHub autodeploy + Wait for CI (not token CD from Actions). |
| 4 | **Risk:** Supabase Free **pause (~1 week idle)** breaks hosted demos until wake — expected; Pro is optional escape. |
| 5 | **Risk:** Railway Free **$1/mo** / **0.5 GB** may stop always-on API — fall back to local or optional Hobby. |
| 6 | **Risk:** Limited Trial outbound restrictions can block Supabase connectivity — verify GitHub on Railway. |
| 7 | **Risk:** Wrong `DATABASE_URL` (pooler/SSL) breaks hosted pools — document in stage 4. |
| 8 | **Risk:** CI + shared Free DB can burn **5 GB egress** — prefer Actions Postgres service for integration tests when practical. |
| 9 | **Soft carry-over:** migration tool and `400` vs `422` chosen in stage 4. |

**Go** to stage 4 (repo framework + design-plan docs including schema) when ready.
