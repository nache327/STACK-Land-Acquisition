"""Parity tests for ring-metric aggregation.

This is the load-bearing contract for the server-side precompute: server +
client must produce identical numbers from the same tract inputs, otherwise
a parcel scored server-side will flip its verdict the moment a user
re-computes on the client.

Every test here pins one historical bug-fix as a regression guard. The
fixtures are intentionally hand-crafted with simple arithmetic so the
expected outputs can be verified with a calculator. Don't replace them with
randomized fuzz data — the point is to lock in the exact math.
"""
from __future__ import annotations

import pytest

from app.services.ring_metrics_aggregation import (
    RingMetrics,
    TractData,
    compute_ring_metrics,
)


# ── Empty / degenerate inputs ────────────────────────────────────────────────


def test_empty_tract_list_zeroes_everything() -> None:
    out = compute_ring_metrics([])
    assert out == RingMetrics(
        total_population=0,
        hnw_households=0,
        weighted_median_hhi=0.0,
        weighted_median_home_value=0.0,
        tract_count=0,
    )


def test_all_tracts_zero_household_count_treated_as_invalid() -> None:
    """tract_count reflects raw input length, but every aggregate that requires
    valid (household_count > 0) tracts comes out 0. Mirrors `valid =
    tracts.filter(t => t.household_count > 0)` in the JS."""
    tracts = [
        TractData(household_count=0, population=100, median_hhi=50_000),
        TractData(household_count=None, population=50, median_hhi=60_000),
    ]
    out = compute_ring_metrics(tracts)
    assert out.total_population == 0
    assert out.hnw_households == 0
    assert out.weighted_median_hhi == 0.0
    assert out.weighted_median_home_value == 0.0
    assert out.tract_count == 2  # raw input length, not valid length


# ── total_population ─────────────────────────────────────────────────────────


def test_population_prefers_explicit_field_over_household_count() -> None:
    """Per the v5 fix: B01003_001E (population) is authoritative; household
    count is only a backwards-compat fallback for pre-v5 cached blobs."""
    tracts = [TractData(household_count=100, population=2500)]
    out = compute_ring_metrics(tracts)
    # Should NOT be 100 (the household_count). Should be 2500 (the population).
    assert out.total_population == 2500


def test_population_falls_back_to_household_count_when_missing() -> None:
    tracts = [TractData(household_count=400, population=None)]
    out = compute_ring_metrics(tracts)
    assert out.total_population == 400


def test_population_sums_across_tracts() -> None:
    tracts = [
        TractData(household_count=1, population=1500),
        TractData(household_count=1, population=2000),
        TractData(household_count=1, population=500),
    ]
    assert compute_ring_metrics(tracts).total_population == 4000


# ── HNW households (B19001_017E sum) ─────────────────────────────────────────


def test_hnw_is_actual_count_sum_not_binary_proxy() -> None:
    """v5 fix: HNW is `sum(households_over_200k)` per tract — not a binary
    threshold on the tract median. A tract with median $300K used to count
    its FULL household population as HNW, which over-counted by ~10×."""
    tracts = [
        TractData(household_count=500, median_hhi=300_000, households_over_200k=120),
        TractData(household_count=400, median_hhi=180_000, households_over_200k=35),
        TractData(household_count=300, median_hhi=80_000,  households_over_200k=5),
    ]
    out = compute_ring_metrics(tracts)
    assert out.hnw_households == 160  # 120 + 35 + 5


def test_hnw_missing_field_treated_as_zero() -> None:
    tracts = [
        TractData(household_count=100, households_over_200k=None),
        TractData(household_count=100, households_over_200k=20),
    ]
    assert compute_ring_metrics(tracts).hnw_households == 20


# ── Household-weighted means (the v2 bug-fix anchor test) ────────────────────


def test_weighted_median_hhi_uses_household_count_as_denominator_not_population() -> None:
    """v2 bug: the denominator was totalPopulation, deflating values by the
    average household size (~2.7 in NJ). A two-tract ring where Marlboro's
    $148K-HHI tracts showed ~$54K. We hard-code the correct expected output
    so any regression to a population-denominator divides by ~2.5x and the
    assertion fails loudly.
    """
    tracts = [
        # 100 households, $200K median, 270 people (2.7 person/HH)
        TractData(household_count=100, population=270, median_hhi=200_000.0),
        # 200 households, $80K median, 540 people
        TractData(household_count=200, population=540, median_hhi=80_000.0),
    ]
    out = compute_ring_metrics(tracts)
    # Correct (household-weighted):
    #   (100 * 200_000 + 200 * 80_000) / (100 + 200)
    #   = (20_000_000 + 16_000_000) / 300
    #   = 36_000_000 / 300
    #   = 120_000
    assert out.weighted_median_hhi == 120_000.0
    # The buggy (population-weighted) computation would have been:
    #   36_000_000 / (270 + 540) = 36_000_000 / 810 ≈ 44_444
    # which is what the v2 bug produced. Guard explicitly:
    assert out.weighted_median_hhi != pytest.approx(44_444, rel=0.05)


def test_weighted_median_home_value_same_shape() -> None:
    tracts = [
        TractData(household_count=50,  population=130, median_home_value=900_000.0),
        TractData(household_count=150, population=400, median_home_value=300_000.0),
    ]
    out = compute_ring_metrics(tracts)
    # (50 * 900_000 + 150 * 300_000) / 200
    #   = (45_000_000 + 45_000_000) / 200
    #   = 90_000_000 / 200
    #   = 450_000
    assert out.weighted_median_home_value == 450_000.0


def test_weighted_mean_skips_tracts_with_null_value_but_keeps_them_for_other_metrics() -> None:
    """If a tract has median_hhi=null but median_home_value=$500K, it's excluded
    from the HHI denominator but still contributes to home-value math and to
    total_population. Mirrors the per-metric filter chain in the JS."""
    tracts = [
        # Has both
        TractData(household_count=100, population=270, median_hhi=200_000, median_home_value=500_000),
        # Missing HHI; has home value
        TractData(household_count=100, population=270, median_hhi=None,    median_home_value=300_000),
    ]
    out = compute_ring_metrics(tracts)
    # HHI: only the first tract counts → (200_000 * 100) / 100 = 200_000
    assert out.weighted_median_hhi == 200_000.0
    # Home value: both count → (500_000 * 100 + 300_000 * 100) / 200 = 400_000
    assert out.weighted_median_home_value == 400_000.0
    # Population: both count
    assert out.total_population == 540


def test_all_null_for_a_metric_returns_zero_not_div_by_zero() -> None:
    tracts = [
        TractData(household_count=100, median_hhi=None, median_home_value=None),
        TractData(household_count=200, median_hhi=None, median_home_value=None),
    ]
    out = compute_ring_metrics(tracts)
    assert out.weighted_median_hhi == 0.0
    assert out.weighted_median_home_value == 0.0


# ── tract_count is raw length, not filtered length ──────────────────────────


def test_tract_count_includes_invalid_tracts() -> None:
    """The JS uses tracts.length (the raw input), not valid.length. This is
    surfaced in the dashboard's drawer as 'N tracts intersect' — it should
    reflect the true geometric intersection count even if some are
    zero-household."""
    tracts = [
        TractData(household_count=0, population=0),          # invalid
        TractData(household_count=100, median_hhi=80_000),   # valid
        TractData(household_count=None, population=None),    # invalid
    ]
    assert compute_ring_metrics(tracts).tract_count == 3
