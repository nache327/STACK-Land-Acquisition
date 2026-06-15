"""Worth a Look noise gate — asserts _top_parcels_for_filter wires the
`requirePriced` filter_json flag into the SQL gate + bound params.

When requirePriced=true the candidate query must drop unpriced listings
(sale_price NULL/0) rather than surfacing them behind the no-price soft flag.
Lightweight fake session: capture the (sql, params) of the candidate query.
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
    f.daily_email_top_n = 10
    return f


def _run(filter_json):
    db = _FakeSession()
    try:
        asyncio.run(_top_parcels_for_filter(db, _filter(filter_json)))
    except Exception:
        pass
    for sql, params in db.calls:
        if "require_priced" in sql and "LIMIT :lim" in sql:
            return sql, params
    raise AssertionError("candidate query not captured")


def test_require_priced_clause_present():
    sql, _ = _run({"requireListed": True, "requirePriced": True})
    # The gate must drop unpriced listings.
    assert ":require_priced" in sql
    assert "lst.sale_price IS NOT NULL AND lst.sale_price > 0" in sql


def test_require_priced_param_true_when_set():
    _, params = _run({"requireListed": True, "requirePriced": True})
    assert params["require_priced"] is True


def test_require_priced_defaults_false():
    # Absent flag => no-price listings still pass (current Worth a Look behavior
    # until the flag is explicitly set), so the gate is a no-op.
    _, params = _run({"requireListed": True})
    assert params["require_priced"] is False
