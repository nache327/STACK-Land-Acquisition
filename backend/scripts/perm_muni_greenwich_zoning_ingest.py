"""Phase 7C.3 — Greenwich, CT city zoning Class A ingest.

Wave 3 second Phase 7C.3 fire after Stamford (PR #308 MERGED). Greenwich
flipped from LOW Path B citations-only to HIGH Path A by Lane A's live
GIS probe (2026-06-19): Town of Greenwich publishes a public ArcGIS
Feature Server hosted by greenwichgis (Daniel.Clark_greenwichgis org),
authoritative for the official Zoning Instant App.

Source: Town of Greenwich GIS authoritative zoning layer
  https://services2.arcgis.com/cYiUUgMhu4YB7W9G/arcgis/rest/services/
  Zone_Boundaries/FeatureServer/0

Live probes (2026-06-19):
  - Total polygons : 285 (true zoning map — NOT parcel-density)
  - Geom           : Polygon, SR 102100 (Web Mercator) → outSR=4326
  - Code field     : Layer (51 unique codes — RA-1/2/4, R-7/12/20, CGB,
                     GB, LB, LBR-1/2, GBO, P, WB, H-1/2, plus HO/HRO
                     Historic Overlay variants)
  - Name field     : District (47 unique long descriptions)
  - Category field : ZoneType (Residential/Commercial/Waterfront/Planned)
  - Authority      : Daniel.Clark_greenwichgis org — official Zoning App publisher

Per Master's Wave 3 dispatch (2026-06-19): Greenwich was flagged LOW Path B
(PDF/web-map) per Diagnostic PR #257, but live probe surfaced a clean
public ArcGIS Feature Server — promotes Greenwich to HIGH Path A. Same
Stamford-shape pattern. 5/5 expected (Stamford 100% precedent).

Greenwich jurisdiction (registered in PR #307 Phase 7C.2):
  e5406ad0-4e9d-4cea-b20f-800a94d6be8a (18,042 parcels)

Hard rules honored:
  - raw_attributes preserved (Norfolk gate)
  - municipality matches prod_city_value ('Greenwich', title-case PR #228)
  - inline jurisdictions.bbox UPDATE (PR #261 codified)
  - skip in-DB ROLLBACK preflight at Class A scale (PR #253)
  - PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
  - Don't author matrix (orchestrator's pre-stage will absorb the upgrade
    from LOW Path B → HIGH Path A; report code drift if any)
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

logger = logging.getLogger("greenwich_zoning_ingest")

GREENWICH_JID = "e5406ad0-4e9d-4cea-b20f-800a94d6be8a"
MUNI_NAME = "Greenwich"
PROD_CITY_VALUE = "Greenwich"
LAYER_URL = (
    "https://services2.arcgis.com/cYiUUgMhu4YB7W9G/arcgis/rest/services/"
    "Zone_Boundaries/FeatureServer/0"
)
ZONE_CODE_FIELD = "Layer"
ZONE_NAME_FIELD = "District"
RAW_PASSTHROUGH = (
    "OBJECTID_1", "FID", "Entity", "Layer", "District",
    "ZoneType", "Use_group", "Hold", "UseGroup", "Conserv",
)
ARCGIS_PAGE_SIZE = 1000

# Greenwich bbox sanity range (per Phase 7C.2 PR #307).
BBOX_LON_RANGE = (-73.73, -73.55)
BBOX_LAT_RANGE = (40.97, 41.15)


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
                "orderByFields": "OBJECTID_1",
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
    """PR #285 + PR #303 pattern."""
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
        zone_name = attrs.get(ZONE_NAME_FIELD) or zone_code
        raw_attributes = {
            "source_url": LAYER_URL,
            "source_filter": "1=1",
            "source_kind": "arcgis_feature_server",
            "ingested_at": "2026-06-19",
            "muni_name": MUNI_NAME,
            "muni_type": "town",
            "publisher": "Town of Greenwich GIS (Daniel.Clark_greenwichgis)",
        }
        for k in RAW_PASSTHROUGH:
            if k in attrs and attrs[k] is not None:
                raw_attributes[k] = attrs[k]
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID_1=%s, ring parse: %s",
                           attrs.get("OBJECTID_1"), exc)
            continue
        out.append({
            "jurisdiction_id": GREENWICH_JID,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip(),
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Greenwich city zoning ingest ===\n")
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
    print(f"\n=== FIRE: Greenwich city zoning ingest ===\n")
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        p_before = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) AS bound
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            GREENWICH_JID,
        )
        print(f"PRE-FIRE: Greenwich parcels {p_before['total']:,} bound: "
              f"{p_before['bound']:,}")

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
                    ST_Multi(ST_MakeValid(ST_GeomFromText($5, 4326))),
                    $6::jsonb, $7::zone_source_enum
                )
                """,
                r["jurisdiction_id"], r["zone_code"], r["zone_name"],
                r["zone_class"], r["geom_wkt"], r["raw_attributes"],
                r["source"],
            )
        print(f"[INSERT] {len(rows)} rows committed")

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
            GREENWICH_JID,
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
            GREENWICH_JID, binding_label, float(nearest_within_meters),
        )
        n2 = int(s2.split()[-1]) if s2.split() else -1
        print(f"[spatial] {binding_label} UPDATEd {n2}")

        ext = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Extent(geom)) AS minx,
                   ST_YMin(ST_Extent(geom)) AS miny,
                   ST_XMax(ST_Extent(geom)) AS maxx,
                   ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            GREENWICH_JID,
        )
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"Greenwich bbox {bbox} outside expected range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            GREENWICH_JID, json.dumps(bbox),
        )
        print(f"\n[bbox] verified+UPDATEd: {bbox}")

        print("\n=== 5-GATE VERDICT ===")
        p_after = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '') AS bound,
                   COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                   COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
            FROM parcels WHERE jurisdiction_id = $1::uuid
            """,
            GREENWICH_JID,
        )
        d_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            GREENWICH_JID,
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid
               AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)""",
            GREENWICH_JID,
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

        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id = $1::uuid AND zoning_code IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC""",
            GREENWICH_JID,
        )
        print(f"\n=== Greenwich zoning_code distribution ({len(codes)} codes) ===")
        for r in codes:
            print(f"  {r['zoning_code']:15s} {r['n']:>5,}")

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
