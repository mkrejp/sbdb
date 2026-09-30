# Stage 7 — Build application & deploy

Stage 7 includes an explicit **build application** step, then deploy, DB updates, and smoke testing.

## Sequence

| Step | Action |
| --- | --- |
| 1 | Mirror tested Origin `marek-k-ejpsk/genesis` → GitHub `mkrejp/sbdb` (`release` / `main`) |
| 2 | **Build application** — Docker image from repo `Dockerfile` on Railway (service **sbdb-api** in **zesty-adaptation**); resolve build errors before proceed |
| 3 | Wake Supabase Free **samplebackdb** if paused; apply migrations `001`/`002` if needed |
| 4 | Deploy built service with shared env (`DATABASE_URL`, `LOG_LEVEL`, `PUBLIC_HOSTNAME`) |
| 5 | Smoke: `GET /health` (+ one read path) |
| 6 | Optional: DNS `sbdb.animarium.ai`; NPÚ sync from WSL |

## Build notes

- Source of build: **GitHub** `mkrejp/sbdb`, not Origin directly.  
- Keep image within Railway Free RAM (0.5 GB); single uvicorn worker.  
- Do not commit secrets; use Railway shared variables.  
- Ask immediately if GitHub write, Railway, or `DATABASE_URL` access is missing.

## After stage 7

→ Stage 8: evaluate live app, monitoring, version/changelog/PR promotion.  
→ Stage 9: billing / cost watch.
