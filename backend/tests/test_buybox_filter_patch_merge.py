"""PATCH /buybox-filters/{id} must MERGE filter_json, never replace it.

Server-managed gate keys share the filter_json blob with the UI-editable knobs:
  - minPop3mi        the too-rural floor
  - maxAcres/minAcres the oversize gate
  - storageVerdictMode, requirePriced, maxPricePerAcre, maxTotalPrice
  - dashboardEnabled  enrols the filter in the board push AND, since the 2026-07-24
                      systemic fix, in auto_score_jurisdiction

The frontend's BuyBoxFilter type historically carried none of them, so the first
UI save built from DEFAULT_FILTER would have replaced the whole blob and silently
disarmed every gate — and by dropping dashboardEnabled, un-enrolled the filter
from scoring, re-creating the stale-board bug the sweep had just fixed. Latent
(no caller sent patch.filter yet) but one keystroke from live.

This test pins the merge semantics on the handler's own logic, no DB/app needed.
"""
from __future__ import annotations


def _merge(existing: dict, patch: dict) -> dict:
    """The exact expression update_filter uses (app/api/buybox.py)."""
    merged = {**(existing or {}), **patch}
    return {k: v for k, v in merged.items() if v is not None}


SEEDED_BOARD_FILTER = {
    "storageVerdictMode": "exclude",
    "minAcres": 1.5,
    "maxAcres": 15,
    "minPop3mi": 30000,
    "dashboardEnabled": True,
    "minMedianHomeValue": 475000,
    "minMedianHHI": 100000,
    "listingScoreBoost": 15,
    "requireListed": True,
}

# What a UI save built from DEFAULT_FILTER looks like — note every server-managed
# key is absent.
UI_SAVE_FROM_DEFAULTS = {
    "driveTimeMinutes": 10,
    "minPopulation": 50000,
    "minMedianHHI": 100000,
    "minMedianHomeValue": 475000,
    "minHnwHouseholds": 4400,
    "matchLogic": "AND",
    "requireListed": True,
    "listingScoreBoost": 15,
    "sortListedFirst": False,
}


def test_ui_save_cannot_strip_the_gates():
    out = _merge(SEEDED_BOARD_FILTER, UI_SAVE_FROM_DEFAULTS)
    # The gates survive a save that never mentioned them.
    assert out["maxAcres"] == 15
    assert out["minAcres"] == 1.5
    assert out["minPop3mi"] == 30000
    assert out["storageVerdictMode"] == "exclude"


def test_ui_save_cannot_unenrol_the_board():
    """dashboardEnabled drives BOTH the board push and auto-scoring."""
    out = _merge(SEEDED_BOARD_FILTER, UI_SAVE_FROM_DEFAULTS)
    assert out["dashboardEnabled"] is True


def test_patch_still_updates_keys_it_does_send():
    out = _merge(SEEDED_BOARD_FILTER, {"maxAcres": 25, "requireListed": False})
    assert out["maxAcres"] == 25
    assert out["requireListed"] is False
    # ...and leaves the rest intact
    assert out["minPop3mi"] == 30000


def test_explicit_null_deletes_a_key():
    """The documented escape hatch for actually removing a gate."""
    out = _merge(SEEDED_BOARD_FILTER, {"maxAcres": None})
    assert "maxAcres" not in out
    assert out["minPop3mi"] == 30000


def test_merge_on_empty_existing_is_just_the_patch():
    out = _merge({}, {"maxAcres": 15})
    assert out == {"maxAcres": 15}


def test_handler_uses_merge_not_assignment():
    """Guard the handler source itself: a future refactor back to
    `f.filter_json = payload.filter_json` would silently reopen the hole."""
    import inspect

    from app.api import buybox

    src = inspect.getsource(buybox.update_filter)
    assert "merged = {**(f.filter_json or {}), **payload.filter_json}" in src
    assert "f.filter_json = payload.filter_json" not in src
