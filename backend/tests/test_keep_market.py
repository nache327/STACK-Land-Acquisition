"""Keep-market lane rules (services/keep_market) — the calibration's sanity anchors.

Values from outputs/KEEP_MARKET_CALIBRATION_2026-10.md: the three test sites and the
Toy Barn Scottsdale (Helm) comp. If any of these flips, the rules drifted from the study.
"""
from __future__ import annotations

import pytest

from app.services import keep_market as km


def test_robbinsville_is_core_with_band():
    a = km.assess(0.024, 36, 247)
    assert a.keep_lane == km.LANE_CORE
    assert (a.price_band_low, a.price_band_high) == (222, 321)
    assert a.velocity_flag is None


def test_westampton_is_core():
    a = km.assess(0.018, 38, 234)
    assert a.keep_lane == km.LANE_CORE
    assert (a.price_band_low, a.price_band_high) == (211, 304)


def test_spring_hill_is_growth_corridor_and_far():
    a = km.assess(0.005, 57, 173)
    assert a.keep_lane == km.LANE_GROWTH
    assert a.velocity_flag == km.VELOCITY_FAR_FROM_WEALTH
    assert (a.price_band_low, a.price_band_high) == (121, 190)


def test_toy_barn_scottsdale_helm_is_edge_of_wealth():
    assert km.classify_lane(0.139, 25) == km.LANE_EDGE


@pytest.mark.parametrize("share,drive,lane", [
    (0.03, 40, km.LANE_EDGE),          # both thresholds inclusive
    (0.03, 40.1, km.LANE_CORE),        # deep wealth but far: core via share
    (0.10, 80, km.LANE_CORE),
    (0.0149, 40, km.LANE_CORE),        # thin pool but near a center: core via drive
    (0.015, 41, km.LANE_CORE),         # share floor inclusive
    (0.0149, 40.1, km.LANE_GROWTH),
    (0.0, 120, km.LANE_GROWTH),
])
def test_lane_boundaries(share, drive, lane):
    assert km.classify_lane(share, drive) == lane


@pytest.mark.parametrize("share,drive", [(None, 30), (0.05, None), (None, None)])
def test_null_inputs_never_guess(share, drive):
    a = km.assess(share, drive, 250)
    assert a.keep_lane is None
    assert (a.price_band_low, a.price_band_high) == (None, None)


def test_velocity_flag_boundary_and_null():
    assert km.velocity_flag(55) is None
    assert km.velocity_flag(55.1) == km.VELOCITY_FAR_FROM_WEALTH
    assert km.velocity_flag(None) is None


def test_price_band_needs_ppsf():
    assert km.price_band(km.LANE_EDGE, None) == (None, None)
    assert km.price_band(km.LANE_EDGE, 0) == (None, None)
    assert km.price_band(None, 250) == (None, None)
    assert km.price_band(km.LANE_EDGE, 250) == (300, 450)
    assert km.price_band(km.LANE_GROWTH, 250) == (175, 275)


def test_county_home_ppsf_is_value_over_1800():
    assert km.county_home_ppsf(444_600) == pytest.approx(247.0)
    assert km.county_home_ppsf(None) is None
    assert km.county_home_ppsf(0) is None


def test_band_ratios_match_the_memo():
    assert km.PRICE_RATIO_BANDS == {
        "edge_of_wealth": (1.2, 1.8), "core": (0.9, 1.3), "growth_corridor": (0.7, 1.1)}
    assert km.NEEDLE_LANES == ("edge_of_wealth", "core")


@pytest.mark.parametrize("share,delta", [
    (None, None), (0.0, 0.0), (0.01, 0.0), (0.055, 7.5), (0.10, 15.0), (0.25, 15.0),
])
def test_wealth_depth_delta(share, delta):
    assert km.wealth_depth_delta(share) == delta


def test_far_from_wealth_delta():
    assert km.far_from_wealth_delta(56) == -10.0
    assert km.far_from_wealth_delta(55) == 0.0
    assert km.far_from_wealth_delta(None) == 0.0


def test_docstring_carries_product_assumption_and_memo():
    doc = km.__doc__ or ""
    assert "KEEP_MARKET_CALIBRATION_2026-10" in doc
    assert "FINISHED CLUBHOUSE" in doc and "Toy Barn" in doc
