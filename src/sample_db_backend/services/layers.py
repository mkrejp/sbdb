"""CRUD services for layers, objects, typed properties, tags, and URLs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation

from sample_db_backend.db import (
    as_jsonb,
    database_configured,
    get_connection,
    stub_layers,
    stub_object_tags,
    stub_objects,
    stub_properties,
    stub_tags,
    stub_urls,
)
from sample_db_backend.schemas import (
    Layer,
    LayerCreate,
    LayerObject,
    LayerUpdate,
    ObjectCreate,
    ObjectProperty,
    ObjectUpdate,
    ObjectUrl,
    ObjectUrlCreate,
    ObjectUrlUpdate,
    PropertyCreate,
    PropertyUpdate,
    PropertyValueType,
    Tag,
    TagCreate,
    TagUpdate,
)


class NotFoundError(Exception):
    """Missing resource."""


class ConflictError(Exception):
    """Unique constraint conflict."""


def _now() -> datetime:
    return datetime.now(UTC)


def _layer(row: dict[str, Any]) -> Layer:
    return Layer.model_validate(row)


def _object(row: dict[str, Any]) -> LayerObject:
    return LayerObject.model_validate(row)


def _prop(row: dict[str, Any]) -> ObjectProperty:
    data = dict(row)
    if isinstance(data.get("value_type"), str):
        data["value_type"] = PropertyValueType(data["value_type"])
    if data.get("meta") is None:
        data["meta"] = {}
    return ObjectProperty.model_validate(data)


def _tag(row: dict[str, Any]) -> Tag:
    return Tag.model_validate(row)


def _url(row: dict[str, Any]) -> ObjectUrl:
    return ObjectUrl.model_validate(row)


# --- layers ------------------------------------------------------------------


_LAYER_COLS = "id, name, description, source_key, source_url, created_at, updated_at"


def list_layers(*, limit: int = 50) -> list[Layer]:
    """List layers newest-first."""
    if not database_configured():
        rows = sorted(stub_layers(), key=lambda r: r["created_at"], reverse=True)[:limit]
        return [_layer(r) for r in rows]
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_LAYER_COLS}
            FROM map_layers ORDER BY created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [_layer(dict(r)) for r in rows]


def get_layer(layer_id: UUID) -> Layer:
    """Fetch one layer."""
    if not database_configured():
        for row in stub_layers():
            if row["id"] == layer_id:
                return _layer(row)
        raise NotFoundError(str(layer_id))
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_LAYER_COLS} FROM map_layers WHERE id = %s",
            (layer_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError(str(layer_id))
    return _layer(dict(row))


def create_layer(payload: LayerCreate) -> Layer:
    """Insert a layer."""
    if not database_configured():
        now = _now()
        row = {
            "id": uuid4(),
            "name": payload.name,
            "description": payload.description,
            "source_key": None,
            "source_url": None,
            "created_at": now,
            "updated_at": now,
        }
        stub_layers().append(row)
        return _layer(row)
    with get_connection() as conn:
        row = conn.execute(
            f"""
            INSERT INTO map_layers (name, description) VALUES (%s, %s)
            RETURNING {_LAYER_COLS}
            """,
            (payload.name, payload.description),
        ).fetchone()
        conn.commit()
    assert row is not None
    return _layer(dict(row))


def update_layer(layer_id: UUID, payload: LayerUpdate) -> Layer:
    """Partial-update a layer."""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_layer(layer_id)
    if not database_configured():
        for row in stub_layers():
            if row["id"] == layer_id:
                row.update(data)
                row["updated_at"] = _now()
                return _layer(row)
        raise NotFoundError(str(layer_id))
    sets = [f"{k} = %s" for k in data]
    values: list[Any] = list(data.values()) + [layer_id]
    with get_connection() as conn:
        row = conn.execute(
            f"UPDATE map_layers SET {', '.join(sets)} WHERE id = %s RETURNING {_LAYER_COLS}",
            values,
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(layer_id))
    return _layer(dict(row))


def delete_layer(layer_id: UUID) -> None:
    """Delete layer and cascade stub children."""
    if not database_configured():
        layers = stub_layers()
        for idx, row in enumerate(layers):
            if row["id"] == layer_id:
                obj_ids = {o["id"] for o in stub_objects() if o["layer_id"] == layer_id}
                stub_objects()[:] = [o for o in stub_objects() if o["layer_id"] != layer_id]
                stub_properties()[:] = [
                    p for p in stub_properties() if p["object_id"] not in obj_ids
                ]
                stub_object_tags()[:] = [
                    t for t in stub_object_tags() if t["object_id"] not in obj_ids
                ]
                stub_urls()[:] = [u for u in stub_urls() if u["object_id"] not in obj_ids]
                del layers[idx]
                return
        raise NotFoundError(str(layer_id))
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM map_layers WHERE id = %s RETURNING id", (layer_id,)
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(layer_id))


# --- objects -----------------------------------------------------------------


# GeoJSON for REST: prefer PostGIS geom (source of truth), fall back to JSONB.
_OBJECT_SELECT = (
    "id, layer_id, "
    "COALESCE(ST_AsGeoJSON(geom)::jsonb, geometry) AS geometry, "
    "created_at, updated_at"
)


def _geojson_text(geometry: dict[str, Any]) -> str:
    """Serialize GeoJSON for ST_GeomFromGeoJSON."""
    return json.dumps(geometry, separators=(",", ":"), ensure_ascii=False)


def list_objects(
    layer_id: UUID | None = None,
    *,
    tag: str | None = None,
    limit: int = 100,
) -> list[LayerObject]:
    """List objects, optionally scoped to a layer and/or tag name."""
    if layer_id is not None:
        get_layer(layer_id)
    if not database_configured():
        rows = list(stub_objects())
        if layer_id is not None:
            rows = [o for o in rows if o["layer_id"] == layer_id]
        if tag is not None:
            tag_ids = {t["id"] for t in stub_tags() if t["name"] == tag}
            linked = {ot["object_id"] for ot in stub_object_tags() if ot["tag_id"] in tag_ids}
            rows = [o for o in rows if o["id"] in linked]
        return [_object(r) for r in rows[:limit]]
    clauses: list[str] = []
    params: list[Any] = []
    if layer_id is not None:
        clauses.append("o.layer_id = %s")
        params.append(layer_id)
    join = ""
    if tag is not None:
        join = "JOIN layer_object_tags ot ON ot.object_id = o.id JOIN tags t ON t.id = ot.tag_id"
        clauses.append("t.name = %s")
        params.append(tag)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT
                o.id,
                o.layer_id,
                COALESCE(ST_AsGeoJSON(o.geom)::jsonb, o.geometry) AS geometry,
                o.created_at,
                o.updated_at
            FROM layer_objects o
            {join}
            {where}
            ORDER BY o.created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return [_object(dict(r)) for r in rows]


def get_object(object_id: UUID) -> LayerObject:
    """Fetch one layer object."""
    if not database_configured():
        for row in stub_objects():
            if row["id"] == object_id:
                return _object(row)
        raise NotFoundError(str(object_id))
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT {_OBJECT_SELECT}
            FROM layer_objects WHERE id = %s
            """,
            (object_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError(str(object_id))
    return _object(dict(row))


def create_object(layer_id: UUID, payload: ObjectCreate) -> LayerObject:
    """Create an object under a layer (dual-write JSONB + PostGIS)."""
    get_layer(layer_id)
    if not database_configured():
        now = _now()
        row = {
            "id": uuid4(),
            "layer_id": layer_id,
            "geometry": payload.geometry,
            "created_at": now,
            "updated_at": now,
        }
        stub_objects().append(row)
        return _object(row)
    with get_connection() as conn:
        row = conn.execute(
            f"""
            INSERT INTO layer_objects (layer_id, geometry, geom)
            VALUES (
                %s,
                %s,
                ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
            )
            RETURNING {_OBJECT_SELECT}
            """,
            (layer_id, as_jsonb(payload.geometry), _geojson_text(payload.geometry)),
        ).fetchone()
        conn.commit()
    assert row is not None
    return _object(dict(row))


def update_object(object_id: UUID, payload: ObjectUpdate) -> LayerObject:
    """Update object geometry (dual-write JSONB + PostGIS)."""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_object(object_id)
    if not database_configured():
        for row in stub_objects():
            if row["id"] == object_id:
                row.update(data)
                row["updated_at"] = _now()
                return _object(row)
        raise NotFoundError(str(object_id))
    geometry = data["geometry"]
    with get_connection() as conn:
        row = conn.execute(
            f"""
            UPDATE layer_objects
            SET geometry = %s,
                geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
            WHERE id = %s
            RETURNING {_OBJECT_SELECT}
            """,
            (as_jsonb(geometry), _geojson_text(geometry), object_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(object_id))
    return _object(dict(row))


def delete_object(object_id: UUID) -> None:
    """Delete an object and stub children."""
    if not database_configured():
        objs = stub_objects()
        for idx, row in enumerate(objs):
            if row["id"] == object_id:
                stub_properties()[:] = [p for p in stub_properties() if p["object_id"] != object_id]
                stub_object_tags()[:] = [
                    t for t in stub_object_tags() if t["object_id"] != object_id
                ]
                stub_urls()[:] = [u for u in stub_urls() if u["object_id"] != object_id]
                del objs[idx]
                return
        raise NotFoundError(str(object_id))
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM layer_objects WHERE id = %s RETURNING id", (object_id,)
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(object_id))


# --- properties --------------------------------------------------------------


_PROP_COLS = (
    "id, object_id, key, value_type, text_value, temporal_value, temporal_end, "
    "storage_bucket, storage_path, storage_url, content_type, byte_size, checksum, "
    "meta, created_at, updated_at"
)


def list_properties(object_id: UUID) -> list[ObjectProperty]:
    """List typed properties for an object."""
    get_object(object_id)
    if not database_configured():
        return [_prop(p) for p in stub_properties() if p["object_id"] == object_id]
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_PROP_COLS} FROM layer_object_properties WHERE object_id = %s ORDER BY key",
            (object_id,),
        ).fetchall()
    return [_prop(dict(r)) for r in rows]


def get_property(property_id: UUID) -> ObjectProperty:
    """Fetch one property."""
    if not database_configured():
        for row in stub_properties():
            if row["id"] == property_id:
                return _prop(row)
        raise NotFoundError(str(property_id))
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_PROP_COLS} FROM layer_object_properties WHERE id = %s",
            (property_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError(str(property_id))
    return _prop(dict(row))


def create_property(object_id: UUID, payload: PropertyCreate) -> ObjectProperty:
    """Create a typed property."""
    get_object(object_id)
    data = payload.model_dump()
    data["value_type"] = payload.value_type.value
    if not database_configured():
        for row in stub_properties():
            if row["object_id"] == object_id and row["key"] == payload.key:
                raise ConflictError(payload.key)
        now = _now()
        row = {"id": uuid4(), "object_id": object_id, **data, "created_at": now, "updated_at": now}
        stub_properties().append(row)
        return _prop(row)
    try:
        with get_connection() as conn:
            row = conn.execute(
                f"""
                INSERT INTO layer_object_properties (
                    object_id, key, value_type, text_value, temporal_value, temporal_end,
                    storage_bucket, storage_path, storage_url, content_type, byte_size,
                    checksum, meta
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING {_PROP_COLS}
                """,
                (
                    object_id,
                    payload.key,
                    payload.value_type.value,
                    payload.text_value,
                    payload.temporal_value,
                    payload.temporal_end,
                    payload.storage_bucket,
                    payload.storage_path,
                    payload.storage_url,
                    payload.content_type,
                    payload.byte_size,
                    payload.checksum,
                    as_jsonb(payload.meta),
                ),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ConflictError(payload.key) from exc
    assert row is not None
    return _prop(dict(row))


def update_property(property_id: UUID, payload: PropertyUpdate) -> ObjectProperty:
    """Partial-update property fields (value_type is immutable in this slice)."""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_property(property_id)
    if not database_configured():
        for row in stub_properties():
            if row["id"] == property_id:
                new_key = data.get("key", row["key"])
                for other in stub_properties():
                    if (
                        other["id"] != property_id
                        and other["object_id"] == row["object_id"]
                        and other["key"] == new_key
                    ):
                        raise ConflictError(new_key)
                row.update(data)
                row["updated_at"] = _now()
                return _prop(row)
        raise NotFoundError(str(property_id))
    sets: list[str] = []
    values: list[Any] = []
    for key, value in data.items():
        sets.append(f"{key} = %s")
        values.append(as_jsonb(value) if key == "meta" else value)
    values.append(property_id)
    try:
        with get_connection() as conn:
            row = conn.execute(
                f"UPDATE layer_object_properties SET {', '.join(sets)} WHERE id = %s "
                f"RETURNING {_PROP_COLS}",
                values,
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ConflictError(str(data.get("key", ""))) from exc
    if row is None:
        raise NotFoundError(str(property_id))
    return _prop(dict(row))


def delete_property(property_id: UUID) -> None:
    """Delete a property."""
    if not database_configured():
        props = stub_properties()
        for idx, row in enumerate(props):
            if row["id"] == property_id:
                del props[idx]
                return
        raise NotFoundError(str(property_id))
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM layer_object_properties WHERE id = %s RETURNING id",
            (property_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(property_id))


# --- tags --------------------------------------------------------------------


def list_tags(*, limit: int = 100) -> list[Tag]:
    """List tags."""
    if not database_configured():
        return [_tag(t) for t in stub_tags()[:limit]]
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM tags ORDER BY name LIMIT %s",
            (limit,),
        ).fetchall()
    return [_tag(dict(r)) for r in rows]


def get_tag(tag_id: UUID) -> Tag:
    """Fetch one tag."""
    if not database_configured():
        for row in stub_tags():
            if row["id"] == tag_id:
                return _tag(row)
        raise NotFoundError(str(tag_id))
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, updated_at FROM tags WHERE id = %s",
            (tag_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError(str(tag_id))
    return _tag(dict(row))


def create_tag(payload: TagCreate) -> Tag:
    """Create a tag."""
    if not database_configured():
        for row in stub_tags():
            if row["name"] == payload.name:
                raise ConflictError(payload.name)
        now = _now()
        row = {"id": uuid4(), "name": payload.name, "created_at": now, "updated_at": now}
        stub_tags().append(row)
        return _tag(row)
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                RETURNING id, name, created_at, updated_at
                """,
                (payload.name,),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ConflictError(payload.name) from exc
    assert row is not None
    return _tag(dict(row))


def update_tag(tag_id: UUID, payload: TagUpdate) -> Tag:
    """Rename a tag."""
    if not database_configured():
        for row in stub_tags():
            if row["id"] == tag_id:
                for other in stub_tags():
                    if other["id"] != tag_id and other["name"] == payload.name:
                        raise ConflictError(payload.name)
                row["name"] = payload.name
                row["updated_at"] = _now()
                return _tag(row)
        raise NotFoundError(str(tag_id))
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE tags SET name = %s WHERE id = %s
                RETURNING id, name, created_at, updated_at
                """,
                (payload.name, tag_id),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ConflictError(payload.name) from exc
    if row is None:
        raise NotFoundError(str(tag_id))
    return _tag(dict(row))


def delete_tag(tag_id: UUID) -> None:
    """Delete a tag and stub links."""
    if not database_configured():
        tags = stub_tags()
        for idx, row in enumerate(tags):
            if row["id"] == tag_id:
                stub_object_tags()[:] = [t for t in stub_object_tags() if t["tag_id"] != tag_id]
                del tags[idx]
                return
        raise NotFoundError(str(tag_id))
    with get_connection() as conn:
        row = conn.execute("DELETE FROM tags WHERE id = %s RETURNING id", (tag_id,)).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(tag_id))


def list_object_tags(object_id: UUID) -> list[Tag]:
    """List tags attached to an object."""
    get_object(object_id)
    if not database_configured():
        tag_ids = {t["tag_id"] for t in stub_object_tags() if t["object_id"] == object_id}
        return [_tag(t) for t in stub_tags() if t["id"] in tag_ids]
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.created_at, t.updated_at
            FROM tags t
            JOIN layer_object_tags ot ON ot.tag_id = t.id
            WHERE ot.object_id = %s
            ORDER BY t.name
            """,
            (object_id,),
        ).fetchall()
    return [_tag(dict(r)) for r in rows]


def attach_tag(object_id: UUID, tag_id: UUID) -> None:
    """Attach a tag to an object (idempotent)."""
    get_object(object_id)
    get_tag(tag_id)
    if not database_configured():
        for link in stub_object_tags():
            if link["object_id"] == object_id and link["tag_id"] == tag_id:
                return
        stub_object_tags().append({"object_id": object_id, "tag_id": tag_id, "created_at": _now()})
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO layer_object_tags (object_id, tag_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (object_id, tag_id),
        )
        conn.commit()


def detach_tag(object_id: UUID, tag_id: UUID) -> None:
    """Detach a tag from an object."""
    get_object(object_id)
    get_tag(tag_id)
    if not database_configured():
        links = stub_object_tags()
        for idx, link in enumerate(links):
            if link["object_id"] == object_id and link["tag_id"] == tag_id:
                del links[idx]
                return
        raise NotFoundError(f"{object_id}:{tag_id}")
    with get_connection() as conn:
        row = conn.execute(
            """
            DELETE FROM layer_object_tags
            WHERE object_id = %s AND tag_id = %s
            RETURNING object_id
            """,
            (object_id, tag_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(f"{object_id}:{tag_id}")


# --- object URLs -------------------------------------------------------------


def list_urls(object_id: UUID) -> list[ObjectUrl]:
    """List URLs for an object ordered by sort_order."""
    get_object(object_id)
    if not database_configured():
        rows = [u for u in stub_urls() if u["object_id"] == object_id]
        rows.sort(key=lambda r: (r["sort_order"], r["created_at"]))
        return [_url(r) for r in rows]
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, object_id, url, label, sort_order, created_at, updated_at
            FROM layer_object_urls
            WHERE object_id = %s
            ORDER BY sort_order ASC, created_at ASC
            """,
            (object_id,),
        ).fetchall()
    return [_url(dict(r)) for r in rows]


def get_url(url_id: UUID) -> ObjectUrl:
    """Fetch one URL row."""
    if not database_configured():
        for row in stub_urls():
            if row["id"] == url_id:
                return _url(row)
        raise NotFoundError(str(url_id))
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, object_id, url, label, sort_order, created_at, updated_at
            FROM layer_object_urls WHERE id = %s
            """,
            (url_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError(str(url_id))
    return _url(dict(row))


def create_url(object_id: UUID, payload: ObjectUrlCreate) -> ObjectUrl:
    """Append a URL to an object's list."""
    get_object(object_id)
    if not database_configured():
        now = _now()
        row = {
            "id": uuid4(),
            "object_id": object_id,
            "url": payload.url,
            "label": payload.label,
            "sort_order": payload.sort_order,
            "created_at": now,
            "updated_at": now,
        }
        stub_urls().append(row)
        return _url(row)
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO layer_object_urls (object_id, url, label, sort_order)
            VALUES (%s, %s, %s, %s)
            RETURNING id, object_id, url, label, sort_order, created_at, updated_at
            """,
            (object_id, payload.url, payload.label, payload.sort_order),
        ).fetchone()
        conn.commit()
    assert row is not None
    return _url(dict(row))


def update_url(url_id: UUID, payload: ObjectUrlUpdate) -> ObjectUrl:
    """Partial-update a URL row."""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_url(url_id)
    if not database_configured():
        for row in stub_urls():
            if row["id"] == url_id:
                row.update(data)
                row["updated_at"] = _now()
                return _url(row)
        raise NotFoundError(str(url_id))
    sets = [f"{k} = %s" for k in data]
    values: list[Any] = list(data.values()) + [url_id]
    with get_connection() as conn:
        row = conn.execute(
            f"UPDATE layer_object_urls SET {', '.join(sets)} WHERE id = %s "
            "RETURNING id, object_id, url, label, sort_order, created_at, updated_at",
            values,
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(url_id))
    return _url(dict(row))


def delete_url(url_id: UUID) -> None:
    """Delete a URL row."""
    if not database_configured():
        urls = stub_urls()
        for idx, row in enumerate(urls):
            if row["id"] == url_id:
                del urls[idx]
                return
        raise NotFoundError(str(url_id))
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM layer_object_urls WHERE id = %s RETURNING id",
            (url_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(str(url_id))
