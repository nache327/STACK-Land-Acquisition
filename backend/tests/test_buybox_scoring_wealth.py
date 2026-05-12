"""Unit tests for the wealth-density contribution to score_for_parcel.

Validates the three Homes ≥$1M/$2M/$5M bonuses + below-threshold penalties.
Doesn't touch the DB — pure Python over the score_for_parcel function.
"""
from __future__ import annotations

from app.services.buybox_scoring import ParcelInputs, score_for_parcel


def _base_inputs(**over) -> ParcelInputs:
    """Baseline parcel inputs — vacant, permitted, neutral on every other
    signal so the wealth-density factors are what we observe."""
    defaults = dict(
        parcel_id=1,
        storage_permission="permitted",
        acres=None,
        aadt=None,
        in_flood_zone=False,
        in_wetland=False,
        has_structure=False,
        homes_over_1m=None,
        homes_over_2m=None,
        homes_over_5m=None,
    )
    defaults.update(over)
    return ParcelInputs(**defaults)


def _factor(scored, label: str) -> dict | None:
    return next((f for f in scored.factors if f["label"] == label), None)


# ─── No-op cases ────────────────────────────────────────────────────────

def test_no_filter_no_wealth_factors():
    s = score_for_parcel(_base_inputs(homes_over_1m=100))
    assert _factor(s, "Homes ≥$1M") is None


def test_slider_off_no_wealth_factor():
    s = score_for_parcel(
        _base_inputs(homes_over_1m=100),
        filter_json={"minHomesOver1M": None},
    )
    assert _factor(s, "Homes ≥$1M") is None


def test_slider_zero_no_wealth_factor():
    # Sliders at 0 mean "off" in the UI; scorer should treat the same.
    s = score_for_parcel(
        _base_inputs(homes_over_1m=100),
        filter_json={"minHomesOver1M": 0},
    )
    assert _factor(s, "Homes ≥$1M") is None


# ─── Bonus path ─────────────────────────────────────────────────────────

def test_meets_min_gives_half_bonus():
    # actual == min → 50% of max (8.0) = 4.0
    s = score_for_parcel(
        _base_inputs(homes_over_1m=50),
        filter_json={"minHomesOver1M": 50},
    )
    f = _factor(s, "Homes ≥$1M")
    assert f is not None
    assert f["delta"] == 4.0


def test_double_min_gives_full_bonus():
    # actual = 2× min → ratio capped at 2.0 → full max (8.0)
    s = score_for_parcel(
        _base_inputs(homes_over_1m=200),
        filter_json={"minHomesOver1M": 100},
    )
    f = _factor(s, "Homes ≥$1M")
    assert f is not None
    assert f["delta"] == 8.0


def test_well_above_min_caps_at_max():
    s = score_for_parcel(
        _base_inputs(homes_over_1m=10_000),
        filter_json={"minHomesOver1M": 100},
    )
    f = _factor(s, "Homes ≥$1M")
    assert f["delta"] == 8.0


# ─── Penalty path ───────────────────────────────────────────────────────

def test_below_min_gives_fixed_penalty():
    s = score_for_parcel(
        _base_inputs(homes_over_1m=10),
        filter_json={"minHomesOver1M": 100},
    )
    f = _factor(s, "Homes ≥$1M")
    assert f is not None
    assert f["delta"] == -10


# ─── Pending data path ──────────────────────────────────────────────────

def test_unmeasured_ring_records_pending_zero():
    # homes_over_1m=None when slider is on → transparent factor with no delta
    s = score_for_parcel(
        _base_inputs(homes_over_1m=None),
        filter_json={"minHomesOver1M": 100},
    )
    f = _factor(s, "Homes ≥$1M")
    assert f is not None
    assert f["delta"] == 0
    assert "not yet measured" in f["reason"].lower()


# ─── All three thresholds stack ─────────────────────────────────────────

def test_all_three_thresholds_contribute_independently():
    s = score_for_parcel(
        _base_inputs(homes_over_1m=200, homes_over_2m=50, homes_over_5m=10),
        filter_json={
            "minHomesOver1M": 100,
            "minHomesOver2M": 25,
            "minHomesOver5M": 5,
        },
    )
    # Each at 2× min → full bonus
    assert _factor(s, "Homes ≥$1M")["delta"] == 8.0
    assert _factor(s, "Homes ≥$2M")["delta"] == 6.0
    assert _factor(s, "Homes ≥$5M")["delta"] == 4.0


def test_mixed_pass_and_fail():
    s = score_for_parcel(
        _base_inputs(homes_over_1m=200, homes_over_2m=5, homes_over_5m=None),
        filter_json={
            "minHomesOver1M": 100,
            "minHomesOver2M": 50,  # fails (only 5)
            "minHomesOver5M": 2,   # pending
        },
    )
    assert _factor(s, "Homes ≥$1M")["delta"] == 8.0
    assert _factor(s, "Homes ≥$2M")["delta"] == -10
    assert _factor(s, "Homes ≥$5M")["delta"] == 0


# ─── Score-range invariant ──────────────────────────────────────────────

def test_score_stays_in_0_to_100():
    # All penalties stacked → expect floor at 0
    s = score_for_parcel(
        _base_inputs(
            storage_permission="prohibited",
            in_flood_zone=True,
            in_wetland=True,
            homes_over_1m=0,
            homes_over_2m=0,
            homes_over_5m=0,
        ),
        filter_json={
            "minHomesOver1M": 100,
            "minHomesOver2M": 50,
            "minHomesOver5M": 5,
        },
    )
    assert 0 <= s.score <= 100
