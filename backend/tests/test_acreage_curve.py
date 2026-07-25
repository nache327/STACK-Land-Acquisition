"""Acreage curve — peaked, then GRADUATED oversize penalty (2026-07-22 sweep,
graduated 2026-07-24).

History (why this shape):
  - Original: min(acres/30,1)*20 — a 160-ac parcel scored the SAME +20 as a
    30-ac one and was never penalized, so oversize parcels sorted "Excellent".
  - Sweep v1: peak +20 @ 2-8ac, decay to +5 @ 15ac, FLAT -15 above.
  - Sweep v2 (current): the flat penalty treated 16ac and 259ac identically,
    so a high-pop/wealth 33-ac parcel still read 80. Replaced with a graduated
    ramp (ACRE_OVERSIZE_SLOPE per acre past ACRE_MAX, floored at
    ACRE_OVERSIZE_FLOOR) PLUS OVERSIZE_SCORE_CAP so any parcel past the
    board's maxAcres gate can never read deal-grade on the card.

Pure Python over score_for_parcel — no DB. The vectors here are also the
backend half of the shared golden fixture that keeps
frontend/lib/compositeScore.ts in lock-step (see
tests/fixtures/score_golden_vectors.json and the vitest that reads it).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.buybox_scoring import (
    ACRE_EDGE,
    ACRE_MAX,
    ACRE_OVERSIZE_FLOOR,
    ACRE_OVERSIZE_SLOPE,
    ACRE_PEAK,
    OVERSIZE_SCORE_CAP,
    ParcelInputs,
    _acreage_delta,
    score_for_parcel,
    tier_for,
)


def _inputs(acres, permission="permitted"):
    return ParcelInputs(
        parcel_id=1, storage_permission=permission, acres=acres, aadt=None,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True,
    )


def _acre_factor(scored):
    return next((f for f in scored.factors if f["label"] == "Acres"), None)


def _oversize_delta(acres: float) -> float:
    """Expected graduated penalty, computed independently of the impl."""
    return round(max(ACRE_EDGE - (acres - ACRE_MAX) * ACRE_OVERSIZE_SLOPE,
                     ACRE_OVERSIZE_FLOOR), 1)


# ─── The curve itself ────────────────────────────────────────────────────

@pytest.mark.parametrize("acres,expected", [
    (0.5, round(0.5 / 2.0 * ACRE_PEAK, 1)),   # sub-sweet ramp
    (2.0, ACRE_PEAK),                          # plateau start
    (5.0, ACRE_PEAK),                          # plateau middle
    (8.0, ACRE_PEAK),                          # plateau end
    (15.0, ACRE_EDGE),                         # decay endpoint
    (16.0, 4.4),                               # barely over — barely dinged
    (20.0, 2.0),
    (33.0, -5.8),                              # Edison
    (100.0, -46.0),
    (160.0, ACRE_OVERSIZE_FLOOR),              # Skillman — floored
    (259.0, ACRE_OVERSIZE_FLOOR),              # Hillsborough — floored
])
def test_acreage_delta(acres, expected):
    assert _acreage_delta(acres) == expected


@pytest.mark.parametrize("acres", [15.01, 16.0, 20.0, 33.0, 50.0, 100.0, 160.0])
def test_oversize_matches_graduated_formula(acres):
    assert _acreage_delta(acres) == _oversize_delta(acres)


def test_oversize_is_graduated_not_a_cliff():
    """16ac and 259ac must NOT be penalized identically (the v1 defect)."""
    assert _acreage_delta(16.0) > _acreage_delta(33.0) > _acreage_delta(100.0)
    assert _acreage_delta(16.0) > 0             # barely over is barely dinged
    # Continuous at the gate: 15.01ac rounds to the same +5.0 as 15.0ac (no
    # cliff), and the ramp only becomes visible a fraction of an acre later.
    assert _acreage_delta(15.01) <= ACRE_EDGE
    assert _acreage_delta(17.0) < ACRE_EDGE


def test_decay_is_monotonic_between_8_and_15():
    prev = ACRE_PEAK + 1
    for a in [8.0, 10.0, 12.0, 14.0, 15.0]:
        d = _acreage_delta(a)
        assert d <= prev
        prev = d


def test_curve_is_continuous_at_the_gate():
    """No jump discontinuity crossing ACRE_MAX — 15.0 -> 15.01 is a small step."""
    assert abs(_acreage_delta(15.0) - _acreage_delta(15.01)) < 0.1


def test_penalty_is_floored():
    assert _acreage_delta(10_000.0) == ACRE_OVERSIZE_FLOOR


# ─── Behavior through score_for_parcel ───────────────────────────────────

def test_oversize_parcel_scores_below_sweet_spot():
    """The whole point: a 160-ac permitted parcel must NOT score like a 5-ac one."""
    big = score_for_parcel(_inputs(160.0))
    good = score_for_parcel(_inputs(5.0))
    assert big.score < good.score
    assert _acre_factor(big)["delta"] == ACRE_OVERSIZE_FLOOR
    assert "oversize" in _acre_factor(big)["reason"]


def test_sweet_spot_is_excellent():
    s = score_for_parcel(_inputs(4.0))
    # base 50 + permitted 30 + acres 20 = 100 → excellent
    assert s.score >= 80
    assert s.tier == "excellent"


@pytest.mark.parametrize("acres", [15.01, 16.0, 28.0, 33.0, 100.0, 160.0, 259.0])
def test_no_oversize_parcel_can_read_deal_grade(acres):
    """Display honesty: anything past the board's maxAcres gate must read <70
    on the card, even with every other signal maxed (permitted + listed +
    vacant + high traffic). This is OVERSIZE_SCORE_CAP's contract."""
    p = ParcelInputs(
        parcel_id=1, storage_permission="permitted", acres=acres, aadt=50_000,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True, listing_source="costar", listing_sale_price=100_000,
        hnw_households=9_000, pop_3mi=250_000,
    )
    s = score_for_parcel(p, {"listingScoreBoost": 15})
    assert s.score <= OVERSIZE_SCORE_CAP
    assert s.score < 70
    assert s.tier != "excellent"


def test_cap_does_not_touch_in_band_parcels():
    """A 4-ac parcel with everything going for it must still be able to hit 100."""
    p = ParcelInputs(
        parcel_id=1, storage_permission="permitted", acres=4.0, aadt=50_000,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True, listing_source="costar", listing_sale_price=100_000,
        pop_3mi=250_000,
    )
    s = score_for_parcel(p, {"listingScoreBoost": 15})
    assert s.score > OVERSIZE_SCORE_CAP
    assert s.tier == "excellent"


def test_cap_sits_below_the_digest_listed_floor():
    """Undocumented-but-load-bearing coupling: OVERSIZE_SCORE_CAP is one below
    daily_email._MIN_SCORE_LISTED, so the display cap also excludes oversize
    parcels from the listed digest/board. If either number moves, this fails
    loudly instead of silently changing what surfaces."""
    from app.workers.daily_email import _MIN_SCORE_LISTED
    assert OVERSIZE_SCORE_CAP < _MIN_SCORE_LISTED


# ─── Shared golden vectors (backend half of the mirror guard) ────────────

_FIXTURE = Path(__file__).parent / "fixtures" / "score_golden_vectors.json"


def test_golden_vectors_match_backend():
    """The same (inputs -> score) table is asserted by frontend vitest against
    compositeScore.ts. If the two formulas drift, one of the two suites fails.
    """
    vectors = json.loads(_FIXTURE.read_text())
    for v in vectors["vectors"]:
        i = v["input"]
        p = ParcelInputs(
            parcel_id=1,
            storage_permission=i.get("storage_permission"),
            acres=i.get("acres"),
            aadt=i.get("aadt"),
            in_flood_zone=i.get("in_flood_zone", False),
            in_wetland=i.get("in_wetland", False),
            has_structure=i.get("has_structure"),
            classification_source="human", confidence=0.95,
            human_reviewed=True, verdict_matched=True,
        )
        s = score_for_parcel(p)
        assert s.score == v["score"], f"{v['name']}: {s.score} != {v['score']}"
        assert s.tier == v["tier"], f"{v['name']}: {s.tier} != {v['tier']}"


def test_tier_boundaries():
    for score, tier in [(80, "excellent"), (79, "strong"), (60, "strong"),
                        (59, "decent"), (40, "decent"), (39, "weak"),
                        (20, "weak"), (19, "avoid"), (0, "avoid")]:
        assert tier_for(score) == tier
