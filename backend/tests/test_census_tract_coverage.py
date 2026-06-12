"""Regression: ensure_census_tracts must NOT short-circuit on mere presence.

discipline-catch #16: the bbox ST_Intersects count includes neighboring-county
tracts already loaded from other jurisdictions, so a target whose own tracts are
absent still tripped the old `if existing > 0: return` path (Westchester loaded
14/~223 tracts because 111 adjacent NYC/Bergen/Rockland tracts intersected its
bbox). The fix always fetches the full bbox set + upserts.
"""
import asyncio

import app.services.census as census


class _Res:
    def __init__(self, val):
        self._v = val

    def scalar(self):
        return self._v


class _FakeDB:
    """First execute() = the COUNT(*) of existing tracts; later = INSERT upserts."""
    def __init__(self, existing):
        self.existing = existing
        self.calls = 0
        self.inserts = 0

    async def execute(self, stmt, params=None):
        self.calls += 1
        if self.calls == 1:
            return _Res(self.existing)
        self.inserts += 1
        return _Res(None)

    async def flush(self):
        pass


_TRACTS = [
    {"geoid": "36119010100", "name": "T1", "population": 5000, "wkt": "POLYGON((0 0,0 1,1 1,1 0,0 0))"},
    {"geoid": "36119010200", "name": "T2", "population": 4000, "wkt": "POLYGON((1 1,1 2,2 2,2 1,1 1))"},
    {"geoid": "36119010300", "name": "T3", "population": 3000, "wkt": "POLYGON((2 2,2 3,3 3,3 2,2 2))"},
]


def test_no_shortcircuit_when_existing_present(monkeypatch):
    called = {}

    async def fake_fetch(bbox):
        called["fetched"] = True
        return _TRACTS

    monkeypatch.setattr(census, "_fetch_tracts_with_population", fake_fetch)
    db = _FakeDB(existing=111)  # neighboring-county tracts already cached
    n = asyncio.run(census.ensure_census_tracts((-74.0, 40.8, -73.4, 41.4), db))

    assert called.get("fetched") is True, "must fetch even when existing>0 (presence != completeness)"
    assert db.inserts == 3, "must upsert ALL fetched tracts, not short-circuit"
    assert n == 3


def test_empty_fetch_keeps_existing(monkeypatch):
    async def fake_fetch(bbox):
        return []

    monkeypatch.setattr(census, "_fetch_tracts_with_population", fake_fetch)
    db = _FakeDB(existing=42)
    n = asyncio.run(census.ensure_census_tracts((-74.0, 40.8, -73.4, 41.4), db))

    assert db.inserts == 0
    assert n == 42, "transient empty fetch must not regress a populated bbox to 0"
