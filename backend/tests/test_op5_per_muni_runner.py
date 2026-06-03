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
    async def _ingest(m, e, *, preview_branch):
        return runner.IngestResult(
            jurisdiction_id="jid-test",
            polygons_written=len(e.polygons),
            nearest_within_meters=runner.DEFAULT_NEAREST_WITHIN_METERS,
        )

    async def _backfill(jid, *, nearest_within_meters):
        return None

    async def _audit(jid, m, seed=8819):
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

    async def _ingest(m, e, *, preview_branch):
        return runner.IngestResult(
            jurisdiction_id="jid-spec",
            polygons_written=len(e.polygons),
            nearest_within_meters=100.0,
        )

    async def _backfill(jid, *, nearest_within_meters):
        assert nearest_within_meters == 100.0
        return None

    async def _audit(jid, m, seed=8819):
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

    async def _ingest(m, e, *, preview_branch):
        return runner.IngestResult("jid-low", len(e.polygons), 100.0)

    async def _backfill(jid, *, nearest_within_meters):
        return None

    async def _audit(jid, m, seed=8819):
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
