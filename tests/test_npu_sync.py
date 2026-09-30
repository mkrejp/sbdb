"""Unit tests for NPÚ Geoportal sync helpers (no live network / DB)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sample_db_backend.sync.npu_geoportal import (
    SYNC_HEADERS,
    SYNC_USER_AGENT,
    _request_with_retries,
    classify_attribute,
    extract_npu_objectid,
    fetch_layer_metadata,
    iter_geojson_pages,
)


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


def test_fetch_metadata_and_pagination() -> None:
    """Metadata read + offset paging stops on short page."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert request.headers.get("User-Agent") == SYNC_USER_AGENT
        assert request.headers.get("Accept") == "application/json"
        if path.endswith("/0"):
            assert request.url.params.get("f") == "pjson"
            return httpx.Response(
                200,
                json={
                    "name": "TestLayer",
                    "maxRecordCount": 2,
                    "advancedQueryCapabilities": {"supportsPagination": True},
                },
            )
        offset = int(request.url.params.get("resultOffset", "0"))
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
        return httpx.Response(
            200,
            json={"type": "FeatureCollection", "features": features},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        meta = fetch_layer_metadata(client, "https://example.test/MapServer/0")
        assert meta.max_record_count == 2
        assert meta.supports_pagination is True
        pages = list(
            iter_geojson_pages(
                client,
                "https://example.test/MapServer/0",
                page_size=2,
            )
        )
    assert len(pages) == 2
    assert len(pages[0]) == 2
    assert len(pages[1]) == 1


def test_request_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 responses are retried with backoff then succeed."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.time.sleep",
        lambda s: sleeps.append(s),
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        response = _request_with_retries(client, "GET", "https://example.test/x")
    assert response.status_code == 200
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_request_retries_three_times_on_500_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 500: 1 try + 3 retries (4 attempts) then abort with HTTPStatusError."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.time.sleep",
        lambda s: sleeps.append(s),
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.headers.get("User-Agent") == SYNC_USER_AGENT
        assert request.headers.get("Accept") == "application/json"
        return httpx.Response(500, json={"error": "server"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            _request_with_retries(client, "GET", "https://example.test/meta")
    assert exc_info.value.response.status_code == 500
    assert calls["n"] == 4  # 1 initial + 3 retries
    assert len(sleeps) == 3
    assert sleeps == [0.5, 1.0, 2.0]


def test_fetch_metadata_falls_back_to_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If f=pjson keeps failing after retries, fall back to f=json."""
    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.time.sleep",
        lambda _s: None,
    )
    seen_formats: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fmt = request.url.params.get("f", "")
        seen_formats.append(fmt)
        assert request.headers.get("User-Agent") == SYNC_USER_AGENT
        assert request.headers.get("Accept") == "application/json"
        if fmt == "pjson":
            return httpx.Response(500, json={"error": "pjson fail"})
        return httpx.Response(
            200,
            json={
                "name": "FallbackLayer",
                "maxRecordCount": 500,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        meta = fetch_layer_metadata(client, "https://example.test/MapServer/0")
    assert meta.name == "FallbackLayer"
    assert meta.max_record_count == 500
    assert seen_formats.count("pjson") == 4  # exhausted retries on pjson
    assert seen_formats[-1] == "json"


def test_config_defaults_match_cp_uap_pvo() -> None:
    """Settings defaults lock MapServer URL and CP_UAP_PVO field maps."""
    from sample_db_backend.config import Settings

    settings = Settings(_env_file=None)
    assert settings.npu_layer_url is not None
    assert settings.npu_layer_url.endswith("/Tematicke/CP_UAP_PVO/MapServer/0")
    assert "Subtyp" in (settings.npu_tag_fields or "")
    assert "urlExt" in (settings.npu_url_fields or "")
    assert "platn_od" in (settings.npu_temporal_fields or "")
