"""Tests for database connection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from sample_db_backend.config import get_settings
from sample_db_backend.db import get_connection

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_get_connection_sets_search_path(monkeypatch: MonkeyPatch) -> None:
    """Production PostGIS is in schema extensions; session search_path must include it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/geobjectsdb")
    get_settings.cache_clear()
    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_conn
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr("sample_db_backend.db.psycopg.connect", MagicMock(return_value=mock_cm))

    try:
        with get_connection() as conn:
            assert conn is mock_conn
            mock_conn.execute.assert_called_once_with("SET search_path TO public, extensions")
    finally:
        get_settings.cache_clear()


def test_get_connection_requires_database_url(monkeypatch: MonkeyPatch) -> None:
    """Stub mode (no DATABASE_URL) still refuses to open a connection."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            with get_connection():
                pass
    finally:
        get_settings.cache_clear()
