"""NPÚ Geoportal sync — Python side: JSON parse/transform + Postgres upserts.

HTTP fetches are owned by the bash orchestrator (``scripts/sample-db-npu-sync``)
via ``wget -O``. This module never calls wget/httpx/requests for NPÚ.

Bash flow (Marek):
  1. wget object **list** JSON (``returnIdsOnly`` pages → ``pamatky.json``)
  2. for each id (or small batch): wget **detail** GeoJSON
  3. Python transform + insert/upsert into destination Postgres

CLI (invoked by bash)::

    uv run python -m sample_db_backend.sync.npu_geoportal page-size META.json
    uv run python -m sample_db_backend.sync.npu_geoportal extract-ids LIST.json
    uv run python -m sample_db_backend.sync.npu_geoportal ensure-layer ...
    uv run python -m sample_db_backend.sync.npu_geoportal upsert-file DETAIL.json ...

Entrypoint ``sample-db-npu-sync`` execs the bash script.
"""

from __future__ import annotations

import argparse
import json
import logging
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
_EPOCH_MS_MIN = 1_000_000_000_000  # ~2001 in ms
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


def _parse_temporal(value: Any) -> datetime | None:
    """Parse ArcGIS epoch-ms or ISO-ish strings into aware datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        if num >= _EPOCH_MS_MIN:
            return datetime.fromtimestamp(num / 1000.0, tz=UTC)
        if num > 1_000_000_000:  # seconds
            return datetime.fromtimestamp(num, tz=UTC)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
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
    """
    if value is None or value == "" or _is_skip_key(key):
        return None
    temporal_fields = temporal_fields or set()
    lower = key.lower()
    if _field_match(key, tag_fields):
        return ("tag", str(value).strip())
    if _field_match(key, url_fields):
        return ("url", str(value).strip())
    if isinstance(value, str) and _URL_RE.match(value.strip()):
        return ("url", value.strip())
    temporal = _parse_temporal(value)
    if _field_match(key, temporal_fields):
        if temporal is not None:
            return ("temporal", temporal)
        return ("text", str(value))
    dateish = "date" in lower or "datum" in lower or "time" in lower
    if temporal is not None and (dateish or isinstance(value, (int, float))):
        return ("temporal", temporal)
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

    row = conn.execute(
        """
        INSERT INTO layer_objects (layer_id, npu_objectid, geometry)
        VALUES (%s, %s, %s)
        ON CONFLICT (layer_id, npu_objectid) WHERE npu_objectid IS NOT NULL
        DO UPDATE SET
            geometry = EXCLUDED.geometry,
            updated_at = now()
        RETURNING id
        """,
        (layer_id, npu_id, Jsonb(geometry)),
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
) -> UpsertStats:
    """Parse one wget detail JSON and upsert all features in a single transaction."""
    tags = tag_fields or set()
    urls = url_fields or set()
    temporals = temporal_fields or set()
    data = load_json_file(detail_path)
    features = features_from_detail(data)
    upserted = 0
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        try:
            for feature in features:
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
    return UpsertStats(features=len(features), upserted=upserted)


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
    )
    logger.info(
        "npu_upsert_ok features=%s upserted=%s path=%s",
        stats.features,
        stats.upserted,
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
    p_up.set_defaults(func=_cmd_upsert_file)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    # ``python -m sample_db_backend.sync.npu_geoportal …`` → helpers
    # ``sample-db-npu-sync`` console script → main() → bash
    raise SystemExit(cli())
