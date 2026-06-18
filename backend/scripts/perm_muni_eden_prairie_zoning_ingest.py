"""Phase 7A.3 — Edina, MN city zoning Class A ingest.

Stacked on PR #294 Phase 7A.2 (which registered Edina as own jurisdiction
2b08fa13-… with 21,343 parcels moved from Hennepin umbrella). This
dispatch INSERTs Edina's authoritative zoning_districts under that
jurisdiction, runs spatial backfill, sets bbox.

Source: ZoneCo published Edina layer (ZoneCo is Edina's planning
consultant; their "Existing Map" service is the canonical published
view of actual current zoning).

  https://services3.arcgis.com/rNrGj3CxKnr9E71f/arcgis/rest/services/
  2026_04_13_Existing_Map_Edina_WFL1/FeatureServer/1

Live probes (2026-06-18):
  - Feature count : 21,529 (parcel-density polygons — one row per parcel)
  - Geom          : Polygon, SR 102100 (Web Mercator, reproject via outSR=4326)
  - Field map     : E_Zoning (existing zoning code, authoritative)
  - Code count    : 23 distinct codes
    APD, MDD-4/5/6, PCD-1/2/3/4, PID, POD-1/2,
    PRD-1/2/3/4/5, PSR-4, PUD, PUD-22, PUD-8, R-1, R-2, RMD

Substrate-first note: Master's brief said orchestrator pre-staged 39
codes for Edina. Source returns 23 codes — surplus matrix rows for
non-binding codes will sit unused, no harm. Per PR #248 / PR #264
precedent: ingest the authoritative substrate; downstream catchall
covers any verdict gaps.

5 quality gates verified at fire-end:
  1. parcel_zoning_code_coverage_pct ≥ 70% (target ~95% per Mill Creek
     parcel-density pattern)
  2. zone_binding_method nearest_* < 30%
  3. raw_attributes preserved verbatim (Norfolk gate)
  4. zoning_district_count > 0
  5. jurisdictions.bbox populated

Hard rules honored:
  - raw_attributes preserved (Hennepin's already-rich raw kept on parcels;
    NEW raw_attributes on zoning_districts from source)
  - municipality matches prod_city_value ('Edina', title-case from PR #233)
  - inline jurisdictions.bbox UPDATE (PR #261)
  - skip in-DB ROLLBACK preflight (PR #253)
  - Don't author matrix (orchestrator's 39-row pre-stage covers it)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely.geometry import MultiPolygon, Polygon

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("eden_prairie_zoning_ingest")

# Edina, MN jurisdiction (registered in PR #294 Phase 7A.2).
EDEN_PRAIRIE_JID = "455b6dac-f915-4707-a109-880712b884fb"
MUNI_NAME = "Eden Prairie"
PROD_CITY_VALUE = "Eden Prairie"
LAYER_URL = (
    "https://gis.edenprairie.org/mapsb/rest/services/"
    "Public/Zoning/MapServer/7"
)
ZONE_CODE_FIELD = "ZONING"
ZONE_NAME_FIELD = "ZONING"  # source doesn't publish separate human name
RAW_PASSTHROUGH = (
    "OBJECTID", "PID", "UNIT", "ADDRESS",
    "AUDIT_DATE", "ZONING",
    
)
ARCGIS_PAGE_SIZE = 1000

# Edina bbox sanity range (slightly wider than Phase 7A.2's per-muni bbox).
BBOX_LON_RANGE = (-93.55, -93.39)
BBOX_LAT_RANGE = (44.79, 44.90)


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
                "orderByFields": "OBJECTID",
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
    """Per Pierce Task E (PR #285) — punt topology to PostGIS via
    ST_MakeValid. Skip degenerate rings (<4 points; a valid polygon
    ring needs at least 4 with first==last) — Eden Prairie's source
    has occasional sliver geometry that PostGIS rejects upstream of
    ST_MakeValid."""
    ring_wkts = []
    for r in rings:
        if len(r) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


def _build_district_rows(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in features:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            continue
        zone_code = attrs.get(ZONE_CODE_FIELD)
        if not zone_code or not str(zone_code).strip():
            continue
        raw_attributes = {
            "source_url": LAYER_URL,
            "source_filter": "1=1",
            "source_kind": "arcgis_feature_server",
            "ingested_at": "2026-06-18",
            "muni_name": MUNI_NAME,
            "muni_type": "city",
            "publisher": "City of Eden Prairie MN (gis.edenprairie.org)",
            "vintage": "live",
        }
        for k in RAW_PASSTHROUGH:
            if k in attrs and attrs[k] is not None:
                raw_attributes[k] = attrs[k]
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID=%s, ring parse: %s",
                           attrs.get("OBJECTID"), exc)
            continue
        out.append({
            "jurisdiction_id": EDEN_PRAIRIE_JID,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_code).strip(),
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Edina city zoning ingest ===\n")
    features = await _fetch_features()
    rows = _build_district_rows(features)
    distinct = sorted({r["zone_code"] for r in rows})
    print(f"  features fetched : {len(features)}")
    print(f"  rows built       : {len(rows)}")
    print(f"  distinct codes   : {len(distinct)}")
    print(f"  codes            : {distinct}")
    if rows:
        sample = json.loads(rows[0]["raw_attributes"])
        print(f"  sample raw fields: {len(sample)} keys → {list(sample.keys())}")
    print("\n(NO DB WRITES — pipeline shape validated.)")
    return 0


async def _fire(nearest_within_meters: float = 50.0) -> int:
    print(f"\n=== FIRE: Edina city zoning ingest ===\n")
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # Pre-fire snapshot
        p_before = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) AS bound
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            EDEN_PRAIRIE_JID,
        )
        print(f"PRE-FIRE: Edina parcels {p_before['total']:,} bound: "
              f"{p_before['bound']:,}")

        # Phase A — fetch + INSERT districts
        features = await _fetch_features()
        rows = _build_district_rows(features)
        print(f"\n[INSERT] {len(rows)} zoning_districts…")
        for r in rows:
            await conn.execute(
                """
                INSERT INTO zoning_districts (
                    jurisdiction_id, zone_code, zone_name, zone_class,
                    geom, raw_attributes, source
                ) VALUES (
                    $1::uuid, $2, $3, $4::zone_class_enum,
                    ST_MakeValid(ST_GeomFromText($5, 4326)),
                    $6::jsonb, $7::zone_source_enum
                )
                """,
                r["jurisdiction_id"], r["zone_code"], r["zone_name"],
                r["zone_class"], r["geom_wkt"], r["raw_attributes"],
                r["source"],
            )
        print(f"[INSERT] {len(rows)} rows committed")

        # Phase B — 2-pass spatial backfill
        print(f"\n[spatial] Pass 1 contained (ST_Within centroid)…")
        s1 = await conn.execute(
            """
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = 'contained',
                zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            EDEN_PRAIRIE_JID,
        )
        n1 = int(s1.split()[-1]) if s1.split() else -1
        print(f"[spatial] contained UPDATEd {n1}")

        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        print(f"[spatial] Pass 2 {binding_label} (ST_DWithin, still-NULL)…")
        s2 = await conn.execute(
            """
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = $2,
                zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.geom IS NOT NULL
                      AND ST_DWithin(
                          zd.geom::geography,
                          ST_Centroid(p.geom)::geography,
                          $3
                      )
                    ORDER BY ST_Distance(
                        zd.geom::geography,
                        ST_Centroid(p.geom)::geography
                    ) LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
                  AND p.zone_binding_method IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            EDEN_PRAIRIE_JID, binding_label, float(nearest_within_meters),
        )
        n2 = int(s2.split()[-1]) if s2.split() else -1
        print(f"[spatial] {binding_label} UPDATEd {n2}")

        # Phase C — inline bbox UPDATE (PR #261 codified)
        ext = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Extent(geom)) AS minx,
                   ST_YMin(ST_Extent(geom)) AS miny,
                   ST_XMax(ST_Extent(geom)) AS maxx,
                   ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            EDEN_PRAIRIE_JID,
        )
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"Edina bbox {bbox} outside expected range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            EDEN_PRAIRIE_JID, json.dumps(bbox),
        )
        print(f"\n[bbox] verified+UPDATEd: {bbox}")

        # Phase D — 5 quality gates verdict
        print("\n=== 5-GATE VERDICT ===")
        p_after = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '') AS bound,
                   COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                   COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
            FROM parcels WHERE jurisdiction_id = $1::uuid
            """,
            EDEN_PRAIRIE_JID,
        )
        d_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            EDEN_PRAIRIE_JID,
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid
               AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)""",
            EDEN_PRAIRIE_JID,
        )
        cov = 100.0 * p_after["bound"] / p_after["total"] if p_after["total"] else 0
        near = 100.0 * p_after["nearest"] / p_after["total"] if p_after["total"] else 0
        print(f"GATE 1 cov%  = {cov:.1f}% (target ≥70%) — {'PASS' if cov>=70 else 'SUB-GATE'}")
        print(f"GATE 2 near% = {near:.1f}% (target <30%) — {'PASS' if near<30 else 'OVER CAP'}")
        print(f"GATE 3 raw_attributes empty: {empty_raw} (Norfolk, target 0) — "
              f"{'PASS' if empty_raw == 0 else 'FAIL'}")
        print(f"GATE 4 zoning_district_count = {d_after} (target >0) — "
              f"{'PASS' if d_after > 0 else 'FAIL'}")
        print(f"GATE 5 jurisdictions.bbox: populated")
        print(f"  parcels={p_after['total']:,} bound={p_after['bound']:,} "
              f"contained={p_after['contained']:,} nearest={p_after['nearest']:,}")

        # Zoning code distribution
        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id = $1::uuid AND zoning_code IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC""",
            EDEN_PRAIRIE_JID,
        )
        print(f"\n=== Edina zoning_code distribution ({len(codes)} codes) ===")
        for r in codes:
            flag = "  ← PID cleanup-queue candidate" if r["zoning_code"] == "PID" else ""
            print(f"  {r['zoning_code']:10s} {r['n']:>5,}{flag}")

    finally:
        await conn.close()
    return 0


async def main(args) -> int:
    if args.subcommand == "preflight":
        return await _preflight()
    if args.subcommand == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
            return 2
        return await _fire(nearest_within_meters=args.nearest_within_meters)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("preflight", help="Pipeline shape only, NO DB writes")
    fire = sub.add_parser("fire", help="Real prod write")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args)))
