"""Database connection helpers and in-memory stub stores."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from sample_db_backend.config import get_settings

_layers: list[dict[str, Any]] = []
_objects: list[dict[str, Any]] = []
_properties: list[dict[str, Any]] = []
_tags: list[dict[str, Any]] = []
_object_tags: list[dict[str, Any]] = []
_urls: list[dict[str, Any]] = []


def database_configured() -> bool:
    """Return True when a DATABASE_URL is present."""
    return bool(get_settings().database_url)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection[Any]]:
    """Open a short-lived connection to Supabase Postgres."""
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    with psycopg.connect(url, row_factory=dict_row) as conn:
        yield conn


def probe_database() -> str:
    """Probe DB connectivity. Returns connected|skipped|unavailable."""
    if not database_configured():
        return "skipped"
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return "connected"
    except Exception:
        return "unavailable"


def stub_layers() -> list[dict[str, Any]]:
    """In-memory layers."""
    return _layers


def stub_objects() -> list[dict[str, Any]]:
    """In-memory layer objects."""
    return _objects


def stub_properties() -> list[dict[str, Any]]:
    """In-memory typed properties."""
    return _properties


def stub_tags() -> list[dict[str, Any]]:
    """In-memory tags."""
    return _tags


def stub_object_tags() -> list[dict[str, Any]]:
    """In-memory object↔tag links."""
    return _object_tags


def stub_urls() -> list[dict[str, Any]]:
    """In-memory object URL rows."""
    return _urls


def clear_memory_store() -> None:
    """Clear all stub collections (tests)."""
    _layers.clear()
    _objects.clear()
    _properties.clear()
    _tags.clear()
    _object_tags.clear()
    _urls.clear()


def as_jsonb(value: Any) -> Jsonb:
    """Wrap a Python value for psycopg JSONB binding."""
    return Jsonb(value)
