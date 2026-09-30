# Stage 4 — Design overview

Implementation design for the Sample DB backend. Stack: **Python FastAPI** + **PostgreSQL via Supabase** (`samplebackdb`, `bsauzwsgiwghkwgehcid`, eu-central-2). CI: GitHub Actions. Host: Railway (later). Public hostname: `sbdb.animarium.ai` (see [dns-sbdb-animarium-ai.md](./dns-sbdb-animarium-ai.md)).

**Domain:** GeoJSON **map layers** (design artifact label: **notes-for-data-model**).

Artifacts: [notes-for-data-model.sql](./notes-for-data-model.sql) · [notes-for-data-model.json](./notes-for-data-model.json) · [api-design.json](./api-design.json)

---

## 1. Components

| Component | Path | Role |
| --- | --- | --- |
| HTTP API | `src/sample_db_backend/` | FastAPI routes, Pydantic validation (`422`) |
| Services | `services/layers.py` | Layers / objects / typed props / tags / URLs |
| Persistence | `db.py` + SQL | `DATABASE_URL` or in-memory stub |
| Migrations | `migrations/*.sql` | Versioned SQL |
| CI | `.github/workflows/ci.yml` | Ruff + pytest |
| Host (later) | Railway | Autodeploy `main`; DB on Supabase |

No auth, queues, or frontend in this slice.

---

## 2. Data model

### Storage choices

| Concern | Choice | Why |
| --- | --- | --- |
| Geometry | **JSONB** GeoJSON | Free-tier friendly; GIN index; PostGIS later if needed |
| Image/binary **properties** | **Supabase Storage refs** on the property row | Avoid large BYTEA; bucket/path/url + metadata |
| Explicit URL lists | **`layer_object_urls`** (1:N, `sort_order`) | Distinct from typed image/binary Storage properties |

### Tables

| Table | Purpose |
| --- | --- |
| `map_layers` | Generic layer containers |
| `layer_objects` | Layer objects / GeoJSON features (`geometry JSONB`) |
| `layer_object_properties` | Typed props: `value_type` ∈ `text\|temporal\|image\|binary` |
| `tags` | Classification labels |
| `layer_object_tags` | M2M objects ↔ tags |
| `layer_object_urls` | Ordered URL list per object |

RLS enabled on all tables; FastAPI uses the Postgres role (bypasses RLS).

---

## 3. API (summary)

Layers, objects, properties, tags (+ attach/detach), URLs. Validation → **422**. Conflicts (unique key/tag) → **409**. Missing → **404**. See [api-design.json](./api-design.json).

---

## 4. Env vars

`DATABASE_URL`, `PORT` (default `8010`), `HOST`, `LOG_LEVEL`, `PUBLIC_HOSTNAME` (`sbdb.animarium.ai`). `.env.example` only — never commit secrets. Prefer Supabase **pooler** URL for Railway.

---

## 5. Migrate / deploy (stage 3 aligned)

```bash
psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql
```

Release: PR → GHA lint+test → merge → Railway Wait-for-CI → migrate Supabase Free → smoke `/health`. Wake Free project if paused. No destructive auto-resets.

---

## 6. Out of scope here

Auth, PostGIS spatial ops, Storage upload helpers (refs only), Alembic, frontend map UI.
