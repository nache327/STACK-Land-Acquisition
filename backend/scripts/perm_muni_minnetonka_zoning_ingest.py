"""Phase 7A.3 — Minnetonka, MN city zoning Class A ingest.

Stacks the per-muni Hennepin zoning cohort started by Edina (PR #295),
Plymouth (PR #304), Eden Prairie (PR #303). Minnetonka jurisdiction
3267204b-… was registered in Phase 7A.2 (PR #294) with 20,911 parcels
moved from the Hennepin umbrella.

Source: ZoneCo published Minnetonka layer (named "Proposed Zoning" at
the service level — substrate-vs-proposed risk flagged by orchestrator).
Field-level inspection shows the ZONING field carries current/existing
zoning codes (Proposed_Zone is a separate column for proposed changes),
which materially mitigates the proposed-vs-existing risk: we ingest
ZONING as the authoritative current substrate.

  https://services3.arcgis.com/rNrGj3CxKnr9E71f/arcgis/rest/services/
  20260521_Zoning_Map_Minnetonka/FeatureServer/0

Live probes (2026-06-18):
  - Feature count : 17,571 (parcel-density polygons — one row per parcel)
  - Geom          : Polygon, SR 102100 (Web Mercator, reproject via outSR=4326)
  - Field map     : ZONING (existing zoning code, authoritative)
                    Proposed_Zone (proposed change — NOT used)
                    LAND_USE (land use classification — passthrough only)
  - maxRecordCount: 2000

Substrate-vs-proposed mitigation: ZoneCo's service-level "Proposed Zoning"
name appears to be the publisher's branding for the active project — the
FIELDS confirm ZONING = current substrate. If audit verdict shows code
drift from orchestrator's pre-stage (commit 5287ee4, 10 ArcGIS + 4
ordinance = 14 rows), document drift in PR body and let orchestrator
decide Path A apply vs Path B re-author per pre-stage discipline.

5 quality gates verified at fire-end:
  1. parcel_zoning_code_coverage_pct ≥ 70%
  2. zone_binding_method nearest_* < 30%
  3. raw_attributes preserved (Norfolk gate)
  4. zoning_district_count > 0
  5. jurisdictions.bbox populated inline (PR #261)

Hard rules honored:
  - raw_attributes preserved (Phase 7A.1's rich raw kept on parcels;
    NEW raw_attributes on zoning_districts from source)
  - municipality matches prod_city_value ('Minnetonka', title-case PR #233)
  - inline jurisdictions.bbox UPDATE (PR #261 codified)
  - skip in-DB ROLLBACK preflight at Class A scale (PR #253)
  - PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
  - Don't author matrix (orchestrator's 14-row pre-stage covers)
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

logger = logging.getLogger("minnetonka_zoning_ingest")

# Minnetonka, MN jurisdiction (registered in PR #294 Phase 7A.2).
MINNETONKA_JID = "3267204b-fa88-45c5-bddd-3162cea4eb41"
MUNI_NAME = "Minnetonka"
PROD_CITY_VALUE = "Minnetonka"
LAYER_URL = (
    "https://services3.arcgis.com/rNrGj3CxKnr9E71f/arcgis/rest/services/"
    "20260521_Zoning_Map_Minnetonka/FeatureServer/0"
)
ZONE_CODE_FIELD = "ZONING"
ZONE_NAME_FIELD = "ZONING"
RAW_PASSTHROUGH = (
    "OBJECTID", "PID", "AREA_", "PERIMETER", "ACRES",
    "HOUSE_NUMB", "STREET", "ADDRESS", "UNIT", "ZIP",
    "IM_ID", "ZONING", "Proposed_Zone", "LAND_USE",
)
ARCGIS_PAGE_SIZE = 1000

# Minnetonka bbox sanity range (consistent with Phase 7A.2 city bbox).
BBOX_LON_RANGE = (-93.55, -93.35)
BBOX_LAT_RANGE = (44.88, 45.00)


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
    """PR #285 Pierce Task E pattern + PR #303 Eden Prairie degenerate-ring
    skip: emit each ring as separate polygon body in MULTIPOLYGON, let
    PostGIS reconstruct topology via ST_Multi(ST_MakeValid(...)). Skip
    rings with <4 points (degenerate, would error on ST_MakeValid)."""
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
            "publisher": "ZoneCo (Minnetonka planning consultant)",
            "vintage": "2026-05-21",
            "note_substrate": "service-level name 'Proposed Zoning' but "
                              "ZONING field carries current/existing code; "
                              "Proposed_Zone is separate column",
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
            "jurisdiction_id": MINNETONKA_JID,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_code).strip(),
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Minnetonka city zoning ingest ===\n")
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
    print(f"\n=== FIRE: Minnetonka city zoning ingest ===\n")
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        p_before = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) AS bound
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            MINNETONKA_JID,
        )
        print(f"PRE-FIRE: Minnetonka parcels {p_before['total']:,} bound: "
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
            MINNETONKA_JID,
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
            MINNETONKA_JID, binding_label, float(nearest_within_meters),
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
            MINNETONKA_JID,
        )
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"Minnetonka bbox {bbox} outside expected range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            MINNETONKA_JID, json.dumps(bbox),
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
            MINNETONKA_JID,
        )
        d_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            MINNETONKA_JID,
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid
               AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)""",
            MINNETONKA_JID,
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
            MINNETONKA_JID,
        )
        print(f"\n=== Minnetonka zoning_code distribution ({len(codes)} codes) ===")
        for r in codes:
            flag = "  ← I-1 cleanup-queue candidate" if r["zoning_code"] == "I-1" else ""
            print(f"  {r['zoning_code']:20s} {r['n']:>5,}{flag}")

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
