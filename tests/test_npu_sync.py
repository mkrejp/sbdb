"""Unit tests for NPÚ sync — Python parse/transform + insert helpers.

No live NPÚ / network. Bash wget is covered separately with a PATH mock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sample_db_backend.sync.npu_geoportal import (
    SYNC_ACCEPT,
    SYNC_HEADERS,
    SYNC_USER_AGENT,
    classify_attribute,
    extract_npu_objectid,
    extract_object_ids,
    features_from_detail,
    load_json_file,
    page_size,
    parse_layer_metadata,
    upsert_detail_file,
    upsert_feature,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch

FIXTURES = Path(__file__).parent / "fixtures" / "npu"


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
    """Documented bot identity for wget User-Agent / Accept."""
    assert SYNC_USER_AGENT == "YourSyncBot/1.0"
    assert SYNC_HEADERS["User-Agent"] == "YourSyncBot/1.0"
    assert SYNC_HEADERS["Accept"] == "application/json"
    assert SYNC_ACCEPT == "application/json"


def test_parse_meta_and_page_size_from_fixture() -> None:
    """Metadata fixture drives client page size (cap 1000)."""
    meta = parse_layer_metadata(load_json_file(FIXTURES / "meta.json"))
    assert meta.name.startswith("Národní")
    assert meta.max_record_count == 2000
    assert meta.supports_pagination is True
    assert page_size(meta) == 1000


def test_extract_object_ids_from_list_fixture() -> None:
    """returnIdsOnly pamatky.json → OBJECTID list."""
    ids = extract_object_ids(load_json_file(FIXTURES / "pamatky-ids.json"))
    assert ids == [101, 102, 103]
    assert extract_object_ids(load_json_file(FIXTURES / "pamatky-ids-empty.json")) == []


def test_features_from_detail_fixture() -> None:
    """Detail GeoJSON FeatureCollection → feature list."""
    features = features_from_detail(load_json_file(FIXTURES / "detail.geojson"))
    assert len(features) == 2
    assert extract_npu_objectid(features[0]["properties"]) == 101


def test_config_defaults_match_cp_uap_pvo() -> None:
    """Settings defaults lock MapServer URL and CP_UAP_PVO field maps."""
    from sample_db_backend.config import Settings

    settings = Settings(_env_file=None)
    assert settings.npu_layer_url is not None
    assert settings.npu_layer_url.endswith("/Tematicke/CP_UAP_PVO/MapServer/0")
    assert "Subtyp" in (settings.npu_tag_fields or "")
    assert "urlExt" in (settings.npu_url_fields or "")
    assert "platn_od" in (settings.npu_temporal_fields or "")


class _FakeResult:
    """Minimal stand-in for psycopg execute result."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        """Return the prepared row."""
        return self._row


class _FakeConn:
    """In-memory fake connection recording SQL for upsert tests."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []
        self._object_id = uuid4()

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _FakeResult:
        """Record statement; return plausible RETURNING rows."""
        self.statements.append((sql, params))
        lowered = " ".join(sql.lower().split())
        if "insert into layer_objects" in lowered:
            return _FakeResult({"id": self._object_id})
        if "insert into tags" in lowered:
            return _FakeResult({"id": uuid4()})
        return _FakeResult(None)

    def commit(self) -> None:
        """No-op commit."""

    def rollback(self) -> None:
        """No-op rollback."""

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *args: object) -> None:
        del args


def test_upsert_feature_writes_object_and_children() -> None:
    """Upsert inserts layer_objects and derived tag/url/text rows."""
    conn = _FakeConn()
    feature = features_from_detail(load_json_file(FIXTURES / "detail.geojson"))[0]
    ok = upsert_feature(
        conn,  # type: ignore[arg-type]
        layer_id=uuid4(),
        feature=feature,
        tag_fields={"Subtyp"},
        url_fields={"urlExt"},
        temporal_fields=set(),
    )
    assert ok is True
    joined = " ".join(s[0] for s in conn.statements).lower()
    assert "insert into layer_objects" in joined
    assert "insert into tags" in joined
    assert "layer_object_urls" in joined
    assert "layer_object_properties" in joined


def test_upsert_detail_file_commits_once(monkeypatch: MonkeyPatch) -> None:
    """upsert_detail_file opens one connection and commits the batch."""
    fake = _FakeConn()
    commits = {"n": 0}

    def fake_connect(*args: Any, **kwargs: Any) -> _FakeConn:
        del args, kwargs
        return fake

    def counting_commit(self: _FakeConn) -> None:
        commits["n"] += 1

    monkeypatch.setattr(
        "sample_db_backend.sync.npu_geoportal.psycopg.connect",
        fake_connect,
    )
    monkeypatch.setattr(_FakeConn, "commit", counting_commit)

    stats = upsert_detail_file(
        database_url="postgresql://unused",
        layer_id=uuid4(),
        detail_path=FIXTURES / "detail.geojson",
        tag_fields={"Subtyp"},
        url_fields={"urlExt"},
    )
    assert stats.features == 2
    assert stats.upserted == 2
    assert commits["n"] == 1


def test_cli_extract_ids(capsys: CaptureFixture[str]) -> None:
    """CLI extract-ids prints one OBJECTID per line."""
    from sample_db_backend.sync.npu_geoportal import cli

    rc = cli(["extract-ids", str(FIXTURES / "pamatky-ids.json")])
    assert rc == 0
    assert capsys.readouterr().out.strip().splitlines() == ["101", "102", "103"]


def test_cli_page_size(capsys: CaptureFixture[str]) -> None:
    """CLI page-size prints capped page size."""
    from sample_db_backend.sync.npu_geoportal import cli

    rc = cli(["page-size", str(FIXTURES / "meta.json")])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "1000"


def test_module_has_no_wget_or_httpx_imports() -> None:
    """Happy-path Python module must not import HTTP clients for NPÚ."""
    import sample_db_backend.sync.npu_geoportal as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import httpx" not in src
    assert "import requests" not in src
    assert "subprocess" not in src
    assert "_wget" not in src
