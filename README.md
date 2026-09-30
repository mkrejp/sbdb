# Sample DB backend

**Python FastAPI** + **PostgreSQL on Supabase**. Domain: **GeoJSON map layers** (design artifact: **notes-for-data-model**).

| Item | Value |
| --- | --- |
| Supabase | `samplebackdb` (`bsauzwsgiwghkwgehcid`, eu-central-2, Free) |
| Public host (later) | `sbdb.animarium.ai` → Railway |
| CI / host | GitHub Actions · Railway (no Railway Postgres) |
| Geometry | JSONB GeoJSON |
| Image/binary props | Supabase Storage refs (not BYTEA) |
| Object URLs | `layer_object_urls` ordered 1:N list |

## Quick start

```bash
uv sync --group dev
cp .env.example .env   # optional DATABASE_URL
uv run sample-db-backend
curl -s http://127.0.0.1:8010/health
```

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
uv run ruff check src tests && uv run pytest -q
```

## Design docs

- [Design overview](docs/design-overview.md)
- [Schema SQL](docs/notes-for-data-model.sql) · [Schema JSON](docs/notes-for-data-model.json)
- [API design](docs/api-design.json)

## Tables

`map_layers` → `layer_objects` → `layer_object_properties` / `layer_object_urls` / `layer_object_tags` ↔ `tags`

Validation errors: HTTP **422**.
