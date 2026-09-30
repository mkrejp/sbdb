# NPÚ Geoportal REST — mirror & sync practices

Initial data fill for map layers comes from the **NPÚ Geoportal REST Services** (ArcGIS). NPÚ primarily publishes via **MapServer** (read-only query), not editable FeatureServer. MapServer layers expose the same query operations used here (`f=geojson`, pagination, etc.).

Portal entry: [npu.cz](https://npu.cz) · REST directory: [geoportal.npu.cz/arcgis/rest/services](https://geoportal.npu.cz/arcgis/rest/services)

## Locked layer (`NPU_LAYER_URL`)

| Item | Value |
| --- | --- |
| Layer root | `https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0` |
| Name | Národní kulturní památky (Feature Layer, polygons) |
| `maxRecordCount` | 2000 |
| Pagination | `supportsPagination: true` |
| Sync CLI | `uv run sample-db-npu-sync` (requires `DATABASE_URL`) |

HTTP client: **GNU wget** (`wget -O <file.json> "<url>"`), not httpx. The portal
entry `https://npu.cz` is not the object-list JSON; the sync uses the MapServer
layer / query URLs below (Marek’s `-O` pattern, locked layer for data).

Example metadata fetch (object attributes / paging caps):

```bash
wget -O pamatky.json \
  --user-agent=YourSyncBot/1.0 \
  --header='Accept: application/json' \
  'https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0?f=json'
```

Example query (paged GeoJSON features):

```bash
wget -O pamatky-page.json \
  --user-agent=YourSyncBot/1.0 \
  --header='Accept: application/json' \
  'https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0/query?where=1%3D1&outFields=*&resultRecordCount=5&outSR=4326&f=geojson'
```

`NPU_LAYER_URL` must be this concrete MapServer **layer root** (`…/MapServer/<id>`), not only `https://npu.cz`.

## Limits

- Server enforces `maxRecordCount` (this layer: **2000**).
- `where=1=1` on a large layer **truncates without warning** if you do not page.
- Reliable sync: **paged architecture** via `resultOffset` / `resultRecordCount`.

## Step 1 — Layer rules

Before pulling, `wget -O` the **MapServer layer root** metadata JSON (`…/MapServer/<id>?f=json`) and note:

- `maxRecordCount`
- `supportsPagination: true` (often under `advancedQueryCapabilities`)

Configure the client cap **at or below** that max (e.g. 1000). wget sends `User-Agent: YourSyncBot/1.0` and `Accept: application/json`.

## Step 2 — Paged fetch (blueprint)

1. Optional: `returnCountOnly=true` to learn total scope.
2. Loop: `where=1=1`, `outFields=*`, `outSR=4326`, `f=geojson`, `resultOffset`, `resultRecordCount=MAX`.
3. Advance offset by `len(features)`; stop when a page returns fewer than `MAX` (or empty).
4. Stream into Postgres (do not hold huge layers entirely in memory).

Identity: prefer `properties.OBJECTID` (this layer) as the **stable external key** for upserts.

## Step 3 — Long-term sync into Postgres

| Phase | Strategy | Method |
| --- | --- | --- |
| Primary keys | Identity binding | NPÚ `OBJECTID` → `layer_objects.npu_objectid` |
| SQL storage | Upsert | `INSERT … ON CONFLICT (layer_id, npu_objectid) DO UPDATE …` |
| Geometry | JSONB GeoJSON | This project; PostGIS `ST_GeomFromGeoJSON` optional later |
| Automation | Schedule | Weekly/monthly later (stage 7) |

## Project mapping (CP_UAP_PVO)

| NPÚ | App |
| --- | --- |
| Layer root + name | `map_layers` |
| Feature geometry | `layer_objects.geometry` (JSONB) |
| `OBJECTID` | `layer_objects.npu_objectid` |
| `Subtyp`, `typOchranyKod`, `typOchranyNazev`, `fazeOchranyKod`, `fazeOchranyNazev`, `PrStavNazev` | `tags` / `layer_object_tags` |
| `urlExt`, `urlInt` | `layer_object_urls` |
| `platn_od`, `platn_do`, `aktual`, `datumStavuOchrany` | `layer_object_properties` (`temporal`) |
| Other scalars (e.g. `nazev` / display fields) | `layer_object_properties` (`text`) |

## Field-config defaults (`NPU_*`)

Config / `.env.example` defaults match the CP_UAP_PVO mapping above:

| Env | Default fields |
| --- | --- |
| `NPU_TAG_FIELDS` | `Subtyp,typOchranyKod,typOchranyNazev,fazeOchranyKod,fazeOchranyNazev,PrStavNazev` |
| `NPU_URL_FIELDS` | `urlExt,urlInt` |
| `NPU_TEMPORAL_FIELDS` | `platn_od,platn_do,aktual,datumStavuOchrany` |

CLI uses **wget** (`-O` temp `pamatky.json`, then parse). Headers:
`User-Agent: YourSyncBot/1.0`, `Accept: application/json`. Retries: **1 try + 3
retries (= 4 attempts)** per URL on non-zero wget exit / bad JSON, then abort.

## Where to run live sync

Free tier: page → upsert; **do not** full-mirror from cloud agents whose IPs are WAF-blocked on `/query`. Prefer the user’s **WSL** checkout:

```bash
# /home/cursor/dev/genesis
export DATABASE_URL=…   # Supabase pooler
uv run sample-db-npu-sync
```

CI and cloud agents must mock NPÚ (`tests/test_npu_sync.py`); never hit `geoportal.npu.cz` from Actions.
