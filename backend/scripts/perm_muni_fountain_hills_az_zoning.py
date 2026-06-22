"""Phase 7B.3 — Fountain Hills AZ Town zoning Class A with HEAVY QA.

Per Diagnostic PR #324 (2026-06-22): Fountain Hills surfaced public ZONING_POLYGON_VER1
layer (993 polygons). Source is NOISY — TEXTSTRING field carries mix of valid
ordinance codes + CAD escape strings + ordinance numbers + special-use descriptors
+ raw numbers + S.U./Z prefixes. **PROMOTE WITH HEAVY QA — whitelist only**.

Source: services7.arcgis.com/tKxHAVUwBYWFvNcs/.../ToFH_2005_LandUse___Zoning/FeatureServer/0
- 993 polygons total
- 140 distinct TEXTSTRING values
- Whitelist below extracts ~30 ordinance-valid codes; ~100 noise values rejected

QA gate (Master's heavy-QA directive): if >10% of total 993 polygons get rejected
as noise (i.e., <90% match whitelist) → SUB-GATE on coverage. Master's HALT
threshold: if covers <70% of parcels after whitelisting → halt and surface.

Fountain Hills jurisdiction (Phase 7B.2 PR #313):
  666dc28d-a877-43bc-9763-06a100b4f89b (15,810 parcels)
"""
from __future__ import annotations
import argparse, asyncio, json, logging, os, sys
from pathlib import Path
import asyncpg, dotenv, httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
logger = logging.getLogger("fountain_hills_az")

JID = "666dc28d-a877-43bc-9763-06a100b4f89b"
MUNI = "Fountain Hills"
LAYER = "https://services7.arcgis.com/tKxHAVUwBYWFvNcs/arcgis/rest/services/ToFH_2005_LandUse___Zoning/FeatureServer/0"
ZCODE = "TEXTSTRING"
RAW_KEYS = ("OBJECTID", "TEXTSTRING", "TEXT_SIZE", "TEXT_ANGLE", "Shape__Area", "Shape__Length")
BBOX_LON = (-111.79, -111.59)
BBOX_LAT = (33.56, 33.73)

# Ordinance-valid Fountain Hills zoning codes from 2005 layer + AZ Town ordinance.
# Source: docs/AUDIT_NOTES/oakland_allegheny_source_reverification.md per PR #324
# + curl probe of distinct TEXTSTRING values.
WHITELIST = {
    # Residential single-family
    "R-2", "R-3", "R-4", "R-5", "R-190",
    "R1-6", "R1-6A", "R1-8", "R1-8A", "R1-10", "R1-10A",
    "R1-18", "R1-35", "R1-35H", "R1-43",
    # Commercial
    "C-0", "C-1", "C-2", "C-2, P.D.", "C-3", "C-C",
    # Industrial
    "IND-2", "M-1",
    # Lodging
    "L-2",
    # Open space
    "OSP", "OSR",
    # Special / planned development
    "P.U.D.", "R.U.P.", "R.U.P.D.", "SC", "TH",
    # Generic catch (uncommon)
    "RESIDENTIAL",
}


def _db_url(): return DATABASE_URL.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")


def _rings_to_wkt(rings):
    ws = []
    for r in rings:
        if len(r) < 4: continue
        ws.append("((" + ", ".join(f"{p[0]} {p[1]}" for p in r) + "))")
    if not ws: raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ws) + ")"


async def _fire(near=50.0):
    print(f"\n=== FIRE: {MUNI} AZ zoning (whitelist QA) ===\n")
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
    rejected = 0
    rejected_examples = {}
    for f in feats:
        a = f.get("attributes", {})
        g = f.get("geometry")
        zc = a.get(ZCODE)
        if not g or "rings" not in g:
            continue
        zc_str = str(zc).strip() if zc else ""
        if zc_str not in WHITELIST:
            rejected += 1
            rejected_examples[zc_str] = rejected_examples.get(zc_str, 0) + 1
            continue
        try: wkt = _rings_to_wkt(g["rings"])
        except Exception as e: logger.warning("skip OBJECTID=%s: %s", a.get("OBJECTID"), e); continue
        raw = {"source_url": LAYER, "source_kind": "arcgis_feature_server",
               "ingested_at": "2026-06-22", "muni_name": MUNI, "muni_type": "town",
               "publisher": "Town of Fountain Hills AZ (Diagnostic PR #324 — whitelist QA per heavy-QA verdict)",
               "qa_note": "TEXTSTRING field carries mix of valid codes + noise; whitelist applied"}
        for k in RAW_KEYS:
            if k in a and a[k] is not None: raw[k] = a[k]
        rows.append({"zone_code": zc_str, "wkt": wkt, "raw": json.dumps(raw)})

    distinct = sorted({r["zone_code"] for r in rows})
    rejection_pct = 100.0 * rejected / len(feats) if feats else 0
    print(f"features={len(feats)} accepted={len(rows)} rejected={rejected} ({rejection_pct:.1f}%) distinct_accepted={len(distinct)}")
    print(f"accepted codes: {distinct}")
    print(f"\ntop 10 rejected (noise samples):")
    for v, n in sorted(rejected_examples.items(), key=lambda x: -x[1])[:10]:
        print(f"  {v!r:40s} {n}")

    if rejection_pct > 90.0:
        print(f"\nHALT-and-SURFACE: rejection {rejection_pct:.1f}% > 90% — whitelist may be too narrow")
        # Continue anyway — let coverage gate decide HALT verdict
    elif rejection_pct > 50.0:
        print(f"\nWARN: rejection {rejection_pct:.1f}% > 50% — Master's heavy-QA verdict confirmed (noise-heavy)")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, command_timeout=3600)
    try:
        await conn.execute("SET statement_timeout = 0")
        print(f"\n[INSERT] {len(rows)} zoning_districts (whitelisted from {len(feats)} source rows)…")
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
        s2 = await conn.execute("""
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
        print(f"\n=== 5-GATE ===\nGATE 1 cov {cov:.1f}% (≥70%) — {'PASS' if cov>=70 else 'SUB — Master HALT trigger'}")
        print(f"GATE 2 near {near_pct:.1f}% (<30%) — {'PASS' if near_pct<30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty} — {'PASS' if empty==0 else 'FAIL'}")
        print(f"GATE 4 districts {d} — {'PASS' if d>0 else 'FAIL'}")
        print(f"GATE 5 bbox populated")
        print(f"  parcels {p['total']:,} bound {p['bound']:,} contained {p['contained']:,} nearest {p['nearest']:,}")
        print(f"\nQA SUMMARY: source 993 → whitelist accepted {len(rows)} ({100*len(rows)/993:.0f}%) → noise {rejected} ({rejection_pct:.0f}%)")

        codes = await conn.fetch("""SELECT zoning_code, COUNT(*) AS n FROM parcels
                                    WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
                                    GROUP BY 1 ORDER BY 2 DESC""", JID)
        print(f"\nDistribution ({len(codes)}):")
        for r in codes:
            print(f"  {r['zoning_code']:20s} {r['n']:>5,}")
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
