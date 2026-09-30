"""NPÚ Geoportal REST → Postgres mirror (safe pagination).

Follows docs/npu-geoportal-sync.md:
- Read layer metadata for maxRecordCount / supportsPagination
- Page with resultOffset + resultRecordCount
- Request GeoJSON outSR=4326
- Upsert by NPÚ OBJECTID/id into layer_objects.npu_objectid
- Stream page → upsert (free-tier friendly; avoid holding huge layers in memory)

Usage::

    uv run sample-db-npu-sync

Env:
    DATABASE_URL              required for upsert
    NPU_LAYER_URL             FeatureServer/MapServer *layer root* (…/FeatureServer/0)
    NPU_LAYER_NAME            optional display name for map_layers
    NPU_TAG_FIELDS            comma-separated attribute names → tags (optional)
    NPU_URL_FIELDS            comma-separated attribute names → object URLs (optional)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from sample_db_backend.config import get_settings

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class LayerMeta:
    """Subset of ArcGIS layer metadata needed for safe paging."""

    name: str
    max_record_count: int
    supports_pagination: bool


@dataclass(frozen=True)
class SyncStats:
    """Counters from one sync run."""

    pages: int
    features: int
    upserted: int
    layer_id: str


def _normalize_layer_root(url: str) -> str:
    """Strip trailing /query and slash from a layer URL."""
    cleaned = url.strip().rstrip("/")
    if cleaned.lower().endswith("/query"):
        cleaned = cleaned[: -len("/query")].rstrip("/")
    return cleaned


def fetch_layer_metadata(client: httpx.Client, layer_root: str) -> LayerMeta:
    """GET layer root metadata JSON; require pagination support."""
    response = client.get(layer_root, params={"f": "json"})
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Layer metadata error: {data['error']}")

    max_count = int(data.get("maxRecordCount") or 1000)
    supports = bool(data.get("advancedQueryCapabilities", {}).get("supportsPagination"))
    if not supports and data.get("supportsPagination") is True:
        supports = True
    name = str(data.get("name") or "NPÚ layer")
    if not supports:
        logger.warning(
            "Layer %s does not advertise supportsPagination; proceeding cautiously "
            "with resultOffset paging (verify server behavior).",
            layer_root,
        )
    return LayerMeta(name=name, max_record_count=max_count, supports_pagination=supports)


def _page_size(meta: LayerMeta) -> int:
    """Client page size at or below server maxRecordCount."""
    return max(1, min(meta.max_record_count, 1000))


def iter_geojson_pages(
    client: httpx.Client,
    layer_root: str,
    *,
    page_size: int,
) -> Iterator[list[dict[str, Any]]]:
    """Yield GeoJSON Feature lists using resultOffset / resultRecordCount."""
    query_url = urljoin(layer_root + "/", "query")
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        response = client.get(query_url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            raise RuntimeError(f"Query error at offset {offset}: {payload['error']}")

        features: list[dict[str, Any]]
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            features = list(payload.get("features") or [])
        elif isinstance(payload, dict) and "features" in payload:
            features = list(payload.get("features") or [])
        else:
            raise RuntimeError(f"Unexpected query payload type at offset {offset}")

        if not features:
            break
        yield features
        if len(features) < page_size:
            break
        offset += len(features)


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


def classify_attribute(
    key: str,
    value: Any,
    *,
    tag_fields: set[str],
    url_fields: set[str],
) -> tuple[str, Any] | None:
    """Map one NPÚ attribute into (kind, payload).

    kind ∈ {tag, url, temporal, text}; returns None to skip.
    """
    if value is None or value == "" or _is_skip_key(key):
        return None
    lower = key.lower()
    if key in tag_fields or lower in {t.lower() for t in tag_fields}:
        return ("tag", str(value).strip())
    if key in url_fields or lower in {u.lower() for u in url_fields}:
        return ("url", str(value).strip())
    if isinstance(value, str) and _URL_RE.match(value.strip()):
        return ("url", value.strip())
    temporal = _parse_temporal(value)
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
        mapped = classify_attribute(key, value, tag_fields=tag_fields, url_fields=url_fields)
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


def sync_layer(
    *,
    database_url: str,
    layer_url: str,
    layer_name: str | None = None,
    tag_fields: set[str] | None = None,
    url_fields: set[str] | None = None,
    timeout_s: float = 60.0,
) -> SyncStats:
    """Fetch NPÚ layer pages and upsert into Postgres (JSONB geometry)."""
    layer_root = _normalize_layer_root(layer_url)
    source_key = f"npu:{layer_root}"
    tags = tag_fields or set()
    urls = url_fields or set()

    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        meta = fetch_layer_metadata(client, layer_root)
        page_size = _page_size(meta)
        display_name = layer_name or meta.name
        logger.info(
            "NPÚ sync %s maxRecordCount=%s page_size=%s supportsPagination=%s",
            layer_root,
            meta.max_record_count,
            page_size,
            meta.supports_pagination,
        )

        pages = 0
        features_total = 0
        upserted = 0
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            layer_id = ensure_layer(
                conn,
                source_key=source_key,
                source_url=layer_root,
                name=display_name,
                description=f"Mirrored from NPÚ Geoportal: {layer_root}",
            )
            conn.commit()

            for page in iter_geojson_pages(client, layer_root, page_size=page_size):
                pages += 1
                features_total += len(page)
                for feature in page:
                    if upsert_feature(
                        conn,
                        layer_id=layer_id,
                        feature=feature,
                        tag_fields=tags,
                        url_fields=urls,
                    ):
                        upserted += 1
                conn.commit()
                logger.info("Committed page %s (%s features)", pages, len(page))

    return SyncStats(
        pages=pages,
        features=features_total,
        upserted=upserted,
        layer_id=str(layer_id),
    )


def _parse_csv_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def main() -> None:
    """CLI entry: sync one configured NPÚ layer into DATABASE_URL."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required for NPÚ sync")
    if not settings.npu_layer_url:
        raise SystemExit(
            "NPU_LAYER_URL is required (ArcGIS FeatureServer/MapServer layer root). "
            "See docs/npu-geoportal-sync.md — placeholder example in .env.example."
        )

    stats = sync_layer(
        database_url=settings.database_url,
        layer_url=settings.npu_layer_url,
        layer_name=settings.npu_layer_name,
        tag_fields=_parse_csv_set(settings.npu_tag_fields),
        url_fields=_parse_csv_set(settings.npu_url_fields),
    )
    logger.info(
        "Done pages=%s features=%s upserted=%s layer_id=%s",
        stats.pages,
        stats.features,
        stats.upserted,
        stats.layer_id,
    )


if __name__ == "__main__":
    main()
