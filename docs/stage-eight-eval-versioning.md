# Stage 8 — Evaluate live app, monitoring, versioning

Post-deploy evaluation after Stage 7. **Do not push GitHub** — Marek mirrors Origin `marek-k-ejpsk/genesis` → GitHub `mkrejp/sbdb` from WSL. Railway **zesty-adaptation** / **sbdb-api** rebuilds from `mkrejp/sbdb` `main`. Stage 9 (billing) is later.

## Preconditions

| Check | Done when |
| --- | --- |
| Origin `main` tip mirrored to GitHub `mkrejp/sbdb` `main` | SHAs match (compare Origin tip ↔ `gh`/`get_commit` on `mkrejp/sbdb`) |
| Railway deploy SUCCESS for that SHA | `list-deployments` / dashboard shows SUCCESS, not BUILDING/FAILED |
| Custom domain | https://sbdb.animarium.ai reaches **sbdb-api** (:8080) |
| Supabase **samplebackdb** awake | Not paused; migrations `001`–`004` applied as needed |

## A. Live smoke (required)

Run against **https://sbdb.animarium.ai** (prefer curl; save Actions minutes).

| # | Call | Expect |
| --- | --- | --- |
| 1 | `GET /health` | **200** `{"status":"ok","database":"connected"}` (not `degraded` / Railway “Application not found”) |
| 2 | `GET /layers?limit=5` | **200** with NPÚ layer present when sync has run |
| 3 | `GET /layers/{id}/objects?limit=2` | **200** GeoJSON `geometry` (Polygon/etc.) |
| 4 | `GET /objects?limit=2` | **200**; after #14 deploy: NPÚ columns on `LayerObject` (`npu_objectid`, `hlavni_prvek`, `pr_stav_nazev`, …) |
| 5 | `GET /openapi.json` → `info.version` | Matches advertised package version after promotion |
| 6 | Optional light write | Create → get → delete a throwaway layer/object; expect **422** on bad body, **404** on missing UUID |

**Note PostGIS / attrs:** Geometry is GeoJSON in API responses (PostGIS dual-write under the hood when migration `003` is applied). Attribute columns appear on `/objects` only after mirror includes #14 **and** Railway has rebuilt that SHA. Null attrs on older sync rows are OK until WSL re-sync dual-writes.

**Out of scope for cloud agents:** full NPÚ `/query` sync (WAF) — Marek keeps sync on WSL.

## B. Monitoring (free-tier only)

No paid APM. Adjust only what Free/Trial already provides.

| Surface | Action |
| --- | --- |
| Railway | Confirm healthcheck path `/health` (timeout ~120s); watch deploy logs on FAIL/CRASH; single replica, ≤0.5 GB RAM, one uvicorn worker |
| Railway metrics | Spot-check CPU/RAM after smoke; if OOM → reduce concurrency / stay Free escape notes for Stage 9 |
| Supabase | Dashboard **Advisors** (security/perf); wake if paused; watch Free **500 MB** / egress |
| DNS | `sbdb.animarium.ai` CNAME → Railway; no extra CDN monitoring |
| Alerts | Optional: Railway webhook or email on deploy fail only — **no** cron-heavy Actions, **no** paid Datadog/Sentry |

**Do not:** add second Railway env, PR previews, or always-on paid monitors.

## C. Semver + changelog

Current advertised version: **0.1.0** (`pyproject.toml` + FastAPI `info.version`).

| Bump | When |
| --- | --- |
| **0.2.0** (proposed) | First public deploy slice is live + PostGIS schema (#13) + NPÚ attribute columns (#14) + successful Railway rebuild from mirrored tip — **after** smoke A confirms attrs on API |
| **0.2.x** | Docs/monitoring-only or small fixes post-0.2.0 |
| **0.3.0+** | Later feature slices (not Stage 8 default) |

**Changelog rules**

- Draft `CHANGELOG.md` (Keep a Changelog style): Added / Fixed / Changed only for **verified** merges (`#7` lock, `#12` skip-existing, `#13` PostGIS, `#14` NPÚ columns, live health/layers/objects).
- Do **not** claim full NPÚ layer completeness, billing readiness, or untested CRUD edge cases.
- Bump in lockstep: `pyproject.toml` `version`, FastAPI `version=` in `main.py`, OpenAPI `info.version`, changelog header.

## D. PR version promotion (Origin)

1. Branch off Origin `main`: `cursor/stage-eight-v0-2-0-d808` (or current agent suffix).
2. Docs + version + changelog **only** (no feature code in the promotion PR).
3. Open **draft** Origin PR; wait for CI green.
4. Marek merges (ask immediately if merge permissions / CI blocked).
5. After merge: Marek mirrors to `mkrejp/sbdb`; Railway rebuilds; re-check `GET /openapi.json` → `0.2.0`.

**Agents must not** `git push` to GitHub `mkrejp/sbdb`.

## E. Exit criteria → Stage 9

- [ ] Smoke A green on current mirrored SHA  
- [ ] Monitoring B notes recorded (no paid add-ons)  
- [ ] Version/changelog PR merged (or explicitly deferred by Marek)  
- [ ] Mirrored tip serves matching `info.version`  
- [ ] Handoff: Stage 9 billing / cost watch  

## Status snapshot (2026-09-30)

| Item | Status |
| --- | --- |
| Mirror | GitHub `mkrejp/sbdb` `main` = `b42d1c2` (#14) — matches Origin tip (`d7fa3f7..b42d1c2`) |
| Railway | Deploy `7304b0dc…` **SUCCESS** · commit `b42d1c2` · **sbdb-api** production |
| Health / smoke | `GET /health` **200** ok/connected; layers/objects **200**; NPÚ columns + Polygon geom present; light create/422/delete/404 OK |
| Free-tier metrics | ~1h: CPU avg ~0.2%; RAM avg ~0.10 GB / max ~0.27 GB (under 0.5 GB Free) |
| Version PR | **0.2.0** changelog + version bump (this PR) |
| Marek still | Merge version PR when CI green; mirror again so OpenAPI `info.version` becomes `0.2.0` |
