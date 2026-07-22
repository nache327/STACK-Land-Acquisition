"""Acreage curve — peaked, not monotonic (2026-07-22 buy-box sweep).

The old formula was min(acres/30,1)*20, so a 160-ac parcel scored the SAME
+20 as a 30-ac one and never got penalized — which is why oversize parcels
sorted as "Excellent". The new curve peaks at the 2-8 ac sweet spot, decays to
+5 by 15 ac, and applies a flat penalty above 15 ac. Pure Python over
score_for_parcel — no DB.
"""
from __future__ import annotations

import pytest

from app.services.buybox_scoring import (
    ACRE_EDGE,
    ACRE_MAX,
    ACRE_OVERSIZE,
    ACRE_PEAK,
    ParcelInputs,
    _acreage_delta,
    score_for_parcel,
)


def _inputs(acres):
    return ParcelInputs(
        parcel_id=1, storage_permission="permitted", acres=acres, aadt=None,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True,
    )


def _acre_factor(scored):
    return next((f for f in scored.factors if f["label"] == "Acres"), None)


# ─── The curve itself ────────────────────────────────────────────────────

@pytest.mark.parametrize("acres,expected", [
    (0.5, round(0.5 / 2.0 * ACRE_PEAK, 1)),   # sub-sweet ramp
    (2.0, ACRE_PEAK),                          # plateau start
    (5.0, ACRE_PEAK),                          # plateau middle
    (8.0, ACRE_PEAK),                          # plateau end
    (15.0, ACRE_EDGE),                         # decay endpoint
    (15.01, ACRE_OVERSIZE),                    # just over → penalty
    (33.0, ACRE_OVERSIZE),                     # Edison
    (160.0, ACRE_OVERSIZE),                    # Skillman
])
def test_acreage_delta(acres, expected):
    assert _acreage_delta(acres) == expected


def test_decay_is_monotonic_between_8_and_15():
    prev = ACRE_PEAK + 1
    for a in [8.0, 10.0, 12.0, 14.0, 15.0]:
        d = _acreage_delta(a)
        assert d <= prev
        prev = d


# ─── Behavior through score_for_parcel ───────────────────────────────────

def test_oversize_parcel_scores_below_sweet_spot():
    """The whole point: a 160-ac permitted parcel must NOT score like a 5-ac one."""
    big = score_for_parcel(_inputs(160.0))
    good = score_for_parcel(_inputs(5.0))
    assert big.score < good.score
    assert _acre_factor(big)["delta"] == ACRE_OVERSIZE
    assert "oversize" in _acre_factor(big)["reason"]


def test_sweet_spot_is_excellent():
    s = score_for_parcel(_inputs(4.0))
    # base 50 + permitted 30 + acres 20 = 100 → excellent
    assert s.score >= 80
    assert s.tier == "excellent"


def test_oversize_no_longer_excellent_on_zoning_alone():
    # base 50 + permitted 30 - 15 oversize = 65 → not "excellent" (>=80)
    s = score_for_parcel(_inputs(160.0))
    assert s.tier != "excellent"
