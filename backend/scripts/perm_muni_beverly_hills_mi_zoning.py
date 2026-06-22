"""Phase 7E.3 — Beverly Hills MI city zoning Class A ingest.

Per Diagnostic 2026-06-22 re-verification (docs/AUDIT_NOTES/oakland_allegheny_
source_reverification.md): Beverly Hills MI publishes a live FeatureServer
that surfaced AFTER Lane A's prior 2026-06-19 probe missed it. Diagnostic
confirmed fresh + queryable.

Source: services5.arcgis.com/1PnnJue8khcujdxm/.../Zoning_Dissolved/FeatureServer/0
- 322 polygons
- Zoning field (12 distinct nonblank codes + 1 blank — filter blanks)
- Polygon geometry, fresh as of 2026-06-22

Beverly Hills jurisdiction (Phase 7E.2 PR #318):
  53edb548-7359-4e9d-9ff0-ec81fadb8c5d (4,174 parcels)
"""
from __future__ import annotations
import argparse, asyncio, json, logging, os, sys
from pathlib import Path
from typing import Any
import asyncpg, dotenv, httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
logger = logging.getLogger("beverly_hills_mi")

JID = "53edb548-7359-4e9d-9ff0-ec81fadb8c5d"
MUNI = "Beverly Hills"
LAYER = "https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0"
ZCODE = "Zoning"
RAW_KEYS = ("OBJECTID", "Zoning", "Shape__Area", "Shape__Length")
BBOX_LON = (-83.28, -83.20)
BBOX_LAT = (42.50, 42.54)


def _db_url(): return DATABASE_URL.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")


def _rings_to_wkt(rings):
    ws = []
    for r in rings:
        if len(r) < 4: continue
        ws.append("((" + ", ".join(f"{p[0]} {p[1]}" for p in r) + "))")
    if not ws: raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ws) + ")"


async def _fire(near=50.0):
    print(f"\n=== FIRE: {MUNI} MI zoning ===\n")
    async with httpx.AsyncClient(timeout=120.0) as client:
        feats = []
        offset = 0
        while True:
            r = await client.get(f"{LAYER}/query", params={
                "where": "1=1", "outFields": "*", "returnGeometry": "true",
                "outSR": 4326, "resultOffset": offset, "resultRecordCount": 1000,
                "f": "json", "orderByFields": "OBJECTID",
            })
            r.raise_for_status()
            b = r.json().get("features", [])
            feats.extend(b)
            logger.info("fetched %d (cum %d)", len(b), len(feats))
            if len(b) < 1000: break
            offset += 1000

    rows = []
    skipped = 0
    for f in feats:
        a = f.get("attributes", {})
        g = f.get("geometry")
        zc = a.get(ZCODE)
        if not g or "rings" not in g or not zc or not str(zc).strip():
            if not zc or not str(zc).strip(): skipped += 1
            continue
        try: wkt = _rings_to_wkt(g["rings"])
        except Exception as e: logger.warning("skip OBJECTID=%s: %s", a.get("OBJECTID"), e); continue
        raw = {"source_url": LAYER, "source_kind": "arcgis_feature_server",
               "ingested_at": "2026-06-22", "muni_name": MUNI, "muni_type": "village",
               "publisher": "Village of Beverly Hills MI (Diagnostic 2026-06-22 re-verified)"}
        for k in RAW_KEYS:
            if k in a and a[k] is not None: raw[k] = a[k]
        rows.append({"zone_code": str(zc).strip(), "wkt": wkt, "raw": json.dumps(raw)})

    distinct = sorted({r["zone_code"] for r in rows})
    print(f"features={len(feats)} rows={len(rows)} blank_skipped={skipped} distinct={len(distinct)}: {distinct}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, command_timeout=3600)
    try:
        await conn.execute("SET statement_timeout = 0")
        print(f"\n[INSERT] {len(rows)} zoning_districts…")
        for r in rows:
            await conn.execute(
                """INSERT INTO zoning_districts (jurisdiction_id, zone_code, zone_name, zone_class, geom, raw_attributes, source)
                   VALUES ($1::uuid, $2, $2, 'unknown'::zone_class_enum,
                       ST_Multi(ST_MakeValid(ST_GeomFromText($3, 4326))),
                       $4::jsonb, 'arcgis'::zone_source_enum)""",
                JID, r["zone_code"], r["wkt"], r["raw"],
            )
        print(f"[INSERT] {len(rows)} committed")

        s1 = await conn.execute("""
            UPDATE parcels target SET zone_class=sub.zone_class, zone_binding_method='contained',
                zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
            FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                  LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                           WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                             AND ST_Within(ST_Centroid(p.geom), zd.geom)
                           ORDER BY zd.id LIMIT 1) m
                  WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL) sub
            WHERE target.id = sub.parcel_id""", JID)
        print(f"[spatial] contained UPDATEd {int(s1.split()[-1])}")

        bl = f"nearest_{int(round(near))}m"
        s2 = await conn.execute(f"""
            UPDATE parcels target SET zone_class=sub.zone_class, zone_binding_method=$2,
                zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
            FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                  LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                           WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                             AND ST_DWithin(zd.geom::geography, ST_Centroid(p.geom)::geography, $3)
                           ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography) LIMIT 1) m
                  WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL AND p.zone_binding_method IS NULL) sub
            WHERE target.id = sub.parcel_id""", JID, bl, float(near))
        print(f"[spatial] {bl} UPDATEd {int(s2.split()[-1])}")

        ext = await conn.fetchrow("""SELECT ST_XMin(ST_Extent(geom)) AS minx, ST_YMin(ST_Extent(geom)) AS miny,
                                            ST_XMax(ST_Extent(geom)) AS maxx, ST_YMax(ST_Extent(geom)) AS maxy
                                     FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""", JID)
        bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
        if not (BBOX_LON[0] <= bbox[0] <= BBOX_LON[1] and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]):
            raise RuntimeError(f"bbox {bbox} outside envelope")
        await conn.execute("UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid", JID, json.dumps(bbox))
        print(f"\nbbox {bbox}")

        p = await conn.fetchrow("""SELECT COUNT(*) AS total,
                                          COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
                                          COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                                          COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
                                   FROM parcels WHERE jurisdiction_id=$1::uuid""", JID)
        d = await conn.fetchval("SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid", JID)
        empty = await conn.fetchval("SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)", JID)
        cov = 100.0 * p["bound"] / p["total"] if p["total"] else 0
        near_pct = 100.0 * p["nearest"] / p["total"] if p["total"] else 0
        print(f"\n=== 5-GATE ===\nGATE 1 cov {cov:.1f}% — {'PASS' if cov>=70 else 'SUB'}")
        print(f"GATE 2 near {near_pct:.1f}% — {'PASS' if near_pct<30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty} — {'PASS' if empty==0 else 'FAIL'}")
        print(f"GATE 4 districts {d} — {'PASS' if d>0 else 'FAIL'}")
        print(f"GATE 5 bbox populated")
        print(f"  parcels {p['total']:,} bound {p['bound']:,} contained {p['contained']:,} nearest {p['nearest']:,}")

        codes = await conn.fetch("""SELECT zoning_code, COUNT(*) AS n FROM parcels
                                    WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
                                    GROUP BY 1 ORDER BY 2 DESC""", JID)
        print(f"\nDistribution ({len(codes)}):")
        for r in codes:
            print(f"  {r['zoning_code']:15s} {r['n']:>5,}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--nearest-within-meters", type=float, default=50.0)
    a = p.parse_args()
    if not a.i_know_this_writes_to_prod:
        print("Refusing", file=sys.stderr); sys.exit(2)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_fire(near=a.nearest_within_meters)))
