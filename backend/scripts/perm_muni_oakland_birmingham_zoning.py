"""Phase 7E.3 — Birmingham, MI city zoning Class A ingest.

Wave 4 first Phase 7E.3 fire after Phase 7E.2 (PR #318). Birmingham HIGH
Path A per Diagnostic PR #260 — City of Birmingham GIS publishes a public
ArcGIS Map Server with district polygons. Source freshness verified
2026-06-19.

Source: City of Birmingham MI GIS Zoning layer
  https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0

Live probes (2026-06-19):
  - Total polygons : 400 (true zoning map polygons)
  - Geom           : Polygon, reprojection via outSR=4326
  - Code field     : district (R1, R2, R4, R8, B-1, B-2, MX, TZ-1, etc.)
  - Aux fields     : descript (description), standards, entity, level_
  - 0-1/0-2 numeric ZERO caveat per Diagnostic PR #260 — preserve verbatim

Birmingham jurisdiction (registered in Phase 7E.2 PR #318):
  97474794-c0c8-4903-9fae-51fb8fc795bc (9,778 parcels)

Hard rules:
  - raw_attributes preserved (Norfolk gate)
  - municipality matches prod_city_value 'CITY OF BIRMINGHAM' (MI UPPERCASE+prefix)
  - inline jurisdictions.bbox UPDATE (PR #261)
  - PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
  - Don't author matrix (orchestrator pre-stage 8fe33e5 covers 21-row Birmingham)
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
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("birmingham_zoning_ingest")

BIRMINGHAM_JID = "97474794-c0c8-4903-9fae-51fb8fc795bc"
MUNI_NAME = "Birmingham"
LAYER_URL = "https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0"
ZONE_CODE_FIELD = "district"
ZONE_NAME_FIELD = "descript"
RAW_PASSTHROUGH = (
    "objectid", "cloudgisdata.bhamsql.zoning.entity", "level_",
    "district", "descript", "standards",
)
ARCGIS_PAGE_SIZE = 1000

# Birmingham MI bbox (per Diagnostic PR #260).
BBOX_LON_RANGE = (-83.28, -83.15)
BBOX_LAT_RANGE = (42.51, 42.58)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _fetch_features() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": "1=1", "outFields": "*", "returnGeometry": "true",
                "outSR": 4326, "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE, "f": "json",
                "orderByFields": "objectid",
            }
            r = await client.get(f"{LAYER_URL}/query", params=params)
            r.raise_for_status()
            batch = r.json().get("features", [])
            features.extend(batch)
            logger.info("fetched %d (cumulative %d) offset=%d",
                        len(batch), len(features), offset)
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    ring_wkts = []
    for r in rings:
        if len(r) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


def _build_district_rows(features):
    out = []
    for f in features:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            continue
        zone_code = attrs.get(ZONE_CODE_FIELD)
        if not zone_code or not str(zone_code).strip():
            continue
        zone_name = attrs.get(ZONE_NAME_FIELD) or zone_code
        raw_attributes = {
            "source_url": LAYER_URL,
            "source_filter": "1=1",
            "source_kind": "arcgis_map_server",
            "ingested_at": "2026-06-19",
            "muni_name": MUNI_NAME,
            "muni_type": "city",
            "publisher": "City of Birmingham MI GIS (bhamgov)",
            "numeric_zero_caveat": "0-1/0-2 codes use numeric ZERO not letter O per Diagnostic PR #260",
        }
        for k in RAW_PASSTHROUGH:
            if k in attrs and attrs[k] is not None:
                raw_attributes[k] = attrs[k]
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping objectid=%s: %s", attrs.get("objectid"), exc)
            continue
        out.append({
            "jurisdiction_id": BIRMINGHAM_JID,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip(),
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


async def _fire(nearest_within_meters: float = 50.0) -> int:
    print(f"\n=== FIRE: Birmingham city zoning ingest ===\n")
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        features = await _fetch_features()
        rows = _build_district_rows(features)
        distinct = sorted({r["zone_code"] for r in rows})
        print(f"  features fetched : {len(features)}")
        print(f"  rows built       : {len(rows)}")
        print(f"  distinct codes   : {len(distinct)}: {distinct[:25]}")

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

        print(f"\n[spatial] Pass 1 contained (ST_Within centroid)…")
        s1 = await conn.execute(
            """
            UPDATE parcels target SET zone_class = sub.zone_class,
                zone_binding_method = 'contained',
                zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                         WHERE zd.jurisdiction_id = $1::uuid AND zd.geom IS NOT NULL
                           AND ST_Within(ST_Centroid(p.geom), zd.geom)
                         ORDER BY zd.id LIMIT 1) m
                WHERE p.jurisdiction_id = $1::uuid AND p.geom IS NOT NULL
            ) sub WHERE target.id = sub.parcel_id
            """,
            BIRMINGHAM_JID,
        )
        n1 = int(s1.split()[-1])
        print(f"[spatial] contained UPDATEd {n1}")

        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        s2 = await conn.execute(
            """
            UPDATE parcels target SET zone_class = sub.zone_class,
                zone_binding_method = $2,
                zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                         WHERE zd.jurisdiction_id = $1::uuid AND zd.geom IS NOT NULL
                           AND ST_DWithin(zd.geom::geography, ST_Centroid(p.geom)::geography, $3)
                         ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography) LIMIT 1) m
                WHERE p.jurisdiction_id = $1::uuid AND p.geom IS NOT NULL AND p.zone_binding_method IS NULL
            ) sub WHERE target.id = sub.parcel_id
            """,
            BIRMINGHAM_JID, binding_label, float(nearest_within_meters),
        )
        n2 = int(s2.split()[-1])
        print(f"[spatial] {binding_label} UPDATEd {n2}")

        ext = await conn.fetchrow(
            """SELECT ST_XMin(ST_Extent(geom)) AS minx, ST_YMin(ST_Extent(geom)) AS miny,
                      ST_XMax(ST_Extent(geom)) AS maxx, ST_YMax(ST_Extent(geom)) AS maxy
               FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL""",
            BIRMINGHAM_JID,
        )
        bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(f"Birmingham bbox {bbox} outside expected range")
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            BIRMINGHAM_JID, json.dumps(bbox),
        )
        print(f"\n[bbox] {bbox}")

        # 5-gate verdict
        p_after = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '') AS bound,
                      COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                      COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            BIRMINGHAM_JID,
        )
        d_after = await conn.fetchval("SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid", BIRMINGHAM_JID)
        empty_raw = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)",
            BIRMINGHAM_JID,
        )
        cov = 100.0 * p_after["bound"] / p_after["total"] if p_after["total"] else 0
        near = 100.0 * p_after["nearest"] / p_after["total"] if p_after["total"] else 0
        print(f"\n=== 5-GATE VERDICT ===")
        print(f"GATE 1 cov%  = {cov:.1f}% (≥70%) — {'PASS' if cov>=70 else 'SUB'}")
        print(f"GATE 2 near% = {near:.1f}% (<30%) — {'PASS' if near<30 else 'OVER'}")
        print(f"GATE 3 raw empty = {empty_raw} — {'PASS' if empty_raw==0 else 'FAIL'}")
        print(f"GATE 4 districts = {d_after} — {'PASS' if d_after>0 else 'FAIL'}")
        print(f"GATE 5 bbox: populated")
        print(f"  parcels={p_after['total']:,} bound={p_after['bound']:,} contained={p_after['contained']:,} nearest={p_after['nearest']:,}")

        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id = $1::uuid AND zoning_code IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC""", BIRMINGHAM_JID,
        )
        print(f"\nDistribution ({len(codes)} codes):")
        for r in codes[:20]:
            print(f"  {r['zoning_code']:15s} {r['n']:>5,}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    if not args.i_know_this_writes_to_prod:
        print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
        sys.exit(2)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_fire(nearest_within_meters=args.nearest_within_meters)))
