"""Phase 7E.3 — Bloomfield Hills, MI city zoning Class A ingest.

Source: services9.arcgis.com/jGlVpYnGiHmSg9fR/.../Zoning_BloomfieldHills/FeatureServer/0
- 1,853 polygons (parcel-like — carries PIN + Zoning fields)
- Diagnostic PR #260 marked this the "best proof city" (direct PIN attribute join possible)

Bloomfield Hills jurisdiction (Phase 7E.2 PR #318):
  e914f6d4-9dfd-467a-a0a6-0e6b02c28691 (1,833 parcels)

Same pattern as Birmingham — spatial backfill via ST_Within. Direct PIN
attribute join could be faster (Diagnostic notes) but spatial is universal
and matches Stamford/Greenwich/Birmingham precedent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("bloomfield_hills_zoning")

BLOOMFIELD_HILLS_JID = "e914f6d4-9dfd-467a-a0a6-0e6b02c28691"
MUNI_NAME = "Bloomfield Hills"
LAYER_URL = "https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0"
ZONE_CODE_FIELD = "Zoning"
ZONE_NAME_FIELD = "Zoning"
RAW_PASSTHROUGH = (
    "OBJECTID", "CVTTAXCODE", "CVTTAXDESC", "PIN", "SITEADDRES",
    "SITECITY", "SITESTATE", "SITEZIP5", "STRUCTURE_", "Zoning",
)
ARCGIS_PAGE_SIZE = 1000

BBOX_LON_RANGE = (-83.28, -83.22)
BBOX_LAT_RANGE = (42.55, 42.60)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _fetch_features() -> list[dict[str, Any]]:
    features = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            r = await client.get(
                f"{LAYER_URL}/query",
                params={
                    "where": "1=1", "outFields": "*", "returnGeometry": "true",
                    "outSR": 4326, "resultOffset": offset,
                    "resultRecordCount": ARCGIS_PAGE_SIZE, "f": "json",
                    "orderByFields": "OBJECTID",
                },
            )
            r.raise_for_status()
            batch = r.json().get("features", [])
            features.extend(batch)
            logger.info("fetched %d (cum %d) offset=%d", len(batch), len(features), offset)
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _rings_to_wkt(rings):
    ring_wkts = []
    for r in rings:
        if len(r) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


def _build_rows(features):
    out = []
    for f in features:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            continue
        zone_code = attrs.get(ZONE_CODE_FIELD)
        if not zone_code or not str(zone_code).strip():
            continue
        raw = {
            "source_url": LAYER_URL,
            "source_kind": "arcgis_feature_server",
            "ingested_at": "2026-06-19",
            "muni_name": MUNI_NAME,
            "muni_type": "city",
            "publisher": "City of Bloomfield Hills MI (via services9 ArcGIS)",
            "note": "parcel-like source — carries PIN + Zoning; spatial backfill via ST_Within centroid",
        }
        for k in RAW_PASSTHROUGH:
            if k in attrs and attrs[k] is not None:
                raw[k] = attrs[k]
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skip OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue
        out.append({
            "jurisdiction_id": BLOOMFIELD_HILLS_JID,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_code).strip(),
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw),
            "source": "arcgis",
        })
    return out


async def _fire(nearest_within_meters=50.0):
    print(f"\n=== FIRE: Bloomfield Hills city zoning ===\n")
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        features = await _fetch_features()
        rows = _build_rows(features)
        distinct = sorted({r["zone_code"] for r in rows})
        print(f"features {len(features)} rows {len(rows)} distinct {len(distinct)}: {distinct[:20]}")

        print(f"\n[INSERT] {len(rows)} zoning_districts…")
        for r in rows:
            await conn.execute(
                """
                INSERT INTO zoning_districts (jurisdiction_id, zone_code, zone_name, zone_class, geom, raw_attributes, source)
                VALUES ($1::uuid, $2, $3, $4::zone_class_enum,
                    ST_Multi(ST_MakeValid(ST_GeomFromText($5, 4326))),
                    $6::jsonb, $7::zone_source_enum)
                """,
                r["jurisdiction_id"], r["zone_code"], r["zone_name"], r["zone_class"],
                r["geom_wkt"], r["raw_attributes"], r["source"],
            )
        print(f"[INSERT] {len(rows)} rows committed")

        s1 = await conn.execute(
            """
            UPDATE parcels target SET zone_class=sub.zone_class, zone_binding_method='contained',
                zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
            FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                  LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                           WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                             AND ST_Within(ST_Centroid(p.geom), zd.geom)
                           ORDER BY zd.id LIMIT 1) m
                  WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL) sub
            WHERE target.id = sub.parcel_id
            """,
            BLOOMFIELD_HILLS_JID,
        )
        n1 = int(s1.split()[-1])
        print(f"[spatial] contained UPDATEd {n1}")

        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        s2 = await conn.execute(
            """
            UPDATE parcels target SET zone_class=sub.zone_class, zone_binding_method=$2,
                zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
            FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                  LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                           WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                             AND ST_DWithin(zd.geom::geography, ST_Centroid(p.geom)::geography, $3)
                           ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography) LIMIT 1) m
                  WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL AND p.zone_binding_method IS NULL) sub
            WHERE target.id = sub.parcel_id
            """,
            BLOOMFIELD_HILLS_JID, binding_label, float(nearest_within_meters),
        )
        n2 = int(s2.split()[-1])
        print(f"[spatial] {binding_label} UPDATEd {n2}")

        ext = await conn.fetchrow(
            """SELECT ST_XMin(ST_Extent(geom)) AS minx, ST_YMin(ST_Extent(geom)) AS miny,
                      ST_XMax(ST_Extent(geom)) AS maxx, ST_YMax(ST_Extent(geom)) AS maxy
               FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""",
            BLOOMFIELD_HILLS_JID,
        )
        bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(f"Bloomfield Hills bbox {bbox} outside expected")
        await conn.execute(
            "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
            BLOOMFIELD_HILLS_JID, json.dumps(bbox),
        )
        print(f"\nbbox {bbox}")

        p = await conn.fetchrow(
            """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
                      COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                      COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
               FROM parcels WHERE jurisdiction_id=$1::uuid""",
            BLOOMFIELD_HILLS_JID,
        )
        d = await conn.fetchval("SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid", BLOOMFIELD_HILLS_JID)
        empty = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)",
            BLOOMFIELD_HILLS_JID,
        )
        cov = 100.0 * p["bound"] / p["total"] if p["total"] else 0
        near = 100.0 * p["nearest"] / p["total"] if p["total"] else 0
        print(f"\n=== 5-GATE ===\nGATE 1 {cov:.1f}% (≥70%) — {'PASS' if cov>=70 else 'SUB'}")
        print(f"GATE 2 {near:.1f}% (<30%) — {'PASS' if near<30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty} — {'PASS' if empty==0 else 'FAIL'}")
        print(f"GATE 4 districts {d} — {'PASS' if d>0 else 'FAIL'}")
        print(f"GATE 5 bbox populated")
        print(f"  parcels {p['total']:,} bound {p['bound']:,} contained {p['contained']:,} nearest {p['nearest']:,}")

        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC""",
            BLOOMFIELD_HILLS_JID,
        )
        print(f"\nDistribution ({len(codes)}):")
        for r in codes[:20]:
            print(f"  {r['zoning_code']:15s} {r['n']:>5,}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = p.parse_args()
    if not args.i_know_this_writes_to_prod:
        print("Refusing", file=sys.stderr)
        sys.exit(2)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_fire(nearest_within_meters=args.nearest_within_meters)))
