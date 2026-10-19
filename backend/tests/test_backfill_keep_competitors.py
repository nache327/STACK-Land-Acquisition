"""scripts/backfill_keep_competitors.py — pure parts (no DB)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import backfill_keep_competitors as bk  # noqa: E402
from app.services.keep_market import SupplyCampus  # noqa: E402


def test_point_prefers_tract_centroid_then_parcel():
    assert bk.point_for({"t_lat": 1.0, "t_lng": 2.0, "p_lat": 3.0, "p_lng": 4.0}) == (1.0, 2.0)
    assert bk.point_for({"t_lat": None, "t_lng": None, "p_lat": 3.0, "p_lng": 4.0}) == (3.0, 4.0)
    assert bk.point_for({"t_lat": None, "t_lng": None, "p_lat": None, "p_lng": None}) == (None, None)


def test_compute_and_batches():
    camps = [SupplyCampus("A", 40.05, -74.6, 10), SupplyCampus("B", 40.1, -74.6, 5)]
    rows = [
        {"parcel_id": 1, "t_lat": 40.0, "t_lng": -74.6, "p_lat": None, "p_lng": None},
        {"parcel_id": 2, "t_lat": None, "t_lng": None, "p_lat": 50.0, "p_lng": -74.6},
        {"parcel_id": 3, "t_lat": None, "t_lng": None, "p_lat": None, "p_lng": None},
    ]
    assert bk.compute(rows, camps) == [(1, 15), (2, 0), (3, None)]
    assert [len(b) for b in bk.batches(list(range(12)), 5)] == [5, 5, 2]


def test_update_sql_is_batched_and_idempotent():
    assert "unnest($1::bigint[], $2::int[])" in bk._UPDATE_SQL
    assert "IS DISTINCT FROM" in bk._UPDATE_SQL
