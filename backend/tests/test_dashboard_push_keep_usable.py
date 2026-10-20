"""Usable acres, existing building, card flag and the unsynced-card keep refresh
(owner decision 2026-10-19). No DB: board + ParcelLogic connections are faked."""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

from app.services import dashboard_push as dp

_KEEP_ROW = {"keep_lane": "edge_of_wealth", "owner_1m_share_20": 0.05,
             "price_band_low": 356, "price_band_high": 450, "velocity_flag": None,
             "competitor_units_30": 10, "parcel_state": "NJ"}


def test_new_columns_and_board_owned_columns_never_pushed():
    for c in ("keep_gross_acres", "keep_usable_acres", "keep_existing_building",
              "keep_improvement_share", "keep_contingency_pct", "keep_flag"):
        assert c in dp._KEEP_COLUMNS
    sql = dp._upsert_sql(dp._FACT_COLUMNS + dp._KEEP_COLUMNS)
    for owned in ("keep_sf_per_ac", "keep_dev_fee_override", "keep_contingency_override"):
        assert owned in dp._BOARD_OWNED_KEEP_COLUMNS
        assert owned not in dp._KEEP_COLUMNS and owned not in sql
    i = dp._KEEP_COLUMNS.index("keep_usable_acres") + len(dp._FACT_COLUMNS) + 1
    assert f"${i}::float8" in sql


def test_land_psf_and_margin_use_usable_acres():
    gross = dp._keep_fields(_KEEP_ROW, sale_price=9_000_000, acres=6)
    usable = dp._keep_fields(_KEEP_ROW | {"usable_acres": 4.5, "gross_acres": 6.0},
                             sale_price=9_000_000, acres=6)
    assert gross["keep_land_psf"] == 100.0 and gross["keep_usable_acres"] is None
    assert usable["keep_land_psf"] == pytest.approx(9e6 / (4.5 * 15000), abs=0.01)
    assert usable["keep_margin_pct"] < gross["keep_margin_pct"]
    assert usable["keep_gross_acres"] == 6.0 and usable["keep_usable_acres"] == 4.5
    assert usable["keep_contingency_pct"] == 0.0
    assert usable["keep_hard_psf"] == 127.5  # excludes contingency


def test_gross_falls_back_to_metrics_row_when_card_has_no_acres():
    f = dp._keep_fields(_KEEP_ROW | {"usable_acres": 5.0, "gross_acres": 6.0},
                        sale_price=None, acres=None)
    assert f["keep_gross_acres"] == 6.0 and f["keep_margin_basis"] == "no_price"


def test_zero_usable_acres_is_no_usable_land_not_a_margin():
    f = dp._keep_fields(_KEEP_ROW | {"usable_acres": 0.0, "gross_acres": 6.0},
                        sale_price=3_000_000, acres=6)
    assert f["keep_land_psf"] is None and f["keep_margin_pct"] is None
    assert f["keep_margin_basis"] == "no_usable_land"


def test_existing_building_and_flags():
    f = dp._keep_fields(_KEEP_ROW | {"improvement_share": 0.61234, "existing_building": True},
                        sale_price=3_000_000, acres=6)
    assert f["keep_existing_building"] is True and f["keep_improvement_share"] == 0.6123
    assert f["keep_flag"] == "existing_building"
    # $18M on 6 ac at the top tier -> negative margin
    f = dp._keep_fields(_KEEP_ROW | {"existing_building": False}, sale_price=18_000_000, acres=6)
    assert f["keep_margin_pct"] < 0 and f["keep_flag"] == "negative_margin"
    # $0.5M on 6 ac -> land $5.6/SF -> verify
    f = dp._keep_fields(_KEEP_ROW, sale_price=500_000, acres=6)
    assert f["keep_flag"] == "verify"
    f = dp._keep_fields(_KEEP_ROW, sale_price=9_000_000, acres=6)
    assert f["keep_flag"] is None
    # unmeasured lane -> every keep field NULL, building fields included
    f = dp._keep_fields({"keep_lane": None, "existing_building": True, "improvement_share": 0.9})
    assert all(v is None for k, v in f.items() if k.startswith("keep_"))


def test_apply_keep_recomputes_with_usable_acres_from_the_card():
    keep = dp._keep_fields(_KEEP_ROW | {"usable_acres": 3.0, "gross_acres": 6.0})
    row = {"asset_type": "both", "sale_price": 9_000_000.0, "acres": 6.0,
           "situs_city": "Bernards township"}
    dp._apply_keep(row, keep)
    assert row["keep_land_psf"] == 200.0  # 9M / (3 × 15000)
    assert row["keep_usable_acres"] == 3.0 and row["keep_gross_acres"] == 6.0
    assert not any(k.startswith("_") for k in row)


# ── refresh_keep_fields_for_unsynced ─────────────────────────────────────────

class RefreshBoard:
    def __init__(self, columns, cards):
        self.columns = list(columns)
        self.cards = cards
        self.executed: list[tuple[str, tuple]] = []
        self.many: list[tuple[str, list]] = []
        self.card_query_args = None

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            wanted = set(args[0])
            return [{"column_name": c} for c in self.columns if c in wanted]
        if sql.startswith("SELECT parcel_id, sale_price, acres"):
            self.card_query_args = args
            statuses, assets, synced = args
            return [c for c in self.cards
                    if (c.get("status") or "new") in statuses
                    and c["asset_type"] in assets and c["parcel_id"] not in synced]
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "DELETE 0"

    async def executemany(self, sql, args):
        self.many.append((sql, list(args)))

    def transaction(self):
        return _Tx()

    async def close(self):
        pass


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _card(pid, **kw):
    return {"parcel_id": pid, "sale_price": 9_000_000, "acres": 6, "situs_city": None,
            "city": "Bernards township", "asset_type": "luxury_garage_condo",
            "status": "reviewing"} | kw


@pytest.mark.asyncio
async def test_refresh_updates_only_unsynced_open_lgc_cards(monkeypatch):
    board = RefreshBoard(dp._KEEP_COLUMNS, [
        _card(1), _card(2, status="watching"), _card(3)])
    seen = {}

    async def keep_metrics(ids):
        seen["ids"] = list(ids)
        return {1: dp._keep_fields(_KEEP_ROW | {"usable_acres": 4.5, "gross_acres": 6.0}),
                2: dp._keep_fields(_KEEP_ROW)}

    monkeypatch.setattr(dp, "_keep_metrics", keep_metrics)
    n = await dp.refresh_keep_fields_for_unsynced(board, [3], dp._KEEP_COLUMNS)
    assert n == 2 and seen["ids"] == [1, 2]
    statuses, assets, synced = board.card_query_args
    assert statuses == ["new", "reviewing", "watching"]
    assert assets == ["luxury_garage_condo", "both"] and synced == [3]
    (sql, args), = board.many
    assert sql.startswith("UPDATE deal_prospect SET keep_lane=$2")
    assert sql.endswith("WHERE parcel_id = $1")
    for owned in dp._BOARD_OWNED_KEEP_COLUMNS:
        assert owned not in sql
    assert "status" not in sql and "acres=" not in sql.replace("_acres=", "")
    cols = dp._KEEP_COLUMNS
    by_id = {a[0]: a for a in args}
    land = by_id[1][1 + cols.index("keep_land_psf")]
    assert land == pytest.approx(9e6 / (4.5 * 15000), abs=0.01)
    assert by_id[2][1 + cols.index("keep_land_psf")] == 100.0
    i = cols.index("keep_usable_acres") + 2
    assert f"keep_usable_acres=${i}::float8" in sql


@pytest.mark.asyncio
async def test_refresh_nulls_a_card_whose_keep_row_is_gone(monkeypatch):
    board = RefreshBoard(dp._KEEP_COLUMNS, [_card(7, status="new")])

    async def keep_metrics(ids):
        return {}  # e.g. an NJ condo unit whose keep row was deleted

    monkeypatch.setattr(dp, "_keep_metrics", keep_metrics)
    assert await dp.refresh_keep_fields_for_unsynced(board, [], dp._KEEP_COLUMNS) == 1
    (_sql, args), = board.many
    assert all(v is None for v in args[0][1:])


@pytest.mark.asyncio
async def test_refresh_only_writes_columns_the_board_has(monkeypatch):
    board = RefreshBoard(["keep_lane", "keep_margin_pct"], [_card(1)])

    async def keep_metrics(ids):
        return {1: dp._keep_fields(_KEEP_ROW)}

    monkeypatch.setattr(dp, "_keep_metrics", keep_metrics)
    n = await dp.refresh_keep_fields_for_unsynced(board, [], ["keep_lane", "keep_margin_pct"])
    assert n == 1
    (sql, args), = board.many
    assert sql == "UPDATE deal_prospect SET keep_lane=$2, keep_margin_pct=$3 WHERE parcel_id = $1"
    assert args[0][1] == "edge_of_wealth"


@pytest.mark.asyncio
async def test_refresh_noop_without_keep_columns_or_cards(monkeypatch):
    async def boom(ids):
        raise AssertionError("must not read keep metrics")

    monkeypatch.setattr(dp, "_keep_metrics", boom)
    assert await dp.refresh_keep_fields_for_unsynced(RefreshBoard([], [_card(1)]), [], []) == 0
    assert await dp.refresh_keep_fields_for_unsynced(
        RefreshBoard(dp._KEEP_COLUMNS, []), [], dp._KEEP_COLUMNS) == 0


@pytest.mark.asyncio
async def test_refresh_read_failure_never_nulls_cards(monkeypatch):
    board = RefreshBoard(dp._KEEP_COLUMNS, [_card(1)])

    async def boom(ids):
        raise RuntimeError("parcel_keep_metrics unreachable")

    monkeypatch.setattr(dp, "_keep_metrics", boom)
    with pytest.raises(RuntimeError):
        await dp.refresh_keep_fields_for_unsynced(board, [], dp._KEEP_COLUMNS)
    assert board.many == []


@pytest.mark.asyncio
async def test_run_push_refreshes_unsynced_cards_at_the_end(monkeypatch):
    # Parcel 1 is in today's sync; parcel 9 is an older open card the sync didn't carry.
    board = RefreshBoard(dp._KEEP_COLUMNS, [_card(1), _card(9, status="watching")])

    class FakeDB:
        async def scalar(self, *a, **k):
            return "luxury_garage_condo"

    @contextlib.asynccontextmanager
    async def session():
        yield FakeDB()

    async def top(*a, **k):
        return [SimpleNamespace(parcel_id=1, use_verdict="permitted")]

    async def supplement(db, ids):
        return {}

    async def connect(dsn, **kw):
        return board

    async def zero(*a, **k):
        return 0

    async def no_closed():
        return set()

    async def keep_metrics(ids):
        return {pid: dp._keep_fields(_KEEP_ROW | {"usable_acres": 3.0}) for pid in ids}

    async def filters(db):
        return [SimpleNamespace(id=1, use_case_id=1)]

    def row_for(d, s, a):
        return {c: None for c in dp._FACT_COLUMNS} | {"parcel_id": d.parcel_id, "asset_type": a}

    monkeypatch.setattr(dp, "_dashboard_dsn", lambda: "postgresql://board")
    monkeypatch.setattr(dp, "long_running_session_maker", session)
    monkeypatch.setattr(dp, "_dashboard_filters", filters)
    monkeypatch.setattr(dp, "_top_parcels_for_filter", top)
    monkeypatch.setattr(dp, "_supplement", supplement)
    monkeypatch.setattr(dp, "_row_for", row_for)
    monkeypatch.setattr(dp.asyncpg, "connect", connect)
    monkeypatch.setattr(dp, "_sync_dispositions_back", zero)
    monkeypatch.setattr(dp, "_closed_parcel_ids", no_closed)
    monkeypatch.setattr(dp, "_cleanup_delisted", zero)
    monkeypatch.setattr(dp, "_keep_metrics", keep_metrics)

    result = await dp.run_push()
    assert result["synced"] == 1 and result["keep_refreshed"] == 1
    (sql, args), = board.many
    assert [a[0] for a in args] == [9]
    assert args[0][1 + dp._KEEP_COLUMNS.index("keep_usable_acres")] == 3.0


@pytest.mark.asyncio
async def test_run_push_survives_refresh_failure(monkeypatch):
    board = RefreshBoard(dp._KEEP_COLUMNS, [])

    async def boom(*a, **k):
        raise RuntimeError("board hiccup")

    from tests import test_dashboard_push_keep as base

    base._patch(monkeypatch, board, {})
    monkeypatch.setattr(dp, "refresh_keep_fields_for_unsynced", boom)
    result = await dp.run_push()
    assert result["status"] == "ok" and result["keep_refreshed"] == 0
