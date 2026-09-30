-- Migration 003: PostGIS on layer_objects (NPÚ geospatial)
-- Supabase: install postgis into schema "extensions" (never public).
-- Dual-write: keep geometry JSONB for REST compatibility; geom is spatial source of truth.
-- Apply: psql "$DATABASE_URL" -f migrations/003_postgis_layer_objects.sql
-- Or: Supabase MCP apply_migration / Dashboard SQL.

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;

-- Ensure PostGIS types/functions resolve when search_path is minimal
SET search_path TO public, extensions;

ALTER TABLE layer_objects
    ADD COLUMN IF NOT EXISTS geom geometry(Geometry, 4326);

-- Backfill PostGIS from existing GeoJSON JSONB (EPSG:4326 / WGS84)
UPDATE layer_objects
SET geom = ST_SetSRID(ST_GeomFromGeoJSON(geometry::text), 4326)
WHERE geom IS NULL
  AND geometry IS NOT NULL
  AND jsonb_typeof(geometry) = 'object'
  AND geometry ? 'type'
  AND geometry->>'type' IS DISTINCT FROM 'GeometryCollection';

CREATE INDEX IF NOT EXISTS idx_layer_objects_geom_gist
    ON layer_objects USING GIST (geom);

COMMENT ON COLUMN layer_objects.geom IS
    'PostGIS geometry (EPSG:4326); source of truth for spatial ops. Dual-written with geometry JSONB.';
COMMENT ON COLUMN layer_objects.geometry IS
    'GeoJSON Geometry as JSONB (API / sync compatibility). Kept in sync with geom on write.';

-- Fill the missing side only; when app dual-writes both, leave values as provided.
CREATE OR REPLACE FUNCTION sync_layer_object_geometry_jsonb()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path TO public, extensions
AS $$
BEGIN
    IF NEW.geom IS NULL AND NEW.geometry IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry::text), 4326);
    ELSIF NEW.geometry IS NULL AND NEW.geom IS NOT NULL THEN
        NEW.geometry := ST_AsGeoJSON(NEW.geom)::jsonb;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.geom IS DISTINCT FROM OLD.geom
           AND NEW.geometry IS NOT DISTINCT FROM OLD.geometry THEN
            NEW.geometry := ST_AsGeoJSON(NEW.geom)::jsonb;
        ELSIF NEW.geometry IS DISTINCT FROM OLD.geometry
              AND NEW.geom IS NOT DISTINCT FROM OLD.geom THEN
            NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry::text), 4326);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_layer_objects_sync_geom ON layer_objects;
CREATE TRIGGER trg_layer_objects_sync_geom
    BEFORE INSERT OR UPDATE OF geometry, geom ON layer_objects
    FOR EACH ROW EXECUTE FUNCTION sync_layer_object_geometry_jsonb();
