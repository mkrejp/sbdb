# Agents instructions — Sample DB backend (genesis)

Reference for any agent working on this repository. Prefer this file plus `docs/` over chat history.

**Repo:** [marek-k-ejpsk/genesis](https://cursor.com/codebase/marek-k-ejpsk/genesis)  
**Project store (Context):** also mirrors plans under the Sample DB backend Project store.

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
| **7** | Deploy; DB data updates; deployment agents put release online and start testing |
| **8** | Test/evaluate deployed app; monitoring setup changes; version numbering, changelog, PR version promotion |
| **9** | Watch billing; cost-of-running estimates; financial optimization (tokens + hosting) |

**Build agents implement after stage 6 final plans.** Stage 4 introduces framework + design docs only (not full feature productization). Stages 1–3: no scaffolding.

---

## 3. Stack & infra (locked)

- **App:** Python + FastAPI  
- **DB:** PostgreSQL via **Supabase** project **samplebackdb** (`bsauzwsgiwghkwgehcid`, `eu-central-2`, Free)  
- **CI:** GitHub Actions  
- **Host:** Railway (free/trial preferred; Hobby only as escape hatch)  
- **Public hostname:** `sbdb.animarium.ai` → Railway (see `docs` / Context DNS notes)  
- **Cost posture:** all free if possible; paid only as escape hatches  
- **Validation:** FastAPI default **422** for request validation  

---

## 4. Domain & data model (locked)

Design artifact label: **notes-for-data-model**. Domain is **GeoJSON map layers**, not simple notes CRUD.

### Tables (conceptual)

| Table | Role |
| --- | --- |
| `map_layers` | Layer containers (`source_url`, `source_key`, …) |
| `layer_objects` | GeoJSON features (`geometry` JSONB; `npu_objectid` for sync) |
| `layer_object_properties` | Typed props: **text** / **temporal** / **image** / **binary** (Storage refs for image/binary, not large BYTEA) |
| `tags` + `layer_object_tags` | Classification (M2M) |
| `layer_object_urls` | Ordered list of URLs per object (1:N) |

---

## 5. NPÚ initial data fill (locked)

- Source: **NPÚ Geoportal REST**, primarily **MapServer** (same query API as FeatureServer: `f=geojson`, pagination).  
- Portal: https://npu.cz · host: `geoportal.npu.cz`  
- **`NPU_LAYER_URL`:**  
  `https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0`  
- Page with `resultOffset` / `resultRecordCount`; respect `maxRecordCount` (often 2000). Never assume a single `where=1=1` returns all rows.  
- Upsert on `OBJECTID` / `id` → `npu_objectid`.  
- CLI: `uv run sample-db-npu-sync` (see repo sync module).  
- Request headers used in probes: `User-Agent: YourSyncBot/1.0`, `Accept: application/json`.  
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
22. **This step:** document prompts/decisions as **agents-instructions** in the repo for other agents.

---

## 8. Doc map (read these)

| Doc | Purpose |
| --- | --- |
| This file (`docs/agents-instructions.md`) | Standing agent brief |
| Stage 1–3 plans | Architecture, cost, DevOps/QA (Context and/or `docs/`) |
| Stage 4 design (`notes-for-data-model.*`, API design) | Schema + API |
| Stage 5 (`stage-five-tooling-and-optimizations.md`) | Pipeline/app tooling + perf; Cursor-plan tooling |
| Stage 6 (`stage-six-final-build-plans.md`) | Final build-agent work packages (implement **after user approves**) |
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

- Stage 4 framework merged to `main` via PR #1 (`775339a` on user clone).  
- Supabase schema applied on **samplebackdb**.  
- Live NPÚ `/query` may need user’s network (WAF on some cloud IPs) — prefer WSL `/home/cursor/dev/genesis`.  
- **Stage 5 done:** tooling + optimizations → [stage-five-tooling-and-optimizations.md](./stage-five-tooling-and-optimizations.md).  
- **Stage 6 done (plans only):** [stage-six-final-build-plans.md](./stage-six-final-build-plans.md) — confirmed locks, `main` vs gaps, WP-A–E for build agents, NPÚ/WAF/WSL notes, stage 7–8 deploy handoff, do-not-reopen list.  
- **Stage 6 approved → WP-A–E in draft PR #4** (`cursor/wp-a-e-harden-8c7c`): NPU defaults, API/sync harden, pre-commit/CI format, Dockerfile + Railway prep docs. No stage-7 deploy / live NPÚ fill from agents until authorized.  
- After merge → stage 7 (deploy / DB updates / smoke) and stage 8 (eval / monitoring / version hygiene).
