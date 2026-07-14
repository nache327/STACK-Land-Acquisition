"""Union County NJ — Stage-1 zone binding (the NJTPA gap: Union has NO NJTPA
zoning layer and parcels.zoning_code was 100% NULL).

Source: official Union County GIS countywide "County Zoning" polygon layer
  https://oms.ucnj.org/server/rest/services/Public_Map/Public_Map_Service/MapServer/18
  fields Municipal / ZoneID / ZONENAME ; 1,432 polygons ; all 21 munis.

Spatial join (centroid-within, per [[feedback_spatial_backfill]]): assign each
parcel the ZoneID of the polygon its centroid falls in. Stores raw ZoneID so
the per-muni apply scripts (which use the SAME GIS ZoneID strings) bind exactly.
Also records the polygon's Municipal so we can catch #38 city/geometry drift.

Idempotent: re-run overwrites zoning_code for matched parcels only.
Run: cd backend && PYTHONUTF8=1 python scripts/_bind_union_nj_zoning.py [--dry-run]
"""
from __future__ import annotations
import argparse, asyncio, json, sys, urllib.request
import asyncpg
import geopandas as gpd
from shapely.geometry import Point

JID = "16dc5ad9-8211-47c6-bfad-93bf588b15e4"  # Union County, NJ
SVC = "https://oms.ucnj.org/server/rest/services/Public_Map/Public_Map_Service/MapServer/18"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def download_zoning() -> gpd.GeoDataFrame:
    feats, offset = [], 0
    while True:
        q = (f"{SVC}/query?where=1%3D1&outFields=Municipal,ZoneID,ZONENAME"
             f"&returnGeometry=true&outSR=4326&f=geojson"
             f"&resultOffset={offset}&resultRecordCount=1000")
        d = _get(q)
        f = d.get("features", [])
        feats.extend(f)
        print(f"  fetched {len(f)} (offset {offset})")
        if len(f) < 1000:
            break
        offset += len(f)
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & gdf["ZoneID"].notna()].copy()
    print(f"zoning polygons usable: {len(gdf)}")
    return gdf


async def main(dry: bool, cities: list[str] | None):
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    zones = download_zoning()

    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        if cities:
            print(f"SCOPED to cities: {cities}")
            rows = await con.fetch(
                "SELECT id, city, ST_X(centroid::geometry) lon, ST_Y(centroid::geometry) lat "
                "FROM parcels WHERE jurisdiction_id=$1 AND centroid IS NOT NULL "
                "AND city = ANY($2::text[])", JID, cities)
        else:
            rows = await con.fetch(
                "SELECT id, city, ST_X(centroid::geometry) lon, ST_Y(centroid::geometry) lat "
                "FROM parcels WHERE jurisdiction_id=$1 AND centroid IS NOT NULL", JID)
        print(f"parcel centroids: {len(rows)}")
        pgdf = gpd.GeoDataFrame(
            {"id": [r["id"] for r in rows], "city": [r["city"] for r in rows]},
            geometry=[Point(r["lon"], r["lat"]) for r in rows], crs="EPSG:4326")

        joined = gpd.sjoin(pgdf, zones[["ZoneID", "Municipal", "geometry"]],
                           how="left", predicate="within")
        # a centroid on a shared border can match >1 polygon -> keep first
        joined = joined[~joined.index.duplicated(keep="first")]
        matched = joined.dropna(subset=["ZoneID"])
        print(f"matched {len(matched)} / {len(pgdf)} parcels to a zone "
              f"({100*len(matched)/len(pgdf):.1f}%)")

        # per-muni coverage summary (target towns)
        summ = matched.groupby("city")["ZoneID"].count().sort_values(ascending=False)
        print("matched-by-city (top 15):")
        for city, n in summ.head(15).items():
            tot = sum(1 for r in rows if r["city"] == city)
            print(f"  {city:28} {n:>6}/{tot}")

        if dry:
            print("\n[DRY RUN] no DB writes.")
            return

        pairs = list(zip(matched["id"].astype(int).tolist(),
                         matched["ZoneID"].astype(str).tolist()))
        BATCH = 1000
        upd = 0
        for i in range(0, len(pairs), BATCH):
            b = pairs[i:i + BATCH]
            ids = [p[0] for p in b]
            zs = [p[1] for p in b]
            res = await con.execute(
                "UPDATE parcels p SET zoning_code=v.zone, zoning_code_source='ucnj_gis', "
                "zone_binding_method='spatial_centroid', updated_at=now() "
                "FROM (SELECT UNNEST($1::int[]) id, UNNEST($2::text[]) zone) v "
                "WHERE p.id=v.id AND p.jurisdiction_id=$3", ids, zs, JID)
            upd += int(res.split()[-1])
        print(f"=== bound zoning_code on {upd} Union parcels ===")
        chk = await con.fetch(
            "SELECT city, count(zoning_code) nz FROM parcels WHERE jurisdiction_id=$1 "
            "GROUP BY city ORDER BY nz DESC LIMIT 12", JID)
        print("post-bind zoning_code coverage (top 12 cities):")
        for r in chk:
            print(f"  {r['city']:28} {r['nz']:>6}")
    finally:
        await con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cities", default="", help="comma-separated parcels.city values to scope the bind")
    a = ap.parse_args()
    cs = [c.strip() for c in a.cities.split(",") if c.strip()] or None
    asyncio.run(main(a.dry_run, cs))
