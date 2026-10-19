"""scripts/precompute_keep_metrics.py — pure parts (no DB, no Mapbox)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import precompute_keep_metrics as pk  # noqa: E402
from app.models.parcel_keep_metric import ParcelKeepMetric  # noqa: E402


def test_table_columns_match_model():
    model_cols = {c.name for c in ParcelKeepMetric.__table__.columns} - {"computed_at"}
    assert set(pk.TABLE_COLUMNS) == model_cols


def test_candidate_sql_scope():
    sql = pk._CANDIDATES_SQL
    assert "IN ('permitted', 'unclear')" in sql
    assert "p.acres >= 1.5" in sql
    assert "ST_Within(p.centroid, ct.geom)" in sql
    assert "$1::uuid" in sql


def test_parcel_rows_assess_and_null_policy():
    cands = [
        {"parcel_id": 1, "geoid": "34021000100", "jurisdiction_id": "j", "lgc_verdict": "permitted"},
        {"parcel_id": 2, "geoid": None, "jurisdiction_id": "j", "lgc_verdict": "unclear"},
        {"parcel_id": 3, "geoid": "99999000100", "jurisdiction_id": "j", "lgc_verdict": "permitted"},
    ]
    tm = {
        "34021000100": {"hh_200k_20": 12516, "owner_1m_count_20": 900, "owner_1m_share_20": 0.024,
                        "seasonal_share_20": 0.01, "young_old_200k_ratio_20": 2.0,
                        "wealth_center_drive_min": 36.0, "wealth_center_km": 20.0,
                        "wealth_center_label": "x"},
        "99999000100": {"hh_200k_20": None, "owner_1m_count_20": None, "owner_1m_share_20": None,
                        "seasonal_share_20": None, "young_old_200k_ratio_20": None,
                        "wealth_center_drive_min": 60.0, "wealth_center_km": 50.0,
                        "wealth_center_label": "y"},
    }
    rows = pk._parcel_rows(cands, tm, {"34021": 247.0})
    r1, r2, r3 = rows
    assert (r1["keep_lane"], r1["price_band_low"], r1["price_band_high"]) == ("core", 222, 321)
    assert r2["keep_lane"] is None and r2["tract_source"] == "none"
    assert r3["keep_lane"] is None and r3["velocity_flag"] == "far_from_wealth"
    assert r3["county_home_ppsf"] is None


def test_parse_csv_row_types():
    r = {c: "" for c in pk.CSV_COLUMNS}
    r.update(parcel_id="42", owner_1m_share_20="0.024", price_band_low="222.0",
             keep_lane="core", tract_geoid="34021000100")
    t = pk._parse_csv_row(r)
    d = dict(zip(pk.TABLE_COLUMNS, t))
    assert d["parcel_id"] == 42 and d["price_band_low"] == 222
    assert d["owner_1m_share_20"] == 0.024 and d["keep_lane"] == "core"
    assert d["hh_200k_20"] is None


def test_unpopulated_tracts_use_parcel_centroid():
    acs = {"49049010212": {"B01003_001E": 5000}, "49049020100": {"B01003_001E": 0}}
    cands = [
        {"geoid": "49049010212", "t_lng": -111.85, "t_lat": 40.43, "p_lng": -111.80, "p_lat": 40.40},
        {"geoid": "49049980100", "t_lng": -112.04, "t_lat": 40.41, "p_lng": -111.95, "p_lat": 40.45},
        {"geoid": "49049980100", "t_lng": -112.04, "t_lat": 40.41, "p_lng": -111.97, "p_lat": 40.47},
        {"geoid": "49049020100", "t_lng": -112.00, "t_lat": 40.00, "p_lng": -111.90, "p_lat": 40.10},
    ]
    pts = pk._tract_origins(cands, acs)
    assert pts["49049010212"] == (-111.85, 40.43)          # populated: tract centroid
    assert pts["49049980100"] == pytest.approx((-111.96, 40.46))  # special-use: parcel mean
    assert pts["49049020100"] == (-111.90, 40.10)          # zero population: parcel mean


def test_load_upsert_never_writes_unknown_parcels():
    assert "JOIN parcels p ON p.id = s.parcel_id" in pk._LOAD_UPSERT
    assert "ON CONFLICT (parcel_id) DO UPDATE" in pk._LOAD_UPSERT


def test_parcel_rows_competitor_units_from_tract_point():
    from app.services.keep_market import SupplyCampus

    camps = [SupplyCampus("Near", 40.05, -74.60, 91), SupplyCampus("Far", 42.0, -74.6, 500)]
    cands = [
        {"parcel_id": 1, "geoid": "34021000100", "t_lat": 40.0, "t_lng": -74.6,
         "p_lat": 45.0, "p_lng": -74.6, "jurisdiction_id": "j", "lgc_verdict": "permitted"},
        {"parcel_id": 2, "geoid": None, "p_lat": 41.99, "p_lng": -74.6,
         "jurisdiction_id": "j", "lgc_verdict": "unclear"},
        {"parcel_id": 3, "geoid": None, "jurisdiction_id": "j", "lgc_verdict": "unclear"},
    ]
    rows = pk._parcel_rows(cands, {}, {}, camps)
    assert [r["competitor_units_30"] for r in rows] == [91, 500, None]
    # No campuses passed → column left NULL (and COALESCEd on load).
    assert all(r["competitor_units_30"] is None for r in pk._parcel_rows(cands, {}, {}))
    assert "COALESCE(EXCLUDED.competitor_units_30" in pk._LOAD_UPSERT
