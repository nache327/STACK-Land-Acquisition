"""Lane-aware demand factors (2026-07-22): HNW depth (LGC), saturation split
(storage only), and price-per-acre. Pure Python over score_for_parcel.
"""
from __future__ import annotations

from app.config import settings
from app.services.buybox_scoring import (
    LGC_HNW_FULL,
    ParcelInputs,
    SAT_OVERSUPPLIED_PENALTY,
    SAT_UNDERSERVED_BONUS,
    score_for_parcel,
)
from app.services.use_verdicts import LGC_SLUG, SELF_STORAGE_SLUG


def _inputs(**kw):
    base = dict(
        parcel_id=1, storage_permission="permitted", acres=4.0, aadt=None,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True,
    )
    base.update(kw)
    return ParcelInputs(**base)


def _factor(s, label):
    return next((f for f in s.factors if f["label"] == label), None)


# ─── LGC HNW depth ───────────────────────────────────────────────────────

def test_lgc_hnw_bonus_scales():
    s = score_for_parcel(_inputs(lane=LGC_SLUG, hnw_households=LGC_HNW_FULL))
    f = _factor(s, "HNW depth")
    assert f is not None and f["delta"] > 0


def test_hnw_only_applies_to_lgc_lane():
    s = score_for_parcel(_inputs(lane=SELF_STORAGE_SLUG, hnw_households=LGC_HNW_FULL))
    assert _factor(s, "HNW depth") is None


def test_hnw_absent_no_factor():
    s = score_for_parcel(_inputs(lane=LGC_SLUG, hnw_households=None))
    assert _factor(s, "HNW depth") is None


# ─── Saturation split (storage lane only) ────────────────────────────────

def test_storage_oversupplied_penalized():
    s = score_for_parcel(_inputs(
        lane=SELF_STORAGE_SLUG,
        sqft_per_capita_3mi=settings.saturation_threshold_high + 1,
    ))
    f = _factor(s, "Saturation")
    assert f is not None and f["delta"] == SAT_OVERSUPPLIED_PENALTY


def test_storage_underserved_rewarded():
    s = score_for_parcel(_inputs(
        lane=SELF_STORAGE_SLUG,
        sqft_per_capita_3mi=settings.saturation_threshold_low - 0.1,
    ))
    f = _factor(s, "Saturation")
    assert f is not None and f["delta"] == SAT_UNDERSERVED_BONUS


def test_lgc_neutral_to_saturation():
    s = score_for_parcel(_inputs(
        lane=LGC_SLUG,
        sqft_per_capita_3mi=settings.saturation_threshold_high + 5,
    ))
    assert _factor(s, "Saturation") is None


# ─── Price per acre ──────────────────────────────────────────────────────

def test_cheap_dirt_bonus():
    s = score_for_parcel(_inputs(acres=10.0, listing_sale_price=1_000_000))  # 100k/ac
    f = _factor(s, "$/acre")
    assert f is not None and f["delta"] == 8.0


def test_expensive_penalized():
    s = score_for_parcel(_inputs(acres=2.0, listing_sale_price=2_000_000))  # 1M/ac
    f = _factor(s, "$/acre")
    assert f is not None and f["delta"] == -15.0


def test_no_price_no_factor():
    s = score_for_parcel(_inputs(acres=4.0, listing_sale_price=None))
    assert _factor(s, "$/acre") is None


def test_default_lane_is_storage_no_hnw():
    # A ParcelInputs built without lane defaults to self_storage — the LGC HNW
    # factor must not fire (protects existing callers/tests).
    s = score_for_parcel(_inputs(hnw_households=LGC_HNW_FULL))
    assert _factor(s, "HNW depth") is None
