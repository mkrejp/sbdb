"""API tests for layers / objects / properties / tags / urls (stub mode)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sample_db_backend.db import clear_memory_store
from sample_db_backend.main import create_app

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture(autouse=True)
def _clean_stub(monkeypatch: MonkeyPatch) -> Iterator[None]:
    """Run without DATABASE_URL; clear stub stores."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from sample_db_backend.config import get_settings

    get_settings.cache_clear()
    clear_memory_store()
    yield
    clear_memory_store()
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(create_app())


def test_health_ok_without_database(client: TestClient) -> None:
    """Health ok when DB skipped."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "skipped"
    assert body["status"] == "ok"


def test_empty_lists_return_200(client: TestClient) -> None:
    """Empty collections return 200 with empty items."""
    assert client.get("/layers").json()["items"] == []
    assert client.get("/objects").json()["items"] == []
    assert client.get("/tags").json()["items"] == []


def test_missing_resources_404(client: TestClient) -> None:
    """Unknown IDs return 404."""
    missing = str(uuid4())
    assert client.get(f"/layers/{missing}").status_code == 404
    assert client.get(f"/objects/{missing}").status_code == 404
    assert client.get(f"/tags/{missing}").status_code == 404
    assert client.get(f"/properties/{missing}").status_code == 404
    assert client.get(f"/urls/{missing}").status_code == 404


def test_blank_layer_name_422(client: TestClient) -> None:
    """Blank names return 422."""
    assert client.post("/layers", json={"name": "  "}).status_code == 422


def test_tag_conflict_409(client: TestClient) -> None:
    """Duplicate tag names return 409."""
    assert client.post("/tags", json={"name": "park"}).status_code == 201
    assert client.post("/tags", json={"name": "park"}).status_code == 409


def test_property_conflict_409(client: TestClient) -> None:
    """Duplicate property keys on an object return 409."""
    layer_id = client.post("/layers", json={"name": "L"}).json()["id"]
    object_id = client.post(
        f"/layers/{layer_id}/objects",
        json={"geometry": {"type": "Point", "coordinates": [0, 0]}},
    ).json()["id"]
    payload = {"key": "label", "value_type": "text", "text_value": "a"}
    assert client.post(f"/objects/{object_id}/properties", json=payload).status_code == 201
    assert client.post(f"/objects/{object_id}/properties", json=payload).status_code == 409


def test_list_limit_capped(client: TestClient) -> None:
    """List endpoints reject limit above 100."""
    assert client.get("/layers", params={"limit": 101}).status_code == 422
    assert client.get("/objects", params={"limit": 101}).status_code == 422
    assert client.get("/tags", params={"limit": 101}).status_code == 422


def test_layer_exposes_source_fields(client: TestClient) -> None:
    """Layer reads include source_key / source_url (null for manual creates)."""
    layer = client.post("/layers", json={"name": "Manual"}).json()
    assert "source_key" in layer
    assert "source_url" in layer
    assert layer["source_key"] is None
    assert layer["source_url"] is None
    fetched = client.get(f"/layers/{layer['id']}").json()
    assert fetched["source_key"] is None


def test_object_exposes_npu_attribute_columns(client: TestClient) -> None:
    """Object create/read/update round-trips NPÚ columns (stub mode)."""
    layer_id = client.post("/layers", json={"name": "NKP"}).json()["id"]
    created = client.post(
        f"/layers/{layer_id}/objects",
        json={
            "geometry": {"type": "Point", "coordinates": [13.9, 49.26]},
            "npu_objectid": 34228,
            "pr_stav_id": 84095,
            "subtyp": 12,
            "pr_stav_nazev": "Hrad Strakonice",
            "typ_ochrany_kod": "NKP",
            "url_ext": "https://pamatkovykatalog.cz/pravni-ochrana/x-84095",
            "verejny": 1,
            "hlavni_prvek_id": 15155748,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["npu_objectid"] == 34228
    assert body["pr_stav_id"] == 84095
    assert body["subtyp"] == 12
    assert body["pr_stav_nazev"] == "Hrad Strakonice"
    assert body["typ_ochrany_kod"] == "NKP"
    assert body["platn_od"] is None
    fetched = client.get(f"/objects/{body['id']}").json()
    assert fetched["hlavni_prvek_id"] == 15155748
    patched = client.patch(
        f"/objects/{body['id']}",
        json={"hlavni_prvek": "1000146986 - hrad Strakonice"},
    )
    assert patched.status_code == 200
    assert patched.json()["hlavni_prvek"].startswith("1000146986")


def test_layer_object_property_tag_url_flow(client: TestClient) -> None:
    """End-to-end stub flow across core tables."""
    layer = client.post("/layers", json={"name": "Parks"}).json()
    layer_id = layer["id"]

    obj = client.post(
        f"/layers/{layer_id}/objects",
        json={"geometry": {"type": "Point", "coordinates": [14.4, 50.1]}},
    ).json()
    object_id = obj["id"]
    assert "npu_objectid" in obj
    assert obj["npu_objectid"] is None

    text_prop = client.post(
        f"/objects/{object_id}/properties",
        json={"key": "label", "value_type": "text", "text_value": "Letná"},
    )
    assert text_prop.status_code == 201

    image_prop = client.post(
        f"/objects/{object_id}/properties",
        json={
            "key": "photo",
            "value_type": "image",
            "storage_bucket": "layer-media",
            "storage_path": "parks/letna.jpg",
            "content_type": "image/jpeg",
            "byte_size": 1024,
        },
    )
    assert image_prop.status_code == 201

    bad = client.post(
        f"/objects/{object_id}/properties",
        json={"key": "x", "value_type": "text"},
    )
    assert bad.status_code == 422

    tag = client.post("/tags", json={"name": "park"}).json()
    assert client.put(f"/objects/{object_id}/tags/{tag['id']}").status_code == 204
    tagged = client.get("/objects", params={"tag": "park"})
    assert tagged.status_code == 200
    assert len(tagged.json()["items"]) == 1

    url1 = client.post(
        f"/objects/{object_id}/urls",
        json={"url": "https://example.com/a", "sort_order": 1},
    )
    url0 = client.post(
        f"/objects/{object_id}/urls",
        json={"url": "https://example.com/b", "sort_order": 0, "label": "home"},
    )
    assert url1.status_code == 201 and url0.status_code == 201
    urls = client.get(f"/objects/{object_id}/urls").json()["items"]
    assert [u["sort_order"] for u in urls] == [0, 1]

    assert client.delete(f"/layers/{layer_id}").status_code == 204
    assert client.get(f"/objects/{object_id}").status_code == 404
