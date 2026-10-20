"""scripts/backfill_keep_usable.py + scripts/_repair_keep_acreage_2026_10_19.py — pure
parts (no DB, no network)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _repair_keep_acreage_2026_10_19 as rk  # noqa: E402
import backfill_keep_usable as bu  # noqa: E402


# ── value resolution ─────────────────────────────────────────────────────────

def test_resolve_values_raw_family_first():
    nj = {"IMPRVT_VAL": "115900", "LAND_VAL": "62100", "NET_VALUE": "178000"}
    assert bu.resolve_values(None, None, nj) == (115900.0, 178000.0, 62100.0)
    chester = {"LOT_ASSESS": "889800.0", "PROP_ASSESS": "2635800.0", "TOT_ASSESS": "3525600.0"}
    assert bu.resolve_values(None, None, chester)[:2] == (2635800.0, 3525600.0)
    # NY RPS: no improvement field -> total − land
    ny = {"LAND_AV": "115700.0", "TOTAL_AV": "193900.0"}
    assert bu.resolve_values(None, None, ny) == (78200.0, 193900.0, 115700.0)
    # CA: no total -> land + improvement
    ca = {"IMP_VAL": "13891335", "LAND_VALUE": "4452264"}
    assert bu.resolve_values(None, None, ca)[1] == 13891335 + 4452264


def test_resolve_values_never_mixes_bases_and_falls_back_to_columns():
    # A CT building value with no land/total of the same basis is not used ...
    ct_partial = {"Assessed_Building": "100.0"}
    assert bu.resolve_values(None, None, ct_partial) == (None, None, None)
    # ... and the parcel columns are the fallback.
    assert bu.resolve_values(250000, 1000000, ct_partial) == (250000.0, 1000000.0, None)
    assert bu.resolve_values(250000, None, None) == (None, None, None)  # MA/MD: no total
    assert bu.resolve_values(None, 1000, {}) == (None, None, None)
    # All-zero roll rows (exempt / unassessed) are unmeasured, not 0%.
    zero = {"IMPRVT_VAL": "0", "LAND_VAL": "0", "NET_VALUE": "0"}
    assert bu.resolve_values(None, None, zero) == (None, None, None)


def test_raw_keys_cover_every_family():
    for fam in bu.VALUE_FAMILIES:
        for k in fam:
            if k:
                assert f"'{k}', p.raw->'{k}'" in bu._RAW_SQL


# ── tiles + split ────────────────────────────────────────────────────────────

def test_tiles_for_bounds_and_envelope():
    t = bu.tiles_for_bounds(-75.61, 40.005, -75.59, 40.015, 0.02)
    assert sorted(t) == [(-3781, 2000), (-3780, 2000)]
    assert bu.tile_envelope(-3780, 2000, 0.02) == (-75.6, 40.0, -75.58, 40.02)
    assert len(bu.tiles_for_bounds(0.001, 0.001, 0.002, 0.002, 0.02)) == 1


def test_usable_split():
    s = bu.usable_split(10.0, 0.2, 0.3, 0.4)
    assert s == {"gross_acres": 10.0, "usable_acres": 6.0, "wetland_acres": 2.0,
                 "sfha_acres": 3.0}
    assert bu.usable_split(10.0, 0, 0, 1.2)["usable_acres"] == 0.0
    assert bu.usable_split(None, 0.1, 0.1, 0.1)["usable_acres"] is None


def test_parse_features_filters_sfha_zones_and_non_polygons():
    poly = mapping(box(0, 0, 1, 1))
    fc = {"features": [
        {"id": 1, "geometry": poly, "properties": {"FLD_ZONE": "AE"}},
        {"geometry": poly, "properties": {"OBJECTID": 2, "FLD_ZONE": "X"}},
        {"geometry": poly, "properties": {"OBJECTID": 3, "FLD_ZONE": "VE"}},
        {"geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}},
        {"geometry": None, "properties": {}},
    ]}
    assert [fid for fid, _ in bu.parse_features(fc, bu.LAYER_SFHA)] == ["1", "3"]
    assert [fid for fid, _ in bu.parse_features(fc, bu.LAYER_WETLAND)] == ["1", "2", "3"]


# ── measurement (synthetic squares near 40N, -75W) ───────────────────────────

def _sq(x0, y0, x1, y1):
    return mapping(box(-75.0 + x0, 40.0 + y0, -75.0 + x1, 40.0 + y1))


def test_measure_unions_overlap_not_double_counted():
    from shapely.geometry import shape

    parcel = bu.to_equal_area(shape(_sq(0, 0, 0.004, 0.004)))
    wet, sfha = bu.OverlayIndex(), bu.OverlayIndex()
    wet.add("w1", _sq(0, 0, 0.002, 0.004))       # left half
    sfha.add("f1", _sq(0.001, 0, 0.003, 0.004))  # middle half (overlaps 1/4)
    sfha.add("f1", _sq(0.001, 0, 0.003, 0.004))  # duplicate id across tiles: ignored
    fw, ff, fu = bu.measure(parcel, wet, sfha)
    assert fw == pytest.approx(0.5, abs=0.01)
    assert ff == pytest.approx(0.5, abs=0.01)
    assert fu == pytest.approx(0.75, abs=0.01)  # union, not 1.0
    assert len(sfha.geoms) == 1


def test_measure_no_overlays_and_outside_overlays():
    from shapely.geometry import shape

    parcel = bu.to_equal_area(shape(_sq(0, 0, 0.004, 0.004)))
    assert bu.measure(parcel, bu.OverlayIndex(), bu.OverlayIndex()) == (0.0, 0.0, 0.0)
    far = bu.OverlayIndex()
    far.add("x", _sq(0.1, 0.1, 0.2, 0.2))
    assert bu.measure(parcel, far, bu.OverlayIndex()) == (0.0, 0.0, 0.0)


def _row(pid, geom_json, acres, **kw):
    from shapely.geometry import shape

    return {"parcel_id": pid, "acres": acres, "wkb": shape(geom_json).wkb,
            "improvement_value": None, "assessed_value": None, "raw_vals": None} | kw


def test_compute_rows_measured_unmeasured_and_values():
    from shapely.geometry import shape

    p_json = _sq(0.0005, 0.0005, 0.0035, 0.0035)  # inside one 0.02° tile
    (tile,) = bu.tiles_for_bounds(*shape(p_json).bounds, 0.02)
    feats = {(bu.LAYER_WETLAND, tile): [("w", _sq(0, 0, 0.002, 0.004))],
             (bu.LAYER_SFHA, tile): []}
    rows = [
        _row(1, p_json, 4.0, raw_vals=json.dumps(
            {"IMPRVT_VAL": "300", "LAND_VAL": "700", "NET_VALUE": "1000"})),
        _row(2, p_json, None, improvement_value=10, assessed_value=1000),
        {"parcel_id": 3, "acres": 2.0, "wkb": None, "improvement_value": None,
         "assessed_value": None, "raw_vals": None},
    ]
    out = {r["parcel_id"]: r for r in bu.compute_rows(rows, feats, 0.02)}
    r1 = out[1]
    assert r1["measured"] and r1["gross_acres"] == 4.0
    assert r1["wetland_acres"] == pytest.approx(4.0 * 0.5, abs=0.05)
    assert r1["usable_acres"] == pytest.approx(2.0, abs=0.05)
    assert r1["sfha_acres"] == 0.0
    assert r1["improvement_share"] == pytest.approx(0.3) and r1["existing_building"] is True
    # gross from the geometry when parcels.acres is NULL
    assert out[2]["measured"] and out[2]["gross_acres"] > 0
    assert out[2]["existing_building"] is False
    # no geometry -> unmeasured, gross kept, usable NULL
    assert not out[3]["measured"] and out[3]["usable_acres"] is None
    assert out[3]["gross_acres"] == 2.0 and out[3]["improvement_share"] is None


def test_compute_rows_failed_tile_leaves_row_unmeasured():
    from shapely.geometry import shape

    p_json = _sq(0.0005, 0.0005, 0.0035, 0.0035)
    (tile,) = bu.tiles_for_bounds(*shape(p_json).bounds, 0.02)
    feats = {(bu.LAYER_WETLAND, tile): [], (bu.LAYER_SFHA, tile): None}  # SFHA fetch failed
    (r,) = bu.compute_rows([_row(1, p_json, 4.0)], feats, 0.02)
    assert r["measured"] is False and r["usable_acres"] is None


def test_update_sql_is_batched_and_keeps_old_values_when_unmeasured():
    assert "unnest($1::bigint[]" in bu._UPDATE_SQL
    assert "CASE WHEN v.measured THEN v.usable ELSE k.usable_acres END" in bu._UPDATE_SQL
    assert "usable_computed_at = CASE WHEN v.measured THEN now()" in bu._UPDATE_SQL
    assert "{todo}" in bu._ROWS_SQL.replace("{todo}", "{todo}")


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


class _Client:
    """Pages of 1000 then a short page; records the offsets requested."""

    def __init__(self, pages):
        self.pages = pages
        self.offsets = []

    async def get(self, url, params=None):
        self.offsets.append(params["resultOffset"])
        i = params["resultOffset"] // bu._PAGE
        return _Resp(self.pages[i] if i < len(self.pages) else {"features": []})


def _page(start, n, zone="AE"):
    poly = mapping(box(0, 0, 1, 1))
    return {"features": [{"geometry": poly, "properties": {"OBJECTID": start + i,
                                                           "FLD_ZONE": zone}}
                         for i in range(n)]}


def test_tile_fetcher_paginates_caches_and_reuses(tmp_path):
    f = bu.TileFetcher(tmp_path, 0.02, 2)
    client = _Client([_page(0, 1000), _page(1000, 3)])
    feats = asyncio.run(f.fetch(client, bu.LAYER_SFHA, (1, 2)))
    assert len(feats) == 1003 and client.offsets == [0, 1000]
    again = asyncio.run(f.fetch(_Client([]), bu.LAYER_SFHA, (1, 2)))
    assert len(again) == 1003 and f.stats["sfha_cache"] == 1
    offline = bu.TileFetcher(tmp_path, 0.02, 2, offline=True)
    assert asyncio.run(offline.fetch(_Client([]), bu.LAYER_WETLAND, (1, 2))) is None


def test_split_envelope():
    q = bu.split_envelope((0.0, 0.0, 2.0, 2.0))
    assert q == [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0), (0.0, 1.0, 1.0, 2.0),
                 (1.0, 1.0, 2.0, 2.0)]


def test_tile_fetcher_retries_a_failed_tile_as_quarters(tmp_path, monkeypatch):
    whole = bu.tile_envelope(1, 2, 0.02)

    class Flaky:
        async def get(self, url, params=None):
            env = tuple(float(v) for v in params["geometry"].split(","))
            if env == whole:
                raise RuntimeError("timeout")
            # every quarter returns the same polygon (id 7) plus its own (id by x0)
            poly = mapping(box(0, 0, 1, 1))
            return _Resp({"features": [
                {"geometry": poly, "properties": {"OBJECTID": 7, "FLD_ZONE": "AE"}},
                {"geometry": poly,
                 "properties": {"OBJECTID": f"{env[0]}_{env[1]}", "FLD_ZONE": "AE"}},
            ]})

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(bu.asyncio, "sleep", no_sleep)
    f = bu.TileFetcher(tmp_path, 0.02, 2)
    feats = asyncio.run(f.fetch(Flaky(), bu.LAYER_SFHA, (1, 2)))
    assert len(feats) == 5  # shared id 7 once + one per quarter
    assert f.stats["sfha_split"] == 1 and f.stats["sfha_failed"] == 0


def test_tile_fetcher_failure_is_none_and_not_cached(tmp_path, monkeypatch):
    class Boom:
        async def get(self, url, params=None):
            raise RuntimeError("503")

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(bu.asyncio, "sleep", no_sleep)
    f = bu.TileFetcher(tmp_path, 0.02, 2)
    assert asyncio.run(f.fetch(Boom(), bu.LAYER_WETLAND, (5, 5))) is None
    assert f.stats["nwi_failed"] == 1
    assert f.cached(bu.LAYER_WETLAND, (5, 5)) is None


# ── acreage repair (Allentown + NJ condo units) ──────────────────────────────

def test_sqft_read_as_sqm_ratio():
    assert rk.SQFT_AS_SQM_RATIO == pytest.approx(10.7639, abs=1e-3)
    assert rk.ratio_is_sqft_as_sqm(2129.926, 197.893)  # Allentown 125389500
    assert not rk.ratio_is_sqft_as_sqm(5.0, 5.1)
    assert not rk.ratio_is_sqft_as_sqm(5.0, 0)


def test_condo_base():
    assert rk.condo_base("0219_3652_1_C1433") == "0219_3652_1"
    assert rk.condo_base("1409_603_1_C22") == "1409_603_1"
    assert rk.condo_base("0219_3652_1") is None
    assert rk.condo_base("1408_50001_3.01") is None
    assert rk.condo_base("1412_1102_3_QFARM") is None
    assert rk.condo_base(None) is None


def _nj(pid, apn, acres, geom="g1", jid="j"):
    return {"id": pid, "apn": apn, "jid": jid, "city": "Fort Lee borough",
            "acres": acres, "geom_hash": geom, "has_keep": False}


def test_condo_groups_qualifier_shared_geometry_and_skips():
    rows = [
        # qualifier group: 3 units, distinct geometries, same lot acreage
        _nj(1, "0219_3652_1_C1433", 5.219, "a"), _nj(2, "0219_3652_1_C1523", 5.219, "b"),
        _nj(3, "0219_3652_1_C1585", 5.219, "c"),
        # mother lot (no qualifier, own geometry) is not a unit
        _nj(4, "0219_3652_1", 5.219, "m"),
        # shared-geometry group: lot-decimal units on one polygon
        _nj(5, "1408_50001_3.01", 9.5, "d"), _nj(6, "1408_50001_3.02", 9.5, "d"),
        # same APN twice on one geometry = a duplicate, not a condo
        _nj(7, "1500_1_1", 3.0, "e"), _nj(8, "1500_1_1", 3.0, "e"),
        # non-uniform acreage -> skipped
        _nj(9, "1409_603_1_C22", 3.9, "f"), _nj(10, "1409_603_1_C44", 1.6, "g"),
        # lone qualifier unit -> skipped
        _nj(11, "1412_7501_10_C0001", 1.6, "h"),
    ]
    groups, skipped = rk.condo_groups(rows)
    ids = {k: sorted(m["id"] for m in v) for k, v in groups.items()}
    assert ids == {"Q|j|0219_3652_1": [1, 2, 3], "G|j|d": [5, 6]}
    assert skipped == {"non_uniform_acres": 1, "single_unit": 1}
    assert rk.unit_acres(5.219, 3) == 1.74
    assert rk.lot_acres([{"acres": 5.219}, {"acres": 5.219}]) == 5.219
    assert rk.group_geo_acres([{"geo_acres": 0.02}, {"geo_acres": 0.05}, {}]) == 0.05
    assert rk.group_geo_acres([{}]) is None
    # Fort Lee: 100 units on 5.219 ac, unit footprints tiny -> share, NOT the footprint
    assert rk.unit_acres(5.219, 100, geo=0.03) == 0.052
    # never 0 (0 = "never measured" to the acres backfill)
    assert rk.unit_acres(0.03, 100) == 0.001
    # an inflated copied acreage whose share is still >= 1.5 is capped by the geometry
    assert rk.unit_acres(52700.0, 5, geo=1.2) == 0.24
    assert rk.unit_acres(9.0, 2, geo=None) == 4.5
    assert rk.unit_acres(9.5, 38) == 0.25


def test_read_backup_acres(tmp_path):
    p = tmp_path / "b.csv"
    rk._write_backup(p, [
        {"repair": "allentown_sqft_as_sqm", "id": 1, "apn": "A", "jid": "j", "city": "x",
         "old_acres": 10.0, "new_acres": 1.0},
        {"repair": "nj_condo_unit_qualifier", "id": 2, "apn": "B", "jid": "j", "city": "y",
         "old_acres": 5.219, "new_acres": 0.0},
    ], {2: {"parcel_id": 2}})
    assert rk.read_backup_acres(p) == {2: 5.219}


def test_condo_groups_are_per_jurisdiction():
    rows = [_nj(1, "0219_1_1_C1", 5.0, "a", jid="j1"), _nj(2, "0219_1_1_C2", 5.0, "b", jid="j2")]
    groups, skipped = rk.condo_groups(rows)
    assert groups == {} and skipped["single_unit"] == 2


def test_backup_csv_has_every_change(tmp_path):
    p = tmp_path / "b.csv"
    changes = [{"repair": "allentown_sqft_as_sqm", "id": 1, "apn": "A", "jid": "j",
                "city": "Allentown", "old_acres": 10.76, "new_acres": 1.0}]
    rk._write_backup(p, changes, {5: {"parcel_id": 5, "keep_lane": "core"}})
    text = p.read_text(encoding="utf-8").splitlines()
    assert text[0].startswith("repair,table,action,parcel_id")
    assert "allentown_sqft_as_sqm,parcels,update_acres,1,A,j,Allentown,10.76,1.0" in text[1]
    assert text[2].startswith("nj_condo_unit,parcel_keep_metrics,delete,5")
    assert '""keep_lane"": ""core""' in text[2]


def test_migration_0060_is_idempotent_and_linear():
    import importlib.util

    path = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0060_keep_usable_acres.py")
    spec = importlib.util.spec_from_file_location("m0060", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "0060" and m.down_revision == "0059"
    names = [c for c, _ in m._COLUMNS]
    for c in ("gross_acres", "usable_acres", "wetland_acres", "sfha_acres",
              "improvement_share", "existing_building"):
        assert c in names
    executed = []

    class _Op:
        def execute(self, sql):
            executed.append(sql)

    m.op = _Op()
    m.upgrade()
    assert executed and all("ADD COLUMN IF NOT EXISTS" in s for s in executed)
    assert dict(m._COLUMNS)["existing_building"] == "BOOLEAN"
    assert dict(m._COLUMNS)["usable_acres"] == "DOUBLE PRECISION"
