# Sample DB backend

**Python FastAPI** + **PostgreSQL on Supabase**. Domain: **GeoJSON map layers** (design artifact: **notes-for-data-model**). Initial fill: **NPÚ Geoportal** paged MapServer sync.

| Item | Value |
| --- | --- |
| Supabase | `samplebackdb` (`bsauzwsgiwghkwgehcid`, eu-central-2, Free) |
| Public host (later) | `sbdb.animarium.ai` → Railway |
| Dev → deploy | Origin `marek-k-ejpsk/genesis` → GitHub `mkrejp/sbdb` (env **release**) → Railway **zesty-adaptation** / **sbdb-api** |
| CI / host | GitHub Actions · Railway (no Railway Postgres) |
| Geometry | JSONB GeoJSON |
| Image/binary props | Supabase Storage refs (not BYTEA) |
| Object URLs | `layer_object_urls` ordered 1:N list |
| Ingest | `uv run sample-db-npu-sync` ← [NPÚ practices](docs/npu-geoportal-sync.md) |
| Locked layer | `…/Tematicke/CP_UAP_PVO/MapServer/0` |

## Quick start

```bash
uv sync --group dev
cp .env.example .env   # set DATABASE_URL; NPU_LAYER_URL defaults to locked MapServer/0
uv run sample-db-backend
curl -s http://127.0.0.1:8010/health
```

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
psql "$DATABASE_URL" -f migrations/002_npu_sync_keys.sql
# Live NPÚ sync: prefer user WSL (/home/cursor/dev/genesis) — cloud IPs may be WAF-blocked
uv run sample-db-npu-sync
uv run ruff check src tests && uv run ruff format --check src tests && uv run pytest -q
```

`NPU_LAYER_URL` is locked to the CP_UAP_PVO MapServer layer (see `.env.example` and [NPÚ sync](docs/npu-geoportal-sync.md)).

## Deploy prep (stage 7 — do not deploy from this slice)

Artifacts only; **no live Railway deploy** from build agents.

### Dockerfile

```bash
docker build -t sample-db-backend .
# Optional local check (stub mode if DATABASE_URL unset):
docker run --rm -e PORT=8010 -p 8010:8010 sample-db-backend
```

Image is single-worker uvicorn, sized for Railway Free (~0.5 GB RAM).

### Railway start command

```bash
uv run uvicorn sample_db_backend.main:app --host 0.0.0.0 --port $PORT
```

Or use the Dockerfile `CMD` (same shape). Prefer **Wait for CI** autodeploy on `main`. Do **not** provision Railway Postgres — use Supabase pooler `DATABASE_URL`.

### Required Railway variables

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | Supabase **pooler** URL + SSL (not Railway Postgres) |
| `PORT` | Set by Railway |
| `LOG_LEVEL` | e.g. `INFO` |
| `PUBLIC_HOSTNAME` | `sbdb.animarium.ai` (DNS later — [dns doc](docs/dns-sbdb-animarium-ai.md)) |
| `NPU_*` | Optional; defaults lock CP_UAP_PVO MapServer + field maps |

### Migrate (explicit `psql`, not Alembic)

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
psql "$DATABASE_URL" -f migrations/002_npu_sync_keys.sql
```

Wake Supabase Free if paused before migrate/deploy. Secrets stay in Railway/env only — never commit.

## Documentation

- [Agents instructions](docs/agents-instructions.md) — standing brief for agents working on this repo
- [Stage 5 — tooling & optimizations](docs/stage-five-tooling-and-optimizations.md) — pipeline/app tooling; Cursor-plan recommendations
- [Stage 6 — final build-agent plans](docs/stage-six-final-build-plans.md) — WP-A–E; implement after user approval (not deploy yet)
- [Stage 1–4 build plans](docs/stage-one-architecture-plan.md) — architecture → function/cost → DevOps/QA → [design overview](docs/stage-four-design-overview.md)

## Design docs

- [Design overview](docs/design-overview.md) · [Stage 4 design plan](docs/stage-four-design-overview.md)
- [NPÚ sync practices](docs/npu-geoportal-sync.md)
- [DNS — sbdb.animarium.ai](docs/dns-sbdb-animarium-ai.md)
- [Schema SQL](docs/notes-for-data-model.sql) · [Schema JSON](docs/notes-for-data-model.json)
- [API design](docs/api-design.json)

## Tables

`map_layers` → `layer_objects` → `layer_object_properties` / `layer_object_urls` / `layer_object_tags` ↔ `tags`

Validation errors: HTTP **422**.
