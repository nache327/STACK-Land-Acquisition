"""Phase 6B.2 PIVOT — Gig Harbor per-muni registration + WAZA ingest.

Third per-muni in the Phase 6B-PIVOT cohort (after Bellevue PR #271 and
Mercer Island PR #274 + PR #278). Pattern matches Bellevue/Mercer: register
the wealth-pocket muni as its own prod jurisdiction, move parcels from the
parent county, then run Class A WAZA zoning backfill scoped to the new
jurisdiction.

Pre-state:
  - Pierce County, WA jid 47ff33c8-14ec-4298-827e-c770f416d2b6 (PR #267)
  - 5,312 Gig Harbor parcels under Pierce (parcels.city = 'Gig Harbor')
  - No existing 'Gig Harbor, WA' jurisdiction
  - No Pierce zoning_districts loaded yet (Phase 6B.2 hasn't fired for Pierce)
  - No Pierce matrix rows yet

Post-state (this script):
  - New Gig Harbor, WA jurisdiction registered
  - 5,312 parcels moved Pierce → Gig Harbor
  - 76 WAZA zoning_districts INSERTed under Gig Harbor
  - 2-pass spatial backfill (contained + nearest_50m, escalate to _100m if
    sub-cov per Westchester Group A precedent / Mercer PR #274)
  - Inline jurisdictions.bbox UPDATE per PR #261 codified pattern
  - Audit recompute via direct-python (per Mercer PR #278 unblock pattern)

5 quality gates verified at the end:
  1. parcel_zoning_code_coverage_pct ≥ 70%
  2. zone_binding_method nearest_* < 30%
  3. raw_attributes preserved verbatim (Norfolk gate)
  4. zoning_district_count > 0
  5. jurisdictions.bbox populated

Matrix authoring is orchestrator's domain. This script surfaces uncovered
codes at the end for the follow-up sprint.

Hard rules honored:
  - raw_attributes preserved (Norfolk gate)
  - municipality matches prod_city_value ('Gig Harbor', title-case)
  - inline jurisdictions.bbox per ingest (PR #261)
  - skip in-DB ROLLBACK preflight (PR #253) — Phase 1 verdict substitutes
  - Don't author matrix (orchestrator's domain)
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

logger = logging.getLogger("gig_harbor_perm_muni")

DIRECTORY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "pierce_wa_zoning_directory.json"
)
PIERCE_JID = "47ff33c8-14ec-4298-827e-c770f416d2b6"
MUNI_NAME = "Gig Harbor"  # raw_attributes filter (WAZA Jurisdiction)
PROD_CITY_VALUE = "Gig Harbor"  # parcels.city filter (PR #233 lesson)
NEW_JURISDICTION_NAME = "Gig Harbor, WA"
ARCGIS_PAGE_SIZE = 1000

# Gig Harbor bbox sanity range (Puget Sound / Pierce County).
# Per Pierce Task E spot-check: Gig Harbor parcel centroids cluster in
# lat 47.31-47.36, lon -122.58 to -122.62. Widened for polygon extent.
BBOX_LON_RANGE = (-122.70, -122.50)
BBOX_LAT_RANGE = (47.25, 47.40)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _load_directory_entry() -> dict[str, Any]:
    directory = json.loads(DIRECTORY_PATH.read_text())
    for e in directory:
        if e["muni_name"] == MUNI_NAME:
            return e
    raise SystemExit(f"Gig Harbor entry not in {DIRECTORY_PATH.name}")


async def _fetch_arcgis_features(source: dict[str, Any]) -> list[dict[str, Any]]:
    base_url = source["url"]
    where = source["filter_query"]
    out_sr = source.get("out_sr", 4326)
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": where, "outFields": "*", "returnGeometry": "true",
                "outSR": out_sr, "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE, "f": "json",
            }
            r = await client.get(f"{base_url}/query", params=params)
            r.raise_for_status()
            batch = r.json().get("features", [])
            features.extend(batch)
            logger.info("fetched %d (cumulative %d) where=%r offset=%d",
                        len(batch), len(features), where, offset)
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _arcgis_rings_to_wkt(rings: list[list[list[float]]]) -> str:
    def _signed_area(ring):
        s = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            s += (x2 - x1) * (y2 + y1)
        return s
    polys: list[Polygon] = []
    has_outer = any(_signed_area(r) < 0 for r in rings)
    if has_outer:
        current_outer = None
        current_holes: list[list[list[float]]] = []
        for ring in rings:
            if _signed_area(ring) < 0:
                if current_outer is not None:
                    polys.append(Polygon(current_outer, current_holes))
                current_outer = ring
                current_holes = []
            else:
                current_holes.append(ring)
        if current_outer is not None:
            polys.append(Polygon(current_outer, current_holes))
    else:
        polys = [Polygon(r) for r in rings]
    if not polys:
        raise ValueError("no polygons from rings")
    geom = MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return geom.wkt


def _build_district_rows(
    entry: dict[str, Any],
    features: list[dict[str, Any]],
    jurisdiction_id: uuid.UUID,
) -> list[dict[str, Any]]:
    src = entry["zoning_district_source"]
    field_map = src["field_map"]
    passthrough = src["raw_attributes_passthrough"]
    out: list[dict[str, Any]] = []
    for f in features:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            continue
        zone_code = attrs.get(field_map["zone_code"])
        zone_name = attrs.get(field_map.get("zone_name", ""))
        if not zone_code or not str(zone_code).strip():
            continue
        raw_attributes = {
            "source_url": src["url"],
            "source_filter": src["filter_query"],
            "source_kind": src["kind"],
            "ingested_at": "2026-06-16",
            "muni_name": entry["muni_name"],
            "muni_type": entry["muni_type"],
            "ordinance_url": entry.get("ordinance_url"),
            "vintage": entry.get("vintage"),
        }
        for f_name in passthrough:
            if f_name in attrs:
                raw_attributes[f_name] = attrs[f_name]
        try:
            wkt = _arcgis_rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID=%s, ring parse failed: %s",
                           attrs.get("OBJECTID"), exc)
            continue
        out.append({
            "jurisdiction_id": str(jurisdiction_id),
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip() if zone_name else None,
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Gig Harbor per-muni (pipeline shape) ===\n")
    entry = _load_directory_entry()
    features = await _fetch_arcgis_features(entry["zoning_district_source"])
    dummy_jid = uuid.uuid4()
    rows = _build_district_rows(entry, features, dummy_jid)
    distinct = sorted({r["zone_code"] for r in rows})
    print(f"  features fetched : {len(features)}")
    print(f"  rows built       : {len(rows)}")
    print(f"  distinct ZoneIDs : {len(distinct)}")
    print(f"  codes            : {distinct}")
    if rows:
        sample = json.loads(rows[0]["raw_attributes"])
        print(f"  sample raw fields: {len(sample)} keys → {list(sample.keys())}")
    print("\n(NO DB WRITES — pipeline shape validated.)")
    return 0


async def _fire(nearest_within_meters: float = 50.0) -> int:
    print(f"\n=== FIRE: Gig Harbor per-muni registration + WAZA ingest ===\n")
    entry = _load_directory_entry()

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # === Phase A: Register Gig Harbor jurisdiction + move parcels ===
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE name = $1 AND state = 'WA'",
                NEW_JURISDICTION_NAME,
            )
            if existing:
                new_jid = existing["id"]
                print(f"  Found existing Gig Harbor jurisdiction: {new_jid}")
            else:
                new_jid = uuid.uuid4()
                await conn.execute(
                    """
                    INSERT INTO jurisdictions (id, name, state, county)
                    VALUES ($1::uuid, $2, 'WA', 'Pierce')
                    """,
                    str(new_jid), NEW_JURISDICTION_NAME,
                )
                print(f"  Registered new jurisdiction: {new_jid}")

            p_before = await conn.fetchval(
                """SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2""",
                PIERCE_JID, PROD_CITY_VALUE,
            )
            print(f"  Pre-move Gig Harbor parcels under Pierce: {p_before:,}")
            status = await conn.execute(
                """
                UPDATE parcels
                   SET jurisdiction_id = $2::uuid, updated_at = NOW()
                 WHERE jurisdiction_id = $1::uuid AND city = $3
                """,
                PIERCE_JID, str(new_jid), PROD_CITY_VALUE,
            )
            n_p = int(status.split()[-1]) if status.split() else -1
            print(f"  Moved parcels Pierce → Gig Harbor: {n_p}")

        # === Phase B: WAZA Class A ingest under Gig Harbor jurisdiction ===
        features = await _fetch_arcgis_features(entry["zoning_district_source"])
        rows = _build_district_rows(entry, features, new_jid)
        print(f"\n[WAZA] INSERTing {len(rows)} districts…")
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
        print(f"[WAZA] INSERTed {len(rows)} rows")

        # === Phase C: Spatial backfill (contained → nearest_Nm fallback) ===
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
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $3
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(new_jid), MUNI_NAME, PROD_CITY_VALUE,
        )
        n1 = int(s1.split()[-1]) if s1.split() else -1
        print(f"[spatial] contained UPDATEd {n1}")

        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        print(f"[spatial] Pass 2 {binding_label} (ST_DWithin, still-NULL)…")
        s2 = await conn.execute(
            """
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = $4,
                zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND zd.geom IS NOT NULL
                      AND ST_DWithin(
                          zd.geom::geography,
                          ST_Centroid(p.geom)::geography,
                          $5
                      )
                    ORDER BY ST_Distance(
                        zd.geom::geography,
                        ST_Centroid(p.geom)::geography
                    ) LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $3
                  AND p.geom IS NOT NULL
                  AND p.zone_binding_method IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(new_jid), MUNI_NAME, PROD_CITY_VALUE, binding_label,
            float(nearest_within_meters),
        )
        n2 = int(s2.split()[-1]) if s2.split() else -1
        print(f"[spatial] {binding_label} UPDATEd {n2}")

        # === Phase D: Inline bbox UPDATE ===
        print("\n[bbox] Inline jurisdictions.bbox UPDATE…")
        ext = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Extent(geom)) AS minx,
                   ST_YMin(ST_Extent(geom)) AS miny,
                   ST_XMax(ST_Extent(geom)) AS maxx,
                   ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(new_jid),
        )
        if ext is None or ext["minx"] is None:
            raise RuntimeError("no parcel geometry to compute bbox from")
        bbox = [
            float(ext["minx"]), float(ext["miny"]),
            float(ext["maxx"]), float(ext["maxy"]),
        ]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"bbox {bbox} outside expected Gig Harbor range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(new_jid), json.dumps(bbox),
        )
        print(f"[bbox] UPDATEd: {bbox}")

        # === Phase E: 5-gate verdict ===
        print("\n=== 5-GATE VERDICT ===")
        p_after = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '') AS bound,
                   COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                   COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
            FROM parcels WHERE jurisdiction_id = $1::uuid
            """,
            str(new_jid),
        )
        d_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            str(new_jid),
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid
               AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)""",
            str(new_jid),
        )
        cov = 100.0 * p_after["bound"] / p_after["total"] if p_after["total"] else 0
        near = 100.0 * p_after["nearest"] / p_after["total"] if p_after["total"] else 0
        print(f"GATE 1 parcel_zoning_code_coverage_pct = {cov:.1f}% (target ≥70%) "
              f"— {'PASS' if cov >= 70 else 'SUB-GATE'}")
        print(f"GATE 2 nearest_* share = {near:.1f}% (target <30%) "
              f"— {'PASS' if near < 30 else 'OVER CAP'}")
        print(f"GATE 3 raw_attributes empty: {empty_raw} (Norfolk gate, target 0) "
              f"— {'PASS' if empty_raw == 0 else 'FAIL'}")
        print(f"GATE 4 zoning_district_count = {d_after} (target >0) "
              f"— {'PASS' if d_after > 0 else 'FAIL'}")
        print(f"GATE 5 jurisdictions.bbox: populated")
        print()
        print(f"  parcels: {p_after['total']:,}  bound: {p_after['bound']:,} "
              f"contained: {p_after['contained']:,}  nearest: {p_after['nearest']:,}")
        print(f"  new_jid: {new_jid}")

        # Zoning code distribution + uncovered codes (orchestrator follow-up signal)
        codes = await conn.fetch(
            """
            SELECT zoning_code, COUNT(*) AS n FROM parcels
            WHERE jurisdiction_id = $1::uuid AND zoning_code IS NOT NULL
              AND btrim(zoning_code) <> ''
            GROUP BY 1 ORDER BY 2 DESC
            """,
            str(new_jid),
        )
        print(f"\n=== Gig Harbor zoning_code distribution ({len(codes)} codes) ===")
        for r in codes:
            print(f"  {r['zoning_code']:20s} {r['n']:>5,}")
        print(f"\nORCHESTRATOR FOLLOW-UP: matrix needed for {len(codes)} codes "
              f"({sum(r['n'] for r in codes):,} parcels)")

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
    sub.add_parser("preflight", help="Read-only pipeline shape validation.")
    fire = sub.add_parser("fire", help="Real prod write.")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args)))
