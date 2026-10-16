"""LGC lane: keep-market "Wealth depth" replaces "HNW depth" when measured (Phase B).

Storage scoring must be untouched: the storage SELECT renders without any reference to
parcel_keep_metrics, and keep inputs never move a storage score.
"""
from __future__ import annotations

from app.services.buybox_scoring import (
    LGC_HNW_FULL,
    ParcelInputs,
    _select_parcels_sql,
    score_for_parcel,
)
from app.services.use_verdicts import LGC_SLUG, SELF_STORAGE_SLUG, verdict_expr


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


def test_keep_measured_replaces_hnw_depth():
    s = score_for_parcel(_inputs(lane=LGC_SLUG, hnw_households=LGC_HNW_FULL,
                                 owner_1m_share_20=0.082, wealth_center_drive_min=30))
    f = _factor(s, "Wealth depth")
    assert f is not None
    assert f["delta"] == round((0.082 - 0.01) / 0.09 * 15, 1)
    assert f["reason"] == "8.2% of homes $1M+ within 20 min"
    assert _factor(s, "HNW depth") is None
    assert _factor(s, "Far from wealth") is None


def test_wealth_depth_caps_and_floors():
    hi = score_for_parcel(_inputs(lane=LGC_SLUG, owner_1m_share_20=0.4, wealth_center_drive_min=10))
    lo = score_for_parcel(_inputs(lane=LGC_SLUG, owner_1m_share_20=0.004, wealth_center_drive_min=10))
    assert _factor(hi, "Wealth depth")["delta"] == 15.0
    assert _factor(lo, "Wealth depth")["delta"] == 0.0


def test_far_from_wealth_penalty():
    s = score_for_parcel(_inputs(lane=LGC_SLUG, owner_1m_share_20=0.005,
                                 wealth_center_drive_min=57.4))
    f = _factor(s, "Far from wealth")
    assert f == {"label": "Far from wealth", "delta": -10.0,
                 "reason": "57 min to nearest wealthy ($700K+) area"}


def test_no_keep_row_falls_back_to_hnw_unchanged():
    with_keep_none = score_for_parcel(_inputs(lane=LGC_SLUG, hnw_households=LGC_HNW_FULL))
    f = _factor(with_keep_none, "HNW depth")
    assert f is not None and f["delta"] == 15.0
    assert _factor(with_keep_none, "Wealth depth") is None


def test_storage_lane_ignores_keep_inputs():
    base = score_for_parcel(_inputs(lane=SELF_STORAGE_SLUG))
    keep = score_for_parcel(_inputs(lane=SELF_STORAGE_SLUG, owner_1m_share_20=0.2,
                                    wealth_center_drive_min=90))
    assert base.score == keep.score and base.factors == keep.factors


def test_storage_select_never_touches_keep_table():
    ss = _select_parcels_sql(verdict_expr(SELF_STORAGE_SLUG))
    assert "parcel_keep_metrics" not in ss and "pkm." not in ss
    # Passing the storage slug explicitly renders the identical string.
    assert _select_parcels_sql(verdict_expr(SELF_STORAGE_SLUG), SELF_STORAGE_SLUG) == ss


def test_lgc_select_left_joins_keep_table():
    sql = _select_parcels_sql(verdict_expr(LGC_SLUG), LGC_SLUG)
    assert "LEFT JOIN parcel_keep_metrics pkm" in sql
    assert "pkm.owner_1m_share_20 AS owner_1m_share_20" in sql
    assert "pkm.wealth_center_drive_min AS wealth_center_drive_min" in sql
    assert sql.rstrip().endswith("WHERE p.jurisdiction_id = $1::uuid")


def test_refresh_script_is_field_complete_for_keep_inputs():
    """refresh_lgc_hotdeals_scores upserts the same score rows; it must carry the keep
    inputs or it would overwrite a Wealth-depth score with an HNW one."""
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import refresh_lgc_hotdeals_scores as r

    assert "LEFT JOIN parcel_keep_metrics pkm" in r._INPUTS_SQL
    row = {
        "parcel_id": 1, "storage_permission": "permitted", "acres": 4.0, "aadt": None,
        "in_flood_zone": False, "in_wetland": False, "has_structure": False,
        "homes_over_1m": None, "homes_over_2m": None, "homes_over_5m": None,
        "hnw_households": 100, "pop_3mi": None, "sqft_per_capita_3mi": None,
        "listing_source": None, "listing_sale_price": None, "listing_dom": None,
        "classification_source": "human", "verdict_confidence": 0.9, "human_reviewed": True,
        "overlay_tags": None, "owner_1m_share_20": 0.05, "wealth_center_drive_min": 60.0,
    }
    inp = r._inputs(row)
    assert inp.owner_1m_share_20 == 0.05 and inp.wealth_center_drive_min == 60.0
