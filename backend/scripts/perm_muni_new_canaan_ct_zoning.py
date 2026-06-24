"""Phase 2 Fairfield CT add-on: New Canaan Class B per-muni zoning adapter.

PREP ONLY - DO NOT FIRE without Master approval.

Per Diagnostic PR #361, New Canaan has an anonymous public Tighe & Bond
zoning layer:

  https://hostingdata3.tighebond.com/arcgis/rest/services/
      NewCanaanCT/NewCanaanDynamic/MapServer/89

Freshness check on 2026-06-24:
  - 65 zoning polygons
  - Geometry type: esriGeometryPolygon
  - Source SR: 102656 / latest 2234; server-side outSR=4326 works
  - `ZONING` and `Code` are 65/65 non-null
  - 16 distinct `Code` values: A, B, C, D, E, F, G, H, I, J, K, L, M, O, P, Q

This script follows the Winnetka PR #334 idempotency shape, but includes
New Canaan per-muni registration in the same transaction because Fairfield CT
already has county-umbrella parcels with `city='New Canaan'` from PR #228.

Pipeline:
  1. Find or create `New Canaan, CT`.
  2. Move Fairfield umbrella parcels where `city='New Canaan'` to that JID.
  3. DELETE existing New Canaan zoning_districts rows.
  4. Reset New Canaan parcel zoning bindings.
  5. INSERT zoning_districts from Tighe & Bond MapServer/89.
  6. Backfill parcels by contained centroid, then nearest_50m fallback.
  7. Populate jurisdictions.bbox inline.

Hard guards:
  - No default fire: pass --source-check, --dry-run, or --i-know-this-writes-to-prod.
  - --dry-run runs the full DB pipeline inside one transaction and rolls back.
  - Re-fire safe: district rows are DELETE-then-INSERT and parcel bindings reset.
  - No matrix writes.
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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("new_canaan_ct_zoning")

FAIRFIELD_CT_ID = "66230887-aabe-4d62-aebb-856939ba77bb"
JURISDICTION_NAME = "New Canaan, CT"
JURISDICTION_STATE = "CT"
JURISDICTION_COUNTY = "Fairfield"
MUNI_NAME = "New Canaan"
PROD_CITY_VALUE = "New Canaan"

LAYER_URL = (
    "https://hostingdata3.tighebond.com/arcgis/rest/services/"
    "NewCanaanCT/NewCanaanDynamic/MapServer/89"
)
DISCOVERY_URL = "https://hosting.tighebond.com/NewCanaanCT/"
ZONE_CODE_FIELD = "Code"
ZONE_NAME_FIELD = "ZONING"
RAW_KEYS = (
    "OBJECTID",
    "ZONING",
    "Code",
    "SHAPE_Length",
    "SHAPE_Area",
    "Shape__Length",
    "Shape__Area",
)
ARCGIS_PAGE_SIZE = 1000
MIN_PARCELS_FOR_FIRE = 100

# New Canaan source bbox from 2026-06-24 source check:
# [-73.55554, 41.11408, -73.44847, 41.21193]. Keep this as a gross
# mismatch envelope, not a tight QA bound.
BBOX_LON = (-73.58, -73.43)
BBOX_LAT = (41.09, 41.23)


def _db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL not set")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    ring_wkts: list[str] = []
    for ring in rings:
        if len(ring) < 4:
            continue
        coords = ", ".join(f"{pt[0]} {pt[1]}" for pt in ring)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


async def _fetch_features() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE,
                "f": "json",
                "orderByFields": "OBJECTID",
            }
            response = await client.get(f"{LAYER_URL}/query", params=params)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS query error: {data['error']}")
            batch = data.get("features", [])
            features.extend(batch)
            logger.info("fetched %d features (cumulative %d)", len(batch), len(features))
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


async def _fetch_layer_metadata() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(LAYER_URL, params={"f": "json"})
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"ArcGIS metadata error: {data['error']}")
        return data


def _build_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        if not geom or "rings" not in geom:
            continue

        zone_code = attrs.get(ZONE_CODE_FIELD)
        zone_name = attrs.get(ZONE_NAME_FIELD)
        if not zone_code or not str(zone_code).strip():
            continue
        if not zone_name or not str(zone_name).strip():
            continue

        try:
            geom_wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue

        raw = {
            "source_url": LAYER_URL,
            "source_discovery_url": DISCOVERY_URL,
            "source_kind": "arcgis_map_server",
            "source_filter": "1=1",
            "source_srid_native": 102656,
            "source_srid_latest": 2234,
            "requested_outSR": 4326,
            "source_checked_at": "2026-06-24",
            "muni_name": MUNI_NAME,
            "muni_type": "town",
            "publisher": "Town of New Canaan CT / Tighe & Bond hosted WebGIS",
        }
        for key in RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]

        rows.append(
            {
                "zone_code": str(zone_code).strip(),
                "zone_name": str(zone_name).strip(),
                "geom_wkt": geom_wkt,
                "raw_attributes": json.dumps(raw, sort_keys=True),
            }
        )
    return rows


async def _source_check() -> int:
    print("\n=== SOURCE CHECK: New Canaan CT zoning ===\n")
    metadata = await _fetch_layer_metadata()
    features = await _fetch_features()
    rows = _build_rows(features)

    codes = sorted({row["zone_code"] for row in rows})
    names = sorted({row["zone_name"] for row in rows})
    non_null_both = sum(
        1
        for feature in features
        if feature.get("attributes", {}).get(ZONE_CODE_FIELD)
        and feature.get("attributes", {}).get(ZONE_NAME_FIELD)
    )

    xs: list[float] = []
    ys: list[float] = []
    for feature in features:
        for ring in feature.get("geometry", {}).get("rings", []):
            for x, y in ring:
                xs.append(float(x))
                ys.append(float(y))

    print(f"  layer name      : {metadata.get('name')}")
    print(f"  geometry type   : {metadata.get('geometryType')}")
    print(f"  capabilities    : {metadata.get('capabilities')}")
    print(f"  features fetched: {len(features)}")
    print(f"  rows built      : {len(rows)}")
    print(f"  non-null fields : {non_null_both}/{len(features)} Code + ZONING")
    print(f"  distinct codes  : {len(codes)} {codes}")
    print(f"  distinct names  : {len(names)}")
    if xs:
        print(f"  bbox4326        : {[min(xs), min(ys), max(xs), max(ys)]}")
    if rows:
        sample = json.loads(rows[0]["raw_attributes"])
        print(f"  sample raw keys : {list(sample.keys())}")
    print("\n(NO DB WRITES)")
    return 0


async def _resolve_or_create_jurisdiction(conn: asyncpg.Connection) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if existing:
        jid = str(existing["id"])
        print(f"[registration] found existing jurisdiction {JURISDICTION_NAME}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO jurisdictions (id, name, state, county)
           VALUES ($1::uuid, $2, $3, $4)""",
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
    )
    print(f"[registration] created jurisdiction {JURISDICTION_NAME}: {jid}")
    return jid


async def _move_or_verify_parcels(conn: asyncpg.Connection, jid: str) -> int:
    candidates = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
           WHERE jurisdiction_id=$1::uuid AND city=$2""",
        FAIRFIELD_CT_ID,
        PROD_CITY_VALUE,
    )
    current = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    print(f"[registration] Fairfield candidates city={PROD_CITY_VALUE!r}: {candidates:,}")
    print(f"[registration] current New Canaan parcels: {current:,}")

    if candidates:
        status = await conn.execute(
            """UPDATE parcels
                  SET jurisdiction_id=$2::uuid, updated_at=NOW()
                WHERE jurisdiction_id=$1::uuid AND city=$3""",
            FAIRFIELD_CT_ID,
            jid,
            PROD_CITY_VALUE,
        )
        moved = int(status.split()[-1]) if status.split() else -1
        print(f"[registration] moved parcels: {moved:,}")
    else:
        moved = 0
        print("[registration] no Fairfield candidates to move; treating as re-fire path")

    total = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    if total < MIN_PARCELS_FOR_FIRE:
        raise RuntimeError(
            f"REFUSE FIRE - only {total} parcels under {JURISDICTION_NAME}; "
            f"expected roughly 7,386 after Fairfield city re-derivation."
        )
    print(f"[gate] {total:,} parcels under New Canaan JID")
    return int(total)


async def _update_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    extent = await conn.fetchrow(
        """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                  ST_YMin(ST_Extent(geom)) AS miny,
                  ST_XMax(ST_Extent(geom)) AS maxx,
                  ST_YMax(ST_Extent(geom)) AS maxy
           FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""",
        jid,
    )
    if extent is None or extent["minx"] is None:
        raise RuntimeError("no New Canaan parcel geometry post-move")
    bbox = [
        float(extent["minx"]),
        float(extent["miny"]),
        float(extent["maxx"]),
        float(extent["maxy"]),
    ]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
    ):
        raise RuntimeError(
            f"bbox {bbox} outside New Canaan envelope "
            f"(lon {BBOX_LON}, lat {BBOX_LAT})"
        )
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _fire(nearest_within_meters: float, dry_run: bool) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: New Canaan CT zoning (Class B per-muni) ===\n")

    features = await _fetch_features()
    rows = _build_rows(features)
    distinct = sorted({row["zone_code"] for row in rows})
    print(
        f"[source] features={len(features)} rows={len(rows)} "
        f"distinct={len(distinct)} {distinct}"
    )
    if len(rows) != 65:
        raise RuntimeError(f"expected 65 zoning rows from source; got {len(rows)}")
    if len(distinct) != 16:
        raise RuntimeError(f"expected 16 distinct source codes; got {len(distinct)}")

    conn = await asyncpg.connect(
        _db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            jid = await _resolve_or_create_jurisdiction(conn)
            await _move_or_verify_parcels(conn, jid)

            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(f"[idempotency] cleared {cleared.split()[-1]} zoning_districts")

            reset = await conn.execute(
                """UPDATE parcels
                      SET zoning_code=NULL,
                          zone_class=NULL,
                          zone_binding_method=NULL
                    WHERE jurisdiction_id=$1::uuid""",
                jid,
            )
            print(f"[idempotency] reset bindings on {reset.split()[-1]} parcels")

            print(f"[insert] inserting {len(rows)} zoning_districts")
            for row in rows:
                await conn.execute(
                    """INSERT INTO zoning_districts (
                           jurisdiction_id, zone_code, zone_name, zone_class,
                           geom, raw_attributes, source
                       ) VALUES (
                           $1::uuid, $2, $3, 'unknown'::zone_class_enum,
                           ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                           $5::jsonb, 'arcgis'::zone_source_enum
                       )""",
                    jid,
                    row["zone_code"],
                    row["zone_name"],
                    row["geom_wkt"],
                    row["raw_attributes"],
                )

            contained = await conn.execute(
                """
                UPDATE parcels target
                   SET zone_class=sub.zone_class,
                       zone_binding_method='contained',
                       zoning_code=COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT zd.zone_class, zd.zone_code
                        FROM zoning_districts zd
                        WHERE zd.jurisdiction_id=$1::uuid
                          AND zd.geom IS NOT NULL
                          AND ST_Within(ST_Centroid(p.geom), zd.geom)
                        ORDER BY zd.id
                        LIMIT 1
                    ) m
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid,
            )
            print(f"[spatial] contained UPDATEd {int(contained.split()[-1])}")

            binding_label = f"nearest_{int(round(nearest_within_meters))}m"
            nearest = await conn.execute(
                """
                UPDATE parcels target
                   SET zone_class=sub.zone_class,
                       zone_binding_method=$2,
                       zoning_code=COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT zd.zone_class, zd.zone_code
                        FROM zoning_districts zd
                        WHERE zd.jurisdiction_id=$1::uuid
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
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid,
                binding_label,
                float(nearest_within_meters),
            )
            print(f"[spatial] {binding_label} UPDATEd {int(nearest.split()[-1])}")

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] {bbox}")

            if dry_run:
                raise _RollbackForDryRun()

        parcel_stats = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (
                          WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>''
                      ) AS bound,
                      COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                      COUNT(*) FILTER (
                          WHERE zone_binding_method LIKE 'nearest_%'
                      ) AS nearest
               FROM parcels WHERE jurisdiction_id=$1::uuid""",
            jid,
        )
        districts = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
            jid,
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts
               WHERE jurisdiction_id=$1::uuid
                 AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)""",
            jid,
        )
        coverage = (
            100.0 * parcel_stats["bound"] / parcel_stats["total"]
            if parcel_stats["total"]
            else 0.0
        )
        nearest_pct = (
            100.0 * parcel_stats["nearest"] / parcel_stats["total"]
            if parcel_stats["total"]
            else 0.0
        )
        print("\n=== 5-GATE ===")
        print(f"GATE 1 cov {coverage:.1f}% (>=70%) - {'PASS' if coverage >= 70 else 'SUB'}")
        print(f"GATE 2 near {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty_raw} - {'PASS' if empty_raw == 0 else 'FAIL'}")
        print(f"GATE 4 districts {districts} - {'PASS' if districts > 0 else 'FAIL'}")
        print("GATE 5 bbox populated")
        print(
            f"  parcels {parcel_stats['total']:,} bound {parcel_stats['bound']:,} "
            f"contained {parcel_stats['contained']:,} nearest {parcel_stats['nearest']:,}"
        )

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside transaction to force rollback."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-check",
        action="store_true",
        help="Fetch live source metadata/features only; no DB connection or writes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full DB pipeline in one transaction, then rollback.",
    )
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.source_check:
        raise SystemExit(asyncio.run(_source_check()))
    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass --source-check, --dry-run, or "
            "--i-know-this-writes-to-prod.",
            file=sys.stderr,
        )
        sys.exit(2)
    raise SystemExit(
        asyncio.run(
            _fire(
                nearest_within_meters=args.nearest_within_meters,
                dry_run=args.dry_run,
            )
        )
    )
