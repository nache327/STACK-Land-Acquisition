"""Storage Needles digest gate — asserts _top_parcels_for_filter wires the
`storageVerdictMode` filter_json flag into the SQL gate + bound params.

Lightweight: a fake AsyncSession captures the (sql, params) of the candidate
query and returns no rows, so we verify the contract (gate clause present,
param bound correctly) without a live DB.
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
        # Row post-processing may choke on the empty fake result; we only
        # care about the captured execute() call for the candidate query.
        pass
    # The candidate query is the one carrying the storage gate + :lim.
    for sql, params in db.calls:
        if "storage_verdict_mode" in sql and "LIMIT :lim" in sql:
            return sql, params
    raise AssertionError("candidate query not captured")


def test_gate_clause_present_in_sql():
    sql, _ = _run({"requireListed": True, "storageVerdictMode": "only"})
    assert ":storage_verdict_mode" in sql
    assert "zum.self_storage::text IN ('permitted', 'conditional')" in sql
    assert "zum.human_reviewed = TRUE" in sql


def test_only_mode_binds_param():
    _, params = _run({"requireListed": True, "storageVerdictMode": "only"})
    assert params["storage_verdict_mode"] == "only"


def test_exclude_mode_binds_param():
    _, params = _run({"requireListed": True, "storageVerdictMode": "exclude"})
    assert params["storage_verdict_mode"] == "exclude"


def test_absent_mode_is_none_no_gate_effect():
    # No flag -> param is None -> the gate's first OR branch (IS NULL) passes
    # everything (current behavior preserved).
    _, params = _run({"requireListed": True})
    assert params["storage_verdict_mode"] is None
