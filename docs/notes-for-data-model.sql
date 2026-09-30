-- Migration 001: notes-for-data-model — layers / objects / typed props / tags / urls
-- Geometry: JSONB GeoJSON (Supabase Free; PostGIS optional later).
-- Images/binary props: Supabase Storage refs (bucket/path/url + metadata), never BYTEA.
-- Explicit URL lists: layer_object_urls (1:N), distinct from typed image/binary properties.
-- Apply: psql "$DATABASE_URL" -f migrations/001_create_notes_for_data_model.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Drop prior prototypes
DROP TABLE IF EXISTS layer_feature_properties CASCADE;
DROP TABLE IF EXISTS layer_features CASCADE;
DROP TABLE IF EXISTS layer_object_tags CASCADE;
DROP TABLE IF EXISTS layer_object_urls CASCADE;
DROP TABLE IF EXISTS layer_object_properties CASCADE;
DROP TABLE IF EXISTS layer_objects CASCADE;
DROP TABLE IF EXISTS map_layers CASCADE;
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS notes_for_data_model CASCADE;
DROP FUNCTION IF EXISTS set_notes_for_data_model_updated_at() CASCADE;
DROP FUNCTION IF EXISTS set_updated_at() CASCADE;
DROP TYPE IF EXISTS property_value_type CASCADE;

CREATE TYPE property_value_type AS ENUM ('text', 'temporal', 'image', 'binary');

CREATE TABLE map_layers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT map_layers_name_not_blank CHECK (char_length(btrim(name)) > 0)
);

CREATE INDEX idx_map_layers_created_at ON map_layers (created_at DESC);

-- Layer objects (= GeoJSON features)
CREATE TABLE layer_objects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id UUID NOT NULL REFERENCES map_layers (id) ON DELETE CASCADE,
    geometry JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT layer_objects_geometry_object CHECK (jsonb_typeof(geometry) = 'object'),
    CONSTRAINT layer_objects_geometry_has_type CHECK (geometry ? 'type')
);

CREATE INDEX idx_layer_objects_layer_id ON layer_objects (layer_id);
CREATE INDEX idx_layer_objects_geometry_gin ON layer_objects USING GIN (geometry);

-- Typed additional properties (discriminated by value_type)
CREATE TABLE layer_object_properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_id UUID NOT NULL REFERENCES layer_objects (id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_type property_value_type NOT NULL,
    -- text
    text_value TEXT,
    -- temporal (instant; optional end for intervals)
    temporal_value TIMESTAMPTZ,
    temporal_end TIMESTAMPTZ,
    -- image / other binary → Supabase Storage reference (not BYTEA)
    storage_bucket TEXT,
    storage_path TEXT,
    storage_url TEXT,
    content_type TEXT,
    byte_size BIGINT,
    checksum TEXT,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT layer_object_properties_key_not_blank CHECK (char_length(btrim(key)) > 0),
    CONSTRAINT layer_object_properties_object_key_unique UNIQUE (object_id, key),
    CONSTRAINT layer_object_properties_byte_size_nonneg CHECK (byte_size IS NULL OR byte_size >= 0),
    CONSTRAINT layer_object_properties_temporal_range CHECK (
        temporal_end IS NULL OR temporal_value IS NULL OR temporal_end >= temporal_value
    ),
    CONSTRAINT layer_object_properties_typed_payload CHECK (
        (value_type = 'text' AND text_value IS NOT NULL
            AND temporal_value IS NULL AND temporal_end IS NULL
            AND storage_bucket IS NULL AND storage_path IS NULL AND storage_url IS NULL
            AND content_type IS NULL AND byte_size IS NULL AND checksum IS NULL)
        OR
        (value_type = 'temporal' AND temporal_value IS NOT NULL
            AND text_value IS NULL
            AND storage_bucket IS NULL AND storage_path IS NULL AND storage_url IS NULL
            AND content_type IS NULL AND byte_size IS NULL AND checksum IS NULL)
        OR
        (value_type IN ('image', 'binary')
            AND storage_bucket IS NOT NULL AND storage_path IS NOT NULL
            AND text_value IS NULL AND temporal_value IS NULL AND temporal_end IS NULL)
    )
);

CREATE INDEX idx_layer_object_properties_object_id ON layer_object_properties (object_id);
CREATE INDEX idx_layer_object_properties_value_type ON layer_object_properties (value_type);

-- Classification tags (many-to-many with layer objects)
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tags_name_not_blank CHECK (char_length(btrim(name)) > 0),
    CONSTRAINT tags_name_unique UNIQUE (name)
);

CREATE TABLE layer_object_tags (
    object_id UUID NOT NULL REFERENCES layer_objects (id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_id, tag_id)
);

CREATE INDEX idx_layer_object_tags_tag_id ON layer_object_tags (tag_id);

-- Explicit URL list per object (1:N), ordered; not the same as typed image/binary props
CREATE TABLE layer_object_urls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_id UUID NOT NULL REFERENCES layer_objects (id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT layer_object_urls_url_not_blank CHECK (char_length(btrim(url)) > 0)
);

CREATE INDEX idx_layer_object_urls_object_id ON layer_object_urls (object_id);
CREATE INDEX idx_layer_object_urls_object_sort ON layer_object_urls (object_id, sort_order);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_map_layers_updated_at
    BEFORE UPDATE ON map_layers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_layer_objects_updated_at
    BEFORE UPDATE ON layer_objects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_layer_object_properties_updated_at
    BEFORE UPDATE ON layer_object_properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_tags_updated_at
    BEFORE UPDATE ON tags
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_layer_object_urls_updated_at
    BEFORE UPDATE ON layer_object_urls
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE map_layers ENABLE ROW LEVEL SECURITY;
ALTER TABLE layer_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE layer_object_properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE layer_object_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE layer_object_urls ENABLE ROW LEVEL SECURITY;
