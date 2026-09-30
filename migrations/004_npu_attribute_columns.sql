-- Migration 004: Promote definitive NPÚ attributes onto layer_objects columns
-- Marek's locked attribute set (CP_UAP_PVO Feature properties) — dual-write with
-- layer_object_properties / tags / urls. OBJECTID stays as existing npu_objectid.
-- Apply: psql "$DATABASE_URL" -f migrations/004_npu_attribute_columns.sql
-- Or: Supabase MCP apply_migration name=npu_attribute_columns

ALTER TABLE layer_objects
    ADD COLUMN IF NOT EXISTS pr_stav_id BIGINT,
    ADD COLUMN IF NOT EXISTS subtyp INTEGER,
    ADD COLUMN IF NOT EXISTS platn_od TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS platn_do TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS aktual TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS akt_stav_id BIGINT,
    ADD COLUMN IF NOT EXISTS pravni_akt_id BIGINT,
    ADD COLUMN IF NOT EXISTS pravni_stav_id BIGINT,
    ADD COLUMN IF NOT EXISTS pravni_akt_pravniho_stavu_id BIGINT,
    ADD COLUMN IF NOT EXISTS zmena_uzemniho_rozsahu INTEGER,
    ADD COLUMN IF NOT EXISTS datum_stavu_ochrany TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hlavni_prvek TEXT,
    ADD COLUMN IF NOT EXISTS pr_stav_nazev TEXT,
    ADD COLUMN IF NOT EXISTS rejstrikove_cislo_uskp TEXT,
    ADD COLUMN IF NOT EXISTS typ_ochrany_kod TEXT,
    ADD COLUMN IF NOT EXISTS typ_ochrany_nazev TEXT,
    ADD COLUMN IF NOT EXISTS upresneni_typu_ochrany TEXT,
    ADD COLUMN IF NOT EXISTS url_ext TEXT,
    ADD COLUMN IF NOT EXISTS url_int TEXT,
    ADD COLUMN IF NOT EXISTS xx_prohlaseni TEXT,
    ADD COLUMN IF NOT EXISTS verejny INTEGER,
    ADD COLUMN IF NOT EXISTS hlavni_prvek_id BIGINT;

COMMENT ON COLUMN layer_objects.npu_objectid IS
    'NPÚ OBJECTID (sync upsert key). Source attribute: OBJECTID.';
COMMENT ON COLUMN layer_objects.pr_stav_id IS 'NPÚ PrStav_id';
COMMENT ON COLUMN layer_objects.subtyp IS 'NPÚ Subtyp';
COMMENT ON COLUMN layer_objects.platn_od IS 'NPÚ platn_od (epoch-ms → timestamptz)';
COMMENT ON COLUMN layer_objects.platn_do IS 'NPÚ platn_do (epoch-ms → timestamptz)';
COMMENT ON COLUMN layer_objects.aktual IS 'NPÚ aktual (epoch-ms → timestamptz)';
COMMENT ON COLUMN layer_objects.akt_stav_id IS 'NPÚ AktStav_id';
COMMENT ON COLUMN layer_objects.pravni_akt_id IS 'NPÚ pravniAktId';
COMMENT ON COLUMN layer_objects.pravni_stav_id IS 'NPÚ pravniStavId';
COMMENT ON COLUMN layer_objects.pravni_akt_pravniho_stavu_id IS
    'NPÚ pravniAktPravnihoStavuId';
COMMENT ON COLUMN layer_objects.zmena_uzemniho_rozsahu IS 'NPÚ zmenaUzemnihoRozsahu';
COMMENT ON COLUMN layer_objects.datum_stavu_ochrany IS
    'NPÚ datumStavuOchrany (epoch-ms → timestamptz)';
COMMENT ON COLUMN layer_objects.hlavni_prvek IS 'NPÚ hlavniPrvek';
COMMENT ON COLUMN layer_objects.pr_stav_nazev IS 'NPÚ PrStavNazev';
COMMENT ON COLUMN layer_objects.rejstrikove_cislo_uskp IS 'NPÚ rejstrikoveCisloUSKP';
COMMENT ON COLUMN layer_objects.typ_ochrany_kod IS 'NPÚ typOchranyKod';
COMMENT ON COLUMN layer_objects.typ_ochrany_nazev IS 'NPÚ typOchranyNazev';
COMMENT ON COLUMN layer_objects.upresneni_typu_ochrany IS 'NPÚ upresneniTypuOchrany';
COMMENT ON COLUMN layer_objects.url_ext IS 'NPÚ urlExt';
COMMENT ON COLUMN layer_objects.url_int IS 'NPÚ urlInt';
COMMENT ON COLUMN layer_objects.xx_prohlaseni IS 'NPÚ xxProhlaseni';
COMMENT ON COLUMN layer_objects.verejny IS 'NPÚ verejny';
COMMENT ON COLUMN layer_objects.hlavni_prvek_id IS 'NPÚ hlavniPrvekId';

-- Light lookup indexes (Free-tier friendly; FKs already indexed elsewhere)
CREATE INDEX IF NOT EXISTS idx_layer_objects_pr_stav_id
    ON layer_objects (pr_stav_id)
    WHERE pr_stav_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_layer_objects_hlavni_prvek_id
    ON layer_objects (hlavni_prvek_id)
    WHERE hlavni_prvek_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_layer_objects_rejstrikove_cislo_uskp
    ON layer_objects (rejstrikove_cislo_uskp)
    WHERE rejstrikove_cislo_uskp IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Backfill from existing EAV / urls (fill null columns only).
-- Tag-routed fields (Subtyp, typOchranyKod, typOchranyNazev, PrStavNazev) are
-- not keyed in tags — they fill on next sync dual-write. Properties + urls do.
-- ---------------------------------------------------------------------------

-- Temporal props → timestamptz columns
UPDATE layer_objects lo
SET platn_od = p.temporal_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'platn_od'
  AND p.value_type = 'temporal'
  AND p.temporal_value IS NOT NULL
  AND lo.platn_od IS NULL;

UPDATE layer_objects lo
SET platn_do = p.temporal_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'platn_do'
  AND p.value_type = 'temporal'
  AND p.temporal_value IS NOT NULL
  AND lo.platn_do IS NULL;

UPDATE layer_objects lo
SET aktual = p.temporal_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'aktual'
  AND p.value_type = 'temporal'
  AND p.temporal_value IS NOT NULL
  AND lo.aktual IS NULL;

UPDATE layer_objects lo
SET datum_stavu_ochrany = p.temporal_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'datumStavuOchrany'
  AND p.value_type = 'temporal'
  AND p.temporal_value IS NOT NULL
  AND lo.datum_stavu_ochrany IS NULL;

-- Text props → typed columns (bigint / int / text)
UPDATE layer_objects lo
SET pr_stav_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'PrStav_id'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.pr_stav_id IS NULL;

UPDATE layer_objects lo
SET subtyp = NULLIF(btrim(p.text_value), '')::INTEGER
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'Subtyp'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.subtyp IS NULL;

UPDATE layer_objects lo
SET akt_stav_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'AktStav_id'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.akt_stav_id IS NULL;

UPDATE layer_objects lo
SET pravni_akt_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'pravniAktId'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.pravni_akt_id IS NULL;

UPDATE layer_objects lo
SET pravni_stav_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'pravniStavId'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.pravni_stav_id IS NULL;

UPDATE layer_objects lo
SET pravni_akt_pravniho_stavu_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'pravniAktPravnihoStavuId'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.pravni_akt_pravniho_stavu_id IS NULL;

UPDATE layer_objects lo
SET zmena_uzemniho_rozsahu = NULLIF(btrim(p.text_value), '')::INTEGER
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'zmenaUzemnihoRozsahu'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.zmena_uzemniho_rozsahu IS NULL;

UPDATE layer_objects lo
SET hlavni_prvek = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'hlavniPrvek'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.hlavni_prvek IS NULL;

UPDATE layer_objects lo
SET pr_stav_nazev = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'PrStavNazev'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.pr_stav_nazev IS NULL;

UPDATE layer_objects lo
SET rejstrikove_cislo_uskp = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'rejstrikoveCisloUSKP'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.rejstrikove_cislo_uskp IS NULL;

UPDATE layer_objects lo
SET typ_ochrany_kod = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'typOchranyKod'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.typ_ochrany_kod IS NULL;

UPDATE layer_objects lo
SET typ_ochrany_nazev = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'typOchranyNazev'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.typ_ochrany_nazev IS NULL;

UPDATE layer_objects lo
SET upresneni_typu_ochrany = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'upresneniTypuOchrany'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.upresneni_typu_ochrany IS NULL;

UPDATE layer_objects lo
SET xx_prohlaseni = p.text_value
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'xxProhlaseni'
  AND p.value_type = 'text'
  AND p.text_value IS NOT NULL
  AND lo.xx_prohlaseni IS NULL;

UPDATE layer_objects lo
SET verejny = NULLIF(btrim(p.text_value), '')::INTEGER
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'verejny'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.verejny IS NULL;

UPDATE layer_objects lo
SET hlavni_prvek_id = NULLIF(btrim(p.text_value), '')::BIGINT
FROM layer_object_properties p
WHERE p.object_id = lo.id
  AND p.key = 'hlavniPrvekId'
  AND p.value_type = 'text'
  AND p.text_value ~ '^-?[0-9]+$'
  AND lo.hlavni_prvek_id IS NULL;

-- URLs dual-stored in layer_object_urls (label = NPÚ key)
UPDATE layer_objects lo
SET url_ext = u.url
FROM layer_object_urls u
WHERE u.object_id = lo.id
  AND u.label = 'urlExt'
  AND lo.url_ext IS NULL;

UPDATE layer_objects lo
SET url_int = u.url
FROM layer_object_urls u
WHERE u.object_id = lo.id
  AND u.label = 'urlInt'
  AND lo.url_int IS NULL;

-- Temporal keys that landed as text (unparseable at sync time) stay null on columns.
-- Subtyp / typOchranyKod / typOchranyNazev / PrStavNazev historically tag-only:
-- next dual-write sync fills those columns.
