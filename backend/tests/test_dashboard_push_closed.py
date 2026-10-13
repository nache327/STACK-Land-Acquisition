"""Passed/dead board cards are tombstoned, purged, and never re-pushed.

No DB: asyncpg connections and the ParcelLogic session are faked, so this pins
the ordering contract of run_push (read-back -> filter -> upsert -> purge)."""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

from app.services import dashboard_push as dp


class FakeConn:
    def __init__(self, fetch_rows=None):
        self.fetch_rows = fetch_rows or []
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql, *args):
        return self.fetch_rows

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "DELETE 2"

    async def executemany(self, sql, args):
        self.executed.append((sql, tuple(args)))

    def transaction(self):
        return _Tx()

    async def close(self):
        pass


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_sync_back_keeps_closed_tombstones(monkeypatch):
    board = FakeConn(fetch_rows=[{"parcel_id": 1, "status": "reviewing", "decided_at": None}])
    pl = FakeConn()

    async def fake_connect(dsn, **kw):
        return pl

    monkeypatch.setattr(dp.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(dp, "_pl_dsn", lambda: "postgresql://x")
    await dp._sync_dispositions_back(board)

    delete_sql, delete_args = next(e for e in pl.executed if e[0].startswith("DELETE"))
    assert "NOT (status = ANY($2::text[]))" in delete_sql
    assert delete_args == ([1], ["passed", "dead"])


@pytest.mark.asyncio
async def test_purge_reasserts_closed_status():
    board = FakeConn()
    assert await dp._purge_closed(board, set()) == 0
    assert board.executed == []

    assert await dp._purge_closed(board, {7, 9}) == 2
    sql, args = board.executed[0]
    assert sql.startswith("DELETE FROM deal_prospect")
    assert "status = ANY($2::text[])" in sql
    assert sorted(args[0]) == [7, 9] and args[1] == ["passed", "dead"]


def _patch_run_push(monkeypatch, board, parcel_ids, closed, synced_ok=True):
    class FakeDB:
        async def scalar(self, *a, **k):
            return "self_storage"

    @contextlib.asynccontextmanager
    async def session():
        yield FakeDB()

    deals = [SimpleNamespace(parcel_id=p) for p in parcel_ids]

    async def top(*a, **k):
        return deals

    async def supplement(db, ids):
        return {}

    async def connect(dsn, **kw):
        return board

    async def sync_back(conn):
        if not synced_ok:
            raise RuntimeError("board unreachable")
        return len(closed)

    async def closed_ids():
        return set(closed)

    async def no_delisted(conn):
        return 0

    async def filters(db):
        return [SimpleNamespace(id=1, use_case_id=1)]

    monkeypatch.setattr(dp, "_dashboard_dsn", lambda: "postgresql://board")
    monkeypatch.setattr(dp, "long_running_session_maker", session)
    monkeypatch.setattr(dp, "_dashboard_filters", filters)
    monkeypatch.setattr(dp, "_top_parcels_for_filter", top)
    monkeypatch.setattr(dp, "_supplement", supplement)
    monkeypatch.setattr(dp, "_row_for", lambda d, s, a: {c: None for c in dp._FACT_COLUMNS} | {"parcel_id": d.parcel_id})
    monkeypatch.setattr(dp.asyncpg, "connect", connect)
    monkeypatch.setattr(dp, "_sync_dispositions_back", sync_back)
    monkeypatch.setattr(dp, "_closed_parcel_ids", closed_ids)
    monkeypatch.setattr(dp, "_cleanup_delisted", no_delisted)


def _upserted(board):
    return [args[0] for sql, args in board.executed if sql.startswith("INSERT INTO deal_prospect")]


@pytest.mark.asyncio
async def test_closed_parcels_are_never_repushed_and_get_purged(monkeypatch):
    board = FakeConn()
    _patch_run_push(monkeypatch, board, parcel_ids=[1, 2, 3], closed=[2])
    result = await dp.run_push()

    assert _upserted(board) == [1, 3]
    purge = [e for e in board.executed if e[0].startswith("DELETE FROM deal_prospect")]
    assert purge and purge[0][1][0] == [2]
    assert result["synced"] == 2 and result["closed_purged"] == 2


@pytest.mark.asyncio
async def test_no_purge_when_read_back_fails(monkeypatch):
    """Without a fresh read-back, a card marked dead today isn't tombstoned yet —
    purging then would lose the decision, so the purge is skipped."""
    board = FakeConn()
    _patch_run_push(monkeypatch, board, parcel_ids=[1, 2], closed=[2], synced_ok=False)
    result = await dp.run_push()

    assert not [e for e in board.executed if e[0].startswith("DELETE FROM deal_prospect")]
    assert result["closed_purged"] == 0
