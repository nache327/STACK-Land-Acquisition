"""3-mi population + dt=10 wealth gates: SOFT (flag, don't drop).

History. The population floor originally hard-dropped any parcel whose measured
3-mi population was below minPop3mi. The 2026-07-25 audit showed the persisted
number is a tract-centric approximation that disagrees with the area-weighted
figure the drawer's Saturation panel shows — so the hard drop was silently
removing real deals on the strength of a number the operator couldn't even see.
It is now a soft flag (the score still applies -20).

The wealth thresholds (minMedianHomeValue / minMedianHHI) had the opposite
problem: they were present on every seeded board filter and read by NOTHING on
the backend — only the client-side buy-box panel — so the product's defining
wealth gate was absent from the one path that hands parcels to a human. They are
now surfaced as soft flags too, deliberately NOT hard gates, because their input
(dt=10 tract-centroid rings, no TTL) is the known-suspect data; hard-gating on it
could drop a genuine needle. Harden after the ring repair.

Same fake-session contract style as test_storage_needles_gate.py: capture the
candidate query's (sql, params) without a live DB.
"""
import asyncio
import types

from app.workers.daily_email import _SOFT_FLAG_RULES, _top_parcels_for_filter


class _FakeResult:
    def mappings(self): return self
    def all(self): return []
    def __iter__(self): return iter([])


class _FakeSession:
    def __init__(self): self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), params or {}))
        return _FakeResult()


def _filter(filter_json):
    f = types.SimpleNamespace()
    f.id = "00000000-0000-0000-0000-000000000001"
    f.filter_json = filter_json
    f.daily_email_top_n = 20
    return f


def _run(filter_json):
    db = _FakeSession()
    try:
        asyncio.run(_top_parcels_for_filter(db, _filter(filter_json)))
    except Exception:
        pass
    for sql, params in db.calls:
        if "min_pop_3mi" in sql and "LIMIT :lim" in sql:
            return sql, params
    raise AssertionError("candidate query not captured")


# ── Population floor: HYSTERESIS BAND (drop clearly-below, flag the band) ──

def test_floor_is_never_a_step_function_at_the_threshold():
    """The regression this guards: hard-dropping at exactly the floor decides
    ~119k parcels (0.67%, those within 2% of 30k) by measurement noise, and a
    wrong drop is invisible. The predicate must key on the BAND edge, not the
    raw floor."""
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert "prm3.population >= CAST(:min_pop_3mi AS INT)" not in sql
    assert "prm3.population >= CAST(:pop_hard_floor AS INT)" in sql


def test_band_edges_are_computed_from_the_floor():
    _, params = _run({"requireListed": True, "minPop3mi": 30000})
    assert params["pop_hard_floor"] == 27000     # 30000 * (1 - 0.10)
    assert params["pop_soft_ceiling"] == 33000   # 30000 * (1 + 0.10)


def test_clearly_below_the_band_is_hard_dropped():
    """The point of re-hardening: genuinely rural parcels leave the board."""
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert "CAST(:pop_hard_floor AS INT)" in sql
    # ...and unmeasured still passes, never dropped
    assert "prm3.population IS NULL" in sql


def test_inside_the_band_is_flagged_not_dropped():
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert "soft_below_pop_floor" in sql
    assert "CAST(:pop_soft_ceiling AS INT)" in sql
    assert "soft_pop_unmeasured" in sql
    assert ":min_pop_3mi IS NULL" not in sql  # bare/un-cast form forbidden


def test_no_floor_configured_means_no_drop_and_no_flag():
    _, params = _run({"requireListed": True})
    assert params["min_pop_3mi"] is None
    assert params["pop_hard_floor"] is None
    assert params["pop_soft_ceiling"] is None


def test_radial_join_present():
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert "parcel_radial_metrics prm3" in sql
    assert "prm3.radius_miles = 3.0" in sql


def test_value_binds():
    _, params = _run({"requireListed": True, "minPop3mi": 30000})
    assert params["min_pop_3mi"] == 30000


def test_absent_key_is_none_no_flag_effect():
    _, params = _run({"requireListed": True})
    assert params["min_pop_3mi"] is None


# ── Wealth gate: soft, and actually wired ────────────────────────────────

def test_wealth_thresholds_are_read_from_filter_json():
    """They were dead config for the entire life of the board."""
    _, params = _run({
        "requireListed": True,
        "minMedianHomeValue": 475000,
        "minMedianHHI": 100000,
    })
    assert params["min_home_value"] == 475000
    assert params["min_hhi"] == 100000


def test_wealth_ring_is_joined_at_drive_time_10():
    sql, _ = _run({"requireListed": True, "minMedianHomeValue": 475000})
    assert "parcel_ring_metrics prm10" in sql
    assert "prm10.drive_time_minutes = 10" in sql


def test_wealth_flags_present_and_soft():
    sql, _ = _run({
        "requireListed": True,
        "minMedianHomeValue": 475000,
        "minMedianHHI": 100000,
    })
    assert "soft_below_home_value" in sql
    assert "soft_below_hhi" in sql
    assert "soft_wealth_unmeasured" in sql
    # Soft means no WHERE-level rejection on the wealth columns.
    assert "prm10.median_home_value >= CAST(:min_home_value AS INT)" not in sql
    assert "prm10.median_hhi >= CAST(:min_hhi AS INT)" not in sql


def test_wealth_binds_are_cast():
    sql, _ = _run({"requireListed": True, "minMedianHomeValue": 475000, "minMedianHHI": 100000})
    assert "CAST(:min_home_value AS INT)" in sql
    assert "CAST(:min_hhi AS INT)" in sql


def test_absent_wealth_keys_are_none():
    _, params = _run({"requireListed": True})
    assert params["min_home_value"] is None
    assert params["min_hhi"] is None


def test_new_flags_are_registered_for_rendering():
    """A flag column that isn't in _SOFT_FLAG_RULES is computed and discarded —
    it would never reach the email or demote the deal to the Verify tier."""
    registered = {col for col, _emoji, _label in _SOFT_FLAG_RULES}
    for col in (
        "soft_below_pop_floor",
        "soft_below_home_value",
        "soft_below_hhi",
        "soft_wealth_unmeasured",
    ):
        assert col in registered, f"{col} computed in SQL but not rendered"


def test_triage_columns_selected_for_the_board_card():
    """The board card needs the wealth/demand context, not just score+price."""
    sql, _ = _run({"requireListed": True})
    for col in (
        "ring_median_home_value",
        "ring_median_hhi",
        "ring_hnw_households",
        "pop_3mi",
        "sqft_per_capita_3mi",
    ):
        assert col in sql


# ── The freeze still holds ───────────────────────────────────────────────

def test_frozen_storage_substrings_intact():
    sql, _ = _run({"requireListed": True, "storageVerdictMode": "only", "minPop3mi": 30000})
    assert sql.count("CAST(:storage_verdict_mode AS TEXT)") == 3
    assert "zum.self_storage::text IN ('permitted', 'conditional')" in sql
    assert "zum.human_reviewed = TRUE" in sql
    assert "LIMIT :lim" in sql
