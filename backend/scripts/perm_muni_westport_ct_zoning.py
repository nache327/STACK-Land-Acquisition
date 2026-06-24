"""Westport CT Class B per-muni zoning adapter (PREP - DO NOT FIRE).

Pattern: PR #334 Winnetka Class B adapter + PATH 1 per-muni jurisdiction
move from the Fairfield CT umbrella.

Context:
  - Fairfield CT parcels are already loaded under the Fairfield County
    jurisdiction and PR #228 populated `parcels.city` from CT CAMA
    `raw->>'Town_Name'`.
  - PR #361 promoted Westport to Class B via anonymous AxisGIS public
    FeatureServer access.

Sources:
  - Parcel substrate: existing Fairfield CT umbrella parcels where
    `parcels.city = 'Westport'`.
  - Zoning: Westport AxisGIS web map layer
    `https://services5.arcgis.com/lxjwLyi2Sx6yHvMJ/arcgis/rest/services/Zoning/FeatureServer/58`
    with local code field `ZONE_`.

This script:
  1. Registers/updates `Westport, CT` as a per-muni jurisdiction.
  2. Moves Fairfield umbrella parcels with `city='Westport'` to that JID.
  3. Deletes/reinserts Westport zoning_districts.
  4. Resets parcel zoning bindings and spatially backfills by centroid.
  5. Updates the Westport bbox from moved parcels.

Idempotency:
  - The full write path runs in one transaction.
  - Re-running is safe after the first PATH 1 move: if no Fairfield
    candidates remain but Westport already has parcels, it proceeds against
    the existing Westport JID.
  - `--dry-run` runs the transaction and rolls it back.

PREP ONLY. Default invocation refuses. Do not pass
`--i-know-this-writes-to-prod` from this PR dispatch.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("westport_ct")

ADAPTER_NAME = "perm_muni_westport_ct_zoning"
SOURCE_DATE = "2026-06-24"

FAIRFIELD_CT_JID = "66230887-aabe-4d62-aebb-856939ba77bb"
JURISDICTION_NAME = "Westport, CT"
JURISDICTION_STATE = "CT"
JURISDICTION_COUNTY = "Fairfield"
MUNI_NAME = "Westport"
MUNI_TYPE = "town"
PROD_CITY_VALUE = "Westport"

ZONING_LAYER = (
    "https://services5.arcgis.com/lxjwLyi2Sx6yHvMJ/arcgis/rest/services/"
    "Zoning/FeatureServer/58"
)
ORDINANCE_URL = "https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx"
TOWN_GIS_URL = "https://www.axisgis.com/WestportCT/"

ZONING_WHERE = "ZONE_ IS NOT NULL"
ZONING_CODE_FIELD = "ZONE_"
ZONING_PAGE_SIZE = 1000
MIN_PARCELS_FOR_FIRE = 100

# Broad Westport sanity envelope. This catches wrong-town moves without
# pretending to be a tight municipal boundary.
BBOX_LON = (-73.45, -73.25)
BBOX_LAT = (41.05, 41.25)


def _session_db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL not set in environment")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _polygonal(geom_json: dict[str, Any] | None) -> Polygon | MultiPolygon | None:
    if not geom_json:
        return None
    try:
        geom = make_valid(shape(geom_json))
        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            return geom
        if isinstance(geom, GeometryCollection):
            polys: list[Polygon] = []
            for part in geom.geoms:
                if isinstance(part, Polygon):
                    polys.append(part)
                elif isinstance(part, MultiPolygon):
                    polys.extend(list(part.geoms))
            if polys:
                return MultiPolygon(polys)
    except Exception:
        return None
    return None


def _zone_class(zone: str) -> str:
    z = zone.upper().strip()
    if z in {
        "AAA",
        "AA",
        "A",
        "B",
        "PRD",
        "OSRD",
        "MHP",
        "MHZ",
        "R-AHZ",
        "R-AHZ/W",
        "R-RHOW",
    }:
        return "residential"
    if z.startswith(("GBD", "RBD", "RORD", "RPOD", "BCD", "BCRR", "BPD", "HSD")):
        return "commercial"
    if z.startswith(("DDD", "CPD")):
        return "mixed_use"
    if z.startswith(("DOSRD", "HDD")):
        return "special"
    return "unknown"


async def _fetch_count(client: httpx.AsyncClient) -> int:
    response = await client.get(
        f"{ZONING_LAYER}/query",
        params={"where": ZONING_WHERE, "returnCountOnly": "true", "f": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


async def _fetch_zoning_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(
            f"{ZONING_LAYER}/query",
            params={
                "where": ZONING_WHERE,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": ZONING_PAGE_SIZE,
                "orderByFields": "OBJECTID",
            },
            timeout=120.0,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info("fetched zoning offset=%d batch=%d total=%d", offset, len(batch), len(features))
        if len(batch) < ZONING_PAGE_SIZE:
            break
        offset += len(batch)
    return features


def _zoning_rows(features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    stats = {"missing_zone_or_geom": 0}
    for feature in features:
        attrs = feature.get("properties") or {}
        zone = _text(attrs.get(ZONING_CODE_FIELD))
        geom = _polygonal(feature.get("geometry"))
        if not zone or geom is None:
            stats["missing_zone_or_geom"] += 1
            continue
        raw = {
            "adapter": ADAPTER_NAME,
            "source_url": ZONING_LAYER,
            "source_filter": ZONING_WHERE,
            "source_kind": "arcgis_feature_server",
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": MUNI_TYPE,
            "prod_city_value": PROD_CITY_VALUE,
            "ordinance_url": ORDINANCE_URL,
            "town_gis_url": TOWN_GIS_URL,
            "source_attributes": attrs,
        }
        rows.append({
            "zone_code": zone,
            "zone_name": zone,
            "zone_class": _zone_class(zone),
            "geom_wkb": wkb_dumps(geom, hex=False, srid=4326),
            "raw": json.dumps(raw),
        })
    return rows, stats


async def _fetch_sources() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        count = await _fetch_count(client)
        print(f"[source] Westport zoning count: {count:,}")
        features = await _fetch_zoning_features(client)
    return features


async def _register_jurisdiction(conn: asyncpg.Connection) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if existing:
        jid = str(existing["id"])
        await conn.execute(
            """
            UPDATE jurisdictions
               SET county=$2,
                   parcel_source='county_gis'::parcel_source_enum,
                   parcel_endpoint=(
                       SELECT parcel_endpoint FROM jurisdictions
                       WHERE id=$5::uuid
                   ),
                   zoning_endpoint=$3,
                   ordinance_url=$4,
                   coverage_level='partial'::coverage_level_enum
             WHERE id=$1::uuid
            """,
            jid,
            JURISDICTION_COUNTY,
            ZONING_LAYER,
            ORDINANCE_URL,
            FAIRFIELD_CT_JID,
        )
        print(f"[jurisdiction] found existing {JURISDICTION_NAME}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, parcel_source, parcel_endpoint,
            zoning_endpoint, ordinance_url, coverage_level
        )
        VALUES (
            $1::uuid, $2, $3, $4, 'county_gis'::parcel_source_enum,
            (SELECT parcel_endpoint FROM jurisdictions WHERE id=$7::uuid),
            $5, $6, 'partial'::coverage_level_enum
        )
        """,
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
        ZONING_LAYER,
        ORDINANCE_URL,
        FAIRFIELD_CT_JID,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _path1_move_parcels(conn: asyncpg.Connection, westport_jid: str) -> tuple[int, int]:
    candidates = await conn.fetchval(
        """
        SELECT COUNT(*)
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
           AND lower(btrim(city)) = lower($2)
        """,
        FAIRFIELD_CT_JID,
        PROD_CITY_VALUE,
    )
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        westport_jid,
    )
    print(f"[path1] Fairfield candidates city=Westport: {int(candidates or 0):,}")
    print(f"[path1] existing Westport parcels: {int(existing or 0):,}")

    if int(candidates or 0) == 0 and int(existing or 0) < MIN_PARCELS_FOR_FIRE:
        raise SystemExit(
            "REFUSE - no Fairfield Westport candidates and Westport JID has "
            f"{int(existing or 0)} parcels; expected about 9,947"
        )

    status = await conn.execute(
        """
        UPDATE parcels
           SET jurisdiction_id=$2::uuid,
               city=$3,
               state='CT',
               updated_at=NOW()
         WHERE jurisdiction_id=$1::uuid
           AND lower(btrim(city)) = lower($3)
        """,
        FAIRFIELD_CT_JID,
        westport_jid,
        PROD_CITY_VALUE,
    )
    moved = int(status.split()[-1])
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        westport_jid,
    )
    if int(total or 0) < MIN_PARCELS_FOR_FIRE:
        raise RuntimeError(
            f"only {int(total or 0)} Westport parcels after PATH 1; aborting"
        )
    print(f"[path1] moved {moved:,}; Westport total now {int(total):,}")
    return moved, int(total or 0)


async def _insert_zoning_rows(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    jid: str,
) -> int:
    for row in rows:
        await conn.execute(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class,
                geom, raw_attributes, source
            )
            VALUES (
                $1::uuid, $2, $3, $4::zone_class_enum,
                ST_Multi(ST_MakeValid(ST_GeomFromEWKB($5))),
                $6::jsonb, 'arcgis'::zone_source_enum
            )
            """,
            jid,
            row["zone_code"],
            row["zone_name"],
            row["zone_class"],
            row["geom_wkb"],
            row["raw"],
        )
    return len(rows)


async def _reset_bindings(conn: asyncpg.Connection, jid: str) -> int:
    status = await conn.execute(
        """
        UPDATE parcels
           SET zoning_code = NULL,
               zone_class = NULL,
               zone_binding_method = NULL,
               updated_at = NOW()
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    return int(status.split()[-1])


async def _spatial_backfill(
    conn: asyncpg.Connection,
    jid: str,
    nearest_meters: float,
) -> tuple[int, int]:
    contained_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               zoning_code = sub.zone_code,
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_Within(ST_Centroid(p.geom), z.geom)
                     ORDER BY z.id
                     LIMIT 1
                ) zd
               WHERE p.jurisdiction_id=$1::uuid
                 AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
    )
    binding_label = f"nearest_{int(round(nearest_meters))}m"
    nearest_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = $2,
               zoning_code = sub.zone_code,
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_DWithin(
                           z.geom::geography,
                           ST_Centroid(p.geom)::geography,
                           $3
                       )
                     ORDER BY ST_Distance(
                         z.geom::geography,
                         ST_Centroid(p.geom)::geography
                     )
                     LIMIT 1
                ) zd
               WHERE p.jurisdiction_id=$1::uuid
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
        binding_label,
        float(nearest_meters),
    )
    return int(contained_status.split()[-1]), int(nearest_status.split()[-1])


async def _update_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    ext = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy
          FROM parcels
         WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL
        """,
        jid,
    )
    if not ext or ext["minx"] is None:
        raise RuntimeError("no Westport parcel geometry after PATH 1")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
        and BBOX_LON[0] <= bbox[2] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[3] <= BBOX_LAT[1]
    ):
        raise RuntimeError(f"bbox {bbox} outside Westport envelope lon={BBOX_LON} lat={BBOX_LAT}")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _quality_report(conn: asyncpg.Connection, jid: str) -> None:
    parcels = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (
                   WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>''
               ) AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
               COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
               COUNT(*) FILTER (WHERE raw IS NULL OR raw='{}'::jsonb) AS empty_raw
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    districts = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT zone_code) AS codes,
               COUNT(*) FILTER (
                   WHERE raw_attributes IS NULL OR raw_attributes='{}'::jsonb
               ) AS empty_raw
          FROM zoning_districts
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    total = int(parcels["total"] or 0)
    bound = int(parcels["bound"] or 0)
    nearest = int(parcels["nearest"] or 0)
    coverage = 100.0 * bound / total if total else 0.0
    nearest_pct = 100.0 * nearest / total if total else 0.0
    print("\n=== 5-GATE PREP REPORT ===")
    print(f"GATE 1 coverage {coverage:.1f}% (>=70%) - {'PASS' if coverage >= 70 else 'SUB'}")
    print(f"GATE 2 nearest {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
    print(
        f"GATE 3 parcel raw empty {parcels['empty_raw']} / "
        f"zoning raw empty {districts['empty_raw']}"
    )
    print(f"GATE 4 districts {districts['total']} / distinct codes {districts['codes']}")
    print("GATE 5 bbox populated inline")
    print(
        f"  parcels {total:,} bound {bound:,} contained {parcels['contained']:,} "
        f"nearest {nearest:,}"
    )

    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
          FROM parcels
         WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
         GROUP BY 1
         ORDER BY 2 DESC, 1
         LIMIT 40
        """,
        jid,
    )
    if codes:
        print("\nDistribution:")
        for row in codes:
            print(f"  {row['zoning_code']:14s} {row['n']:>6,}")


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Westport CT source shape (NO DB WRITES) ===\n")
    features = await _fetch_sources()
    rows, stats = _zoning_rows(features)
    zones = sorted({row["zone_code"] for row in rows})
    print(f"zoning features fetched: {len(features):,}")
    print(f"zoning rows built      : {len(rows):,}")
    print(f"zoning build stats     : {stats}")
    print(f"zoning distinct codes  : {len(zones)}")
    print(f"zoning sample codes    : {zones[:30]}")
    if features:
        props = features[0].get("properties") or {}
        print(f"zoning raw field count : {len(props)}")
        print(f"sample OBJECTID/ZONE_  : {props.get('OBJECTID')} / {props.get('ZONE_')}")
    print("\n(NO DB WRITES - source-only validation.)")
    return 0


async def _run(*, dry_run: bool, nearest_meters: float) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Westport CT Class B per-muni adapter ===\n")
    started = time.time()
    features = await _fetch_sources()
    rows, stats = _zoning_rows(features)
    print(f"[zoning] build stats: {stats}")
    print(
        f"[zoning] rows built: {len(rows):,}; "
        f"distinct codes: {len({r['zone_code'] for r in rows})}"
    )
    if not rows:
        raise SystemExit("REFUSE - no Westport zoning rows built")

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _register_jurisdiction(conn)
            await _path1_move_parcels(conn, jid)

            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(f"[idempotency] cleared {cleared.split()[-1]} zoning_district rows")
            reset = await _reset_bindings(conn, jid)
            print(f"[idempotency] reset {reset:,} parcel bindings")

            inserted = await _insert_zoning_rows(conn, rows, jid)
            print(f"[zoning] inserted {inserted:,} Westport zoning rows")

            contained, nearest = await _spatial_backfill(conn, jid, nearest_meters)
            print(f"[spatial] contained UPDATEd {contained:,}")
            print(f"[spatial] nearest_{int(round(nearest_meters))}m UPDATEd {nearest:,}")

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] {bbox}")

            await _quality_report(conn, jid)

            if dry_run:
                raise _RollbackForDryRun()
    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    elapsed = time.time() - started
    print(f"\ncompleted in {elapsed / 60:.1f} min")
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the transaction context to trigger rollback."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Fetch and summarize public zoning source only; no database connection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run PATH 1 + zoning in one transaction, then roll back.",
    )
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.preflight:
        return asyncio.run(_preflight())
    if args.dry_run:
        return asyncio.run(
            _run(dry_run=True, nearest_meters=args.nearest_within_meters)
        )
    if args.i_know_this_writes_to_prod:
        return asyncio.run(
            _run(dry_run=False, nearest_meters=args.nearest_within_meters)
        )

    print(
        "Refusing - pass --preflight for source-only validation, --dry-run for "
        "transactional rehearsal, or --i-know-this-writes-to-prod to fire.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
