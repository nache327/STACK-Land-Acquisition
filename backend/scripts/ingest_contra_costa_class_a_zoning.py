"""Phase 5A.2 — Contra Costa CA Class A zoning backfill via California
Statewide Zoning North.

Master authorized Phase 5A.2 after PR #250 (Phase 5A.1 — 387,492 parcels
loaded). This script is the zoning-side counterpart: it pulls Contra
Costa filtered features from California Statewide Zoning North
FeatureServer, INSERTs them into `zoning_districts`, and runs a
two-pass spatial backfill (`ST_Within` contained → `ST_DWithin`
nearest_50m fallback) scoped to the Contra Costa jurisdiction_id
(not per-city, because this is a Class A primitive — single source
covers the whole county).

Mirrors `backend/scripts/ingest_westchester_class_b_proof.py` shape
but at Class A scale:

  Westchester (Class B per-muni):
    source = county GIS layer
    filter = per-MUN ('MUN=SCD')
    backfill scope = `parcels.city = <muni>`

  Contra Costa (Class A county-wide):
    source = California Statewide Zoning North FeatureServer
    filter = County='CCO'
    backfill scope = `parcels.jurisdiction_id = <contra costa jid>`

Source:

    California Statewide Zoning North FeatureServer/1
    https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_North/FeatureServer/1

Phase 1 verdict (PR #238 / `/tmp/contra_costa_class_a_preview.md`):
  - 9,934 features for County='CCO'
  - 20 distinct Jurisdiction values
  - 578 distinct Code values
  - bbox overlap 95.6 %
  - 1,000-row ST_Within sample match 71.1 %

Subcommands:

  preflight  Read-only transactional ROLLBACK. Pulls features, builds
             zoning_districts rows, INSERTs into BEGIN..ROLLBACK
             transaction, runs the strengthened Class A gates (bbox
             ≥50 %, 1,000-row sample ≥50 %, full-sweep ≥70 % ideal).
             Reports verdicts. NO PROD WRITES SURVIVE.

  fire       Real prod write. Requires --i-know-this-writes-to-prod.
             INSERTs zoning_districts rows + two-pass spatial backfill
             scoped to jurisdiction_id.

Hard rules honoured:
  - raw_attributes preserved (Norfolk gate)
  - municipality unchanged from Phase 5A.1 (this script only writes
    zoning_code + zone_class + zone_binding_method)
  - One refresh per task (operator fires manually at end)
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

# Repo root .env carries the prod Supabase connection string.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("contra_costa_class_a")

DIRECTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "contra_costa_ca_zoning_directory.json"
# Registered in PR #250 (Phase 5A.1).
CONTRA_COSTA_JID = uuid.UUID("7ad622d4-0d36-4fe5-ad8b-53352bdac162")
ARCGIS_PAGE_SIZE = 1000
GATE_BBOX_PCT_MIN = 50.0
GATE_ST_WITHIN_PCT_MIN = 50.0


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


# ────────────────────────────────────────────────────────────────────────────
# Directory + ArcGIS fetch
# ────────────────────────────────────────────────────────────────────────────


def _load_directory_entry() -> dict[str, Any]:
    directory = json.loads(DIRECTORY_PATH.read_text())
    if not directory:
        raise SystemExit(f"{DIRECTORY_PATH.name} is empty")
    return directory[0]


async def _fetch_arcgis_features(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull all features for the directory entry's filter, paginated.

    California Statewide Zoning North is a FeatureServer; same paginated
    query-params shape as the Westchester adapter's MapServer fetch.
    """
    base_url = source["url"]
    where = source["filter_query"]
    out_sr = source.get("out_sr", 4326)
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": out_sr,
                "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE,
                "f": "json",
            }
            r = await client.get(f"{base_url}/query", params=params)
            r.raise_for_status()
            payload = r.json()
            batch = payload.get("features", [])
            features.extend(batch)
            logger.info(
                "fetched %d features (cumulative %d) offset=%d",
                len(batch), len(features), offset,
            )
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _arcgis_rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """ArcGIS rings → WKT via shapely with winding-direction detection.

    Mirrors the Westchester adapter (`_arcgis_rings_to_wkt` at
    backend/scripts/ingest_westchester_class_b_proof.py:131).
    """
    def _signed_area(ring: list[list[float]]) -> float:
        s = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            s += (x2 - x1) * (y2 + y1)
        return s

    polys: list[Polygon] = []
    has_outer = any(_signed_area(r) < 0 for r in rings)
    if has_outer:
        current_outer: list[list[float]] | None = None
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
        raise ValueError("rings produced no polygons")
    geom = MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return geom.wkt


def _build_zoning_district_rows(
    entry: dict[str, Any],
    features: list[dict[str, Any]],
    jurisdiction_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Convert ArcGIS features → zoning_districts insert payload.

    Preserves the directory's `raw_attributes_passthrough` set verbatim
    in raw_attributes (Norfolk gate).
    """
    field_map = entry["zoning_district_source"]["field_map"]
    passthrough = entry["zoning_district_source"]["raw_attributes_passthrough"]
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
            "source_url": entry["zoning_district_source"]["url"],
            "source_filter": entry["zoning_district_source"]["filter_query"],
            "source_kind": entry["zoning_district_source"]["kind"],
            "ingested_at": "2026-06-15",
            "scope": entry.get("scope"),
            "county_jurisdiction_name": entry.get("county_jurisdiction_name"),
            "ordinance_url": entry.get("ordinance_url"),
            "vintage": entry.get("vintage"),
        }
        for f_name in passthrough:
            if f_name in attrs:
                raw_attributes[f_name] = attrs[f_name]
        try:
            wkt = _arcgis_rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping feature OBJECTID=%s, ring parse failed: %s",
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


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight (transactional ROLLBACK)
# ────────────────────────────────────────────────────────────────────────────


async def _preflight(entry: dict[str, Any]) -> int:
    """Read-only pre-flight + transactional dry-run against prod."""
    print(f"\n=== PRE-FLIGHT: Contra Costa CA Class A zoning backfill ===\n")
    features = await _fetch_arcgis_features(entry["zoning_district_source"])
    rows = _build_zoning_district_rows(entry, features, CONTRA_COSTA_JID)
    distinct_zones = sorted({r["zone_code"] for r in rows})
    distinct_jurs = sorted({
        json.loads(r["raw_attributes"]).get("Jurisdiction") or "(null)"
        for r in rows
    })
    print(f"features fetched : {len(features)}")
    print(f"rows built       : {len(rows)}")
    print(f"distinct codes   : {len(distinct_zones)}")
    print(f"distinct Jurisdiction values: {len(distinct_jurs)}")
    print(f"  → {distinct_jurs}")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=1800,
    )
    try:
        await conn.execute("BEGIN")
        await conn.execute("SET LOCAL statement_timeout = 0")
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

        # Gate 1: bbox overlap (district bbox / parcel bbox).
        bbox_pct = await conn.fetchval(
            """
            WITH d AS (
                SELECT ST_SetSRID(ST_Extent(geom)::geometry, 4326) AS bb
                FROM zoning_districts
                WHERE jurisdiction_id = $1::uuid
            ),
            p AS (
                SELECT ST_SetSRID(ST_Extent(geom)::geometry, 4326) AS bb
                FROM parcels
                WHERE jurisdiction_id = $1::uuid
            )
            SELECT ROUND((ST_Area(ST_Intersection(d.bb, p.bb))
                / NULLIF(ST_Area(p.bb), 0) * 100)::numeric, 1)
            FROM d, p
            """, str(CONTRA_COSTA_JID),
        )

        # Gate 2: ST_Within match rate on 1,000-row random sample.
        match_pct = await conn.fetchval(
            """
            WITH sample AS (
                SELECT id, geom FROM parcels
                WHERE jurisdiction_id = $1::uuid
                  AND (zoning_code IS NULL OR btrim(zoning_code) = '')
                  AND geom IS NOT NULL
                ORDER BY random()
                LIMIT 1000
            )
            SELECT ROUND((100.0 * COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND ST_Within(ST_Centroid(s.geom), zd.geom)
                )
            ) / NULLIF(COUNT(*), 0))::numeric, 1)
            FROM sample s
            """, str(CONTRA_COSTA_JID),
        )

        # Coverage prediction: full-sweep ST_Within (would-be contained-only).
        coverage_pct = await conn.fetchval(
            """
            SELECT ROUND((100.0 * COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                )
            ) / NULLIF(COUNT(*), 0))::numeric, 1)
            FROM parcels p
            WHERE p.jurisdiction_id = $1::uuid
              AND p.geom IS NOT NULL
            """, str(CONTRA_COSTA_JID),
        )

        print(f"\n--- strengthened Class A gates (PR #216) ---")
        print(f"  district bbox / parcel bbox : {bbox_pct} %  (gate: >= {GATE_BBOX_PCT_MIN} %)")
        print(f"  1,000-row ST_Within match   : {match_pct} %  (gate: >= {GATE_ST_WITHIN_PCT_MIN} %)")
        print(f"\n--- coverage prediction (would-be contained-only) ---")
        print(f"  full-sweep ST_Within match  : {coverage_pct} %  (gate: >= 70 %)")

        await conn.execute("ROLLBACK")
        print("\n(transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    gates_pass = (
        bbox_pct is not None and float(bbox_pct) >= GATE_BBOX_PCT_MIN
        and match_pct is not None and float(match_pct) >= GATE_ST_WITHIN_PCT_MIN
    )
    return 0 if gates_pass else 1


# ────────────────────────────────────────────────────────────────────────────
# Fire (writes to prod)
# ────────────────────────────────────────────────────────────────────────────


async def _fire(entry: dict[str, Any], nearest_within_meters: float = 50.0) -> int:
    """Real prod write — INSERTs zoning_districts + spatial backfill.

    Two-pass mirrors PR #233's adapter:
      1. ST_Within (centroid contained in district) → zone_binding_method='contained'
      2. ST_DWithin nearest within `nearest_within_meters` m →
         zone_binding_method='nearest_<N>m'

    Scope: `parcels.jurisdiction_id = CONTRA_COSTA_JID` (county-wide,
    not per-city).
    """
    print(f"\n=== FIRE: Contra Costa CA Class A zoning backfill ===\n")
    features = await _fetch_arcgis_features(entry["zoning_district_source"])
    rows = _build_zoning_district_rows(entry, features, CONTRA_COSTA_JID)
    print(f"features fetched : {len(features)}")
    print(f"rows to insert   : {len(rows)}")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        # Phase 1 — INSERT zoning_districts.
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
        print(f"INSERTed {len(rows)} zoning_districts rows")

        # Pass 1: ST_Within (centroid contained).
        status_contained = await conn.execute(
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
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """, str(CONTRA_COSTA_JID),
        )
        try:
            n_contained = int(status_contained.split()[-1])
        except (ValueError, IndexError):
            n_contained = -1
        print(f"Pass 1 contained: UPDATEd {n_contained} parcels")

        # Pass 2: ST_DWithin nearest fallback for the remainder.
        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        status_nearest = await conn.execute(
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
                    )
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
                  AND p.zone_binding_method IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(CONTRA_COSTA_JID), binding_label, float(nearest_within_meters),
        )
        try:
            n_nearest = int(status_nearest.split()[-1])
        except (ValueError, IndexError):
            n_nearest = -1
        print(f"Pass 2 {binding_label}: UPDATEd {n_nearest} parcels")
    finally:
        await conn.close()

    print(
        "\nNext step (operator): POST /api/admin/coverage/refresh"
        f"?jurisdiction_id={CONTRA_COSTA_JID}"
        " — fire ONCE per dispatch hard rule."
    )
    return 0


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes "
             "zoning_districts + parcels rows on prod.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    entry = _load_directory_entry()

    if args.cmd == "preflight":
        return asyncio.run(_preflight(entry))
    elif args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing to fire without --i-know-this-writes-to-prod",
                  file=sys.stderr)
            return 2
        return asyncio.run(_fire(entry))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
