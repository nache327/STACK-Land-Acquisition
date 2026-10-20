"""Keep-market fields on garage-condo board cards (Phase B).

The keep_* columns are added to the dashboard's deal_prospect by a separate dashboard
migration that may land later, so the push must detect them and degrade gracefully.
No DB: asyncpg connections and the ParcelLogic session are faked."""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

from app.services import dashboard_push as dp


class FakeBoard:
    def __init__(self, columns=()):
        self.columns = list(columns)
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            wanted = set(args[0])
            return [{"column_name": c} for c in self.columns if c in wanted]
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "DELETE 0"

    def transaction(self):
        return _Tx()

    async def close(self):
        pass


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_upsert_sql_default_is_fact_columns_only():
    sql = dp._upsert_sql()
    assert "keep_lane" not in sql
    assert sql == dp._upsert_sql(dp._FACT_COLUMNS)


def test_upsert_sql_with_keep_columns():
    sql = dp._upsert_sql(dp._FACT_COLUMNS + dp._KEEP_COLUMNS)
    n = len(dp._FACT_COLUMNS) + len(dp._KEEP_COLUMNS)
    assert f"${n}" in sql and f"${n + 1}" not in sql
    assert "keep_price_low=EXCLUDED.keep_price_low" in sql


@pytest.mark.asyncio
async def test_board_keep_columns_detection_keeps_order():
    assert await dp._board_keep_columns(FakeBoard()) == []
    board = FakeBoard(["keep_velocity_flag", "keep_lane", "unrelated"])
    assert await dp._board_keep_columns(board) == ["keep_lane", "keep_velocity_flag"]


def test_apply_keep_only_for_lgc_and_both():
    keep = {"keep_lane": "core", "keep_price_low": 222, "keep_price_high": 321,
            "keep_velocity_flag": None}
    for asset in ("luxury_garage_condo", "both"):
        row = {"asset_type": asset}
        dp._apply_keep(row, keep)
        assert row["keep_lane"] == "core" and row["keep_price_high"] == 321
    row = {"asset_type": "self_storage"}
    dp._apply_keep(row, keep)
    assert all(row[c] is None for c in dp._KEEP_COLUMNS)
    row = {"asset_type": "luxury_garage_condo"}
    dp._apply_keep(row, None)
    assert all(row[c] is None for c in dp._KEEP_COLUMNS)


def _patch(monkeypatch, board, keep_rows):
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
        return keep_rows

    async def filters(db):
        return [SimpleNamespace(id=1, use_case_id=1)]

    def row_for(d, s, a):
        return {c: None for c in dp._FACT_COLUMNS} | {"parcel_id": d.parcel_id, "asset_type": a,
                                                      "use_verdict": "permitted",
                                                      "verdict_basis": "human-verified"}

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


def _inserts(board):
    return [(sql, args) for sql, args in board.executed if sql.startswith("INSERT INTO deal_prospect")]


_KEEP = {1: {"keep_lane": "edge_of_wealth", "keep_price_low": 356, "keep_price_high": 534,
             "keep_velocity_flag": None}}


@pytest.mark.asyncio
async def test_push_includes_keep_columns_when_board_has_them(monkeypatch):
    board = FakeBoard(dp._KEEP_COLUMNS)
    _patch(monkeypatch, board, _KEEP)
    await dp.run_push()
    (sql, args), = _inserts(board)
    assert "keep_lane" in sql and "keep_velocity_flag" in sql
    cols = dp._FACT_COLUMNS + dp._KEEP_COLUMNS
    assert args[cols.index("keep_lane")] == "edge_of_wealth"
    assert args[cols.index("keep_price_low")] == 356


@pytest.mark.asyncio
async def test_push_omits_keep_columns_on_unmigrated_board(monkeypatch):
    board = FakeBoard([])
    _patch(monkeypatch, board, _KEEP)
    result = await dp.run_push()
    (sql, args), = _inserts(board)
    assert "keep_" not in sql
    assert len(args) == len(dp._FACT_COLUMNS)
    assert result["synced"] == 1


@pytest.mark.asyncio
async def test_push_survives_keep_read_failure(monkeypatch):
    board = FakeBoard(dp._KEEP_COLUMNS)
    _patch(monkeypatch, board, {})

    async def boom(ids):
        raise RuntimeError("relation parcel_keep_metrics does not exist")

    monkeypatch.setattr(dp, "_keep_metrics", boom)
    await dp.run_push()
    (sql, args), = _inserts(board)
    cols = dp._FACT_COLUMNS + dp._KEEP_COLUMNS
    assert args[cols.index("keep_lane")] is None


# ── Tier / mix / competitors / margin (card strategy 2026-10-19) ─────────────

_OLD_KEEP = ["keep_lane", "keep_price_low", "keep_price_high", "keep_velocity_flag"]
_TIER_KEEP = ["keep_tier", "keep_tier_low", "keep_tier_high", "keep_mix",
              "keep_competitor_units_30", "keep_margin_pct"]
_LAND_KEEP = ["keep_land_psf", "keep_hard_psf", "keep_soft_psf", "keep_selling_pct",
              "keep_dev_fee_pct", "keep_margin_basis"]
_USABLE_KEEP = ["keep_gross_acres", "keep_usable_acres", "keep_existing_building",
                "keep_improvement_share", "keep_contingency_pct", "keep_flag"]


def test_keep_columns_include_tier_fields_in_order():
    assert dp._KEEP_COLUMNS == _OLD_KEEP + _TIER_KEEP + _LAND_KEEP + _USABLE_KEEP


def test_keep_sf_per_ac_is_never_pushed():
    # User-editable board column: the push must never write or overwrite it.
    assert "keep_sf_per_ac" not in dp._KEEP_COLUMNS
    assert "keep_sf_per_ac" not in dp._upsert_sql(dp._FACT_COLUMNS + dp._KEEP_COLUMNS)


def test_keep_fields_core_nj():
    f = dp._keep_fields({"keep_lane": "core", "owner_1m_share_20": 0.024,
                         "price_band_low": 222, "price_band_high": 321,
                         "velocity_flag": None, "competitor_units_30": 64,
                         "parcel_state": "NJ"})
    assert f["keep_tier"] == "tier_295_325"
    assert (f["keep_tier_low"], f["keep_tier_high"]) == (295, 325)
    assert f["keep_mix"] == "30/40/30"
    assert f["keep_competitor_units_30"] == 64
    # No listing price -> no land-aware margin, but the cost inputs are still shown.
    assert f["keep_margin_pct"] is None and f["keep_margin_basis"] == "no_price"
    assert f["keep_land_psf"] is None
    assert f["keep_hard_psf"] == 127.5 and f["keep_soft_psf"] == 23.33
    assert f["keep_selling_pct"] == 0.0159 and f["keep_dev_fee_pct"] == 0.05
    assert f["keep_price_low"] == 222
    # $3M on 6 ac -> land $33.33/SF; 310 x 0.9841 vs 193.375 all-in -> 58%
    f = dp._keep_fields({"keep_lane": "core", "owner_1m_share_20": 0.024,
                         "parcel_state": "NJ"}, sale_price=3_000_000, acres=6)
    assert f["keep_land_psf"] == 33.33 and f["keep_margin_basis"] == "listing"
    assert f["keep_margin_pct"] == 58


def test_keep_fields_fl_hard_factor_and_philadelphia():
    f = dp._keep_fields({"keep_lane": "core", "parcel_state": "FL"})
    assert f["keep_hard_psf"] == round(127.5 * 0.95, 2)
    f = dp._keep_fields({"keep_lane": "core", "parcel_state": "PA"}, city="PHILADELPHIA")
    assert f["keep_selling_pct"] == 0.02889


def test_keep_fields_growth_is_pass_and_unmigrated_row_is_null():
    f = dp._keep_fields({"keep_lane": "growth_corridor", "owner_1m_share_20": 0.002,
                         "parcel_state": "TN"})  # no competitor_units_30 key (pre-0059)
    assert f["keep_tier"] == "pass"
    assert f["keep_tier_low"] is None and f["keep_mix"] is None
    assert f["keep_margin_pct"] is None and f["keep_competitor_units_30"] is None
    f = dp._keep_fields({"keep_lane": None})
    assert all(v is None for v in f.values())


_KEEP_TIER = {1: dp._keep_fields({
    "keep_lane": "edge_of_wealth", "owner_1m_share_20": 0.05, "price_band_low": 356,
    "price_band_high": 534, "velocity_flag": None, "competitor_units_30": 120,
    "parcel_state": "NJ"})}


@pytest.mark.asyncio
async def test_push_includes_tier_columns_when_board_has_them(monkeypatch):
    board = FakeBoard(dp._KEEP_COLUMNS)
    _patch(monkeypatch, board, _KEEP_TIER)
    await dp.run_push()
    (sql, args), = _inserts(board)
    cols = dp._FACT_COLUMNS + dp._KEEP_COLUMNS
    assert "keep_mix=EXCLUDED.keep_mix" in sql
    assert args[cols.index("keep_tier")] == "tier_325_350"
    assert args[cols.index("keep_tier_low")] == 325
    assert args[cols.index("keep_tier_high")] == 350
    assert args[cols.index("keep_mix")] == "50/30/20"
    assert args[cols.index("keep_competitor_units_30")] == 120
    # The faked row has no sale_price -> no land-aware margin.
    assert args[cols.index("keep_margin_pct")] is None
    assert args[cols.index("keep_margin_basis")] == "no_price"


@pytest.mark.asyncio
async def test_push_margin_uses_the_cards_own_listing_price(monkeypatch):
    board = FakeBoard(dp._KEEP_COLUMNS)
    _patch(monkeypatch, board, _KEEP_TIER)
    base_row_for = dp._row_for

    def row_for(d, s, a):
        return base_row_for(d, s, a) | {"sale_price": 9_000_000.0, "acres": 6.0,
                                        "situs_city": "Bernards township"}

    monkeypatch.setattr(dp, "_row_for", row_for)
    await dp.run_push()
    (sql, args), = _inserts(board)
    cols = dp._FACT_COLUMNS + dp._KEEP_COLUMNS
    assert args[cols.index("keep_land_psf")] == 100.0
    assert args[cols.index("keep_margin_basis")] == "listing"
    assert args[cols.index("keep_margin_pct")] == 26  # 332.13 net vs 263.375 all-in
    assert args[cols.index("keep_hard_psf")] == 127.5
    assert args[cols.index("keep_dev_fee_pct")] == 0.05
    i = cols.index("keep_land_psf") + 1
    assert f"${i}::float8" in sql
    assert ", _tier" not in sql and "_state" not in sql and "keep_sf_per_ac" not in sql


@pytest.mark.asyncio
async def test_push_omits_tier_columns_on_board_with_only_phase_b_columns(monkeypatch):
    board = FakeBoard(_OLD_KEEP)
    _patch(monkeypatch, board, _KEEP_TIER)
    result = await dp.run_push()
    (sql, args), = _inserts(board)
    assert "keep_lane" in sql
    assert not any(c in sql for c in _TIER_KEEP + _LAND_KEEP + _USABLE_KEEP)
    assert len(args) == len(dp._FACT_COLUMNS) + len(_OLD_KEEP)
    assert result["synced"] == 1
