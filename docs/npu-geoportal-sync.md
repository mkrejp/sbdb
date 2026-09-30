# NPÚ Geoportal REST — mirror & sync practices

Initial data fill for map layers comes from the **NPÚ Geoportal REST Services** (ArcGIS). NPÚ primarily publishes via **MapServer** (read-only query), not editable FeatureServer. MapServer layers expose the same query operations used here (`f=json` / `f=geojson`, pagination, `returnIdsOnly`, `objectIds=`).

Portal entry: [npu.cz](https://npu.cz) · REST directory: [geoportal.npu.cz/arcgis/rest/services](https://geoportal.npu.cz/arcgis/rest/services)

## Architecture (bash + wget + Python insert)

| Role | Owns |
| --- | --- |
| **Bash** (`scripts/sample-db-npu-sync`) | Orchestration: pages, retries, temp files, timeouts |
| **wget only** | All HTTP fetches from NPÚ / source |
| **Python** (`sample_db_backend.sync.npu_geoportal`) | Parse/transform JSON + **inserts/upserts** into destination Postgres (`DATABASE_URL`) |

Happy path: **no** httpx/requests/subprocess-wget inside Python for NPÚ.

### Marek flow

1. **`wget -O pamatky.json`** — fetch the object **list** JSON (`returnIdsOnly`).
2. **For each** OBJECTID (small batches via `NPU_DETAIL_BATCH`, default 10): wget the **detail** GeoJSON.
3. **Python** transforms + upserts into destination (one DB transaction per detail file).

## Locked layer (`NPU_LAYER_URL`)

| Item | Value |
| --- | --- |
| Layer root | `https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0` |
| Name | Národní kulturní památky (Feature Layer, polygons) |
| `maxRecordCount` | 2000 |
| Pagination | `supportsPagination: true` |
| Sync CLI | `./scripts/sample-db-npu-sync` or `uv run sample-db-npu-sync` (requires `DATABASE_URL`) |

`https://npu.cz` is the HTML portal only — **not** the object-list JSON.

## MapServer URLs (documented)

Let `LAYER` = `$NPU_LAYER_URL` (layer root, no trailing `/query`).

### 0) Metadata (paging caps + name)

```bash
wget -O meta.json --timeout=60 --tries=1 \
  "${LAYER}?f=json"
```

### 1) Object **list** page → `pamatky.json`

```bash
wget -O pamatky.json --timeout=60 --tries=1 \
  "${LAYER}/query?where=1%3D1&returnIdsOnly=true&returnGeometry=false&resultOffset=0&resultRecordCount=1000&f=json"
```

Response shape: `{"objectIdFieldName":"OBJECTID","objectIds":[…]}`. Advance `resultOffset` by `len(objectIds)`; stop on empty / short page.

### 2) Per-object (or small-batch) **detail**

```bash
wget -O detail.json --timeout=60 --tries=1 \
  "${LAYER}/query?objectIds=101,102&outFields=*&outSR=4326&returnGeometry=true&f=geojson"
```

### 3) Python insert

```bash
uv run python -m sample_db_backend.sync.npu_geoportal upsert-file detail.json \
  --layer-id "$LAYER_ID" --database-url "$DATABASE_URL"
```

Upsert key: NPÚ `OBJECTID` → `layer_objects.npu_objectid` (per-page/detail-file transaction).

## Limits

- Server enforces `maxRecordCount` (this layer: **2000**).
- Client list page size: **min(maxRecordCount, 1000)**.
- `where=1=1` **without** paging truncates large layers — always page the ID list.
- Detail batch size: `NPU_DETAIL_BATCH` (default **10**).

## Step 1 — Layer rules

Before pulling, wget the **MapServer layer root** metadata (`…/MapServer/<id>?f=json`) and note `maxRecordCount` / `supportsPagination`. Orchestrator wget uses **only** `-O`, `--timeout`, `--tries=1` (URL last); bash owns outer retries via `NPU_MAX_RETRIES`.

## Step 2 — List → detail → insert (blueprint)

1. wget metadata → Python `page-size` / `layer-name` / `ensure-layer`.
2. Loop ID-list pages (`returnIdsOnly` + `resultOffset` / `resultRecordCount`).
3. For each small batch of IDs: wget detail GeoJSON → Python `upsert-file` (one txn).
4. Retries: **1 try + 3 retries (= 4 attempts)** per URL in **bash** (`NPU_MAX_RETRIES`).

## Step 3 — Long-term sync into Postgres

| Phase | Strategy | Method |
| --- | --- | --- |
| Primary keys | Identity binding | NPÚ `OBJECTID` → `layer_objects.npu_objectid` |
| SQL storage | Upsert | `INSERT … ON CONFLICT (layer_id, npu_objectid) DO UPDATE …` |
| Geometry | JSONB GeoJSON | This project; PostGIS optional later |
| Automation | Schedule | Weekly/monthly later (stage 7) |

## Project mapping (CP_UAP_PVO)

| NPÚ | App |
| --- | --- |
| Layer root + name | `map_layers` |
| Feature geometry | `layer_objects.geometry` (JSONB) |
| `OBJECTID` | `layer_objects.npu_objectid` |
| `Subtyp`, `typOchranyKod`, `typOchranyNazev`, `fazeOchranyKod`, `fazeOchranyNazev`, `PrStavNazev` | `tags` / `layer_object_tags` |
| `urlExt`, `urlInt` | `layer_object_urls` |
| `platn_od`, `platn_do`, `aktual`, `datumStavuOchrany` | `layer_object_properties` (`temporal`) — year ∈ `[1000, now+5]`, UTC; unparseable → `text` |
| Other scalars (e.g. `nazev`) | `layer_object_properties` (`text`) |

## Field-config defaults (`NPU_*`)

| Env | Default fields |
| --- | --- |
| `NPU_TAG_FIELDS` | `Subtyp,typOchranyKod,typOchranyNazev,fazeOchranyKod,fazeOchranyNazev,PrStavNazev` |
| `NPU_URL_FIELDS` | `urlExt,urlInt` |
| `NPU_TEMPORAL_FIELDS` | `platn_od,platn_do,aktual,datumStavuOchrany` |
| `NPU_DETAIL_BATCH` | `10` |

## Where to run live sync

Free tier: list → detail → upsert; **do not** full-mirror from cloud agents whose IPs are WAF-blocked on `/query`. Prefer the user’s **WSL** checkout:

```bash
# /home/cursor/dev/genesis
export DATABASE_URL=…   # Supabase pooler
timeout 300 ./scripts/sample-db-npu-sync
# or: timeout 300 uv run sample-db-npu-sync
```

CI and cloud agents must use fixtures / mock wget (`tests/test_npu_sync.py`, `tests/test_npu_sync_bash.sh`); never hit `geoportal.npu.cz` from Actions.

See also Project Context: `docs/npu-sync-wsl.md`.
