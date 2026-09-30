# Agents instructions — Sample DB backend (genesis)

Reference for any agent working on this repository. Prefer this file plus `docs/` over chat history.

**Dev repo (Origin):** [marek-k-ejpsk/genesis](https://cursor.com/codebase/marek-k-ejpsk/genesis)  
**Release mirror (GitHub):** [mkrejp/sbdb](https://github.com/mkrejp/sbdb) — environment **release** holds tested code mirrored from Origin  
**Host:** Railway project **zesty-adaptation**, service **sbdb-api** (deploys from GitHub `mkrejp/sbdb`, not Origin directly)  
**Project store (Context):** also mirrors plans under the Sample DB backend Project store.

### Repo roles (locked)

| Role | Location | Notes |
| --- | --- | --- |
| Development / PRs | Origin `marek-k-ejpsk/genesis` | Primary working tree; Cursor/Origin PRs land here first |
| Tested release mirror | GitHub `mkrejp/sbdb` · env **release** | Mirror **tested** Origin `main` (or release tag) here for deploy |
| Production deploy | Railway **zesty-adaptation** / **sbdb-api** | Build from `mkrejp/sbdb` `main` (or release branch); shared vars `DATABASE_URL`, `LOG_LEVEL`, `PUBLIC_HOSTNAME` |
| Local WSL | `/home/cursor/dev/genesis` | Prefer for NPÚ sync (cloud IPs often WAF-blocked) |

**Mirror rule:** do not treat empty `mkrejp/sbdb` as source of truth. After Origin merges are approved/tested → push/mirror to GitHub → Railway redeploys. Ask immediately if GitHub write auth / PAT is missing.

---

## 1. Mission

Build a **sample DB backend** in stages: plan first, then framework and design docs, then tooling/optimization analysis, final build-agent plans, deploy, evaluate, and cost watch. Stay **free-tier by default**.

---

## 2. Delivery stages (locked)

| Stage | Deliverable |
| --- | --- |
| **1** | Overall plan: components, interactions, connections |
| **2** | Verify plan for functions; compute possible costs of running |
| **3** | DevOps delivery plans + testing/QA process |
| **4** | Initial repo framework + design-plan docs (Markdown + SQL/JSON) |
| **5** | Evaluate tooling (plugins/addons/extensions) for pipeline and app; suggest delivery-pipeline and performance optimizations |
| **6** | Rethink stages 1–5; create **final plans for build agents** to implement the app |
| **7** | **Build** application (Docker/image from GitHub release mirror); deploy; DB data updates; deployment agents put release online and start testing |
| **8** | Test/evaluate deployed app; monitoring setup changes; version numbering, changelog, PR version promotion |
| **9** | Watch billing; cost-of-running estimates; financial optimization (tokens + hosting) |

**Build agents implement after stage 6 final plans.** Stage 4 introduces framework + design docs only (not full feature productization). Stages 1–3: no scaffolding.

---

## 3. Stack & infra (locked)

- **App:** Python + FastAPI  
- **DB:** PostgreSQL via **Supabase** project **samplebackdb** (`bsauzwsgiwghkwgehcid`, `eu-central-2`, Free)  
- **CI:** GitHub Actions (on Origin/GitHub as wired; deploy CI path uses `mkrejp/sbdb`)  
- **Host:** Railway **zesty-adaptation** / **sbdb-api** (Trial/Free; Hobby only as escape hatch) — source **GitHub `mkrejp/sbdb`**  
- **Public hostname:** `sbdb.animarium.ai` → Railway (see DNS notes)  
- **Cost posture:** all free if possible; paid only as escape hatches  
- **Validation:** FastAPI default **422** for request validation  

---

## 4. Domain & data model (locked)

Design artifact label: **notes-for-data-model**. Domain is **GeoJSON map layers**, not simple notes CRUD.

### Tables (conceptual)

| Table | Role |
| --- | --- |
| `map_layers` | Layer containers (`source_url`, `source_key`, …) |
| `layer_objects` | GeoJSON features (`geom` PostGIS EPSG:4326 + `geometry` JSONB dual-write; `npu_objectid` for sync) |
| `layer_object_properties` | Typed props: **text** / **temporal** / **image** / **binary** (Storage refs for image/binary, not large BYTEA) |
| `tags` + `layer_object_tags` | Classification (M2M) |
| `layer_object_urls` | Ordered list of URLs per object (1:N) |

---

## 5. NPÚ initial data fill (locked)

- Source: **NPÚ Geoportal REST**, primarily **MapServer** (same query API as FeatureServer: `f=geojson`, pagination).  
- Portal: https://npu.cz · host: `geoportal.npu.cz`  
- **`NPU_LAYER_URL`:**  
  `https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0`  
- Flow: **bash** orchestrates; **wget** fetches ID list (`returnIdsOnly` → `pamatky.json`) then per-object/small-batch **detail**; **Python** transforms + upserts only.  
- Page ID lists with `resultOffset` / `resultRecordCount`; respect `maxRecordCount` (often 2000). Never assume a single `where=1=1` returns all rows.  
- Upsert on `OBJECTID` / `id` → `npu_objectid`.  
- CLI: `./scripts/sample-db-npu-sync` or `uv run sample-db-npu-sync` (thin wrapper → bash).  
- wget CLI shape: `wget -O <file> --timeout=N --tries=1 <url>` (URL last; no other wget flags).  
- **Cloud agent IPs may be WAF-blocked** on `/query`; prefer running sync from the user’s WSL/network.

Practices detail: `docs/npu-geoportal-sync.md` (and Project Context mirror).

---

## 6. Working style (user preferences)

1. At each stage, ask **only** questions needed for an optimal solution; **speed**, no overthinking.  
2. If stuck on missing **CLI/SSH credentials** or **API keys** that should already exist → **ask the user immediately**; do not spin.  
3. Never commit secrets (Supabase tokens, `DATABASE_URL`, Origin tokens). Env/secrets only; `.env.example` without values.  
4. A Supabase personal access token was once pasted in chat — treat as compromised; rotate; never store in git/Context docs.

---

## 7. Key user prompts / decisions (chronology)

Use as intent history; current locks above override if anything conflicts.

1. No build at first — stages: plan → later data model.  
2. Stage 2 = function verify + running costs.  
3. Stage 3 = DevOps + testing/QA process plans.  
4. Stage 4 = initial framework in repo + design docs (md + sql/json).  
5. Stage 5 = tooling plugins/addons/extensions + pipeline/app performance suggestions.  
6. Stage 6 = rethink 1–5 → final plans for build agents.  
7. Stage 7 = deploy, DB data updates, deployment agents online + start testing.  
8. Stage 8 = test/eval deployed app, monitoring changes, version/changelog/PR promotion.  
9. Stage 9 = billing watch, cost estimates, token/hosting financial optimizations.  
10. Each stage: ask necessary questions; speed; no overthinking.  
11. Stack: Python FastAPI + Postgres from Supabase.  
12. CI: GitHub Actions; host: Railway; include DevOps integrations for both; **all free if possible**.  
13. Supabase project name: **samplebackdb** (created Free).  
14. DNS: **sbdb.animarium.ai**; document setup.  
15. Design name **notes-for-data-model**; then domain = GeoJSON map layers + property tables.  
16. Properties: textual, temporal, images, other binary; objects have **tags**.  
17. Each object has a **list of URLs**.  
18. Initial fill via NPÚ REST with pagination practices (offset / maxRecordCount).  
19. If missing CLI/SSH/API credentials → ask immediately.  
20. NPÚ uses **MapServer**; portal npu.cz; concrete layer **CP_UAP_PVO/MapServer/0** on `geoportal.npu.cz`.  
21. WSL project path: `/home/cursor/dev/genesis`; Origin repo private.  
22. Document prompts/decisions as **agents-instructions** in the repo for other agents.  
23. GitHub deploy mirror: **mkrejp/sbdb** with environment **release**; Railway **zesty-adaptation** deploys from that mirror (shared DB env vars).  
24. Stage 7 includes explicit **build application** (Docker from `mkrejp/sbdb`) before deploy/smoke.

---

## 8. Doc map (read these)

| Doc | Purpose |
| --- | --- |
| This file (`docs/agents-instructions.md`) | Standing agent brief |
| Stage 1–3 plans | Architecture, cost, DevOps/QA (Context and/or `docs/`) |
| Stage 4 design (`notes-for-data-model.*`, API design) | Schema + API |
| Stage 5 (`stage-five-tooling-and-optimizations.md`) | Pipeline/app tooling + perf; Cursor-plan tooling |
| Stage 6 (`stage-six-final-build-plans.md`) | Final build-agent work packages (implement **after user approves**) |
| Stage 7 (`stage-seven-build-and-deploy.md`) | **Build** app image + deploy + DB updates + smoke |
| Stage 8 (`stage-eight-eval-versioning.md`) | Live smoke, free-tier monitoring, semver/changelog, PR promotion |
| `npu-geoportal-sync.md` | NPÚ pagination / upsert practices |
| DNS notes for `sbdb.animarium.ai` | CNAME → Railway |

---

## 9. Do / don’t

**Do**

- Keep changes minimal and stage-appropriate.  
- Prefer free tiers; document escape hatches.  
- Parameterized SQL; migrations versioned.  
- Open draft PRs; watch CI.  
- Ask immediately on credential blockers.

**Don’t**

- Reopen locked stack/domain choices without user confirmation.  
- Commit secrets or paste tokens into docs.  
- Assume FeatureServer-only for NPÚ (MapServer is primary).  
- Load entire NPÚ layers without pagination.  
- Start full “build agent” implementation before stage 6 final plans are **approved by the user**.

---

## 10. Current handoff snapshot

- Origin `main` tip `b42d1c2` (#14 NPÚ attribute columns); mirrored to GitHub `mkrejp/sbdb` `main`; Railway **sbdb-api** SUCCESS on that SHA.  
- Live: https://sbdb.animarium.ai — `/health` ok/connected; layers/objects with GeoJSON + NPÚ attrs.  
- Supabase **samplebackdb**: migrations through `npu_attribute_columns` (004).  
- **Deploy topology:** Origin genesis → Marek WSL mirror → [mkrejp/sbdb](https://github.com/mkrejp/sbdb) → Railway **zesty-adaptation** / **sbdb-api**. Agents do **not** push GitHub.  
- **Stage 8:** [stage-eight-eval-versioning.md](./stage-eight-eval-versioning.md) — smoke + free-tier monitoring + **0.2.0** version/changelog promotion.  
- Live NPÚ `/query`: prefer WSL (cloud WAF). Stage 9 = billing later.
