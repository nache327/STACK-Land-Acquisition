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


def test_fallback_wealth_center_caps_lane_at_core():
    """Lehi UT 2026-10-15: no $1M+ cluster within 60 km -> single-tract fallback center.
    A fallback-measured site may be core at most, never edge of wealth."""
    from app.services.keep_market import LANE_CORE, LANE_EDGE, classify_lane

    assert classify_lane(0.084, 28.2, center_is_cluster=True) == LANE_EDGE
    assert classify_lane(0.084, 28.2, center_is_cluster=False) == LANE_CORE


# ── Card strategy: tier / mix / margin / competitor supply (2026-10-19) ──────

@pytest.mark.parametrize("lane,share,tier", [
    ("core", 0.024, "tier_295_325"),           # Robbinsville NJ
    ("core", 0.018, "tier_295_325"),           # Westampton NJ
    ("core", 0.015, "tier_295_325"),           # boundary is inclusive
    ("core", 0.010, "tier_270_295"),
    ("core", None, "tier_270_295"),            # never promoted on a guess
    ("growth_corridor", 0.002, "pass"),        # Spring Hill
    ("edge_of_wealth", 0.05, "tier_325_350"),  # Toy Barn Helm
    (None, 0.05, None),
    ("bogus", 0.05, None),
])
def test_keep_tier(lane, share, tier):
    assert km.keep_tier(lane, share) == tier


def test_tier_tables_and_mix_label():
    assert km.TIER_PRICE == {"tier_325_350": (325, 350), "tier_295_325": (295, 325),
                              "tier_270_295": (270, 295)}
    assert km.mix_label("tier_325_350") == "50/30/20"
    assert km.mix_label("tier_295_325") == "30/40/30"
    assert km.mix_label("tier_270_295") == "15/40/45"
    assert km.mix_label("pass") is None and km.mix_label(None) is None
    assert all(sum(m) == 100 for m in km.TIER_MIX.values())


def test_cost_model_constants():
    assert km.ALL_IN_COST_PSF == 184.17
    assert km.selling_cost_pct("NJ") == pytest.approx(0.0159)
    assert km.selling_cost_pct("fl") == pytest.approx(0.0145)
    assert km.selling_cost_pct("IL") == pytest.approx(0.0090)
    assert km.selling_cost_pct("PA") == pytest.approx(0.0175)
    assert km.selling_cost_pct("MA") == pytest.approx(0.0121)
    assert km.selling_cost_pct("VA") == pytest.approx(0.0175)  # default 1.0%
    assert km.selling_cost_pct(None) == pytest.approx(0.0175)


def test_margin_pct():
    # 310 × (1 − 0.0159) = 305.07; (305.07 − 184.17) / 184.17 = 0.656
    assert round(km.margin_pct("tier_295_325", "NJ"), 2) == 0.66
    assert round(km.margin_pct("tier_325_350", "NJ"), 2) == round(
        (337.5 * (1 - 0.0159) - 184.17) / 184.17, 2)
    assert km.margin_pct("tier_270_295", "PA") < km.margin_pct("tier_270_295", "IL")
    assert km.margin_pct("pass", "NJ") is None
    assert km.margin_pct(None, "NJ") is None


def test_competitor_units_radius_and_max_not_sum(tmp_path):
    p = tmp_path / "supply.csv"
    p.write_text(
        "name,operator,lat,lng,units_built,units_planned,status,state\n"
        "Near,,40.10,-74.60,91,91,selling,NJ\n"      # built == planned → 91, not 182
        "Planned,,40.20,-74.60,,40,planned,NJ\n"     # blank built → 40
        "Far,,41.00,-74.60,500,,operating,NJ\n"      # ~100 km away
        "NoCoords,,,,100,,operating,NJ\n",
        encoding="utf-8")
    camps = km.load_supply_campuses(p)
    assert [c.name for c in camps] == ["Near", "Planned", "Far"]
    assert km.competitor_units(40.0, -74.6, camps) == 131
    assert km.competitor_units(45.0, -74.6, camps) == 0
    assert km.competitor_units(None, -74.6, camps) is None


def test_shipped_supply_csv_loads():
    camps = km.load_supply_campuses()
    assert len(camps) > 500
    names = [c.name for c in camps]
    assert names.count("M1 Concourse") == 1  # known duplicate dropped
    # Scottsdale has real nearby supply; open ocean has none.
    assert km.competitor_units(33.62, -111.89, camps) > 0
    assert km.competitor_units(30.0, -60.0, camps) == 0


def test_price_band_capped_to_observed_range():
    """Middlesex MA (~$447/SF homes) edge lane: raw 537–805 -> capped 300–450."""
    from app.services.keep_market import LANE_CORE, LANE_EDGE, price_band

    assert price_band(LANE_EDGE, 447) == (300, 450)
    assert price_band(LANE_CORE, 247) == (222, 321)   # Robbinsville unchanged
