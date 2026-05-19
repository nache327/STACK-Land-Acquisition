"""Unit tests for stale-score remediation safety invariants.

Focus on the parts that, if broken, would silently corrupt operator
decisions or leak score writes in dry-run mode:

  - dry-run never writes
  - verified/rejected rows are never mutated, even in live mode
  - confidence_label preserves operator status
  - threshold-crossing detection is correct
  - score-delta bucketing is correct
  - rollback won't overwrite a now-verified row
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import stale_score_remediation as r


# ─── helpers ─────────────────────────────────────────────────────────────────

class _StubJurisdiction:
    def __init__(self, *, name="Bergen County, NJ", county="Bergen", state="NJ",
                 bbox=(-74.27, 40.76, -73.90, 41.13), id=None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.county = county
        self.state = state
        self.bbox = list(bbox)


def _row(**kwargs):
    """Stand-in for a ZoningSource row.

    Note we set both .jurisdiction_id and confidence_breakdown so the
    audit logic can read them directly. Most fields are mutable so the
    rescore writes-back path can be exercised."""
    defaults = dict(
        id=uuid.uuid4(),
        jurisdiction_id=uuid.uuid4(),
        municipality_name="Sample Town",
        title="Sample Zoning",
        zoning_endpoint="https://example.com/FeatureServer/0",
        feature_count=200,
        geometry_type="esriGeometryPolygon",
        field_matches=["ZoneCode"],
        validation_status="pending",
        confidence_score=85,
        confidence_label="discovered",
        confidence_breakdown={"title_positive": 15, "geometry_polygon": 20,
                              "feature_count_ok": 15, "field_matches": 5,
                              "name_match_multi_word": 30},
        reasons=["title matches zoning keywords: ['zoning']"],
        rejected_reason=None,
        notes=None,
        last_verified_at=None,
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ─── _has_bbox_overlap_component ─────────────────────────────────────────────

def test_stale_detection_skips_breakdown_with_bbox_component():
    fresh = {"title_positive": 15, "bbox_overlap_strong": 10}
    assert r._has_bbox_overlap_component(fresh) is True


def test_stale_detection_flags_breakdown_without_bbox_component():
    stale = {"title_positive": 15, "geometry_polygon": 20}
    assert r._has_bbox_overlap_component(stale) is False


def test_stale_detection_handles_none_and_non_dict():
    assert r._has_bbox_overlap_component(None) is False
    assert r._has_bbox_overlap_component([]) is False
    assert r._has_bbox_overlap_component("not a dict") is False


# ─── _crosses_threshold ──────────────────────────────────────────────────────

def test_threshold_down_when_score_falls_below():
    assert r._crosses_threshold(85, 25, 70) == "down"


def test_threshold_up_when_score_rises_above():
    assert r._crosses_threshold(50, 75, 70) == "up"


def test_threshold_none_when_both_above_or_both_below():
    assert r._crosses_threshold(80, 75, 70) is None
    assert r._crosses_threshold(50, 40, 70) is None


def test_threshold_none_when_either_score_is_none():
    assert r._crosses_threshold(None, 25, 70) is None
    assert r._crosses_threshold(85, None, 70) is None


def test_threshold_boundary_at_exactly_70():
    """Boundary semantics: crossing INTO 'below 70' triggers, but 70→70 doesn't."""
    assert r._crosses_threshold(70, 69, 70) == "down"
    assert r._crosses_threshold(70, 70, 70) is None
    # Score that drops from above 70 to exactly 70 is NOT 'down' — it
    # stays in the high-confidence bucket (>= 70).
    assert r._crosses_threshold(85, 70, 70) is None


# ─── _bucket_delta ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("delta,bucket", [
    (-100, "≤-50"), (-60, "≤-50"), (-50, "≤-50"),
    (-49, "-49..-20"), (-20, "-49..-20"),
    (-19, "-19..-1"), (-1, "-19..-1"),
    (0, "0"),
    (1, "1..19"), (19, "1..19"),
    (20, "20..49"), (49, "20..49"),
    (50, "≥50"), (100, "≥50"),
])
def test_bucket_delta_boundaries(delta, bucket):
    assert r._bucket_delta(delta) == bucket


# ─── _snapshot — captures exactly the four fields rollback restores ──────────

def test_snapshot_includes_only_restorable_fields():
    row = _row(confidence_score=85, confidence_label="discovered",
               confidence_breakdown={"a": 1}, reasons=["x"])
    snap = r._snapshot(row)
    assert set(snap.keys()) == {
        "source_id", "confidence_score", "confidence_label",
        "confidence_breakdown", "reasons",
    }
    assert snap["confidence_score"] == 85
    # validation_status is NOT in the snapshot — preserved across rollback.
    assert "validation_status" not in snap


# ─── label preservation under recompute ──────────────────────────────────────

def test_recompute_preserves_verified_label_regardless_of_score():
    """A row marked verified by the operator must keep label=verified
    even if the recomputed score collapses."""
    juris = _StubJurisdiction()
    row = _row(validation_status="verified", confidence_label="verified")
    probe = {"bbox_overlap_ratio": 0.0, "verdict": "disjoint"}
    result = r._recompute_row(
        row=row, probe=probe, jurisdiction=juris,
        name_tokens={"all": [], "rare": [], "common": [], "expect": []},
        denylist=set(),
    )
    assert result["after"]["confidence_label"] == "verified"


def test_recompute_preserves_rejected_label_regardless_of_score():
    juris = _StubJurisdiction()
    row = _row(validation_status="rejected", confidence_label="rejected")
    probe = {"bbox_overlap_ratio": 0.8, "verdict": "good"}
    result = r._recompute_row(
        row=row, probe=probe, jurisdiction=juris,
        name_tokens={"all": [], "rare": [], "common": [], "expect": []},
        denylist=set(),
    )
    assert result["after"]["confidence_label"] == "rejected"


def test_recompute_recomputes_label_for_pending_rows():
    """Pending row whose score lands above threshold → 'discovered';
    below → 'discovered_low'. Mirrors discovery's persist behavior."""
    juris = _StubJurisdiction()
    # Pending row with strong inputs — should land >=70 → discovered.
    row = _row(validation_status="pending", title="Bergen County Zoning")
    probe = {"bbox_overlap_ratio": 0.8, "verdict": "good"}
    out = r._recompute_row(
        row=row, probe=probe, jurisdiction=juris,
        name_tokens={"all": ["bergen"], "rare": ["bergen"], "common": [], "expect": ["bergen"]},
        denylist=set(),
    )
    assert out["after"]["confidence_label"] == "discovered"
    assert out["after"]["confidence_score"] >= 70


def test_recompute_emits_label_discovered_low_when_score_drops():
    juris = _StubJurisdiction()
    # Pending row with disjoint extent — recompute fires -60.
    row = _row(validation_status="pending",
               title="MontereyPark Zoning",  # generic, no real Bergen tokens
               field_matches=[])
    probe = {"bbox_overlap_ratio": 0.0, "verdict": "disjoint"}
    out = r._recompute_row(
        row=row, probe=probe, jurisdiction=juris,
        name_tokens={"all": ["bergen"], "rare": ["bergen"], "common": [], "expect": ["bergen"]},
        denylist=set(),
    )
    assert out["after"]["confidence_label"] == "discovered_low"
    assert out["after"]["confidence_score"] < 70


def test_recompute_fires_bbox_overlap_disjoint_component():
    """The whole point of rescore: stale row with no bbox component
    gets the -60 disjoint penalty wired in."""
    juris = _StubJurisdiction()
    row = _row(validation_status="pending", title="New Milford zoning shapefiles")
    probe = {"bbox_overlap_ratio": 0.0, "verdict": "disjoint"}
    out = r._recompute_row(
        row=row, probe=probe, jurisdiction=juris,
        name_tokens={"all": ["bergen"], "rare": ["bergen"], "common": [], "expect": ["bergen"]},
        denylist=set(),
    )
    assert "bbox_overlap_disjoint" in out["after"]["confidence_breakdown"]
    assert out["after"]["confidence_breakdown"]["bbox_overlap_disjoint"] == -60


# ─── infer_row_scoring_version ──────────────────────────────────────────────

def test_infer_version_returns_1_for_pre_v2_breakdown():
    """Stored breakdowns without any bbox_overlap_* component must be
    treated as v1 — that's the marker the rescore framework uses to
    detect rows scored before the 2026-05-12 fix."""
    bk = {"title_positive": 15, "geometry_polygon": 20, "feature_count_ok": 15}
    assert r.infer_row_scoring_version(bk) == 1


def test_infer_version_returns_2_when_any_bbox_marker_present():
    """A row carrying any one of the bbox_overlap_* keys was scored
    under v2 (or later, when newer markers are added)."""
    for marker in ("bbox_overlap_strong", "bbox_overlap_tiny", "bbox_overlap_disjoint"):
        assert r.infer_row_scoring_version({marker: 10}) == 2


def test_infer_version_handles_none_and_non_dict():
    assert r.infer_row_scoring_version(None) == 1
    assert r.infer_row_scoring_version([]) == 1
    assert r.infer_row_scoring_version("oops") == 1


# ─── rescore_eligibility ─────────────────────────────────────────────────────

def test_eligibility_none_for_v2_row_within_age_and_no_denylist_hit():
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10, "title_positive": 15},
        updated_at=datetime.now(timezone.utc),
    )
    assert r.rescore_eligibility(
        row, current_version=2, jurisdiction_bbox_updated_at=None,
        denylist=set(), max_age_days=90,
    ) is None


def test_eligibility_flags_scoring_version_lower():
    """A v1 row (no bbox_overlap_*) under current_version=2 is eligible
    with reason 'scoring_version_lower'."""
    row = _row(
        confidence_breakdown={"title_positive": 15, "geometry_polygon": 20},
        updated_at=datetime.now(timezone.utc),
    )
    out = r.rescore_eligibility(
        row, current_version=2, jurisdiction_bbox_updated_at=None,
        denylist=set(),
    )
    assert out is not None
    assert out["reason"] == "scoring_version_lower"
    assert "v1" in out["detail"]


def test_eligibility_flags_jurisdiction_bbox_refreshed():
    """A v2 row whose updated_at predates the jurisdiction bbox refresh
    is eligible — Component F was computed against the old bbox."""
    row_ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    juris_ts = datetime(2026, 5, 14, tzinfo=timezone.utc)
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10},
        updated_at=row_ts,
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=juris_ts,
        denylist=set(),
    )
    assert out is not None
    assert out["reason"] == "jurisdiction_bbox_refreshed"


def test_eligibility_scoring_version_takes_priority_over_bbox_refresh():
    """When a row is both v1 AND predates a bbox refresh, the version
    drift is the louder signal — we report scoring_version_lower."""
    row_ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    juris_ts = datetime(2026, 5, 14, tzinfo=timezone.utc)
    row = _row(
        confidence_breakdown={"title_positive": 15},  # v1
        updated_at=row_ts,
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=juris_ts,
        denylist=set(),
    )
    assert out is not None
    assert out["reason"] == "scoring_version_lower"


def test_eligibility_flags_denylist_url_not_reflected():
    """Endpoint is in cross-jurisdiction denylist (operator rejected it
    elsewhere) but this row's breakdown lacks `denylist_rejected` — the
    -80 penalty was never applied here. Eligible."""
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10},  # v2
        updated_at=datetime.now(timezone.utc),
        zoning_endpoint="https://baduniverse.example/FeatureServer/0",
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=None,
        denylist={"https://baduniverse.example/FeatureServer/0"},
    )
    assert out is not None
    assert out["reason"] == "denylist_url_not_reflected"


def test_eligibility_skips_denylist_when_penalty_already_applied():
    """If denylist_rejected is already in the breakdown, the penalty is
    already reflected. Skip — not eligible."""
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10, "denylist_rejected": -80},
        updated_at=datetime.now(timezone.utc),
        zoning_endpoint="https://baduniverse.example/FeatureServer/0",
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=None,
        denylist={"https://baduniverse.example/FeatureServer/0"},
    )
    assert out is None


def test_eligibility_flags_age_exceeds_max():
    """Row older than max_age_days, even when v2 + bbox-fresh + not on
    denylist, is eligible for refresh — last-resort signal."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=120)
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10},
        updated_at=old_ts,
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=None,
        denylist=set(), max_age_days=90,
    )
    assert out is not None
    assert out["reason"] == "age_exceeds_max"


def test_eligibility_age_signal_disabled_when_max_age_days_is_none():
    """Operator can disable the age signal explicitly — useful when
    they want to inspect only structural staleness."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=365 * 5)
    row = _row(
        confidence_breakdown={"bbox_overlap_strong": 10},
        updated_at=old_ts,
    )
    out = r.rescore_eligibility(
        row, current_version=2,
        jurisdiction_bbox_updated_at=None,
        denylist=set(), max_age_days=None,
    )
    assert out is None


# ─── DB-level invariants exercised via the real session fixture ──────────────

@pytest.mark.asyncio
async def test_dry_run_never_writes_to_db(db_session):
    """dry_run=True must leave confidence_score/breakdown/label/reasons
    on every row untouched, even when the recompute would produce a
    different score."""
    from app.models.jurisdiction import Jurisdiction
    from app.models.zoning_source import ZoningSource

    juris = Jurisdiction(
        name="Bergen County, NJ", state="NJ", county="Bergen",
        coverage_level="active", bbox=[-74.27, 40.76, -73.90, 41.13],
    )
    db_session.add(juris)
    await db_session.flush()

    src = ZoningSource(
        jurisdiction_id=juris.id,
        municipality_name="New Milford",
        source_type="arcgis_featureserver",
        # Bogus endpoint so the live probe fails fast; the spatial probe
        # returning error doesn't fire any bbox component anyway.
        zoning_endpoint="https://127.0.0.1:1/never/FeatureServer/0",
        title="New Milford zoning shapefiles",
        feature_count=251,
        geometry_type="esriGeometryPolygon",
        field_matches=["ZoningDist"],
        confidence_score=85,
        confidence_label="discovered",
        confidence_breakdown={
            "title_positive": 15, "geometry_polygon": 20,
            "feature_count_ok": 15, "field_matches": 5,
            "name_match_multi_word": 30,
        },
        validation_status="pending",
        reasons=["title matches zoning keywords: ['zoning']"],
    )
    db_session.add(src)
    await db_session.flush()
    snapshot_before = (
        src.confidence_score, src.confidence_label,
        dict(src.confidence_breakdown), list(src.reasons or []),
    )

    opts = r.RescoreOptions(dry_run=True, max_rows=5, concurrency=1)
    out = await r.rescore_stale_sources(juris.id, db_session, opts)
    assert out["dry_run"] is True
    assert out["summary"]["applied"] == 0

    await db_session.refresh(src)
    snapshot_after = (
        src.confidence_score, src.confidence_label,
        dict(src.confidence_breakdown), list(src.reasons or []),
    )
    assert snapshot_before == snapshot_after, "dry-run mutated the row"


@pytest.mark.asyncio
async def test_live_mode_never_mutates_verified_rows(db_session):
    """Even with dry_run=False and the recompute producing a lower score,
    a verified row must keep its persisted score + label + breakdown."""
    from app.models.jurisdiction import Jurisdiction
    from app.models.zoning_source import ZoningSource

    juris = Jurisdiction(
        name="Bergen County, NJ", state="NJ", county="Bergen",
        coverage_level="active", bbox=[-74.27, 40.76, -73.90, 41.13],
    )
    db_session.add(juris)
    await db_session.flush()

    src = ZoningSource(
        jurisdiction_id=juris.id,
        municipality_name="Paramus",
        source_type="arcgis_featureserver",
        zoning_endpoint="https://127.0.0.1:1/never/FeatureServer/0",
        title="Paramus Zoning",
        feature_count=180,
        geometry_type="esriGeometryPolygon",
        field_matches=["CLASS"],
        confidence_score=92,
        confidence_label="verified",
        confidence_breakdown={"title_positive": 15, "geometry_polygon": 20,
                              "feature_count_ok": 15, "field_matches": 5,
                              "name_match_multi_word": 30},
        validation_status="verified",
        reasons=["title matches zoning keywords: ['zoning']"],
    )
    db_session.add(src)
    await db_session.flush()
    score_before = src.confidence_score
    label_before = src.confidence_label

    # only_status includes verified so the row is scanned, but live mode
    # must still refuse to write it.
    opts = r.RescoreOptions(
        dry_run=False, max_rows=5, concurrency=1,
        only_status=("verified",), stale_only=True,
    )
    out = await r.rescore_stale_sources(juris.id, db_session, opts)
    await db_session.refresh(src)
    assert src.confidence_score == score_before
    assert src.confidence_label == label_before == "verified"
    # If the row appears in changes, it's flagged as not-applied.
    matched = [c for c in out["changes"] if c["source_id"] == str(src.id)]
    if matched:
        assert matched[0]["applied"] is False
        assert "immutable" in matched[0].get("skipped_reason", "")


@pytest.mark.asyncio
async def test_rollback_skips_rows_that_were_verified_after_rescore(db_session):
    """If the operator verified a row between rescore and rollback, the
    rollback must NOT silently overwrite their verify decision back to
    stale state."""
    from app.models.jurisdiction import Jurisdiction
    from app.models.zoning_source import ZoningSource

    juris = Jurisdiction(
        name="Bergen County, NJ", state="NJ", county="Bergen",
        coverage_level="active", bbox=[-74.27, 40.76, -73.90, 41.13],
    )
    db_session.add(juris)
    await db_session.flush()

    src = ZoningSource(
        jurisdiction_id=juris.id,
        municipality_name="Town", source_type="arcgis_featureserver",
        zoning_endpoint="https://example.com/FeatureServer/0",
        title="Town Zoning", feature_count=100, geometry_type="esriGeometryPolygon",
        field_matches=["ZoneCode"],
        confidence_score=40, confidence_label="verified",
        confidence_breakdown={"title_positive": 15},
        validation_status="verified",
        reasons=[],
    )
    db_session.add(src)
    await db_session.flush()

    snapshot = [{
        "source_id": str(src.id),
        "confidence_score": 85,  # what it was before rescore
        "confidence_label": "discovered",
        "confidence_breakdown": {"x": 1},
        "reasons": ["old reason"],
    }]
    out = await r.rollback_rescores(juris.id, db_session, snapshot)
    await db_session.refresh(src)
    # Score must NOT have been overwritten — the row is now verified.
    assert src.confidence_score == 40
    assert src.confidence_label == "verified"
    assert out["restored"] == 0
    assert len(out["skipped"]) == 1
