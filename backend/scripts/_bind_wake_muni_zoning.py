"""Stage-1 bind: Wake County NC municipal zoning -> parcels.zoning_code (per wealth-center city).

Wake County zones only unincorporated land; each municipality zones its own. The shared Wake/
Raleigh ArcGIS service exposes one polygon layer per municipality:
  https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer
    layer 0 Raleigh (field ZONING) | 2 Apex (CLASS) | 3 Cary (CLASS) | 4 County | 5 Fuquay-Varina
    | 6 Garner | 7 Holly Springs | 8 Knightdale | 9 Morrisville | 10 Rolesville | 11 Wake Forest.

Binds each city's NULL-zoning parcels via centroid-within (EPSG:4326), write-once, provenance
zoning_code_source='wake_muni_gis'. DRY by default; --apply to write. Ring metrics already exist
(435k dt=10); this only fills zoning_code.

Targets this batch = the named wealth centers (Cary, Apex, North Raleigh). Extend TARGETS to add
more towns. #38: confirm codes vs each town's CURRENT UDO before grounding.

Run (dry):   python scripts/_bind_wake_muni_zoning.py
Run (apply): python scripts/_bind_wake_muni_zoning.py --apply
"""
from __future__ import annotations
import argparse, asyncio, json, subprocess, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).parent.parent))
import asyncpg
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from shapely.validation import make_valid
from scripts._db import get_sync_dsn

JID = "b05b7317-b412-492c-a56c-433d447d17bf"
SVC = "https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
PROV = "wake_muni_gis"
PAGE = 1000
# parcels.city -> (layer_id, code_field)
TARGETS = {
    "Cary":   (3, "CLASS"),
    "Apex":   (2, "CLASS"),
    "Raleigh":(0, "ZONING"),
}


def _bad(code):
    if not code:
        return True
    code = str(code).strip()
    return not code or len(code) > 20 or code.upper() in ("NULL", "NONE")


def _curl(url):
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
        path = tf.name
    subprocess.run(["curl", "-sL", "-A", UA, url, "-o", path], check=True, timeout=150)
    return json.load(open(path))


def download(layer, field):
    feats, off = [], 0
    while True:
        url = (f"{SVC}/{layer}/query?where={quote('1=1')}&outFields={field}"
               f"&orderByFields=OBJECTID&returnGeometry=true&outSR=4326"
               f"&resultOffset={off}&resultRecordCount={PAGE}&f=geojson")
        fc = _curl(url)
        page = fc.get("features", [])
        for f in page:
            g = f.get("geometry")
            if not g:
                continue
            try:
                geom = shape(g)
            except Exception:  # noqa: BLE001
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
            if geom.is_empty:
                continue
            feats.append((geom, f["properties"].get(field)))
        if len(page) < PAGE:
            break
        off += PAGE
    return feats


async def run(apply):
    con = await asyncpg.connect(get_sync_dsn(), timeout=180, statement_cache_size=0)
    await con.execute("SET statement_timeout=0")
    try:
        for city, (layer, field) in TARGETS.items():
            polys_data = download(layer, field)
            polys = [p[0] for p in polys_data]
            codes = [p[1] for p in polys_data]
            tree = STRtree(polys)
            rows = await con.fetch(
                "SELECT id, ST_X(centroid::geometry) lng, ST_Y(centroid::geometry) lat "
                "FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NULL "
                "AND centroid IS NOT NULL", JID, city)
            matched, updates, dist = 0, [], Counter()
            for r in rows:
                pt = Point(r["lng"], r["lat"])
                hit = None
                for idx in tree.query(pt):
                    if polys[idx].contains(pt):
                        hit = idx
                        break
                if hit is None or _bad(codes[hit]):
                    continue
                matched += 1
                code = str(codes[hit]).strip()
                dist[code] += 1
                updates.append((r["id"], code))
            pct = 100.0 * matched / len(rows) if rows else 0.0
            print(f"\n=== {city}: layer {layer} ({field}) — {len(polys)} polys; "
                  f"matched {matched}/{len(rows)} = {pct:.1f}% ===")
            print("  top codes:", dict(dist.most_common(15)))
            if apply and updates:
                B = 5000
                w = 0
                for i in range(0, len(updates), B):
                    b = updates[i:i+B]
                    res = await con.execute(
                        "UPDATE parcels AS p SET zoning_code=v.code, zoning_code_source=$3 "
                        "FROM unnest($1::bigint[], $2::text[]) AS v(id, code) "
                        "WHERE p.id=v.id AND p.zoning_code IS NULL",
                        [int(i2) for i2, _ in b], [c for _, c in b], PROV)
                    w += int(res.split()[-1])
                print(f"  [APPLY] wrote {w}")
        if apply:
            tot = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1", JID)
            bnd = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL", JID)
            print(f"\n[APPLY] Wake bound now {bnd}/{tot} = {100.0*bnd/tot:.1f}%")
        else:
            print("\n[DRY-RUN] no writes. Re-run with --apply.")
    finally:
        await con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.apply))


if __name__ == "__main__":
    main()
