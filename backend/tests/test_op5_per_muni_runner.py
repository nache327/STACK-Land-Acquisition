"""Unit tests for the Op-5 factory per-muni runner (Pre-build A).

Covers the three contract points called out in docs/OP5_FACTORY_72H_PLAN.md
Pre-build A:

1. Idempotency: re-running on a muni whose cp3_summary.json status=='complete'
   is a no-op (exits 0 without re-extracting).
2. Carve-out: when vision returns 0 reliable labels, runner exits with
   EXIT_CARVE_OUT and writes carve_out.json.
3. Coverage math: 100 parcels / 70 zoned -> exactly 70.0%.

Everything DB / network / Anthropic is stubbed via RunnerHooks; no live
services are hit.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

# Make backend/scripts importable.
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import op5_per_muni_runner as runner  # noqa: E402


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def muni() -> runner.MuniRecord:
    return runner.MuniRecord(
        muni_code="0299",
        muni_name="Westwood Borough",
        map_url="https://example.test/zoning-map.pdf",
        ordinance_url="https://ecode360.com/example",
        website_url="https://example.test/",
    )


@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    root = tmp_path / "op5_factory"
    root.mkdir()
    return root


# ── coverage math (test #3 from the spec) ──────────────────────────────────


@pytest.mark.parametrize(
    "parcel_count,zoned,expected",
    [
        (100, 70, 70.0),   # spec example
        (0, 0, 0.0),       # divide-by-zero guard
        (200, 150, 75.0),
        (1000, 720, 72.0),
        (1, 0, 0.0),
        (3, 1, 33.33),     # rounded to 2 decimals
    ],
)
def test_compute_coverage_pct(parcel_count: int, zoned: int, expected: float) -> None:
    assert runner.compute_coverage_pct(parcel_count, zoned) == expected


# ── idempotency (test #1) ──────────────────────────────────────────────────


def _operational_hooks(extraction: runner.ExtractionResult) -> runner.RunnerHooks:
    async def _ingest(m, e, *, preview_branch, **_kw):
        return runner.IngestResult(
            jurisdiction_id="jid-test",
            polygons_written=len(e.polygons),
            nearest_within_meters=runner.DEFAULT_NEAREST_WITHIN_METERS,
        )

    async def _backfill(jid, *, nearest_within_meters, **_kw):
        return None

    async def _audit(jid, m, seed=8819, **_kw):
        return runner.AuditMetrics(
            parcel_count=100,
            zoned_parcel_count=88,
            coverage_pct=88.0,
            matrix_match_pct_of_zoned=100.0,
            spot_check_total=10,
            spot_check_passes=10,
            spot_check_pass_pct=100.0,
            binding_method_distribution={"contained": 70, "nearest_100m": 18},
        )

    return runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=lambda m, codes: [
            {"zone_code": c, "municipality": m.muni_name, "requires_review": False}
            for c in codes
        ],
        ingest=_ingest,
        backfill=_backfill,
        audit=_audit,
    )


@pytest.mark.asyncio
async def test_idempotent_no_op_when_complete(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    """If cp3_summary.json status=='complete' exists, the second run is a
    no-op: it returns EXIT_COMPLETE_OPERATIONAL and does NOT touch any of
    the hook side-effects."""
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "B-1"}, {"zone_code": "R-1"}],
        color_to_zone={"#aabbcc": "B-1", "#ddeeff": "R-1"},
        source_class="vector",
        vision_label_count=2,
    )
    first_hooks = _operational_hooks(extraction)
    code1, summary1 = await runner.run_per_muni(
        "bergen", muni,
        artifact_root=artifact_root,
        hooks=first_hooks,
    )
    assert code1 == runner.EXIT_COMPLETE_OPERATIONAL
    summary_path = runner.cp3_summary_path("bergen", muni.muni_name, root=artifact_root)
    assert summary_path.exists()
    on_disk = json.loads(summary_path.read_text())
    assert on_disk["status"] == "complete"

    # Second run: hooks that would BLOW UP if called.
    def _explode_extract(_m):
        raise AssertionError("extract called on idempotent run")

    async def _explode_ingest(*_a, **_kw):
        raise AssertionError("ingest called on idempotent run")

    async def _explode_backfill(*_a, **_kw):
        raise AssertionError("backfill called on idempotent run")

    async def _explode_audit(*_a, **_kw):
        raise AssertionError("audit called on idempotent run")

    explode_hooks = runner.RunnerHooks(
        extract=_explode_extract,
        adjudicate=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("adj on idempotent")),
        ingest=_explode_ingest,
        backfill=_explode_backfill,
        audit=_explode_audit,
    )
    code2, summary2 = await runner.run_per_muni(
        "bergen", muni,
        artifact_root=artifact_root,
        hooks=explode_hooks,
    )
    assert code2 == runner.EXIT_COMPLETE_OPERATIONAL
    assert summary2["status"] == "complete"


@pytest.mark.asyncio
async def test_force_bypasses_idempotency(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "B-1"}],
        color_to_zone={"#aabbcc": "B-1"},
        source_class="vector",
        vision_label_count=1,
    )
    hooks = _operational_hooks(extraction)
    code1, _ = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code1 == runner.EXIT_COMPLETE_OPERATIONAL

    calls: list[str] = []

    def _track(m: runner.MuniRecord) -> runner.ExtractionResult:
        calls.append(m.muni_name)
        return extraction

    forced_hooks = replace(hooks, extract=_track)
    code2, _ = await runner.run_per_muni(
        "bergen", muni,
        artifact_root=artifact_root,
        hooks=forced_hooks,
        force=True,
    )
    assert code2 == runner.EXIT_COMPLETE_OPERATIONAL
    assert calls == [muni.muni_name]  # forced re-extract


# ── carve-out path (test #2) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_carve_out_when_vision_returns_zero_labels(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    """If extraction returns vision_label_count==0 even though we got
    a vector PDF with a non-empty legend, runner exits EXIT_CARVE_OUT and
    writes carve_out.json (NOT cp3_summary.json)."""
    extraction = runner.ExtractionResult(
        polygons=[],
        color_to_zone={"#aabbcc": "B-1"},  # legend non-empty
        source_class="vector",
        vision_label_count=0,                # but no reliable labels at >=0.75
    )

    def _adj(*_a, **_kw):
        raise AssertionError("adjudicate should not run on carve-out")

    async def _ing(*_a, **_kw):
        raise AssertionError("ingest should not run on carve-out")

    hooks = runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=_adj,
        ingest=_ing,
        backfill=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("backfill on carve-out")),
        audit=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("audit on carve-out")),
    )
    code, summary = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code == runner.EXIT_CARVE_OUT
    assert summary["status"] == "carve_out"
    assert "vision returned 0 reliable labels" in summary["carve_reason"]

    carve_path = runner.carve_out_path("bergen", muni.muni_name, root=artifact_root)
    summary_path = runner.cp3_summary_path("bergen", muni.muni_name, root=artifact_root)
    assert carve_path.exists()
    assert not summary_path.exists()
    on_disk = json.loads(carve_path.read_text())
    assert on_disk["status"] == "carve_out"
    assert on_disk["muni"] == muni.muni_name


@pytest.mark.asyncio
async def test_carve_out_when_source_is_raster(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    extraction = runner.ExtractionResult(
        polygons=[],
        color_to_zone={},
        source_class="raster",
        vision_label_count=0,
    )
    hooks = runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("adj on raster carve")),
        ingest=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("ingest on raster carve")),
        backfill=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("backfill on raster carve")),
        audit=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("audit on raster carve")),
    )
    code, summary = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code == runner.EXIT_CARVE_OUT
    assert "source_class=raster" in summary["carve_reason"]


@pytest.mark.asyncio
async def test_carve_out_when_color_to_zone_empty(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "B-1"}],
        color_to_zone={},                  # text-only-legend signal
        source_class="vector",
        vision_label_count=1,
    )
    hooks = runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError),
        ingest=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError),
        backfill=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError),
        audit=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError),
    )
    code, summary = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code == runner.EXIT_CARVE_OUT
    assert "text-only legend" in summary["carve_reason"]


# ── coverage math wired into the audit (spec example) ──────────────────────


@pytest.mark.asyncio
async def test_coverage_math_in_summary_matches_spec(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    """100 parcels with 70 zoned -> 70.0% coverage on disk."""
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "B-1"}, {"zone_code": "R-1"}],
        color_to_zone={"#aabbcc": "B-1", "#ddeeff": "R-1"},
        source_class="vector",
        vision_label_count=2,
    )
    spec_coverage = runner.compute_coverage_pct(100, 70)
    assert spec_coverage == 70.0

    async def _ingest(m, e, *, preview_branch, **_kw):
        return runner.IngestResult(
            jurisdiction_id="jid-spec",
            polygons_written=len(e.polygons),
            nearest_within_meters=100.0,
        )

    async def _backfill(jid, *, nearest_within_meters, **_kw):
        assert nearest_within_meters == 100.0
        return None

    async def _audit(jid, m, seed=8819, **_kw):
        return runner.AuditMetrics(
            parcel_count=100,
            zoned_parcel_count=70,
            coverage_pct=spec_coverage,
            matrix_match_pct_of_zoned=100.0,
            spot_check_total=10,
            spot_check_passes=10,
            spot_check_pass_pct=100.0,
            binding_method_distribution={"contained": 60, "nearest_100m": 10},
        )

    hooks = runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=lambda m, codes: [{"zone_code": c} for c in codes],
        ingest=_ingest,
        backfill=_backfill,
        audit=_audit,
    )
    code, summary = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code == runner.EXIT_COMPLETE_OPERATIONAL
    assert summary["parcel_zoning_code_coverage_pct"] == 70.0
    assert summary["operational"] is True
    on_disk = json.loads(
        runner.cp3_summary_path("bergen", muni.muni_name, root=artifact_root).read_text()
    )
    assert on_disk["parcel_zoning_code_coverage_pct"] == 70.0
    assert on_disk["nearest_within_meters"] == 100.0


@pytest.mark.asyncio
async def test_below_operational_gate_returns_exit_1(
    muni: runner.MuniRecord, artifact_root: Path,
) -> None:
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "B-1"}],
        color_to_zone={"#aabbcc": "B-1"},
        source_class="vector",
        vision_label_count=1,
    )

    async def _ingest(m, e, *, preview_branch, **_kw):
        return runner.IngestResult("jid-low", len(e.polygons), 100.0)

    async def _backfill(jid, *, nearest_within_meters, **_kw):
        return None

    async def _audit(jid, m, seed=8819, **_kw):
        return runner.AuditMetrics(
            parcel_count=100,
            zoned_parcel_count=50,
            coverage_pct=50.0,             # below 70% gate
            matrix_match_pct_of_zoned=100.0,
            spot_check_total=10,
            spot_check_passes=8,
            spot_check_pass_pct=80.0,
            binding_method_distribution={"contained": 50},
        )

    hooks = runner.RunnerHooks(
        extract=lambda m: extraction,
        adjudicate=lambda m, codes: [{"zone_code": c} for c in codes],
        ingest=_ingest,
        backfill=_backfill,
        audit=_audit,
    )
    code, summary = await runner.run_per_muni(
        "bergen", muni, artifact_root=artifact_root, hooks=hooks,
    )
    assert code == runner.EXIT_COMPLETE_NOT_OPERATIONAL
    assert summary["operational"] is False


# ── directory loader / artifact paths ──────────────────────────────────────


def test_load_county_directory_bergen_fixture(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    directory = [
        {
            "muni_code": "0299",
            "muni_name": "Westwood Borough",
            "map_url": "https://example.test/map.pdf",
            "ordinance_url": "https://ecode360.com/abc",
            "website_url": "https://example.test/",
        },
        {
            "muni_code": "0298",
            "muni_name": "Wood-Ridge Borough",
            "map_url": None,
            "ordinance_url": None,
        },
    ]
    (data_dir / "bergen_zoning_directory.json").write_text(json.dumps(directory))
    rows = runner.load_county_directory("bergen", data_dir=data_dir)
    assert len(rows) == 2
    assert rows[0].muni_name == "Westwood Borough"
    assert rows[0].map_url == "https://example.test/map.pdf"


def test_load_county_directory_fallback_to_nj_munis(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    fallback = {
        "_meta": {"schema_version": 2},
        "essex": [
            {"name": "Belleville", "type": "Township", "ordinance_vendor": "eCode360"},
            {"name": "Bloomfield", "type": "Township", "ordinance_vendor": "eCode360"},
        ],
    }
    (data_dir / "nj_municipalities.json").write_text(json.dumps(fallback))
    rows = runner.load_county_directory("essex", data_dir=data_dir)
    assert {r.muni_name for r in rows} == {"Belleville", "Bloomfield"}
    # No map_url in the fallback shape -> carve-out path at the runner.
    assert rows[0].map_url is None


def test_find_muni_handles_dca_suffix_variants(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    directory = [{"muni_code": "0299", "muni_name": "Westwood Borough",
                  "map_url": None, "ordinance_url": None}]
    (data_dir / "bergen_zoning_directory.json").write_text(json.dumps(directory))
    assert runner.find_muni("bergen", "Westwood Borough", data_dir=data_dir).muni_code == "0299"
    assert runner.find_muni("bergen", "westwood", data_dir=data_dir).muni_code == "0299"
    with pytest.raises(KeyError):
        runner.find_muni("bergen", "Nonexistent", data_dir=data_dir)


def test_normalize_muni_token() -> None:
    assert runner.normalize_muni_token("Westwood Borough") == "westwood"
    assert runner.normalize_muni_token("Fort Lee Borough") == "fort_lee"
    assert runner.normalize_muni_token("Jersey City") == "jersey"


def test_artifact_paths_are_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "factory"
    p = runner.cp3_summary_path("bergen", "Westwood Borough", root=root)
    assert p == root / "bergen" / "westwood" / "cp3_summary.json"
    co = runner.carve_out_path("bergen", "Westwood Borough", root=root)
    assert co == root / "bergen" / "westwood" / "carve_out.json"


# ── defaults and constants pinned to the OP-5 decision doc ─────────────────


def test_defaults_match_op5_decision_doc() -> None:
    # docs/OP5_PROOF_DECISION.md #1 — 100m production default.
    assert runner.DEFAULT_NEAREST_WITHIN_METERS == 100.0
    # docs/OP5_FACTORY_72H_PLAN.md preview branch.
    assert runner.DEFAULT_PREVIEW_BRANCH == "bbvywbpxwsoyvdvygvyw"
    # municipality_health operational threshold.
    assert runner.OPERATIONAL_COVERAGE_PCT == 70.0
    # Spec section 4 — confidence floor.
    assert runner.VISION_LABEL_CONFIDENCE_FLOOR == 0.75
    # Spec section 10 — spot-check sample size.
    assert runner.SPOT_CHECK_SAMPLE_SIZE == 10
    # Exit code mapping.
    assert runner.EXIT_COMPLETE_OPERATIONAL == 0
    assert runner.EXIT_COMPLETE_NOT_OPERATIONAL == 1
    assert runner.EXIT_CARVE_OUT == 2
    assert runner.EXIT_TRANSIENT_ERROR == 3


# ── boundary tests for the real defaults (CP-Pre Finding 2 / A2) ───────────


def test_default_extract_vector_classification(monkeypatch, muni: runner.MuniRecord) -> None:
    """Vector-class PDF + mocked extractor returns source_class=vector with
    a non-empty polygon list."""
    from op5_lib import extraction as ext

    sample = ext.ExtractionResult(
        polygons=[{
            "zone_code": "R-1",
            "confidence": 0.92,
            "geometry": {"type": "Polygon", "coordinates": [[[-74.0, 40.8], [-74.0, 40.81], [-73.99, 40.81], [-73.99, 40.8], [-74.0, 40.8]]]},
        }],
        color_to_zone={"raster:R-1": "R-1"},
        source_class="vector",
        vision_label_count=1,
    )
    monkeypatch.setattr(ext, "extract_polygons", lambda *_a, **_kw: sample)
    # default_extract... loads op5_lib.extraction lazily — patch on the
    # module before invocation.
    out = runner.default_extract_polygons_from_map(muni)
    assert out.source_class == "vector"
    assert out.polygons and out.polygons[0]["zone_code"] == "R-1"
    assert out.vision_label_count == 1


def test_default_extract_returns_absent_when_no_map_url() -> None:
    m = runner.MuniRecord(
        muni_code="0000",
        muni_name="Nowhere Borough",
        map_url=None,
        ordinance_url=None,
    )
    out = runner.default_extract_polygons_from_map(m)
    assert out.source_class == "absent"
    assert out.polygons == []


def test_default_extract_raster_routes_to_vision(monkeypatch, muni: runner.MuniRecord) -> None:
    from op5_lib import extraction as ext

    sample = ext.ExtractionResult(
        polygons=[{
            "zone_code": "B-2",
            "confidence": 0.85,
            "geometry": {"type": "Polygon", "coordinates": [[[-74, 40.8], [-74, 40.81], [-73.99, 40.81], [-73.99, 40.8], [-74, 40.8]]]},
        }],
        color_to_zone={"raster:B-2": "B-2"},
        source_class="raster",
        vision_label_count=1,
    )
    calls: list[dict] = []

    def _fake(map_url, *, place_name, state="NJ", anthropic_api_key=None):
        calls.append({"map_url": map_url, "place_name": place_name, "state": state})
        return sample

    monkeypatch.setattr(ext, "extract_polygons", _fake)
    out = runner.default_extract_polygons_from_map(muni)
    assert out.source_class == "raster"
    assert calls and calls[0]["place_name"] == "Westwood"


@pytest.mark.asyncio
async def test_default_ingest_refuses_nonpreview_url(monkeypatch, muni: runner.MuniRecord) -> None:
    """When DATABASE_URL doesn't contain the preview ref, the default ingest
    refuses to run."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:x@aws-1-us-east-2.pooler.supabase.com:6543/postgres",
    )
    extraction = runner.ExtractionResult(
        polygons=[{"zone_code": "R-1", "geometry": {"type": "Polygon", "coordinates": [[]]}}],
        color_to_zone={"raster:R-1": "R-1"},
        source_class="vector",
        vision_label_count=1,
    )
    with pytest.raises(RuntimeError, match="preview"):
        await runner.default_ingest_polygons(
            muni, extraction,
            preview_branch=runner.DEFAULT_PREVIEW_BRANCH,
            county="bergen",
        )


@pytest.mark.asyncio
async def test_default_run_backfill_calls_spatial_backfill_with_100m(monkeypatch) -> None:
    """default_run_backfill should call backfill_parcel_zoning_from_districts
    with nearest_within_meters=100.0 (proof default)."""
    from unittest.mock import AsyncMock, patch

    captured: dict = {}

    async def _fake_backfill(jurisdiction_id, db, *, nearest_within_meters=None, **_kw):
        captured["jid"] = str(jurisdiction_id)
        captured["nearest"] = nearest_within_meters
        return 0

    with patch(
        "app.services.spatial_backfill.backfill_parcel_zoning_from_districts",
        new=_fake_backfill,
    ):
        # Stub out engine creation so we don't actually connect to a DB.
        fake_engine = AsyncMock()
        fake_engine.dispose = AsyncMock(return_value=None)

        class _SessionCM:
            async def __aenter__(self_inner):
                m = AsyncMock()
                m.commit = AsyncMock(return_value=None)
                return m

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine",
            return_value=fake_engine,
        ), patch(
            "sqlalchemy.ext.asyncio.async_sessionmaker",
            return_value=lambda: _SessionCM(),
        ):
            await runner.default_run_backfill(
                "4bf00234-4455-4987-a067-b22ee6b6aa1f",
                nearest_within_meters=100.0,
            )

    assert captured.get("nearest") == 100.0
    assert captured.get("jid") == "4bf00234-4455-4987-a067-b22ee6b6aa1f"


def test_orchestrator_default_max_parallel_is_14() -> None:
    """CP-Pre Finding 1 (master decision): default cap is 14, not 5 or 20."""
    import op5_factory_orchestrator as orch  # noqa: WPS433
    assert orch.DEFAULT_MAX_PARALLEL == 14


# ── CP-Pre Finding 4 / Option F2 — proof-state protect list ────────────────


class _FakeAsyncpgConn:
    """Lightweight asyncpg.Connection stand-in for testing the protect-list.

    Records every execute()/fetchrow() invocation so the test can assert
    which SQL was/wasn't run. ``preloaded_rows`` is a list of dicts that
    fetchrow consumes from in order; each call pops the head, returns it,
    and remembers the SQL + args for inspection.
    """

    def __init__(self, preloaded_rows: list[dict]) -> None:
        self._preloaded = list(preloaded_rows)
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql: str, *args):
        self.fetchrow_calls.append((sql, args))
        if not self._preloaded:
            return None
        return self._preloaded.pop(0)

    async def execute(self, sql: str, *args):
        self.execute_calls.append((sql, args))
        return "EXECUTE 0"


@pytest.mark.asyncio
async def test_ingest_refuses_when_proof_state_present() -> None:
    """CP-Pre Finding 4 / Option F2: if rows exist under the target
    op5_town that LACK op5_factory='true', the ingest helper MUST raise
    ProofStateCollisionError BEFORE running any DELETE.
    """
    from op5_lib.ingestion_helpers import (
        ProofStateCollisionError,
        ingest_polygons_additive,
    )

    # The collision-check fetchrow returns n=215 (Garfield proof state).
    conn = _FakeAsyncpgConn(preloaded_rows=[{"n": 215}])

    with pytest.raises(ProofStateCollisionError) as excinfo:
        await ingest_polygons_additive(
            conn,
            jurisdiction_id="4bf00234-4455-4987-a067-b22ee6b6aa1f",
            op5_town="garfield",
            polygons=[{
                "zone_code": "R-1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-74.1, 40.8], [-74.1, 40.81],
                                     [-74.09, 40.81], [-74.09, 40.8], [-74.1, 40.8]]],
                },
            }],
        )

    # The error message names the protected count and the op5_town tag.
    msg = str(excinfo.value)
    assert "215" in msg
    assert "garfield" in msg

    # CRITICAL: the DELETE must NOT have been issued.
    delete_calls = [
        sql for sql, _args in conn.execute_calls if "DELETE" in sql.upper()
    ]
    assert delete_calls == [], (
        f"DELETE was issued despite proof-state collision: {delete_calls}"
    )
    # And no INSERT either.
    insert_calls = [
        sql for sql, _args in conn.execute_calls if "INSERT" in sql.upper()
    ]
    assert insert_calls == []


@pytest.mark.asyncio
async def test_ingest_proceeds_when_no_proof_state_present() -> None:
    """When the pre-flight check finds 0 protected rows, the ingest runs
    the DELETE and INSERT path normally.
    """
    from op5_lib.ingestion_helpers import ingest_polygons_additive

    # n=0 -> safe to proceed.
    conn = _FakeAsyncpgConn(preloaded_rows=[{"n": 0}])

    inserted = await ingest_polygons_additive(
        conn,
        jurisdiction_id="4bf00234-4455-4987-a067-b22ee6b6aa1f",
        op5_town="ridgewood",
        polygons=[{
            "zone_code": "R-1",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-74.1, 40.8], [-74.1, 40.81],
                                 [-74.09, 40.81], [-74.09, 40.8], [-74.1, 40.8]]],
            },
        }],
    )
    assert inserted == 1
    # Exactly one DELETE and one INSERT.
    delete_calls = [
        sql for sql, _args in conn.execute_calls if sql.strip().startswith("\n        DELETE") or "DELETE FROM zoning_districts" in sql
    ]
    insert_calls = [
        sql for sql, _args in conn.execute_calls if "INSERT INTO zoning_districts" in sql
    ]
    assert len(delete_calls) == 1
    assert len(insert_calls) == 1
    # The DELETE retains the op5_factory='true' filter as a backstop.
    assert "op5_factory" in delete_calls[0]


@pytest.mark.asyncio
async def test_protect_check_query_uses_negated_factory_tag() -> None:
    """The protect-check SELECT must count rows where op5_factory is
    NULL or != 'true' — not the inverse. Pin the SQL shape so future
    edits don't accidentally invert the predicate.
    """
    from op5_lib.ingestion_helpers import assert_no_proof_state_collision

    conn = _FakeAsyncpgConn(preloaded_rows=[{"n": 0}])
    n = await assert_no_proof_state_collision(
        conn,
        jurisdiction_id="4bf00234-4455-4987-a067-b22ee6b6aa1f",
        op5_town="garfield",
    )
    assert n == 0
    assert len(conn.fetchrow_calls) == 1
    sql = conn.fetchrow_calls[0][0]
    # Predicate sanity checks — these are the load-bearing pieces.
    assert "op5_town" in sql
    assert "op5_factory" in sql
    assert "IS NULL" in sql.upper()
    assert "<> 'true'" in sql or "!= 'true'" in sql
