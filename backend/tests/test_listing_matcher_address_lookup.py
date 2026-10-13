"""Tier 1/2 address lookup: exact and fallback run as separate statements but
return the same set the old single OR-query did (<=2 ids; 2 = ambiguous)."""
from __future__ import annotations

import uuid

import pytest

from app.services import listing_matcher as lm


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeDB:
    def __init__(self, exact, fallback):
        self.exact, self.fallback = exact, fallback
        self.statements: list[str] = []

    async def execute(self, stmt):
        sql = str(stmt)
        self.statements.append(sql)
        return FakeResult(self.fallback if "IS NULL" in sql else self.exact)


JID = uuid.uuid4()


@pytest.mark.asyncio
async def test_neither_statement_ors_the_two_paths():
    db = FakeDB(exact=[(1,)], fallback=[])
    await lm._parcels_by_address(db, JID, "1 main street")
    assert len(db.statements) == 2
    assert all(" OR " not in s.upper().replace("\n", " ") for s in db.statements)


@pytest.mark.asyncio
async def test_two_exact_hits_skip_the_fallback():
    db = FakeDB(exact=[(1,), (2,)], fallback=[(3,)])
    assert await lm._parcels_by_address(db, JID, "1 main street") == [(1,), (2,)]
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_exact_plus_fallback_hit_stays_ambiguous():
    db = FakeDB(exact=[(1,)], fallback=[(3,)])
    assert await lm._parcels_by_address(db, JID, "1 main street") == [(1,), (3,)]


@pytest.mark.asyncio
async def test_fallback_alone_still_matches_unbackfilled_parcels():
    db = FakeDB(exact=[], fallback=[(3,)])
    assert await lm._parcels_by_address(db, JID, "1 main street") == [(3,)]
