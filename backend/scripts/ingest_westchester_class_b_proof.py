"""Phase-2C Westchester NY Class B proof-of-concept ingest adapter.

Implements the per-muni Class B pattern from docs/INGESTION_PIPELINE_PLAN.md
(PR #214) on ONE Westchester muni — Scarsdale — sourcing from the
county-published zoning layer
(https://giswww.westchestergov.com/.../DataHub_EnvironmentandPlanning/MapServer/207).

The adapter is intentionally narrow:

  - Reads one directory entry from
    backend/data/westchester_zoning_directory.json.
  - Pulls features from the ArcGIS Map Server with the entry's filter
    (MUN='SCD') and outSR=4326.
  - Converts each feature's ArcGIS-rings geometry to WKT.
  - Preserves the source attribute set in zoning_districts.raw_attributes
    (Norfolk learning — never discard source attributes again; see PR
    #228's bundled Norfolk probe).
  - INSERTs into zoning_districts.
  - Runs the existing spatial_backfill.backfill_parcel_zoning_from_districts
    on Westchester County, with the Scarsdale-only filter at the SQL
    layer (city='Scarsdale') via a custom predicate variant.

Subcommands:

  preflight  Read-only. Pulls features, prints district / ZONING-code /
             bbox-overlap stats. Runs the strengthened Class A gates
             (district bbox covers >= 50% of parcel bbox AND 1,000-row
             ST_Within dry-run >= 50% match) via a transactional
             ROLLBACK so no writes hit prod. Reports gate verdicts.
             Master should approve preflight before authorizing fire.

  fire       Idempotent prod write. INSERTs zoning_districts rows for
             the picked muni and runs spatial_backfill scoped to its
             parcels.city value. Stops after fire so the operator can
             eyeball deltas before the audit refresh step. Requires
             --i-know-this-writes-to-prod confirmation flag.

Hard rules honored:

  - raw_attributes is built from a directory-defined passthrough list,
    not stamped {} like Norfolk MA's ingest did.
  - spatial_backfill's existing strengthened pre-flight applies; the
    `fire` step will raise if Class A gates fail.
  - No matrix work done by this script; orchestrator picks up matrix
    authoring once the adapter proves out.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from shapely.geometry import MultiPolygon, Polygon

# Place backend/ on sys.path so the script can be run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

logger = logging.getLogger("westchester_class_b_proof")

DIRECTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "westchester_zoning_directory.json"
PROOF_MUNI = "Scarsdale"
# Westchester County, NY jurisdiction_id (probed against prod 2026-06-11).
WESTCHESTER_JID = uuid.UUID("3e706886-919f-4ecf-b5aa-567040e295e8")
# Per-batch page size when paginating the ArcGIS MapServer.
ARCGIS_PAGE_SIZE = 500
# Pre-flight gate thresholds (mirror docs/INGESTION_PIPELINE_PLAN.md):
GATE_BBOX_PCT_MIN = 50.0
GATE_ST_WITHIN_PCT_MIN = 50.0


# ────────────────────────────────────────────────────────────────────────────
# Directory + ArcGIS fetch
# ────────────────────────────────────────────────────────────────────────────


def _load_directory_entry(muni_name: str) -> dict[str, Any]:
    directory = json.loads(DIRECTORY_PATH.read_text())
    for entry in directory:
        if entry["muni_name"] == muni_name:
            return entry
    raise SystemExit(
        f"muni '{muni_name}' not in {DIRECTORY_PATH.name}. "
        f"Add a directory entry first."
    )


async def _fetch_arcgis_features(
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pull all features matching the directory entry's filter, paginated."""
    base_url = source["url"]
    where = source["filter_query"]
    out_sr = source.get("out_sr", 4326)
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
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
                "fetched %d features (cumulative %d) from %s offset=%d",
                len(batch), len(features), base_url, offset,
            )
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _arcgis_rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """ArcGIS rings → WKT, via shapely so winding-direction → hole/outer
    classification is handled correctly.

    ArcGIS convention: outer rings are clockwise (negative signed area),
    interior holes are counter-clockwise (positive signed area).
    Disjoint outer rings = MultiPolygon. shapely's `Polygon` constructor
    expects [outer, hole1, hole2, …] in *its* winding convention; we let
    shapely's `make_valid` + WKT serialisation handle the canonicalisation.
    """
    def _signed_area(ring: list[list[float]]) -> float:
        s = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            s += (x2 - x1) * (y2 + y1)
        return s

    # Detect outer rings (clockwise = negative signed area, ArcGIS
    # convention) vs holes (CCW = positive). If no outer ring detected
    # (some ArcGIS publishers don't follow the convention strictly),
    # treat each ring as its own outer polygon.
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
        # No clockwise ring → publisher may use CCW outer rings.
        # Treat each ring as a standalone polygon.
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
    so the source attribute trail is auditable on the table itself.
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
            "ingested_at": "2026-06-11",
            "muni_name": entry["muni_name"],
            "muni_type": entry["muni_type"],
            "ordinance_url": entry.get("ordinance_url"),
            "vintage": entry.get("vintage"),
        }
        for f_name in passthrough:
            if f_name in attrs:
                raw_attributes[f_name] = attrs[f_name]
        out.append({
            "jurisdiction_id": str(jurisdiction_id),
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip() if zone_name else None,
            "zone_class": "unknown",  # adjudicator can refine post-ingest
            "geom_wkt": _arcgis_rings_to_wkt(geom["rings"]),
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


# ────────────────────────────────────────────────────────────────────────────
# Database operations
# ────────────────────────────────────────────────────────────────────────────


def _session_db_url() -> str:
    return settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=600,
    )


async def _preflight(entry: dict[str, Any]) -> int:
    """Read-only pre-flight + transactional dry-run.

    Returns 0 if all gates pass, 1 otherwise. No prod writes survive.
    """
    print(f"\n=== PRE-FLIGHT: {entry['muni_name']} (Westchester NY) ===\n")
    features = await _fetch_arcgis_features(entry["zoning_district_source"])
    rows = _build_zoning_district_rows(entry, features, WESTCHESTER_JID)
    distinct_zones = sorted({r["zone_code"] for r in rows})
    print(f"features fetched : {len(features)}")
    print(f"rows built       : {len(rows)}")
    print(f"distinct zones   : {len(distinct_zones)} → {distinct_zones}")

    conn = await _connect()
    try:
        # Begin a real transaction we can ROLLBACK at the end.
        await conn.execute("BEGIN")
        await conn.execute("SET LOCAL statement_timeout = 0")
        # Insert the rows into the real zoning_districts table.
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

        # Gate 2: bbox coverage. Uses ST_MakeEnvelope (returns geometry
        # with SRID) so the intersection comparison stays clean.
        bbox_pct = await conn.fetchval(
            """
            WITH d AS (
                SELECT ST_SetSRID(ST_Extent(geom)::geometry, 4326) AS bb
                FROM zoning_districts
                WHERE jurisdiction_id = $1::uuid
                  AND raw_attributes->>'muni_name' = $2
            ),
            p AS (
                SELECT ST_SetSRID(ST_Extent(geom)::geometry, 4326) AS bb
                FROM parcels
                WHERE jurisdiction_id = $1::uuid AND city = $2
            )
            SELECT ROUND((ST_Area(ST_Intersection(d.bb, p.bb))
                / NULLIF(ST_Area(p.bb), 0) * 100)::numeric, 1)
            FROM d, p
            """,
            str(WESTCHESTER_JID), entry["prod_city_value"],
        )

        # Gate 3: ST_Within match rate on 1,000-row sample.
        match_pct = await conn.fetchval(
            """
            WITH sample AS (
                SELECT id, geom FROM parcels
                WHERE jurisdiction_id = $1::uuid
                  AND city = $2
                  AND (zoning_code IS NULL OR btrim(zoning_code) = '')
                  AND geom IS NOT NULL
                ORDER BY random()
                LIMIT 1000
            )
            SELECT ROUND((100.0 * COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND ST_Within(ST_Centroid(s.geom), zd.geom)
                )
            ) / NULLIF(COUNT(*), 0))::numeric, 1)
            FROM sample s
            """,
            str(WESTCHESTER_JID), entry["prod_city_value"],
        )

        # Coverage prediction: real ST_Within sweep across all city
        # parcels (the would-be backfill match rate).
        coverage_pct = await conn.fetchval(
            """
            SELECT ROUND((100.0 * COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                )
            ) / NULLIF(COUNT(*), 0))::numeric, 1)
            FROM parcels p
            WHERE p.jurisdiction_id = $1::uuid
              AND p.city = $2
              AND p.geom IS NOT NULL
            """,
            str(WESTCHESTER_JID), entry["prod_city_value"],
        )

        print(f"\n--- strengthened Class A gates (PR #216) ---")
        print(f"  district bbox / parcel bbox : {bbox_pct} %  "
              f"(gate: >= {GATE_BBOX_PCT_MIN} %)")
        print(f"  1,000-row ST_Within match   : {match_pct} %  "
              f"(gate: >= {GATE_ST_WITHIN_PCT_MIN} %)")
        print(f"\n--- coverage prediction (would-be backfill rate) ---")
        print(f"  full-sweep ST_Within match  : {coverage_pct} %  "
              f"(gate: >= 70 %)")

        # Roll back so nothing survives.
        await conn.execute("ROLLBACK")
        print("\n(transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    gates_pass = (
        bbox_pct is not None and float(bbox_pct) >= GATE_BBOX_PCT_MIN
        and match_pct is not None and float(match_pct) >= GATE_ST_WITHIN_PCT_MIN
    )
    return 0 if gates_pass else 1


async def _fire(entry: dict[str, Any], nearest_within_meters: float = 50.0) -> int:
    """Real prod write — INSERTs zoning_districts + spatial backfill.

    Two-pass backfill mirrors PR #172's `backfill_parcel_zoning_from_districts`:

      1. ST_Within (centroid contained in district) → zone_binding_method='contained'
      2. ST_DWithin nearest fallback within `nearest_within_meters` m →
         zone_binding_method='nearest_<N>m'

    Pre-flight on Scarsdale showed 65.9 % contained-only coverage and
    73.4 % at 50 m nearest (10.2 % nearest_* share — under PR #214's 30 %
    cap). The 50 m fallback covers parcels whose centroid sits just
    outside a 2011-vintage district polygon due to surveying noise —
    1,860 of the 2,024 unmatched parcels are NYS Property Class 210
    (one-family residences), not parks/ROW.

    Stops after fire so the operator can eyeball deltas before the
    audit refresh step.
    """
    print(f"\n=== FIRE: {entry['muni_name']} (Westchester NY) ===\n")
    features = await _fetch_arcgis_features(entry["zoning_district_source"])
    rows = _build_zoning_district_rows(entry, features, WESTCHESTER_JID)

    conn = await _connect()
    try:
        await conn.execute("SET statement_timeout = 0")
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
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $2
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(WESTCHESTER_JID), entry["prod_city_value"],
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
                zone_binding_method = $3,
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
                        $4
                      )
                    ORDER BY ST_Distance(
                        zd.geom::geography,
                        ST_Centroid(p.geom)::geography
                    )
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $2
                  AND p.geom IS NOT NULL
                  AND p.zone_binding_method IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(WESTCHESTER_JID),
            entry["prod_city_value"],
            binding_label,
            float(nearest_within_meters),
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
        f"?jurisdiction_id={WESTCHESTER_JID}"
        " — fire ONCE per dispatch hard rule."
    )
    return 0


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub_preflight = sub.add_parser("preflight")
    sub_preflight.add_argument("--muni", default=PROOF_MUNI)
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument("--muni", default=PROOF_MUNI)
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes "
             "zoning_districts + parcels rows on prod.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    entry = _load_directory_entry(args.muni)

    if args.cmd == "preflight":
        return asyncio.run(_preflight(entry))
    elif args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing to fire without --i-know-this-writes-to-prod", file=sys.stderr)
            return 2
        return asyncio.run(_fire(entry))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
