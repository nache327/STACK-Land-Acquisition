"""Stage-1 bind: NJTPA Zoning Atlas (082025) -> Passaic County parcels.zoning_code.

Replicates the proven Essex bind (scripts/_bind_essex_njtpa_atlas.py, branch
parcellogic/essex-nj-stage1-njtpa): region-wide Atlas MapServer (all 13 NJTPA counties
in one layer) with a `County` filter, centroid `within` sjoin (EPSG:4326), replace=false
(only NULL zoning_code written), provenance njtpa_atlas_082025.

Fields:  County | Jurisdic_1 (MCD/town) | Abbreviate (=ZoningCode) | Full_District_Name.
Overlay districts (Full_District_Name ILIKE '%overlay%') excluded from the base bind.

*** HELD: this is a PREP script. It DRY-RUNS by default (reports match% + a #38 per-town
    code check, NO writes). It writes ONLY when run with APPLY=1 in the env, and that apply
    is gated on (a) A's Essex distribution confirming suburban-NJ yields and (b) coordinator/
    Nache go. Do not set APPLY=1 without that greenlight. ***

Run (dry):    cd backend && PYTHONUTF8=1 python scripts/_bind_passaic_njtpa_atlas.py
Run (apply):  cd backend && APPLY=1 PYTHONUTF8=1 python scripts/_bind_passaic_njtpa_atlas.py
"""
from __future__ import annotations
import asyncio, collections, json, os, subprocess, sys, time, logging, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
from shapely.geometry import Point
import asyncpg
from scripts._db import get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("passaic_bind")

JID = "7a9ed95d-df89-4864-a203-f831a987b562"
COUNTY = "Passaic"
LAYER = "https://gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas_082025/MapServer/0"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PAGE = 2000

# Passaic suburban/wealthy towns for the per-town #38 spot-check (parcels.city spellings).
SPOTCHECK = ['Wayne township', 'North Haledon borough', 'Wanaque borough', 'Ringwood borough',
             'Pompton Lakes borough', 'Totowa borough', 'Woodland Park borough',
             'Little Falls township', 'Hawthorne borough', 'West Milford township',
             'Bloomingdale borough']


def _bad_code(code: str) -> bool:
    if not code or len(code) > 20:
        return True
    if code.upper() in ("NULL", "NONE"):
        return True
    if " TWP" in code.upper() or "TOWNSHIP" in code.upper():
        return True
    return False


def _curl_json(url: str) -> dict | None:
    try:
        out = subprocess.run(["curl", "-sL", "--max-time", "120", "-A", UA, url],
                             capture_output=True, timeout=150)
        if out.returncode != 0:
            log.warning("curl rc=%d: %s", out.returncode, out.stderr[:200])
            return None
        return json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        log.warning("curl/parse failed: %s", e)
        return None


def fetch_county_polygons() -> gpd.GeoDataFrame:
    feats, offset = [], 0
    while True:
        qs = urllib.parse.urlencode({
            "where": f"County='{COUNTY}'",
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
        raise RuntimeError(f"no {COUNTY} polygons returned")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    log.info("downloaded %d %s polygons", len(gdf), COUNTY)
    return gdf


async def apply_updates(con, pairs: list[tuple]) -> int:
    updated, B = 0, 1000
    for i in range(0, len(pairs), B):
        batch = pairs[i:i+B]
        ids = [int(pid) for pid, _ in batch]
        zones = [str(z) for _, z in batch]
        res = await con.execute(
            "UPDATE parcels AS p SET zoning_code=v.zone, "
            "zone_binding_method='njtpa_atlas_082025', zoning_code_source='njtpa', updated_at=now() "
            "FROM (SELECT UNNEST($1::bigint[]) AS id, UNNEST($2::text[]) AS zone) v "
            "WHERE p.id=v.id AND p.zoning_code IS NULL", ids, zones)
        updated += int(res.split()[-1])
    return updated


async def main():
    t0 = time.time()
    apply = bool(os.environ.get("APPLY"))
    mode = "APPLY (WRITES)" if apply else "DRY-RUN (no writes)"
    log.info("mode = %s", mode)

    zones = fetch_county_polygons()
    zones = zones[zones["Abbreviate"].notna()].copy()
    zones["Abbreviate"] = zones["Abbreviate"].astype(str).str.strip()
    zones["Jurisdic_1"] = zones["Jurisdic_1"].astype(str).str.strip()
    zones = zones[~zones["Abbreviate"].map(_bad_code)]
    fdn = zones["Full_District_Name"].fillna("").astype(str)
    base = zones[~fdn.str.contains("overlay", case=False)].copy()
    log.info("polygons: %d usable, %d base (overlays excluded)", len(zones), len(base))

    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        cen = await con.fetch(
            "SELECT id, ST_X(centroid::geometry) lon, ST_Y(centroid::geometry) lat, city "
            "FROM parcels WHERE jurisdiction_id=$1::uuid AND centroid IS NOT NULL "
            "AND zoning_code IS NULL", JID)
        log.info("loaded %d NULL-zoning parcel centroids", len(cen))
        if not cen:
            log.info("no NULL-zoning parcels — nothing to bind")
            return
        pgdf = gpd.GeoDataFrame(
            {"id": [r["id"] for r in cen], "city": [r["city"] for r in cen]},
            geometry=[Point(r["lon"], r["lat"]) for r in cen], crs="EPSG:4326")

        log.info("centroid-within sjoin (%d parcels x %d base polygons)…", len(pgdf), len(base))
        joined = gpd.sjoin(pgdf, base[["Abbreviate", "geometry"]], how="inner", predicate="within")
        joined = joined.drop_duplicates(subset="id")
        pairs = list(zip(joined["id"].tolist(), joined["Abbreviate"].tolist()))
        mrate = 100.0*len(pairs)/len(pgdf) if len(pgdf) else 0.0
        log.info("matched %d / %d parcels to a base zone (%.1f%%)", len(pairs), len(pgdf), mrate)

        # ---- report (both modes) ----
        print(f"\n=== Passaic NJTPA Atlas 082025 bind — {mode} ===")
        print(f"county centroid match rate: {len(pairs)}/{len(pgdf)} = {mrate:.1f}%")

        # per spot-check town: matched centroids + the Atlas district vocabulary (#38 check)
        joined_city = joined[["city", "Abbreviate"]].copy()
        matched_by_city = collections.Counter(joined_city["city"].tolist())
        total_by_city = collections.Counter(pgdf["city"].tolist())
        print("\n--- per-town centroid match + Atlas base-district codes (#38 spot-check) ---")
        for t in SPOTCHECK:
            m, tot = matched_by_city.get(t, 0), total_by_city.get(t, 0)
            pct = 100.0*m/tot if tot else 0.0
            print(f"\n  {t}: {m}/{tot} = {pct:.1f}% matched")
            codes = collections.Counter(joined_city[joined_city["city"] == t]["Abbreviate"].tolist())
            for code, n in codes.most_common(12):
                fdname = base[base["Abbreviate"] == code]["Full_District_Name"]
                nm = fdname.iloc[0] if len(fdname) else "?"
                print(f"      {code:10} x{n:<5} {nm}")

        # raw Atlas town spellings (to catch any parcels.city vs Jurisdic_1 mismatch)
        print("\n--- Atlas Jurisdic_1 town spellings present in Passaic (first 30) ---")
        for j in sorted(base["Jurisdic_1"].unique())[:30]:
            print(f"    {j}")

        if not apply:
            print("\n=== DRY-RUN complete — NO parcels written, NO grounding. HELD pending Essex + go. ===")
            return

        # ---- apply path (only with APPLY=1 + greenlight) ----
        updated = await apply_updates(con, pairs)
        log.info("=== UPDATED %d parcels ===", updated)
        tot = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid", JID)
        bnd = await con.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL", JID)
        print(f"\ncounty bound_pct: {bnd}/{tot} = {100.0*bnd/tot:.1f}%")
    finally:
        await con.close()
    log.info("elapsed %.1fs", time.time()-t0)


if __name__ == "__main__":
    asyncio.run(main())
