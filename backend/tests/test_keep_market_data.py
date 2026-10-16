"""Pure helpers behind scripts/precompute_keep_metrics.py (no network, no DB)."""
from __future__ import annotations

import math

import pytest

from app.services import keep_market_data as kmd


def test_aggregate_pool_area_weighted():
    a = {"B19001_017E": 1000, "B25075_001E": 2000, "B25075_025E": 100, "B25075_026E": 50,
         "B25075_027E": 50, "B25004_006E": 10, "B25001_001E": 2500,
         "B19037_052E": 300, "B19037_069E": 200}
    b = {"B19001_017E": 400, "B25075_001E": 1000, "B25075_025E": 0, "B25075_026E": 0,
         "B25075_027E": float("nan"), "B25004_006E": 0, "B25001_001E": 1200,
         "B19037_052E": 100, "B19037_069E": None}
    m = kmd.aggregate_pool([(1.0, a), (0.5, b)])
    assert m.hh_200k_20 == 1200
    assert m.owner_1m_count_20 == 200
    assert m.owner_1m_share_20 == pytest.approx(200 / 2500)
    assert m.seasonal_share_20 == pytest.approx(10 / 3100, abs=1e-5)
    assert m.young_old_200k_ratio_20 == pytest.approx(350 / 200)


def test_aggregate_pool_empty_is_unmeasured_not_zero():
    assert kmd.aggregate_pool([]) == kmd.PoolMetrics(None, None, None, None, None)


def test_aggregate_pool_zero_owner_units_gives_null_share():
    m = kmd.aggregate_pool([(1.0, {"B25075_001E": 0, "B19001_017E": 5})])
    assert m.owner_1m_share_20 is None and m.hh_200k_20 == 5


def test_cluster_labels_components():
    lab = kmd.cluster_labels(5, [(0, 1), (1, 2), (3, 4), (2, 2)])
    assert lab[0] == lab[1] == lab[2]
    assert lab[3] == lab[4] and lab[3] != lab[0]


def test_plan_matrix_batches_respects_coordinate_cap():
    origins = {f"g{i:03d}": ["C:a", "C:b", "C:c", "C:d", "C:e"] for i in range(50)}
    origins.update({f"h{i:03d}": ["C:x", "C:y", "C:z", "C:a", "C:b"] for i in range(7)})
    batches = kmd.plan_matrix_batches(origins)
    seen = []
    for o, d in batches:
        assert len(o) + len(d) <= kmd.MATRIX_MAX_COORDS
        for g in o:
            assert set(origins[g]) <= set(d)
        seen += o
    assert sorted(seen) == sorted(origins)
    assert len(batches) <= 4  # 57 origins packed ~20 per request


def test_plan_matrix_batches_skips_empty():
    assert kmd.plan_matrix_batches({"g": []}) == []


def test_pick_center_nearest_by_km_with_fallback():
    cands = [("C:1", 10.0), ("C:2", 12.0)]
    assert kmd.pick_center(cands, {"C:1": 30.0, "C:2": 20.0}) == ("C:1", 30.0, 10.0)
    assert kmd.pick_center(cands, {"C:1": None, "C:2": 20.0}) == ("C:2", 20.0, 12.0)
    assert kmd.pick_center(cands, {}) == ("C:1", None, 10.0)
    assert kmd.pick_center([], {}) == (None, None, None)


def _center(cid, kind, lat, lng):
    return kmd.WealthCenter(cid, kind, 3 if kind == "cluster" else 1, lat, lng, 1000, 1.2e6)


def test_wealth_center_index_uses_cluster_within_60km_else_fallback():
    centers = [_center("C:near", "cluster", 40.35, -74.66),   # Princeton-ish
               _center("S:single", "single", 40.20, -74.60)]
    idx = kmd.WealthCenterIndex(centers)
    near = idx.candidates(40.198, -74.572)                     # Robbinsville
    assert near[0][0] == "C:near" and near[0][1] < 60
    far = idx.candidates(28.43, -82.64)                         # Spring Hill FL
    assert far[0][0] == "S:single"


def test_wealth_center_labels():
    assert "cluster" in _center("C:34021", "cluster", 0, 0).label
    assert _center("S:12053", "single", 0, 0).label.startswith("FALLBACK")


def test_zhvi_loader_latest_full_year(tmp_path):
    months25 = [f"2025-{m:02d}-28" for m in range(1, 13)]
    months26 = [f"2026-{m:02d}-28" for m in range(1, 9)]
    header = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName", "State",
              "Metro", "StateCodeFIPS", "MunicipalCodeFIPS", *months25, *months26]
    rows = [
        ["1", "1", "Mercer County", "county", "NJ", "NJ", "", "34", "21",
         *["444600"] * 12, *["999999"] * 8],
        ["2", "2", "Empty County", "county", "XX", "XX", "", "1", "1", *[""] * 20],
    ]
    p = tmp_path / "zhvi.csv"
    p.write_text("\n".join(",".join(r) for r in [header, *rows]), encoding="utf-8")
    year, ppsf = kmd.load_zhvi_county_ppsf(p)
    assert year == 2025
    assert ppsf == {"34021": 247.0}


def test_scrub_drops_query_strings():
    e = RuntimeError("GET https://api.mapbox.com/x?access_token=SECRET failed")
    assert "SECRET" not in kmd._scrub(e)
    e2 = RuntimeError("https://api.census.gov/data?get=x&key=SECRET")
    assert "SECRET" not in kmd._scrub(e2)


def test_pool_for_isochrone_area_share():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    # Two adjacent tracts; an isochrone covering all of A and half of B.
    tr = gpd.GeoDataFrame({"GEOID": ["A", "B"]},
                          geometry=[box(-100.0, 40.0, -99.9, 40.1), box(-99.9, 40.0, -99.8, 40.1)],
                          crs=4326).to_crs(kmd.EQUAL_AREA_CRS)
    tr["tarea"] = tr.geometry.area
    acs = {"A": {"B25075_001E": 100, "B25075_025E": 10, "B25075_026E": 0, "B25075_027E": 0},
           "B": {"B25075_001E": 100, "B25075_025E": 0, "B25075_026E": 0, "B25075_027E": 0}}
    m = kmd.pool_for_isochrone(box(-100.0, 40.0, -99.85, 40.1), tr, acs)
    assert m.owner_1m_count_20 == 10
    assert m.owner_1m_share_20 == pytest.approx(10 / 150, rel=0.02)
    assert not math.isnan(m.owner_1m_share_20)
