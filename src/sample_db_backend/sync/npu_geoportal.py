"""NPÚ Geoportal sync — Python side: JSON parse/transform + Postgres upserts.

HTTP fetches are owned by the bash orchestrator (``scripts/sample-db-npu-sync``)
via ``wget -O``. This module never calls wget/httpx/requests for NPÚ.

Bash flow (Marek):
  1. wget object **list** JSON (``returnIdsOnly`` pages → ``pamatky.json``)
  2. filter out OBJECTIDs already in Postgres (gradual insert); ``--diff`` skips filter
  3. for each remaining id (small batches): wget **detail** GeoJSON
  4. Python transform + insert/upsert (diff mode: ``--only-if-changed``)

CLI (invoked by bash)::

    uv run python -m sample_db_backend.sync.npu_geoportal page-size META.json
    uv run python -m sample_db_backend.sync.npu_geoportal extract-ids LIST.json
    uv run python -m sample_db_backend.sync.npu_geoportal missing-ids --layer-id …
    uv run python -m sample_db_backend.sync.npu_geoportal ensure-layer ...
    uv run python -m sample_db_backend.sync.npu_geoportal upsert-file DETAIL.json ...

Entrypoint ``sample-db-npu-sync`` execs the bash script.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from sample_db_backend.config import get_settings
from sample_db_backend.sync.npu_columns import (
    UPSERT_COLUMN_SQL,
    UPSERT_PLACEHOLDERS_SQL,
    UPSERT_UPDATE_SQL,
    extract_npu_column_values,
    ordered_column_params,
)

logger = logging.getLogger(__name__)

SYNC_USER_AGENT = "YourSyncBot/1.0"
SYNC_ACCEPT = "application/json"
SYNC_HEADERS = {
    "User-Agent": SYNC_USER_AGENT,
    "Accept": SYNC_ACCEPT,
}

_SKIP_PROP_KEYS = frozenset(
    {
        "objectid",
        "object_id",
        "fid",
        "shape",
        "shape_length",
        "shape_area",
        "shape.len",
        "shape.area",
        "globalid",
    }
)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_DIGIT_EPOCH_RE = re.compile(r"^-?\d+(\.\d+)?$")
_EPOCH_MS_MIN = 1_000_000_000_000  # ~2001-09-09 in ms (ArcGIS date unit)
_EPOCH_S_MIN = 1_000_000_000  # ~2001-09-09 in seconds (legacy heuristic)
_TEMPORAL_YEAR_MIN = 1000
_TEMPORAL_YEAR_MAX_AHEAD = 5
_CLIENT_PAGE_CAP = 1000


@dataclass(frozen=True)
class LayerMeta:
    """Subset of ArcGIS layer metadata needed for safe paging."""

    name: str
    max_record_count: int
    supports_pagination: bool


@dataclass(frozen=True)
class UpsertStats:
    """Counters from one detail-file upsert."""

    features: int
    upserted: int
    unchanged: int = 0


@dataclass(frozen=True)
class FeatureSnapshot:
    """Comparable mirror of one layer object (geometry + derived children)."""

    npu_objectid: int
    geometry_json: str
    tags: frozenset[str]
    urls: tuple[tuple[str, str], ...]
    props: frozenset[tuple[str, str, str]]


def _normalize_layer_root(url: str) -> str:
    """Strip trailing /query and slash from a layer URL."""
    cleaned = url.strip().rstrip("/")
    if cleaned.lower().endswith("/query"):
        cleaned = cleaned[: -len("/query")].rstrip("/")
    return cleaned


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk (wget output)."""
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}")
    return payload


def parse_layer_metadata(data: dict[str, Any]) -> LayerMeta:
    """Parse MapServer layer ``?f=json`` metadata into paging caps."""
    if "error" in data:
        raise RuntimeError(f"Layer metadata error: {data['error']}")

    max_count = int(data.get("maxRecordCount") or 1000)
    supports = bool(data.get("advancedQueryCapabilities", {}).get("supportsPagination"))
    if not supports and data.get("supportsPagination") is True:
        supports = True
    name = str(data.get("name") or "NPÚ layer")
    if not supports:
        logger.warning(
            "Layer does not advertise supportsPagination; proceed cautiously with "
            "resultOffset ID-list paging (verify server behavior)."
        )
    return LayerMeta(name=name, max_record_count=max_count, supports_pagination=supports)


def page_size(meta: LayerMeta) -> int:
    """Client page size at or below server maxRecordCount (cap 1000)."""
    return max(1, min(meta.max_record_count, _CLIENT_PAGE_CAP))


def extract_object_ids(data: dict[str, Any]) -> list[int]:
    """Extract OBJECTID list from a ``returnIdsOnly=true`` query JSON.

    Accepts ArcGIS shapes::

        {"objectIds": [1, 2, 3], "objectIdFieldName": "OBJECTID"}
        {"objectIdFieldName": "OBJECTID", "objectIds": null}  → []
    """
    if "error" in data:
        raise RuntimeError(f"ID list query error: {data['error']}")

    raw = data.get("objectIds")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"Expected objectIds list, got {type(raw).__name__}")

    ids: list[int] = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Non-integer object id: {item!r}") from exc
    return ids


def features_from_detail(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a detail response into a list of GeoJSON Feature dicts."""
    if "error" in data:
        raise RuntimeError(f"Detail query error: {data['error']}")

    if data.get("type") == "FeatureCollection":
        return list(data.get("features") or [])
    if "features" in data:
        return list(data.get("features") or [])
    if data.get("type") == "Feature":
        return [data]
    raise RuntimeError("Unexpected detail payload (expected GeoJSON FeatureCollection)")


def extract_npu_objectid(properties: dict[str, Any]) -> int | None:
    """Prefer properties.OBJECTID, then properties.id, as stable sync key."""
    for key in ("OBJECTID", "objectid", "ObjectID", "FID", "id", "ID"):
        if key in properties and properties[key] is not None:
            try:
                return int(properties[key])
            except (TypeError, ValueError):
                continue
    return None


def _is_skip_key(key: str) -> bool:
    return key.lower() in _SKIP_PROP_KEYS or key.lower().startswith("shape_")


def _is_dateish_key(key: str) -> bool:
    """True when the attribute name looks like a date/time field."""
    lower = key.lower()
    return any(tok in lower for tok in ("date", "datum", "time", "platn", "aktual"))


def _as_aware_utc(dt: datetime) -> datetime:
    """Normalize to timezone-aware UTC (naive ISO treated as UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _within_calendar_window(dt: datetime) -> bool:
    """Reject absurd years outside the heritage-safe window."""
    max_year = datetime.now(tz=UTC).year + _TEMPORAL_YEAR_MAX_AHEAD
    return _TEMPORAL_YEAR_MIN <= dt.year <= max_year


def _datetime_from_epoch_number(num: float) -> datetime | None:
    """Convert a numeric epoch to aware UTC, preferring ArcGIS milliseconds."""
    if not math.isfinite(num) or num <= 0:
        return None
    try:
        if num >= _EPOCH_MS_MIN:
            dt = datetime.fromtimestamp(num / 1000.0, tz=UTC)
        elif num >= _EPOCH_S_MIN:
            # Legacy seconds heuristic (values in ~[1e9, 1e12))
            dt = datetime.fromtimestamp(num, tz=UTC)
        else:
            return None
    except (OverflowError, OSError, ValueError):
        return None
    if not _within_calendar_window(dt):
        logger.warning("temporal_out_of_range epoch=%s year=%s", num, dt.year)
        return None
    return dt


def _parse_temporal(value: Any) -> datetime | None:
    """Parse ArcGIS epoch-ms or ISO-ish strings into aware UTC datetimes.

    Sanity checks:
    - reject empty / NaN / inf / zero / negative
    - prefer epoch **milliseconds** (``>= 1e12``); seconds only in ``[1e9, 1e12)``
    - digit strings (len >= 10) go through the epoch path
    - calendar year must be in ``[1000, now.year + 5]``
    - ISO without offset is treated as UTC
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _datetime_from_epoch_number(float(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if _DIGIT_EPOCH_RE.fullmatch(text):
            return _datetime_from_epoch_number(float(text))
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        dt = _as_aware_utc(dt)
        if not _within_calendar_window(dt):
            logger.warning("temporal_out_of_range iso=%r year=%s", text, dt.year)
            return None
        return dt
    return None


def _field_match(key: str, fields: set[str]) -> bool:
    """Case-insensitive membership for configured NPÚ field names."""
    if key in fields:
        return True
    lower = key.lower()
    return lower in {f.lower() for f in fields}


def classify_attribute(
    key: str,
    value: Any,
    *,
    tag_fields: set[str],
    url_fields: set[str],
    temporal_fields: set[str] | None = None,
) -> tuple[str, Any] | None:
    """Map one NPÚ attribute into (kind, payload).

    kind ∈ {tag, url, temporal, text}; returns None to skip.

    Temporal values are accepted only for configured ``temporal_fields`` or
    dateish attribute names (``date`` / ``datum`` / ``time`` / ``platn`` /
    ``aktual``). Bare large integers on unrelated keys stay ``text``.
    """
    if value is None or value == "" or _is_skip_key(key):
        return None
    temporal_fields = temporal_fields or set()
    if _field_match(key, tag_fields):
        return ("tag", str(value).strip())
    if _field_match(key, url_fields):
        return ("url", str(value).strip())
    if isinstance(value, str) and _URL_RE.match(value.strip()):
        return ("url", value.strip())

    configured_temporal = _field_match(key, temporal_fields)
    dateish = _is_dateish_key(key)
    if configured_temporal or dateish:
        temporal = _parse_temporal(value)
        if temporal is not None:
            return ("temporal", temporal)
        if configured_temporal:
            logger.debug("temporal_fallback_text key=%s value=%r", key, value)
            return ("text", str(value))

    if isinstance(value, (dict, list)):
        return ("text", str(value))
    return ("text", str(value))


def ensure_layer(
    conn: psycopg.Connection[Any],
    *,
    source_key: str,
    source_url: str,
    name: str,
    description: str = "",
) -> Any:
    """Upsert map_layers by source_key; return layer UUID."""
    row = conn.execute(
        """
        INSERT INTO map_layers (name, description, source_key, source_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source_key) WHERE source_key IS NOT NULL
        DO UPDATE SET
            name = EXCLUDED.name,
            source_url = EXCLUDED.source_url,
            updated_at = now()
        RETURNING id
        """,
        (name, description, source_key, source_url),
    ).fetchone()
    assert row is not None
    return row["id"]


def existing_npu_objectids(
    conn: psycopg.Connection[Any],
    *,
    layer_id: Any,
    candidates: list[int],
) -> set[int]:
    """Return the subset of ``candidates`` already stored for ``layer_id``."""
    if not candidates:
        return set()
    rows = conn.execute(
        """
        SELECT npu_objectid
        FROM layer_objects
        WHERE layer_id = %s
          AND npu_objectid = ANY(%s)
        """,
        (layer_id, candidates),
    ).fetchall()
    found: set[int] = set()
    for row in rows:
        raw = row["npu_objectid"]
        if raw is not None:
            found.add(int(raw))
    return found


def missing_npu_objectids(
    conn: psycopg.Connection[Any],
    *,
    layer_id: Any,
    candidates: list[int],
) -> list[int]:
    """Preserve candidate order; drop OBJECTIDs already present in Postgres."""
    existing = existing_npu_objectids(conn, layer_id=layer_id, candidates=candidates)
    return [oid for oid in candidates if oid not in existing]


def _geometry_json(geometry: dict[str, Any]) -> str:
    """Canonical JSON for geometry equality checks."""
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _prop_value_str(kind: str, payload: Any) -> str:
    """Normalize a classified property payload for snapshot comparison."""
    if kind == "temporal" and isinstance(payload, datetime):
        return _as_aware_utc(payload).isoformat()
    return str(payload)


def snapshot_from_feature(
    feature: dict[str, Any],
    *,
    tag_fields: set[str],
    url_fields: set[str],
    temporal_fields: set[str] | None = None,
) -> FeatureSnapshot | None:
    """Build a comparable snapshot from a GeoJSON Feature (no DB)."""
    props = dict(feature.get("properties") or {})
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or "type" not in geometry:
        return None
    npu_id = extract_npu_objectid(props)
    if npu_id is None:
        return None

    tags: set[str] = set()
    urls: list[tuple[str, str]] = []
    prop_rows: set[tuple[str, str, str]] = set()
    for key, value in props.items():
        mapped = classify_attribute(
            key,
            value,
            tag_fields=tag_fields,
            url_fields=url_fields,
            temporal_fields=temporal_fields,
        )
        if mapped is None:
            continue
        kind, payload = mapped
        if kind == "tag":
            name = str(payload).strip()
            if name:
                tags.add(name)
        elif kind == "url":
            urls.append((key, str(payload)))
        else:
            prop_rows.add((key, kind, _prop_value_str(kind, payload)))
    return FeatureSnapshot(
        npu_objectid=npu_id,
        geometry_json=_geometry_json(geometry),
        tags=frozenset(tags),
        urls=tuple(urls),
        props=frozenset(prop_rows),
    )


def load_db_snapshot(
    conn: psycopg.Connection[Any],
    *,
    layer_id: Any,
    npu_objectid: int,
) -> FeatureSnapshot | None:
    """Load the stored snapshot for one NPÚ OBJECTID, or None if absent."""
    row = conn.execute(
        """
        SELECT id,
               COALESCE(ST_AsGeoJSON(geom)::jsonb, geometry) AS geometry
        FROM layer_objects
        WHERE layer_id = %s AND npu_objectid = %s
        """,
        (layer_id, npu_objectid),
    ).fetchone()
    if row is None:
        return None
    object_id = row["id"]
    geometry = row["geometry"]
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    if not isinstance(geometry, dict):
        geometry = {}

    tag_rows = conn.execute(
        """
        SELECT t.name AS name
        FROM layer_object_tags lot
        JOIN tags t ON t.id = lot.tag_id
        WHERE lot.object_id = %s
        """,
        (object_id,),
    ).fetchall()
    tags = frozenset(str(r["name"]) for r in tag_rows if r.get("name"))

    url_rows = conn.execute(
        """
        SELECT label, url
        FROM layer_object_urls
        WHERE object_id = %s
        ORDER BY sort_order, label, url
        """,
        (object_id,),
    ).fetchall()
    urls = tuple((str(r["label"] or ""), str(r["url"])) for r in url_rows)

    prop_rows_db = conn.execute(
        """
        SELECT key, value_type, text_value, temporal_value
        FROM layer_object_properties
        WHERE object_id = %s
        """,
        (object_id,),
    ).fetchall()
    props: set[tuple[str, str, str]] = set()
    for prow in prop_rows_db:
        key = str(prow["key"])
        value_type = str(prow["value_type"])
        if value_type == "temporal" and prow.get("temporal_value") is not None:
            tv = prow["temporal_value"]
            if isinstance(tv, datetime):
                value_str = _as_aware_utc(tv).isoformat()
            else:
                value_str = str(tv)
        else:
            value_str = str(prow.get("text_value") or "")
            value_type = "text"
        props.add((key, value_type, value_str))

    return FeatureSnapshot(
        npu_objectid=npu_objectid,
        geometry_json=_geometry_json(geometry),
        tags=tags,
        urls=urls,
        props=frozenset(props),
    )


def feature_needs_update(
    conn: psycopg.Connection[Any],
    *,
    layer_id: Any,
    feature: dict[str, Any],
    tag_fields: set[str],
    url_fields: set[str],
    temporal_fields: set[str] | None = None,
) -> bool:
    """True when the feature is absent or differs from the stored snapshot."""
    incoming = snapshot_from_feature(
        feature,
        tag_fields=tag_fields,
        url_fields=url_fields,
        temporal_fields=temporal_fields,
    )
    if incoming is None:
        return False
    stored = load_db_snapshot(conn, layer_id=layer_id, npu_objectid=incoming.npu_objectid)
    if stored is None:
        return True
    return stored != incoming


def upsert_feature(
    conn: psycopg.Connection[Any],
    *,
    layer_id: Any,
    feature: dict[str, Any],
    tag_fields: set[str],
    url_fields: set[str],
    temporal_fields: set[str] | None = None,
) -> bool:
    """Upsert one GeoJSON Feature into layer_objects + children. Returns True if keyed."""
    props = dict(feature.get("properties") or {})
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or "type" not in geometry:
        logger.debug("Skipping feature without GeoJSON geometry")
        return False
    npu_id = extract_npu_objectid(props)
    if npu_id is None:
        logger.warning("Skipping feature without OBJECTID/id: keys=%s", list(props)[:12])
        return False

    geojson_text = json.dumps(geometry, separators=(",", ":"), ensure_ascii=False)
    column_values = extract_npu_column_values(props, parse_temporal=_parse_temporal)
    column_params = ordered_column_params(column_values)
    row = conn.execute(
        f"""
        INSERT INTO layer_objects (
            layer_id, npu_objectid, geometry, geom,
            {UPSERT_COLUMN_SQL}
        )
        VALUES (
            %s,
            %s,
            %s,
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
            {UPSERT_PLACEHOLDERS_SQL}
        )
        ON CONFLICT (layer_id, npu_objectid) WHERE npu_objectid IS NOT NULL
        DO UPDATE SET
            geometry = EXCLUDED.geometry,
            geom = EXCLUDED.geom,
            {UPSERT_UPDATE_SQL},
            updated_at = now()
        RETURNING id
        """,
        (layer_id, npu_id, Jsonb(geometry), geojson_text, *column_params),
    ).fetchone()
    assert row is not None
    object_id = row["id"]

    # Replace derived children for this sync (idempotent re-mirror)
    conn.execute("DELETE FROM layer_object_properties WHERE object_id = %s", (object_id,))
    conn.execute("DELETE FROM layer_object_urls WHERE object_id = %s", (object_id,))
    conn.execute("DELETE FROM layer_object_tags WHERE object_id = %s", (object_id,))

    url_order = 0
    for key, value in props.items():
        mapped = classify_attribute(
            key,
            value,
            tag_fields=tag_fields,
            url_fields=url_fields,
            temporal_fields=temporal_fields,
        )
        if mapped is None:
            continue
        kind, payload = mapped
        if kind == "tag":
            tag_name = str(payload)
            if not tag_name:
                continue
            tag = conn.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name,),
            ).fetchone()
            assert tag is not None
            conn.execute(
                """
                INSERT INTO layer_object_tags (object_id, tag_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (object_id, tag["id"]),
            )
        elif kind == "url":
            conn.execute(
                """
                INSERT INTO layer_object_urls (object_id, url, label, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (object_id, str(payload), key, url_order),
            )
            url_order += 1
        elif kind == "temporal":
            conn.execute(
                """
                INSERT INTO layer_object_properties (
                    object_id, key, value_type, temporal_value
                ) VALUES (%s, %s, 'temporal', %s)
                """,
                (object_id, key, payload),
            )
        else:
            conn.execute(
                """
                INSERT INTO layer_object_properties (
                    object_id, key, value_type, text_value
                ) VALUES (%s, %s, 'text', %s)
                """,
                (object_id, key, str(payload)),
            )
    return True


def upsert_detail_file(
    *,
    database_url: str,
    layer_id: Any,
    detail_path: Path,
    tag_fields: set[str] | None = None,
    url_fields: set[str] | None = None,
    temporal_fields: set[str] | None = None,
    only_if_changed: bool = False,
) -> UpsertStats:
    """Parse one wget detail JSON and upsert features in a single transaction.

    When ``only_if_changed`` is True, skip features whose DB snapshot already
    matches the incoming GeoJSON (diff mode).
    """
    tags = tag_fields or set()
    urls = url_fields or set()
    temporals = temporal_fields or set()
    data = load_json_file(detail_path)
    features = features_from_detail(data)
    upserted = 0
    unchanged = 0
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        try:
            for feature in features:
                if only_if_changed and not feature_needs_update(
                    conn,
                    layer_id=layer_id,
                    feature=feature,
                    tag_fields=tags,
                    url_fields=urls,
                    temporal_fields=temporals,
                ):
                    unchanged += 1
                    continue
                if upsert_feature(
                    conn,
                    layer_id=layer_id,
                    feature=feature,
                    tag_fields=tags,
                    url_fields=urls,
                    temporal_fields=temporals,
                ):
                    upserted += 1
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                "npu_upsert_failed path=%s features=%s",
                detail_path,
                len(features),
            )
            raise
    return UpsertStats(features=len(features), upserted=upserted, unchanged=unchanged)


def _parse_csv_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _find_bash_orchestrator() -> Path:
    """Locate ``scripts/sample-db-npu-sync`` from repo root or CWD."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "scripts" / "sample-db-npu-sync",  # …/src/pkg/sync → repo
        Path.cwd() / "scripts" / "sample-db-npu-sync",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        "Bash orchestrator not found (scripts/sample-db-npu-sync). "
        "Run from the repo root or install with scripts present."
    )


def main() -> None:
    """Thin wrapper: exec bash orchestrator (wget list → detail → Python insert)."""
    script = _find_bash_orchestrator()
    os.execve(str(script), [str(script), *sys.argv[1:]], os.environ)


def _cmd_page_size(args: argparse.Namespace) -> int:
    meta = parse_layer_metadata(load_json_file(Path(args.path)))
    print(page_size(meta))
    return 0


def _cmd_layer_name(args: argparse.Namespace) -> int:
    meta = parse_layer_metadata(load_json_file(Path(args.path)))
    override = (args.override or "").strip()
    print(override or meta.name)
    return 0


def _cmd_extract_ids(args: argparse.Namespace) -> int:
    ids = extract_object_ids(load_json_file(Path(args.path)))
    for oid in ids:
        print(oid)
    return 0


def _parse_id_lines(text: str) -> list[int]:
    """Parse one integer OBJECTID per non-empty line."""
    ids: list[int] = []
    for line in text.splitlines():
        item = line.strip()
        if not item:
            continue
        try:
            ids.append(int(item))
        except ValueError as exc:
            raise SystemExit(f"Non-integer object id: {item!r}") from exc
    return ids


def _cmd_missing_ids(args: argparse.Namespace) -> int:
    """Print candidate OBJECTIDs that are not yet in ``layer_objects``."""
    database_url = args.database_url or get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if args.path:
        candidates = _parse_id_lines(Path(args.path).read_text(encoding="utf-8"))
    else:
        candidates = _parse_id_lines(sys.stdin.read())
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        missing = missing_npu_objectids(
            conn,
            layer_id=args.layer_id,
            candidates=candidates,
        )
    for oid in missing:
        print(oid)
    return 0


def _cmd_ensure_layer(args: argparse.Namespace) -> int:
    database_url = args.database_url or get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    layer_root = _normalize_layer_root(args.layer_url)
    source_key = f"npu:{layer_root}"
    name = args.name or "NPÚ layer"
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        layer_id = ensure_layer(
            conn,
            source_key=source_key,
            source_url=layer_root,
            name=name,
            description=f"Mirrored from NPÚ Geoportal: {layer_root}",
        )
        conn.commit()
    print(layer_id)
    return 0


def _cmd_upsert_file(args: argparse.Namespace) -> int:
    database_url = args.database_url or get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    settings = get_settings()
    stats = upsert_detail_file(
        database_url=database_url,
        layer_id=args.layer_id,
        detail_path=Path(args.path),
        tag_fields=_parse_csv_set(args.tag_fields or settings.npu_tag_fields),
        url_fields=_parse_csv_set(args.url_fields or settings.npu_url_fields),
        temporal_fields=_parse_csv_set(args.temporal_fields or settings.npu_temporal_fields),
        only_if_changed=bool(args.only_if_changed),
    )
    logger.info(
        "npu_upsert_ok features=%s upserted=%s unchanged=%s path=%s",
        stats.features,
        stats.upserted,
        stats.unchanged,
        args.path,
    )
    print(f"{stats.upserted}/{stats.features}")
    return 0


def cli(argv: list[str] | None = None) -> int:
    """Argparse entry for bash helpers (parse JSON + DB inserts)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="npu_geoportal",
        description="NPÚ sync Python helpers: parse wget JSON + Postgres upserts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_page = sub.add_parser("page-size", help="Print client page size from meta JSON")
    p_page.add_argument("path", help="Path to wget meta JSON (?f=json)")
    p_page.set_defaults(func=_cmd_page_size)

    p_name = sub.add_parser("layer-name", help="Print layer display name from meta JSON")
    p_name.add_argument("path", help="Path to wget meta JSON")
    p_name.add_argument("--override", default="", help="Optional NPU_LAYER_NAME override")
    p_name.set_defaults(func=_cmd_layer_name)

    p_ids = sub.add_parser("extract-ids", help="Print OBJECTIDs from returnIdsOnly JSON")
    p_ids.add_argument("path", help="Path to pamatky.json (ID list)")
    p_ids.set_defaults(func=_cmd_extract_ids)

    p_miss = sub.add_parser(
        "missing-ids",
        help="Filter OBJECTIDs: print those not yet in layer_objects",
    )
    p_miss.add_argument(
        "path",
        nargs="?",
        default="",
        help="Optional file of one OBJECTID per line (default: stdin)",
    )
    p_miss.add_argument("--layer-id", required=True)
    p_miss.add_argument("--database-url", default="")
    p_miss.set_defaults(func=_cmd_missing_ids)

    p_ensure = sub.add_parser("ensure-layer", help="Upsert map_layers row; print UUID")
    p_ensure.add_argument("--layer-url", required=True)
    p_ensure.add_argument("--name", default="")
    p_ensure.add_argument("--database-url", default="")
    p_ensure.set_defaults(func=_cmd_ensure_layer)

    p_up = sub.add_parser("upsert-file", help="Upsert GeoJSON detail file into Postgres")
    p_up.add_argument("path", help="Path to wget detail GeoJSON")
    p_up.add_argument("--layer-id", required=True)
    p_up.add_argument("--database-url", default="")
    p_up.add_argument("--tag-fields", default="")
    p_up.add_argument("--url-fields", default="")
    p_up.add_argument("--temporal-fields", default="")
    p_up.add_argument(
        "--only-if-changed",
        action="store_true",
        help="Skip features whose stored snapshot already matches (diff mode)",
    )
    p_up.set_defaults(func=_cmd_upsert_file)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    # ``python -m sample_db_backend.sync.npu_geoportal …`` → helpers
    # ``sample-db-npu-sync`` console script → main() → bash
    raise SystemExit(cli())
