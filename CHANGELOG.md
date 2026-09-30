# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [0.2.0] — 2026-09-30

First public deploy slice on Railway **zesty-adaptation** / **sbdb-api** (`sbdb.animarium.ai`), mirrored from Origin via GitHub `mkrejp/sbdb`.

### Added

- PostGIS `geom` (EPSG:4326) dual-write with JSONB `geometry` on `layer_objects` (migration `003`, #13).
- Definitive NPÚ attribute columns on `layer_objects` + API exposure on `LayerObject` (migration `004`, #14).
- NPÚ sync hardening: bash/wget list→detail, skip existing OBJECTIDs, timestamp sanity (#9–#12).
- Live smoke verified 2026-09-30: `GET /health` → `ok`/`connected`; `/layers` + `/objects` return GeoJSON polygons and populated NPÚ attrs (e.g. `npu_objectid`, `hlavni_prvek`, `typ_ochrany_kod`).

### Fixed

- Railway Docker `uv sync --frozen` via real `uv.lock` (not placeholder stub) (#7).

### Changed

- Package / OpenAPI advertised version **0.1.0 → 0.2.0**.

## [0.1.0] — 2026-09-30

Initial framework: FastAPI layers/objects/properties/tags/urls API, Supabase schema migrations `001`/`002`, NPÚ sync CLI, Dockerfile for Railway Free.
