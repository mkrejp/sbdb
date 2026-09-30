"""Unit tests for NPÚ Geoportal sync helpers (no live network / DB)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from sample_db_backend.sync.npu_geoportal import (
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
    assert classify_attribute(
        "TYP", "hrad", tag_fields={"TYP"}, url_fields=set()
    ) == ("tag", "hrad")
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
    assert classify_attribute(
        "NAZEV", "Karlštejn", tag_fields=set(), url_fields=set()
    ) == ("text", "Karlštejn")
    assert classify_attribute("OBJECTID", 1, tag_fields=set(), url_fields=set()) is None


def test_fetch_metadata_and_pagination() -> None:
    """Metadata read + offset paging stops on short page."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/0"):
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
        meta = fetch_layer_metadata(client, "https://example.test/FeatureServer/0")
        assert meta.max_record_count == 2
        assert meta.supports_pagination is True
        pages = list(
            iter_geojson_pages(
                client,
                "https://example.test/FeatureServer/0",
                page_size=2,
            )
        )
    assert len(pages) == 2
    assert len(pages[0]) == 2
    assert len(pages[1]) == 1
