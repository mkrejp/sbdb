# Stage 4 — Design overview

Implementation design for the Sample DB backend. Stack: **Python FastAPI** + **PostgreSQL via Supabase** (`samplebackdb`, `bsauzwsgiwghkwgehcid`, eu-central-2). CI: GitHub Actions. Host: Railway (later). Public hostname: `sbdb.animarium.ai` (see [dns-sbdb-animarium-ai.md](./dns-sbdb-animarium-ai.md)).

**Domain:** GeoJSON **map layers** (design artifact label: **notes-for-data-model**).

**Initial fill:** [NPÚ Geoportal REST](./npu-geoportal-sync.md) via bash+wget (ID list → detail) + Python upsert (`scripts/sample-db-npu-sync`, `sync/npu_geoportal.py`).

Artifacts: [notes-for-data-model.sql](./notes-for-data-model.sql) · [notes-for-data-model.json](./notes-for-data-model.json) · [api-design.json](./api-design.json) · [npu-geoportal-sync.md](./npu-geoportal-sync.md)

---

## 1. Components

| Component | Path | Role |
| --- | --- | --- |
| HTTP API | `src/sample_db_backend/` | FastAPI routes, Pydantic validation (`422`) |
| Services | `services/layers.py` | Layers / objects / typed props / tags / URLs |
| NPÚ sync | `scripts/sample-db-npu-sync` + `sync/npu_geoportal.py` | Bash/wget list→detail; Python upsert (CLI `sample-db-npu-sync`) |
| Persistence | `db.py` + SQL | `DATABASE_URL` or in-memory stub |
| Migrations | `migrations/*.sql` | Versioned SQL (`001` schema, `002` NPÚ keys) |
| CI | `.github/workflows/ci.yml` | Ruff + pytest |
| Host (later) | Railway | Autodeploy `main`; DB on Supabase |

No auth, queues, or frontend in this slice.

---

## 2. Data model

### Storage choices

| Concern | Choice | Why |
| --- | --- | --- |
| Geometry | **PostGIS** `geom` (EPSG:4326) + JSONB dual-write | GIST on `geom`; REST returns GeoJSON via `ST_AsGeoJSON` |
| Image/binary **properties** | **Supabase Storage refs** | Avoid BYTEA; distinct from URL lists |
| Explicit URL lists | **`layer_object_urls`** | Ordered 1:N per object |
| NPÚ identity | **`layer_objects.npu_objectid`** | Upsert key (`OBJECTID`/`id`); unique per layer |

### Tables

| Table | Purpose |
| --- | --- |
| `map_layers` | Layer containers (+ `source_key` / `source_url` for NPÚ) |
| `layer_objects` | GeoJSON features (`geometry JSONB`, `npu_objectid`) |
| `layer_object_properties` | Typed props: `text` / `temporal` / `image` / `binary` |
| `tags` | Classification labels |
| `layer_object_tags` | M2M objects ↔ tags |
| `layer_object_urls` | Ordered URL list per object |

RLS enabled; FastAPI / sync use the Postgres role (bypasses RLS).

---

## 3. NPÚ ingest path

Practices: [npu-geoportal-sync.md](./npu-geoportal-sync.md) (do not invent a different approach).

1. Read **layer root** metadata → `maxRecordCount`, `supportsPagination`.
2. Page `…/query` with `where=1=1`, `outFields=*`, `outSR=4326`, `f=geojson`, `resultOffset`, `resultRecordCount≤max`.
3. Stream each page → upsert (avoid loading entire huge layers into memory).
4. Upsert: `INSERT … ON CONFLICT (layer_id, npu_objectid) DO UPDATE` geometry; refresh properties/tags/urls for that object.

### Field mapping (NPÚ → app)

| NPÚ source | App target |
| --- | --- |
| MapServer layer root + metadata `name` | `map_layers` (`source_url`, `source_key=npu:<url>`, `name`) |
| Feature `geometry` (WGS84 GeoJSON) | `layer_objects.geometry` (JSONB) |
| `properties.OBJECTID` or `properties.id` | `layer_objects.npu_objectid` (sync key) |
| Attributes in `NPU_TAG_FIELDS` (default `TYP,KATEGORIE,DRUH,STATUS,TYP_PAM`) | `tags` + `layer_object_tags` |
| Attributes in `NPU_URL_FIELDS` or values matching `http(s)://` | `layer_object_urls` (`label`=field name, `sort_order`) |
| Date-like attrs (`DATUM`/`DATE`/… or epoch ms) | `layer_object_properties` `value_type=temporal` |
| Remaining scalar attrs | `layer_object_properties` `value_type=text` |
| Image/binary Storage | Not filled by NPÚ sync (manual / later); keep Storage-ref model |

### Config

| Env | Purpose |
| --- | --- |
| `NPU_LAYER_URL` | Locked MapServer layer root `…/Tematicke/CP_UAP_PVO/MapServer/0` — see `.env.example` |
| `NPU_LAYER_NAME` | Optional override for `map_layers.name` |
| `NPU_TAG_FIELDS` / `NPU_URL_FIELDS` | Comma-separated attribute → tags / URLs |

```bash
./scripts/sample-db-npu-sync
# or: uv run sample-db-npu-sync
```

Requires `DATABASE_URL` + `NPU_LAYER_URL`. No secrets in git.

---

## 4. API (summary)

Layers, objects, properties, tags, URLs. Validation → **422**. See [api-design.json](./api-design.json).

---

## 5. Env vars

`DATABASE_URL`, `PORT`, `HOST`, `LOG_LEVEL`, `PUBLIC_HOSTNAME`, plus NPÚ vars above. Prefer Supabase **pooler** for Railway.

---

## 6. Migrate / deploy

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
psql "$DATABASE_URL" -f migrations/002_npu_sync_keys.sql   # if upgrading from 001-only
```

Then optional: `./scripts/sample-db-npu-sync` (or `uv run sample-db-npu-sync`) for initial fill. Schedule weekly/monthly later (stage 7).

---

## 7. Out of scope here

Auth, Storage upload helpers, Alembic, frontend map UI, bbox/intersects query endpoints (PostGIS geom is in place).
