"""Unit tests for NPÚ Geoportal sync helpers (mocked wget; no live network / DB)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest

from sample_db_backend.sync.npu_geoportal import (
    SYNC_ACCEPT,
    SYNC_HEADERS,
    SYNC_USER_AGENT,
    WgetError,
    _build_wget_argv,
    classify_attribute,
    extract_npu_objectid,
    fetch_json_with_retries,
    fetch_layer_metadata,
    iter_geojson_pages,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_extract_npu_objectid_prefers_objectid() -> None:
    """OBJECTID wins over id."""
    assert extract_npu_objectid({"OBJECTID": 42, "id": 9}) == 42
    assert extract_npu_objectid({"id": "7"}) == 7
    assert extract_npu_objectid({"name": "x"}) is None


def test_classify_attribute_routes() -> None:
    """Attributes map to tag / url / temporal / text."""
    assert classify_attribute("TYP", "hrad", tag_fields={"TYP"}, url_fields=set()) == (
        "tag",
        "hrad",
    )
    assert classify_attribute(
        "ODKAZ",
        "https://example.com/a",
        tag_fields=set(),
        url_fields={"ODKAZ"},
    ) == ("url", "https://example.com/a")
    assert classify_attribute(
        "WWW",
        "https://npu.cz/x",
        tag_fields=set(),
        url_fields=set(),
    ) == ("url", "https://npu.cz/x")
    kind, value = classify_attribute(
        "DATUM",
        1_700_000_000_000,
        tag_fields=set(),
        url_fields=set(),
    ) or (None, None)
    assert kind == "temporal"
    assert isinstance(value, datetime)
    assert value.tzinfo == UTC
    assert classify_attribute("NAZEV", "Karlštejn", tag_fields=set(), url_fields=set()) == (
        "text",
        "Karlštejn",
    )
    assert classify_attribute("OBJECTID", 1, tag_fields=set(), url_fields=set()) is None


def test_classify_cp_uap_pvo_defaults() -> None:
    """CP_UAP_PVO field defaults map to tags / urls / temporal."""
    tags = {
        "Subtyp",
        "typOchranyKod",
        "typOchranyNazev",
        "fazeOchranyKod",
        "fazeOchranyNazev",
        "PrStavNazev",
    }
    urls = {"urlExt", "urlInt"}
    temporals = {"platn_od", "platn_do", "aktual", "datumStavuOchrany"}
    assert classify_attribute(
        "Subtyp", "NKP", tag_fields=tags, url_fields=urls, temporal_fields=temporals
    ) == ("tag", "NKP")
    assert classify_attribute(
        "urlExt",
        "https://npu.cz/a",
        tag_fields=tags,
        url_fields=urls,
        temporal_fields=temporals,
    ) == ("url", "https://npu.cz/a")
    kind, value = classify_attribute(
        "platn_od",
        1_700_000_000_000,
        tag_fields=tags,
        url_fields=urls,
        temporal_fields=temporals,
    ) or (None, None)
    assert kind == "temporal"
    assert isinstance(value, datetime)


def test_sync_headers_identify_bot() -> None:
    """Sync client advertises YourSyncBot/1.0."""
    assert SYNC_USER_AGENT == "YourSyncBot/1.0"
    assert SYNC_HEADERS["User-Agent"] == "YourSyncBot/1.0"
    assert SYNC_HEADERS["Accept"] == "application/json"
    assert SYNC_ACCEPT == "application/json"


def test_build_wget_argv_uses_dash_o() -> None:
    """wget argv follows ``wget -O file.json url`` with UA + Accept."""
    out = Path("/tmp/pamatky.json")
    argv = _build_wget_argv("https://example.test/MapServer/0?f=json", out, timeout_s=60.0)
    assert argv[0] == "wget"
    assert argv[1] == "-O"
    assert argv[2] == str(out)
    assert f"--user-agent={SYNC_USER_AGENT}" in argv
    assert f"--header=Accept: {SYNC_ACCEPT}" in argv
    assert "--tries=1" in argv
    assert argv[-1] == "https://example.test/MapServer/0?f=json"


def _install_wget_mock(
    monkeypatch: MonkeyPatch,
    handler: Any,
) -> list[list[str]]:
    """Patch subprocess.run to simulate ``wget -O <file> <url>`` writing JSON.

    ``handler(url)`` returns a JSON-serializable dict (success) or raises
    ``WgetError`` / returns an int exit code via a ``("exit", code)`` tuple.
    """
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
    ) -> Any:
        del capture_output, text, check
        calls.append(list(argv))
        assert argv[0] == "wget"
        assert argv[1] == "-O"
        out_path = Path(argv[2])
        url = argv[-1]
        result = handler(url)
        if isinstance(result, tuple) and result and result[0] == "exit":
            return type(
                "Completed",
                (),
                {"returncode": int(result[1]), "stderr": "mock wget fail", "stdout": ""},
            )()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result), encoding="utf-8")
        return type(
            "Completed",
            (),
            {"returncode": 0, "stderr": "", "stdout": ""},
        )()

    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.subprocess.run",
        fake_run,
    )
    return calls


def test_fetch_metadata_and_pagination(monkeypatch: MonkeyPatch) -> None:
    """Metadata ``?f=json`` + offset paging stops on short page (mocked wget)."""

    def handler(url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/")
        if path.endswith("/0") and not path.endswith("/query"):
            assert qs.get("f") == ["json"]
            return {
                "name": "TestLayer",
                "maxRecordCount": 2,
                "advancedQueryCapabilities": {"supportsPagination": True},
            }
        offset = int((qs.get("resultOffset") or ["0"])[0])
        if offset == 0:
            features = [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 1},
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                },
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 2},
                    "geometry": {"type": "Point", "coordinates": [1, 1]},
                },
            ]
        elif offset == 2:
            features = [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 3},
                    "geometry": {"type": "Point", "coordinates": [2, 2]},
                },
            ]
        else:
            features = []
        return {"type": "FeatureCollection", "features": features}

    calls = _install_wget_mock(monkeypatch, handler)
    meta = fetch_layer_metadata("https://example.test/MapServer/0")
    assert meta.max_record_count == 2
    assert meta.supports_pagination is True
    pages = list(
        iter_geojson_pages(
            "https://example.test/MapServer/0",
            page_size=2,
        )
    )
    assert len(pages) == 2
    assert len(pages[0]) == 2
    assert len(pages[1]) == 1
    assert all(c[1] == "-O" for c in calls)
    assert any(c[-1].endswith("?f=json") or "f=json" in c[-1] for c in calls)


def test_wget_retries_then_succeeds(monkeypatch: MonkeyPatch) -> None:
    """Non-zero wget exits are retried (1+3) with backoff then succeed."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.time.sleep",
        lambda s: sleeps.append(s),
    )
    calls = {"n": 0}

    def handler(url: str) -> Any:
        del url
        calls["n"] += 1
        if calls["n"] < 3:
            return ("exit", 8)
        return {"ok": True}

    _install_wget_mock(monkeypatch, handler)
    payload = fetch_json_with_retries("https://example.test/x")
    assert payload == {"ok": True}
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_wget_retries_exhausted(monkeypatch: MonkeyPatch) -> None:
    """After 4 failed attempts the last WgetError is raised."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.time.sleep",
        lambda s: sleeps.append(s),
    )

    def handler(url: str) -> Any:
        del url
        return ("exit", 8)

    _install_wget_mock(monkeypatch, handler)
    with pytest.raises(WgetError) as excinfo:
        fetch_json_with_retries("https://example.test/fail")
    assert excinfo.value.exit_code == 8
    assert len(sleeps) == 3  # retries after attempts 1–3; 4th fails without sleep


def test_config_defaults_match_cp_uap_pvo() -> None:
    """Settings defaults lock MapServer URL and CP_UAP_PVO field maps."""
    from sample_db_backend.config import Settings

    settings = Settings(_env_file=None)
    assert settings.npu_layer_url is not None
    assert settings.npu_layer_url.endswith("/Tematicke/CP_UAP_PVO/MapServer/0")
    assert "Subtyp" in (settings.npu_tag_fields or "")
    assert "urlExt" in (settings.npu_url_fields or "")
    assert "platn_od" in (settings.npu_temporal_fields or "")
