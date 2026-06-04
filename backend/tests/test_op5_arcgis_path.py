"""Tests for the Op-5 ArcGIS-first classification + ingest path (CP-Pre Finding 5).

Covers:

* :func:`op5_lib.arcgis_lookup.lookup_arcgis_source` — verified, candidate,
  non_zoning exclusion, NJSEA, no-match.
* Classifier's ArcGIS branch (mocked probe).
* Runner short-circuit: extraction returns ``arcgis_*`` without touching
  the PDF path.
* Runner ingest branch: ``ingest_zoning_districts`` is called with
  ``replace=False`` and the FeatureServer URL.

All DB / network / Anthropic is stubbed; no live services.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from op5_lib.arcgis_lookup import (  # noqa: E402
    ArcgisSource,
    NJSEA_FEATURE_SERVER_URL,
    is_arcgis_candidate_excluded,
    lookup_arcgis_source,
    probe_feature_server,
)


# ── lookup_arcgis_source ────────────────────────────────────────────────────


def test_lookup_arcgis_source_paramus_verified() -> None:
    """Paramus appears in verified_munis on the services6 tenant."""
    arc = lookup_arcgis_source("Paramus Borough", "NJ")
    assert arc is not None
    assert arc.confidence == "verified"
    assert "services6.arcgis.com/UcuMPLF9IlsigGHI" in arc.tenant_host
    assert "Paramus_Zoning" in arc.feature_server_url
    assert arc.feature_server_url.endswith("/FeatureServer/0")
    # Verified-tenant matches don't carry a WHERE clause.
    assert arc.where_clause is None


def test_lookup_arcgis_source_westwood_candidate() -> None:
    """Westwood is in candidate_munis on the Paramus vendor tenant."""
    arc = lookup_arcgis_source("Westwood Borough", "NJ")
    assert arc is not None
    assert arc.confidence == "candidate"
    assert (
        arc.feature_server_url
        == "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/"
           "services/Westwood_Zoning_2019/FeatureServer/0"
    )
    assert arc.where_clause is None
    assert "Westwood_Zoning_2019" in arc.source_label


def test_lookup_arcgis_source_excluded_via_non_zoning_munis() -> None:
    """Closter is in non_zoning_munis on the services6 tenant even though
    it might otherwise be present. Verify the exclusion path returns None."""
    # First, build a synthetic tenant dict that mirrors the real catalog
    # shape and confirm the helper rejects an excluded muni regardless of
    # candidate membership.
    tenant = {
        "verified_munis": [],
        "candidate_munis": [
            {"muni": "Closter", "state": "NJ", "service_name": "Closter_Zoning"},
        ],
        "non_zoning_munis": ["Closter"],
    }
    assert is_arcgis_candidate_excluded("Closter Borough", tenant) is True
    # And from the real catalog: Closter is not verified anywhere and is on
    # services6's non_zoning_munis, so the lookup returns None for it.
    arc = lookup_arcgis_source("Closter Borough", "NJ")
    assert arc is None


def test_lookup_arcgis_source_njsea_carlstadt() -> None:
    """Carlstadt has in_njsea_zoning=true (muni_code 0205) -> NJSEA URL
    with WHERE MUN_CODE LIKE '0205%'."""
    arc = lookup_arcgis_source("Carlstadt Borough", "NJ")
    assert arc is not None
    assert arc.confidence == "njsea"
    assert arc.feature_server_url == NJSEA_FEATURE_SERVER_URL
    assert arc.where_clause == "MUN_CODE LIKE '0205%'"
    assert "0205" in arc.source_label


def test_lookup_arcgis_source_no_match_hackensack() -> None:
    """Hackensack is not on any tenant + not NJSEA -> None."""
    arc = lookup_arcgis_source("Hackensack City", "NJ")
    assert arc is None


def test_lookup_arcgis_source_empty_inputs() -> None:
    assert lookup_arcgis_source("", "NJ") is None
    assert lookup_arcgis_source(None, "NJ") is None  # type: ignore[arg-type]


# ── probe_feature_server ────────────────────────────────────────────────────


def test_probe_feature_server_returns_false_on_http_error() -> None:
    """Probe must never raise — bad URL -> False."""
    # Use an unroutable URL; httpx will throw and we should swallow.
    assert probe_feature_server(
        "https://invalid-host-that-doesnt-exist.local/arcgis/rest/services/foo/FeatureServer/0",
        timeout_s=2.0,
    ) is False


def test_probe_feature_server_handles_zero_count() -> None:
    """Mock httpx.get -> count=0 -> False."""
    import op5_lib.arcgis_lookup as _alook

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"count": 0}

    with patch.object(_alook, "httpx", create=True) as fake_httpx:
        fake_httpx.get = MagicMock(return_value=_FakeResp())
        # Need to make sure import inside fn picks it up — patch the actual
        # imported binding instead.
    # Easier: monkey-patch via top-level httpx since arcgis_lookup imports
    # httpx lazily inside probe_feature_server.
    import httpx as real_httpx

    class _FakeResp2:
        status_code = 200

        def json(self):
            return {"count": 0}

    with patch.object(real_httpx, "get", return_value=_FakeResp2()):
        assert probe_feature_server(
            "https://example.test/arcgis/rest/services/x/FeatureServer/0"
        ) is False


def test_probe_feature_server_returns_true_when_count_positive() -> None:
    import httpx as real_httpx

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"count": 42}

    with patch.object(real_httpx, "get", return_value=_FakeResp()):
        assert probe_feature_server(
            "https://example.test/arcgis/rest/services/x/FeatureServer/0",
            where_clause="MUN_CODE LIKE '0205%'",
        ) is True


# ── classifier ArcGIS route ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_arcgis_route() -> None:
    """Mocked probe + lookup -> classification.class == arcgis_verified."""
    import op5_discovery_classify as classify
    from op5_per_muni_runner import MuniRecord

    muni = MuniRecord(
        muni_code="0244",
        muni_name="Paramus Borough",
        map_url="https://example.test/zoning-map.pdf",  # would otherwise route PDF
        ordinance_url=None,
        website_url=None,
    )

    fake_arc = ArcgisSource(
        feature_server_url="https://example.test/x/FeatureServer/0",
        where_clause=None,
        source_label="Paramus_Zoning (verified)",
        confidence="verified",
        tenant_host="services6.arcgis.com/UcuMPLF9IlsigGHI",
    )

    async def _fake_probe(url, where):  # signature matches _probe_feature_server_async
        return True

    with patch.object(classify, "lookup_arcgis_source", return_value=fake_arc), \
            patch.object(classify, "probe_feature_server", return_value=True), \
            patch.object(classify, "_probe_feature_server_async", side_effect=_fake_probe):
        rec = await classify.classify_one(muni)
    assert rec.cls == "arcgis_verified"
    assert rec.feature_server_url == "https://example.test/x/FeatureServer/0"
    assert rec.where_clause is None
    assert rec.map_url_source == "arcgis"
    assert rec.source_label == "Paramus_Zoning (verified)"
    assert rec.error is None


@pytest.mark.asyncio
async def test_classify_njsea_route() -> None:
    """NJSEA confidence -> class label is 'njsea' (not 'arcgis_njsea')."""
    import op5_discovery_classify as classify
    from op5_per_muni_runner import MuniRecord

    muni = MuniRecord(
        muni_code="0205",
        muni_name="Carlstadt Borough",
        map_url=None,
        ordinance_url=None,
        website_url=None,
    )

    fake_arc = ArcgisSource(
        feature_server_url=NJSEA_FEATURE_SERVER_URL,
        where_clause="MUN_CODE LIKE '0205%'",
        source_label="NJSEA 20200609_Zoning (muni_code=0205)",
        confidence="njsea",
        tenant_host="services1.arcgis.com/ze0XBzU1FXj94DJq",
    )

    async def _fake_probe(url, where):
        return True

    with patch.object(classify, "lookup_arcgis_source", return_value=fake_arc), \
            patch.object(classify, "_probe_feature_server_async", side_effect=_fake_probe):
        rec = await classify.classify_one(muni)
    assert rec.cls == "njsea"
    assert rec.feature_server_url == NJSEA_FEATURE_SERVER_URL
    assert rec.where_clause == "MUN_CODE LIKE '0205%'"


# ── runner ArcGIS short-circuit ─────────────────────────────────────────────


def test_runner_arcgis_path_skips_pdf_extraction() -> None:
    """default_extract_polygons_from_map short-circuits when ArcGIS hits."""
    import op5_per_muni_runner as runner

    muni = runner.MuniRecord(
        muni_code="0267",
        muni_name="Westwood Borough",
        map_url="https://example.test/zoning-map.pdf",  # would route PDF
        ordinance_url=None,
        website_url=None,
    )

    fake_arc = ArcgisSource(
        feature_server_url=(
            "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/"
            "Westwood_Zoning_2019/FeatureServer/0"
        ),
        where_clause=None,
        source_label="Westwood candidate",
        confidence="candidate",
        tenant_host="services6.arcgis.com/UcuMPLF9IlsigGHI",
    )

    import op5_lib.arcgis_lookup as alook

    # Patch both the module-level lookup_arcgis_source and probe_feature_server.
    # The runner imports them locally inside the function, so we patch the
    # source module.
    with patch.object(alook, "lookup_arcgis_source", return_value=fake_arc), \
            patch.object(alook, "probe_feature_server", return_value=True):
        result = runner.default_extract_polygons_from_map(muni)

    assert result.source_class == "arcgis_candidate"
    assert result.polygons == []
    assert result.color_to_zone == {}
    assert result.vision_label_count == 0
    assert result.arcgis_source is fake_arc


def test_runner_arcgis_path_falls_through_when_probe_fails() -> None:
    """If lookup hits but probe returns False, runner falls through to the
    existing PDF/absent path."""
    import op5_per_muni_runner as runner

    muni = runner.MuniRecord(
        muni_code="0267",
        muni_name="Westwood Borough",
        map_url=None,  # forces absent on fallthrough
        ordinance_url=None,
        website_url=None,
    )

    fake_arc = ArcgisSource(
        feature_server_url="https://example.test/x/FeatureServer/0",
        where_clause=None,
        source_label="x",
        confidence="candidate",
        tenant_host="example.test",
    )

    import op5_lib.arcgis_lookup as alook

    with patch.object(alook, "lookup_arcgis_source", return_value=fake_arc), \
            patch.object(alook, "probe_feature_server", return_value=False):
        result = runner.default_extract_polygons_from_map(muni)

    # ArcGIS was rejected; map_url is None so we end at absent.
    assert result.source_class == "absent"
    assert result.arcgis_source is None


# ── runner ingest dispatcher: ArcGIS branch ────────────────────────────────


@pytest.mark.asyncio
async def test_runner_arcgis_path_calls_ingest_zoning_districts() -> None:
    """When source_class is arcgis_*, default_ingest_polygons dispatches
    through _ingest_arcgis_source which calls download_all_features +
    ingest_zoning_districts(replace=False)."""
    import op5_per_muni_runner as runner

    muni = runner.MuniRecord(
        muni_code="0267",
        muni_name="Westwood Borough",
        map_url=None,
        ordinance_url=None,
        website_url=None,
    )

    fake_arc = ArcgisSource(
        feature_server_url=(
            "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/"
            "Westwood_Zoning_2019/FeatureServer/0"
        ),
        where_clause=None,
        source_label="Westwood candidate",
        confidence="candidate",
        tenant_host="services6.arcgis.com/UcuMPLF9IlsigGHI",
    )

    extraction = runner.ExtractionResult(
        polygons=[],
        color_to_zone={},
        source_class="arcgis_candidate",
        vision_label_count=0,
        arcgis_source=fake_arc,
    )

    captured: dict = {}

    # Build fake helpers/services modules to short-circuit DB + HTTP.
    fake_helpers = MagicMock()
    fake_helpers.load_db_url = MagicMock(
        return_value="postgresql://x@localhost:5432/x?bbvywbpxwsoyvdvygvyw"
    )
    fake_helpers.assert_preview_url = MagicMock(return_value=None)
    fake_helpers.lookup_jurisdiction_id = AsyncMock(
        return_value="4bf00234-4455-4987-a067-b22ee6b6aa1f"
    )
    fake_helpers.ingest_polygons_additive = AsyncMock(return_value=0)

    import sys as _sys

    # Patch the asyncpg connect path so we don't hit a real DB.
    fake_asyncpg = MagicMock()
    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()

    async def _fake_connect(*_a, **_kw):
        return fake_conn

    fake_asyncpg.connect = _fake_connect

    # Stub the platform services with capturing mocks.
    import pandas as _pd  # noqa: F401  (geopandas import is heavy; we use a sentinel)

    class _FakeGdf:
        empty = False

    async def _fake_download(url, where="1=1"):
        captured["download_url"] = url
        captured["download_where"] = where
        return _FakeGdf()

    async def _fake_ingest_zoning(gdf, jid_uuid, session, replace=True):
        captured["ingest_called"] = True
        captured["ingest_replace"] = replace
        captured["ingest_jid"] = str(jid_uuid)
        return 11

    fake_arcgis_query = MagicMock()
    fake_arcgis_query.download_all_features = _fake_download
    fake_zoning_ingestion = MagicMock()
    fake_zoning_ingestion.ingest_zoning_districts = _fake_ingest_zoning

    # Settings + engine stubs.
    fake_settings_mod = MagicMock()
    fake_settings_mod.settings = MagicMock(
        database_url="postgresql+asyncpg://x@localhost:5432/x?bbvywbpxwsoyvdvygvyw"
    )

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *_a, **_kw):
            class _R:
                def fetchall(self_inner):
                    return []
            return _R()

        async def commit(self):
            return None

    def _fake_sessionmaker(engine, expire_on_commit=False):
        def _make():
            return _FakeSession()
        return _make

    class _FakeEngine:
        async def dispose(self):
            return None

    def _fake_create_engine(*_a, **_kw):
        return _FakeEngine()

    fake_sqla_async = MagicMock()
    fake_sqla_async.async_sessionmaker = _fake_sessionmaker
    fake_sqla_async.create_async_engine = _fake_create_engine

    # Wire all stubs into sys.modules so the in-function imports pick them up.
    sys_mod_patches = {
        "asyncpg": fake_asyncpg,
        "op5_lib.ingestion_helpers": fake_helpers,
        "app.config": fake_settings_mod,
        "app.services.arcgis_query": fake_arcgis_query,
        "app.services.zoning_ingestion": fake_zoning_ingestion,
        "sqlalchemy.ext.asyncio": fake_sqla_async,
    }
    saved = {k: _sys.modules.get(k) for k in sys_mod_patches}
    try:
        for k, v in sys_mod_patches.items():
            _sys.modules[k] = v
        result = await runner.default_ingest_polygons(
            muni, extraction,
            preview_branch="bbvywbpxwsoyvdvygvyw",
            county="bergen",
        )
    finally:
        for k, prev in saved.items():
            if prev is None:
                _sys.modules.pop(k, None)
            else:
                _sys.modules[k] = prev

    assert captured.get("ingest_called") is True
    assert captured.get("ingest_replace") is False  # F2 protect-list contract
    assert captured.get("download_url") == fake_arc.feature_server_url
    assert captured.get("download_where") == "1=1"
    assert result.polygons_written == 11
    assert result.jurisdiction_id == "4bf00234-4455-4987-a067-b22ee6b6aa1f"


@pytest.mark.asyncio
async def test_runner_ingest_dispatcher_routes_non_arcgis_to_existing_path() -> None:
    """When source_class is vector, dispatcher uses ingest_polygons_additive,
    NOT the arcgis path."""
    import op5_per_muni_runner as runner

    muni = runner.MuniRecord(
        muni_code="9999",
        muni_name="Vector Test Borough",
        map_url="https://example.test/x.pdf",
        ordinance_url=None,
        website_url=None,
    )
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "R-1"}],
        color_to_zone={"#fff": "R-1"},
        source_class="vector",
        vision_label_count=1,
        arcgis_source=None,
    )

    fake_helpers = MagicMock()
    fake_helpers.load_db_url = MagicMock(
        return_value="postgresql://x@localhost/x?bbvywbpxwsoyvdvygvyw"
    )
    fake_helpers.assert_preview_url = MagicMock(return_value=None)
    fake_helpers.lookup_jurisdiction_id = AsyncMock(return_value="jid-ok")
    captured = {}

    async def _fake_additive(conn, *, jurisdiction_id, op5_town, polygons, **_kw):
        captured["called"] = True
        captured["op5_town"] = op5_town
        captured["jid"] = jurisdiction_id
        return len(polygons)

    fake_helpers.ingest_polygons_additive = _fake_additive

    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()

    async def _fake_connect(*_a, **_kw):
        return fake_conn

    fake_asyncpg = MagicMock()
    fake_asyncpg.connect = _fake_connect

    import sys as _sys
    saved = {
        "asyncpg": _sys.modules.get("asyncpg"),
        "op5_lib.ingestion_helpers": _sys.modules.get("op5_lib.ingestion_helpers"),
    }
    try:
        _sys.modules["asyncpg"] = fake_asyncpg
        _sys.modules["op5_lib.ingestion_helpers"] = fake_helpers
        result = await runner.default_ingest_polygons(
            muni, extraction,
            preview_branch="bbvywbpxwsoyvdvygvyw",
            county="bergen",
        )
    finally:
        for k, prev in saved.items():
            if prev is None:
                _sys.modules.pop(k, None)
            else:
                _sys.modules[k] = prev

    assert captured.get("called") is True
    assert captured.get("op5_town") == "vector_test"
    assert result.polygons_written == 1
