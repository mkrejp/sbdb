-- Migration 002: NPÚ Geoportal sync keys + layer source metadata
-- Adds identity binding for paged ArcGIS MapServer upserts (see docs/npu-geoportal-sync.md).

ALTER TABLE map_layers
    ADD COLUMN IF NOT EXISTS source_key TEXT,
    ADD COLUMN IF NOT EXISTS source_url TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_map_layers_source_key
    ON map_layers (source_key)
    WHERE source_key IS NOT NULL;

ALTER TABLE layer_objects
    ADD COLUMN IF NOT EXISTS npu_objectid BIGINT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_layer_objects_layer_npu_objectid
    ON layer_objects (layer_id, npu_objectid)
    WHERE npu_objectid IS NOT NULL;

COMMENT ON COLUMN layer_objects.npu_objectid IS
    'NPÚ / ArcGIS OBJECTID (or numeric id) used as sync upsert key';
COMMENT ON COLUMN map_layers.source_key IS
    'Stable ingest key, e.g. npu:<MapServer-layer-path>';
COMMENT ON COLUMN map_layers.source_url IS
    'ArcGIS MapServer layer root URL used for metadata + /query';
