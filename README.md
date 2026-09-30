# Sample DB backend

**Python FastAPI** + **PostgreSQL on Supabase**. Domain: **GeoJSON map layers** (design artifact: **notes-for-data-model**). Initial fill: **NPÚ Geoportal** paged sync.

| Item | Value |
| --- | --- |
| Supabase | `samplebackdb` (`bsauzwsgiwghkwgehcid`, eu-central-2, Free) |
| Public host (later) | `sbdb.animarium.ai` → Railway |
| CI / host | GitHub Actions · Railway (no Railway Postgres) |
| Geometry | JSONB GeoJSON |
| Image/binary props | Supabase Storage refs (not BYTEA) |
| Object URLs | `layer_object_urls` ordered 1:N list |
| Ingest | `uv run sample-db-npu-sync` ← [NPÚ practices](docs/npu-geoportal-sync.md) |

## Quick start

```bash
uv sync --group dev
cp .env.example .env   # set DATABASE_URL; optional NPU_LAYER_URL
uv run sample-db-backend
curl -s http://127.0.0.1:8010/health
```

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
psql "$DATABASE_URL" -f migrations/002_npu_sync_keys.sql
# After setting NPU_LAYER_URL to a concrete FeatureServer layer root:
uv run sample-db-npu-sync
uv run ruff check src tests && uv run pytest -q
```

`NPU_LAYER_URL` is a **placeholder** in `.env.example` until the exact NPÚ Geoportal FeatureServer/MapServer layer is chosen (portal: [npu.cz](https://npu.cz)).

## Documentation

- [Agents instructions](docs/agents-instructions.md) — standing brief for agents working on this repo

## Design docs

- [Design overview](docs/design-overview.md)
- [NPÚ sync practices](docs/npu-geoportal-sync.md)
- [Schema SQL](docs/notes-for-data-model.sql) · [Schema JSON](docs/notes-for-data-model.json)
- [API design](docs/api-design.json)

## Tables

`map_layers` → `layer_objects` → `layer_object_properties` / `layer_object_urls` / `layer_object_tags` ↔ `tags`

Validation errors: HTTP **422**.
