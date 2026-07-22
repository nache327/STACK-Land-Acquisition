"""3-mile population floor digest gate — asserts _top_parcels_for_filter wires
the `minPop3mi` filter_json key into the SQL gate + bound params, and that it
never disturbs the frozen storage-needles substrings.

Same fake-session contract style as test_storage_needles_gate.py: capture the
candidate query's (sql, params) without a live DB.
"""
import asyncio
import types

from app.workers.daily_email import _top_parcels_for_filter


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


def test_gate_clause_present_and_cast():
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert ":min_pop_3mi" in sql
    # asyncpg needs the type; every reference must be CAST to INT.
    assert "CAST(:min_pop_3mi AS INT)" in sql
    assert ":min_pop_3mi IS NULL" not in sql  # bare/un-cast form forbidden
    # Missing measurement passes (surfaced, flagged), measured-below is dropped.
    assert "prm3.population IS NULL" in sql
    assert "prm3.population >= CAST(:min_pop_3mi AS INT)" in sql


def test_radial_join_present():
    sql, _ = _run({"requireListed": True, "minPop3mi": 30000})
    assert "parcel_radial_metrics prm3" in sql
    assert "prm3.radius_miles = 3.0" in sql
    assert "soft_pop_unmeasured" in sql


def test_value_binds():
    _, params = _run({"requireListed": True, "minPop3mi": 30000})
    assert params["min_pop_3mi"] == 30000


def test_absent_key_is_none_no_gate_effect():
    _, params = _run({"requireListed": True})
    assert params["min_pop_3mi"] is None


def test_frozen_storage_substrings_intact():
    # The pop gate must be purely additive — the storage-needles freeze holds.
    sql, _ = _run({"requireListed": True, "storageVerdictMode": "only", "minPop3mi": 30000})
    assert sql.count("CAST(:storage_verdict_mode AS TEXT)") == 3
    assert "zum.self_storage::text IN ('permitted', 'conditional')" in sql
    assert "zum.human_reviewed = TRUE" in sql
    assert "LIMIT :lim" in sql
