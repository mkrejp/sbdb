"""Definitive NPÚ attribute → ``layer_objects`` column mapping (Marek locked set).

``OBJECTID`` maps to existing ``npu_objectid`` (sync upsert key) — not duplicated.
Unknown / extra keys continue to live only in EAV ``layer_object_properties``,
tags, or urls. Sync dual-writes known fields onto columns **and** keeps the
existing classify → properties/tags/urls path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ColumnKind = Literal["bigint", "integer", "timestamptz", "text"]


@dataclass(frozen=True, slots=True)
class NpuColumnSpec:
    """One NPÚ feature attribute promoted onto ``layer_objects``."""

    npu_key: str
    column: str
    kind: ColumnKind


# Order matches Marek's definitive attribute list (excluding OBJECTID → npu_objectid).
NPU_ATTRIBUTE_COLUMNS: tuple[NpuColumnSpec, ...] = (
    NpuColumnSpec("PrStav_id", "pr_stav_id", "bigint"),
    NpuColumnSpec("Subtyp", "subtyp", "integer"),
    NpuColumnSpec("platn_od", "platn_od", "timestamptz"),
    NpuColumnSpec("platn_do", "platn_do", "timestamptz"),
    NpuColumnSpec("aktual", "aktual", "timestamptz"),
    NpuColumnSpec("AktStav_id", "akt_stav_id", "bigint"),
    NpuColumnSpec("pravniAktId", "pravni_akt_id", "bigint"),
    NpuColumnSpec("pravniStavId", "pravni_stav_id", "bigint"),
    NpuColumnSpec("pravniAktPravnihoStavuId", "pravni_akt_pravniho_stavu_id", "bigint"),
    NpuColumnSpec("zmenaUzemnihoRozsahu", "zmena_uzemniho_rozsahu", "integer"),
    NpuColumnSpec("datumStavuOchrany", "datum_stavu_ochrany", "timestamptz"),
    NpuColumnSpec("hlavniPrvek", "hlavni_prvek", "text"),
    NpuColumnSpec("PrStavNazev", "pr_stav_nazev", "text"),
    NpuColumnSpec("rejstrikoveCisloUSKP", "rejstrikove_cislo_uskp", "text"),
    NpuColumnSpec("typOchranyKod", "typ_ochrany_kod", "text"),
    NpuColumnSpec("typOchranyNazev", "typ_ochrany_nazev", "text"),
    NpuColumnSpec("upresneniTypuOchrany", "upresneni_typu_ochrany", "text"),
    NpuColumnSpec("urlExt", "url_ext", "text"),
    NpuColumnSpec("urlInt", "url_int", "text"),
    NpuColumnSpec("xxProhlaseni", "xx_prohlaseni", "text"),
    NpuColumnSpec("verejny", "verejny", "integer"),
    NpuColumnSpec("hlavniPrvekId", "hlavni_prvek_id", "bigint"),
)

NPU_COLUMN_NAMES: tuple[str, ...] = tuple(spec.column for spec in NPU_ATTRIBUTE_COLUMNS)

_NPU_KEY_TO_SPEC: dict[str, NpuColumnSpec] = {spec.npu_key: spec for spec in NPU_ATTRIBUTE_COLUMNS}
_NPU_KEY_LOWER: dict[str, NpuColumnSpec] = {
    spec.npu_key.lower(): spec for spec in NPU_ATTRIBUTE_COLUMNS
}


def lookup_column_spec(npu_key: str) -> NpuColumnSpec | None:
    """Resolve an NPÚ attribute name to its column spec (case-insensitive)."""
    if npu_key in _NPU_KEY_TO_SPEC:
        return _NPU_KEY_TO_SPEC[npu_key]
    return _NPU_KEY_LOWER.get(npu_key.lower())


def _as_int(value: Any) -> int | None:
    """Parse a scalar to int; reject bools and blank strings."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def coerce_column_value(
    spec: NpuColumnSpec,
    value: Any,
    *,
    parse_temporal: Any,
) -> Any:
    """Coerce a raw NPÚ attribute into a Python value for the SQL column.

    ``parse_temporal`` is ``_parse_temporal`` from the sync module (injected to
    avoid a circular import at module load).
    """
    if value is None or value == "":
        return None
    if spec.kind == "text":
        if isinstance(value, (dict, list)):
            return str(value)
        return str(value)
    if spec.kind in {"bigint", "integer"}:
        return _as_int(value)
    if spec.kind == "timestamptz":
        parsed = parse_temporal(value)
        return parsed if isinstance(parsed, datetime) else None
    return None


def extract_npu_column_values(
    properties: dict[str, Any],
    *,
    parse_temporal: Any,
) -> dict[str, Any]:
    """Build ``{sql_column: value}`` for every definitive NPÚ attribute present.

    Missing or unparseable values are omitted (caller treats as SQL NULL via
    ``.get``). ``OBJECTID`` is handled separately as ``npu_objectid``.
    """
    # Prefer exact-case keys from the feature; fall back to case-insensitive.
    by_lower = {str(k).lower(): (k, v) for k, v in properties.items()}
    out: dict[str, Any] = {}
    for spec in NPU_ATTRIBUTE_COLUMNS:
        if spec.npu_key in properties:
            raw = properties[spec.npu_key]
        elif spec.npu_key.lower() in by_lower:
            raw = by_lower[spec.npu_key.lower()][1]
        else:
            continue
        coerced = coerce_column_value(spec, raw, parse_temporal=parse_temporal)
        if coerced is not None:
            out[spec.column] = coerced
    return out


# SQL fragment helpers for upsert / SELECT
UPSERT_COLUMN_SQL = ", ".join(NPU_COLUMN_NAMES)
UPSERT_PLACEHOLDERS_SQL = ", ".join("%s" for _ in NPU_COLUMN_NAMES)
UPSERT_UPDATE_SQL = ",\n            ".join(f"{col} = EXCLUDED.{col}" for col in NPU_COLUMN_NAMES)


def ordered_column_params(values: dict[str, Any]) -> tuple[Any, ...]:
    """Positional params matching ``NPU_COLUMN_NAMES`` / ``UPSERT_*`` fragments."""
    return tuple(values.get(col) for col in NPU_COLUMN_NAMES)
