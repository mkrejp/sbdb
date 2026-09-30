"""API tests for layers / objects / properties / tags / urls (stub mode)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

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
    assert response.json()["database"] == "skipped"


def test_layer_object_property_tag_url_flow(client: TestClient) -> None:
    """End-to-end stub flow across core tables."""
    layer = client.post("/layers", json={"name": "Parks"}).json()
    layer_id = layer["id"]

    obj = client.post(
        f"/layers/{layer_id}/objects",
        json={"geometry": {"type": "Point", "coordinates": [14.4, 50.1]}},
    ).json()
    object_id = obj["id"]

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


def test_blank_layer_name_422(client: TestClient) -> None:
    """Blank names return 422."""
    assert client.post("/layers", json={"name": "  "}).status_code == 422
