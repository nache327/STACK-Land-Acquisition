"""Stage-1 bind: NJTPA Zoning Atlas (082025) -> Essex County parcels.zoning_code.

Systemic NJ binding source. The Atlas MapServer is region-wide (all 13 NJTPA
counties in ONE layer) with a `County` filter — newer than the per-county
NJTPA_Zoning FeatureServer layers in zoning_ingestion.py (which have no Essex).

Fields:  County | Jurisdic_1 (MCD/town) | Abbreviate (=ZoningCode) |
         Full_District_Name (long name).

Mechanism (proven spatial_join_zoning.py pattern): download Essex polygons
(geojson, outSR 4326, browser UA — Cloudflare UA-gated + intermittent 500s),
geopandas centroid `within` sjoin, batch-UPDATE parcels.zoning_code. Overlay
districts (Full_District_Name ILIKE '%overlay%') are EXCLUDED from the base
bind so a parcel is never coded to an overlay (CO/MU-2/MDO/R-5x) instead of its
base district. Provenance recorded: zone_binding_method='njtpa_atlas_082025',
zoning_code_source='njtpa'. replace=false semantics: only NULL zoning_code is
written (Newark's existing codes are preserved).

Run:  cd backend && PYTHONUTF8=1 python scripts/_bind_essex_njtpa_atlas.py
"""
from __future__ import annotations
import asyncio, json, os, subprocess, sys, time, logging, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
from shapely.geometry import Point, shape
import asyncpg
from scripts._db import get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("essex_bind")

JID = "67541a18-c599-423b-bf05-d68153af1e2f"
LAYER = "https://gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas_082025/MapServer/0"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PAGE = 2000

WEALTHY = ['Livingston township','Fairfield township','Montclair township','Millburn township',
           'West Caldwell township','Verona township','West Orange township','North Caldwell borough',
           'Roseland borough','Essex Fells borough']


def _bad_code(code: str) -> bool:
    if not code or len(code) > 20:
        return True
    if code.upper() in ("NULL", "NONE"):
        return True
    if " TWP" in code.upper() or "TOWNSHIP" in code.upper():  # junk like 'FAIRFIELD TWP'
        return True
    return False


def _curl_json(url: str) -> dict | None:
    """Fetch via curl (Cloudflare fingerprints httpx's TLS stack -> 403; curl passes)."""
    try:
        out = subprocess.run(
            ["curl", "-sL", "--max-time", "120", "-A", UA, url],
            capture_output=True, timeout=150)
        if out.returncode != 0:
            log.warning("curl rc=%d: %s", out.returncode, out.stderr[:200])
            return None
        return json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        log.warning("curl/parse failed: %s", e)
        return None


def fetch_essex_polygons() -> gpd.GeoDataFrame:
    feats = []
    offset = 0
    while True:
        qs = urllib.parse.urlencode({
            "where": "County='Essex'",
            "outFields": "Jurisdic_1,Abbreviate,Full_District_Name",
            "returnGeometry": "true", "outSR": "4326", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": PAGE,
        })
        url = f"{LAYER}/query?{qs}"
        data = None
        for attempt in range(4):
            data = _curl_json(url)
            if data is not None and "features" in data:
                break
            log.warning("fetch offset=%d attempt=%d retrying", offset, attempt)
            time.sleep(3)
        if data is None or "features" not in data:
            raise RuntimeError(f"NJTPA fetch failed at offset {offset}")
        page = data.get("features", [])
        feats.extend(page)
        log.info("  fetched %d (offset %d), total %d", len(page), offset, len(feats))
        if len(page) < PAGE:
            break
        offset += len(page)
    if not feats:
        raise RuntimeError("no Essex polygons returned")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    log.info("downloaded %d Essex polygons", len(gdf))
    return gdf


async def fetch_centroids(con) -> list[tuple]:
    rows = await con.fetch(
        "SELECT id, ST_X(centroid::geometry) lon, ST_Y(centroid::geometry) lat "
        "FROM parcels WHERE jurisdiction_id=$1::uuid AND centroid IS NOT NULL "
        "AND zoning_code IS NULL", JID)  # replace=false: only fill NULLs (preserve Newark)
    log.info("loaded %d NULL-zoning parcel centroids", len(rows))
    return rows


async def apply_updates(con, pairs: list[tuple]) -> int:
    updated = 0
    B = 1000
    for i in range(0, len(pairs), B):
        batch = pairs[i:i+B]
        ids = [int(pid) for pid, _ in batch]
        zones = [str(z) for _, z in batch]
        res = await con.execute(
            "UPDATE parcels AS p SET zoning_code=v.zone, "
            "zone_binding_method='njtpa_atlas_082025', zoning_code_source='njtpa', updated_at=now() "
            "FROM (SELECT UNNEST($1::bigint[]) AS id, UNNEST($2::text[]) AS zone) v "
            "WHERE p.id=v.id AND p.zoning_code IS NULL",
            ids, zones)
        updated += int(res.split()[-1])
        if (i // B) % 10 == 0:
            log.info("  updated %d / %d", updated, len(pairs))
    return updated


async def main():
    t0 = time.time()
    zones = fetch_essex_polygons()
    zones = zones[zones["Abbreviate"].notna()].copy()
    zones["Abbreviate"] = zones["Abbreviate"].astype(str).str.strip()
    zones = zones[~zones["Abbreviate"].map(_bad_code)]
    fdn = zones["Full_District_Name"].fillna("").astype(str)
    base = zones[~fdn.str.contains("overlay", case=False)].copy()
    log.info("polygons: %d total, %d base (overlays excluded from base bind)", len(zones), len(base))

    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        cen = await fetch_centroids(con)
        if not cen:
            log.info("no NULL-zoning parcels — nothing to bind")
            return
        pgdf = gpd.GeoDataFrame(
            {"id": [r["id"] for r in cen]},
            geometry=[Point(r["lon"], r["lat"]) for r in cen], crs="EPSG:4326")

        log.info("running centroid-within sjoin (%d parcels x %d base polygons)…", len(pgdf), len(base))
        joined = gpd.sjoin(pgdf, base[["Abbreviate", "geometry"]], how="inner", predicate="within")
        joined = joined.drop_duplicates(subset="id")  # a centroid in >1 base poly (topology) -> first
        pairs = list(zip(joined["id"].tolist(), joined["Abbreviate"].tolist()))
        mrate = 100.0*len(pairs)/len(pgdf) if pgdf.shape[0] else 0
        log.info("matched %d / %d parcels to a base zone (%.1f%%)", len(pairs), len(pgdf), mrate)

        if os.environ.get("DRY"):
            # dry: report match rate + per-town sample, DO NOT write
            import collections
            per = collections.Counter()
            id2city = {}
            crows = await con.fetch("SELECT id, city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=ANY($2::text[])", JID, WEALTHY)
            for r in crows: id2city[r["id"]] = r["city"]
            for pid, z in pairs:
                c = id2city.get(pid)
                if c: per[c] += 1
            print(f"\n=== DRY match rate: {len(pairs)}/{len(pgdf)} = {mrate:.1f}% (NO writes) ===")
            for t in WEALTHY:
                print(f"  {t}: {per.get(t,0)} centroids matched a base zone")
            return

        updated = await apply_updates(con, pairs)
        log.info("=== UPDATED %d parcels ===", updated)

        # report bound_pct overall + per wealthy town
        print("\n=== BIND RESULT (Essex, NJTPA Atlas 082025) ===")
        tot = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid", JID)
        bnd = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL", JID)
        print(f"county bound_pct: {bnd}/{tot} = {100.0*bnd/tot:.1f}%")
        print("\n--- per wealthy town (bound / total | wealth-ring bound) ---")
        for t in WEALTHY:
            r = await con.fetchrow("""
              SELECT count(*) tot,
                count(*) FILTER (WHERE zoning_code IS NOT NULL) bnd,
                count(*) FILTER (WHERE zoning_code IS NOT NULL AND acres>=1.5
                  AND id IN (SELECT parcel_id FROM parcel_ring_metrics WHERE drive_time_minutes=10
                    AND median_home_value>=475000 AND median_hhi>=100000)) wealth_bnd
              FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2""", JID, t)
            pct = 100.0*r['bnd']/r['tot'] if r['tot'] else 0
            print(f"  {t}: {r['bnd']}/{r['tot']} = {pct:.1f}%  | wealth-ring bound={r['wealth_bnd']}")
        print("\n--- sample bound wealthy-town parcels ---")
        smp = await con.fetch("""SELECT city, zoning_code, count(*) n FROM parcels
            WHERE jurisdiction_id=$1::uuid AND city = ANY($2::text[]) AND zoning_code IS NOT NULL
            GROUP BY city, zoning_code ORDER BY city, n DESC""", JID, ['Livingston township','Fairfield township'])
        for r in smp:
            print(f"  {r['city']} {r['zoning_code']}: {r['n']}")
    finally:
        await con.close()
    log.info("elapsed %.1fs", time.time()-t0)


if __name__ == "__main__":
    asyncio.run(main())
