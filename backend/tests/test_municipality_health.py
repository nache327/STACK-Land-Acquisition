"""Unit tests for municipality_health._classify and _envelope_overlap_ratio.

The classifier owns the operational trustworthiness contract. These tests
pin the band boundaries so they can't drift without somebody noticing.
"""
from __future__ import annotations

import pytest

from app.services.municipality_health import (
    MAX_DISTRICT_OVERLAP_RATIO,
    MIN_DISTRICT_COUNT_FOR_OPERATIONAL,
    MIN_EXTENT_OVERLAP_RATIO,
    MIN_PARCEL_CLASS_PCT_PARTIAL,
    MIN_PARCEL_COUNT_FOR_OPERATIONAL,
    MIN_PARCEL_ZONING_PCT_OPERATIONAL,
    MIN_PARCEL_ZONING_PCT_PARTIAL,
    _classify,
    _envelope_overlap_ratio,
)


def _kwargs(**override):
    """Default to an 'operational' muni; tests override specific fields
    to descend into each band."""
    base = dict(
        parcel_count=2_000,
        district_count=20,
        district_invalid=0,
        parcel_zoning_pct=0.90,
        parcel_class_pct=0.60,
        extent_overlap_ratio=0.95,
        overlap_ratio=0.01,
        orphan_zone_code_count=0,
    )
    base.update(override)
    return base


# ─── operational baseline ────────────────────────────────────────────────────

def test_operational_when_all_floors_met():
    band, gaps = _classify(**_kwargs())
    assert band == "operational"
    assert gaps == []


# ─── empty band ──────────────────────────────────────────────────────────────

def test_empty_when_no_parcels_and_no_districts():
    band, gaps = _classify(**_kwargs(
        parcel_count=0, district_count=0,
        parcel_zoning_pct=None, parcel_class_pct=None,
        extent_overlap_ratio=None, overlap_ratio=None,
    ))
    assert band == "empty"
    assert "no parcels" in gaps[0]


# ─── broken band — strongest demote ──────────────────────────────────────────

def test_broken_when_parcel_zoning_rate_near_zero():
    """< 10% zoning_code coverage means the spatial join didn't bind —
    broken regardless of how many districts exist."""
    band, gaps = _classify(**_kwargs(parcel_zoning_pct=0.05))
    assert band == "broken"
    assert any("spatial join" in g for g in gaps)


def test_broken_when_extents_disjoint():
    """Parcel + district envelopes overlap < 50% → districts probably
    belong to the wrong location (CRS bug, wrong-jurisdiction ingest)."""
    band, gaps = _classify(**_kwargs(extent_overlap_ratio=0.20))
    assert band == "broken"
    assert any("extent" in g for g in gaps)


def test_broken_when_any_district_geometry_invalid():
    band, gaps = _classify(**_kwargs(district_invalid=3))
    assert band == "broken"
    assert any("invalid PostGIS geometry" in g for g in gaps)


def test_broken_when_parcels_exist_but_no_districts():
    """Parcels ingested but no zoning_districts for this muni — overlay
    will never bind. Broken."""
    band, gaps = _classify(**_kwargs(
        district_count=0, overlap_ratio=None, extent_overlap_ratio=None,
    ))
    assert band == "broken"
    assert any("districts ingested for this muni: 0" in g for g in gaps)


# ─── degraded band — recoverable but flagged ─────────────────────────────────

def test_degraded_when_zoning_pct_below_partial_floor():
    """30% zoning coverage is under the partial floor of 50% but above
    the broken floor of 10% — degraded."""
    band, gaps = _classify(**_kwargs(parcel_zoning_pct=0.30))
    assert band == "degraded"
    assert any(f"<{MIN_PARCEL_ZONING_PCT_PARTIAL:.0%}" in g for g in gaps)


def test_degraded_when_overlap_ratio_exceeds_max():
    """Duplicate-polygon ingests show up as a high overlap_ratio — for
    self-storage matrix work, duplicate districts cascade into double-
    counted parcels."""
    band, gaps = _classify(**_kwargs(overlap_ratio=0.20))
    assert band == "degraded"
    assert any("overlap" in g.lower() and "sibling" in g for g in gaps)


def test_degraded_when_too_few_districts():
    band, gaps = _classify(**_kwargs(district_count=1))
    assert band == "degraded"
    assert any("distinct district" in g for g in gaps)


def test_degraded_when_below_min_parcel_count():
    band, gaps = _classify(**_kwargs(parcel_count=10))
    assert band == "degraded"
    assert any(f"floor" in g for g in gaps)


# ─── partial band — usable but not full operational ──────────────────────────

def test_partial_when_zoning_pct_between_partial_and_operational_floor():
    """60% zoning coverage → above the partial floor (50%), below the
    operational floor (80%). Partial."""
    band, gaps = _classify(**_kwargs(parcel_zoning_pct=0.60))
    assert band == "partial"
    assert any("operational floor" in g for g in gaps)


def test_partial_when_zone_class_coverage_low():
    """Matrix coverage is shallow — parcels carry zoning_code but most
    fall into zone_class='unknown'."""
    band, gaps = _classify(**_kwargs(parcel_class_pct=0.10))
    assert band == "partial"
    assert any("zone_class" in g for g in gaps)


def test_partial_when_orphan_codes_exist():
    """Parcel.zoning_code populated from parcel source itself — codes
    not present on any district. Matrix bind will miss these."""
    band, gaps = _classify(**_kwargs(orphan_zone_code_count=5))
    assert band == "partial"
    assert any("orphan" not in g.lower() or "zone codes" in g for g in gaps)
    assert any("not present on any district" in g for g in gaps)


# ─── boundary tests pinning the thresholds ──────────────────────────────────

def test_exactly_at_operational_floor_is_operational():
    """80% is the operational floor — exactly at the boundary still
    qualifies; the test pins this since flipping the >= to > silently
    demotes munis with exactly-80% coverage."""
    band, _ = _classify(**_kwargs(parcel_zoning_pct=0.80))
    assert band == "operational"


def test_just_below_operational_floor_is_partial():
    band, _ = _classify(**_kwargs(parcel_zoning_pct=0.79))
    assert band == "partial"


def test_exactly_at_partial_floor_is_partial():
    """50% is the partial floor — at-boundary still passes the partial
    gate; the broken threshold (10%) is lower."""
    band, _ = _classify(**_kwargs(parcel_zoning_pct=0.50))
    assert band == "partial"


def test_just_below_partial_floor_is_degraded():
    band, _ = _classify(**_kwargs(parcel_zoning_pct=0.49))
    assert band == "degraded"


# ─── precedence — broken outranks degraded outranks partial ─────────────────

def test_broken_signal_wins_over_degraded():
    """A muni that's both 'parcel count too low' (degraded) AND
    'extents disjoint' (broken) is classified broken."""
    band, gaps = _classify(**_kwargs(
        parcel_count=10,            # would be degraded alone
        extent_overlap_ratio=0.20,  # broken signal
    ))
    assert band == "broken"
    assert any("extent" in g for g in gaps)


def test_degraded_signal_wins_over_partial():
    """A muni at the partial-zoning-coverage band but with a duplicate-
    polygon problem (degraded) is degraded."""
    band, _ = _classify(**_kwargs(
        parcel_zoning_pct=0.60,   # partial
        overlap_ratio=0.20,       # degraded
    ))
    assert band == "degraded"


# ─── _envelope_overlap_ratio — boundary cases ────────────────────────────────

def test_envelope_overlap_max_of_two_ratios():
    """Mirror of `_bbox_overlap_ratio` semantics — returns the bigger of
    inter/A and inter/B so a small layer fully inside a large jurisdiction
    still scores 1.0."""
    parcels = [0.0, 0.0, 10.0, 10.0]   # area 100
    districts = [0.0, 0.0, 5.0, 10.0]  # area 50 fully inside
    # inter=50; inter/parcels=0.5; inter/districts=1.0; max=1.0
    assert _envelope_overlap_ratio(parcels, districts) == 1.0


def test_envelope_overlap_returns_zero_for_disjoint():
    a = [0.0, 0.0, 1.0, 1.0]
    b = [10.0, 10.0, 11.0, 11.0]
    assert _envelope_overlap_ratio(a, b) == 0.0


def test_envelope_overlap_returns_none_for_malformed():
    assert _envelope_overlap_ratio(None, [0, 0, 1, 1]) is None
    assert _envelope_overlap_ratio([0, 0, 1, 1], None) is None
    assert _envelope_overlap_ratio([0, 0], [0, 0, 1, 1]) is None


def test_envelope_overlap_zero_area_box_counts_as_disjoint():
    """A degenerate (zero-area) bbox touching another box returns 0.0,
    not None — the bbox-intersection check trips before the
    divide-by-zero guard. That's the right behavior for our use:
    'envelopes don't overlap meaningfully' is the operator-visible
    signal regardless of whether one side is degenerate."""
    assert _envelope_overlap_ratio([0, 0, 0, 0], [0, 0, 1, 1]) == 0.0
