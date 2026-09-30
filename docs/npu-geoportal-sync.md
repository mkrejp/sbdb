# NPÚ Geoportal REST — mirror & sync practices

Initial data fill for map layers comes from the **NPÚ Geoportal REST Services** (ArcGIS). Account for server-side request limits.

## Limits

- Server enforces `maxRecordCount` (often **1,000–2,000** objects per call).
- `where=1=1` on a large layer **truncates without warning** if you do not page.
- Reliable sync: **paged architecture** via `resultOffset` / `resultRecordCount`, or a spatial envelope strategy.

## Step 1 — Layer rules

Before pulling, read the **layer endpoint root** (service/layer metadata JSON) and note:

- `maxRecordCount`
- `supportsPagination: true`

Configure the client cap **at or below** that max (e.g. 1000).

Metadata / portal entry: [npu.cz](https://npu.cz) — use the concrete ArcGIS FeatureServer/MapServer **layer query URL** for the chosen layer (not only the site root).

## Step 2 — Paged fetch (blueprint)

1. Optional: `returnCountOnly=true` to learn total scope.
2. Loop: `where=1=1`, `outFields=*`, `outSR=4326`, `f=geojson`, `resultOffset`, `resultRecordCount=MAX`.
3. Append features; advance offset by `len(features)`; stop when a page returns fewer than `MAX` (or empty).
4. Build a FeatureCollection (WGS84 / CRS84) and/or stream into Postgres.

Identity: prefer `properties.OBJECTID` or `properties.id` as the **stable external key** for upserts.

## Step 3 — Long-term sync into Postgres/PostGIS

| Phase | Strategy | Method |
| --- | --- | --- |
| Primary keys | Identity binding | Use NPÚ `OBJECTID`/`id` as the sync key (unique constraint). Do not rely only on arbitrary serials for deduping sync cycles. |
| SQL storage | Upsert | `INSERT … ON CONFLICT (npu_objectid) DO UPDATE …` |
| Geometry | Spatial transform | `ST_GeomFromGeoJSON` (or equivalent) into geometry/geography |
| Automation | Schedule | Weekly/monthly is enough for infrequently changing heritage boundaries; wire later via CI/cron/agent (stage 3/7) |

## Project mapping

- One NPÚ layer → one (or more) app **layers** rows + **layer objects** with GeoJSON geometry.
- Thematic attributes → typed **properties** and/or mapped columns as designed.
- Classification → **tags** where mappable from NPÚ fields.
- External links → object **URL list** when present in attributes or constructed from known NPÚ patterns.

Free tier: batch upserts; avoid loading entire huge layers into memory if a layer is very large — stream page → upsert when needed.
