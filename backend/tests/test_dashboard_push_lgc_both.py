"""'both' cards backed by an unconfirmed storage row show the by-right LGC verdict."""
from app.services.dashboard_push import _promote_lgc_verdict


def test_unconfirmed_storage_both_card_takes_lgc_by_right():
    row = {"asset_type": "both", "use_verdict": "unclear"}
    _promote_lgc_verdict(row, "permitted")
    assert row["use_verdict"] == "permitted"


def test_null_storage_verdict_also_promoted():
    row = {"asset_type": "both", "use_verdict": None}
    _promote_lgc_verdict(row, "permitted")
    assert row["use_verdict"] == "permitted"


def test_viable_storage_verdict_is_kept():
    row = {"asset_type": "both", "use_verdict": "conditional"}
    _promote_lgc_verdict(row, "permitted")
    assert row["use_verdict"] == "conditional"


def test_single_lane_cards_untouched():
    for asset in ("self_storage", "luxury_garage_condo"):
        row = {"asset_type": asset, "use_verdict": "unclear"}
        _promote_lgc_verdict(row, "permitted")
        assert row["use_verdict"] == "unclear"


def test_non_viable_lgc_does_not_promote():
    row = {"asset_type": "both", "use_verdict": "unclear"}
    _promote_lgc_verdict(row, "prohibited")
    assert row["use_verdict"] == "unclear"
