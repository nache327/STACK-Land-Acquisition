"""Phase 7H.x — Englewood CO Class B per-muni zoning adapter.

PREP — DO NOT FIRE from this PR.

Pattern: PR #334 Winnetka single-file adapter + PATH 1 per-muni
jurisdictioning. Englewood is a municipal zoning authority inside Arapahoe
County. Current Arapahoe prod parcels have city=NULL, so this adapter uses the
City of Englewood boundary layer to split the Englewood parcel slice from the
Arapahoe umbrella by centroid containment, then loads Englewood's city zoning
district polygons.

Sources:
  Englewood zoning web experience:
    https://experience.arcgis.com/experience/246d4f9acfde4bcbb8441b1af19d167f

  Web map:
    https://www.arcgis.com/home/item.html?id=933aade897aa4b8286091a5e58fe1a23

  City boundary:
    https://services6.arcgis.com/2gwTlp6STLlfLYIT/arcgis/rest/services/AdministrativeArea/FeatureServer/0

  Base zoning district boundaries:
    https://agiso.englewoodco.gov/public/rest/services/LandUsePlanning/BaseZoningDistrictBoundaries/MapServer/0
    Code field: NEWZONE
    Name/description fields: TYPE, DSCRPT
    Probe count: 94 polygons

Ordinance / matrix support:
  Englewood UDC Chapter 4 identifies permitted and conditional uses in Table
  16-4-2. The zoning layer's Regulations_Link field points to the city zoning
  regulation document.

Idempotency:
  A fire/dry-run wraps jurisdiction registration, Englewood parcel split from
  Arapahoe, existing Englewood zoning cleanup, parcel binding reset, zoning
  insert, spatial backfill, and bbox update in one transaction. Re-running is
  safe for the dedicated Englewood jurisdiction. --dry-run rolls back the full
  rehearsal.
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
from shapely.geometry import shape
from shapely.ops import unary_union

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("englewood_co")

ARAPAHOE_JID = "5c4b612c-a5a7-47dc-af9f-b955d97c3d4e"
JURISDICTION_NAME = "Englewood, CO"
JURISDICTION_STATE = "CO"
JURISDICTION_COUNTY = "Arapahoe"
MUNI_NAME = "Englewood"
PROD_CITY_VALUE = "Englewood"
ZONING_AUTHORITY = "City of Englewood"

WEB_EXPERIENCE_URL = (
    "https://experience.arcgis.com/experience/246d4f9acfde4bcbb8441b1af19d167f"
)
WEB_MAP_URL = "https://www.arcgis.com/home/item.html?id=933aade897aa4b8286091a5e58fe1a23"
CITY_BOUNDARY_LAYER_URL = (
    "https://services6.arcgis.com/2gwTlp6STLlfLYIT/arcgis/rest/services/"
    "AdministrativeArea/FeatureServer/0"
)
ZONING_LAYER_URL = (
    "https://agiso.englewoodco.gov/public/rest/services/LandUsePlanning/"
    "BaseZoningDistrictBoundaries/MapServer/0"
)
ZONING_WHERE = "NEWZONE IS NOT NULL"
ZONING_CODE_FIELD = "NEWZONE"

# Broad Englewood / south metro sanity envelope.
BBOX_LON_RANGE = (-105.05, -104.95)
BBOX_LAT_RANGE = (39.60, 39.72)
MIN_PARCELS_FOR_FIRE = 100
PAGE_SIZE = 1000

RAW_ZONING_KEYS = (
    "OBJECTID",
    "ID",
    "ZONE_ID",
    "NEWZONE",
    "TYPE",
    "DSCRPT",
    "PUDNUM",
    "ACREAGE",
    "PERIMETER",
    "Regulations_Link",
    "Shape.STArea()",
    "Shape.STLength()",
    "GIS.DBO.BaseZoningDistrictBoundary.AREA",
)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _clean_text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_geom(geom_json: dict | None) -> Any:
    if not geom_json:
        return None
    try:
        geom = shape(geom_json)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.is_empty:
            return None
        return geom
    except Exception:
        return None


def _ensure_valid_geom(geom: Any) -> Any:
    if geom is None or geom.is_empty:
        raise ValueError("empty geometry")
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        raise ValueError("empty geometry after make_valid")
    return geom


async def _fetch_arcgis_features(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
    page_size: int = PAGE_SIZE,
    order_by: str = "OBJECTID",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(
            f"{layer_url}/query",
            params={
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": order_by,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        out.extend(batch)
        logger.info("fetched %d from %s (cum %d)", len(batch), layer_url, len(out))
        if len(batch) < page_size:
            return out
        offset += page_size


async def _fetch_count(client: httpx.AsyncClient, layer_url: str, where: str) -> int:
    response = await client.get(
        f"{layer_url}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


def _build_city_boundary(features: list[dict[str, Any]]) -> Any:
    geoms = []
    for feat in features:
        props = feat.get("properties") or {}
        city_name = _clean_text(props.get("City_Name"))
        if city_name and city_name.lower() != "englewood":
            continue
        geom = _parse_geom(feat.get("geometry"))
        if geom is not None:
            geoms.append(geom)
    if not geoms:
        raise RuntimeError("no Englewood city boundary geometry returned")
    return _ensure_valid_geom(unary_union(geoms))


def _build_zoning_rows(
    features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {"geom_skipped": 0, "blank_zone": 0}
    rows = []
    for feat in features:
        attrs = feat.get("properties") or {}
        geom = _parse_geom(feat.get("geometry"))
        if geom is None:
            stats["geom_skipped"] += 1
            continue
        zone_code = _clean_text(attrs.get(ZONING_CODE_FIELD))
        if not zone_code:
            stats["blank_zone"] += 1
            continue
        raw = {
            "source_url": ZONING_LAYER_URL,
            "source_kind": "arcgis_map_server",
            "source_filter": ZONING_WHERE,
            "web_experience_url": WEB_EXPERIENCE_URL,
            "web_map_url": WEB_MAP_URL,
            "muni_name": MUNI_NAME,
            "muni_type": "city",
            "prod_city_value": PROD_CITY_VALUE,
            "zoning_authority": ZONING_AUTHORITY,
            "ingested_at": "2026-06-23",
        }
        for key in RAW_ZONING_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]
        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            logger.warning(
                "skip zoning OBJECTID=%s: non-polygon geometry %s",
                attrs.get("OBJECTID"),
                geom.geom_type,
            )
            stats["geom_skipped"] += 1
            continue
        rows.append(
            {
                "zone_code": zone_code,
                "zone_name": (
                    _clean_text(attrs.get("DSCRPT"))
                    or _clean_text(attrs.get("TYPE"))
                    or zone_code
                ),
                "geom_wkt": geom.wkt,
                "raw_attributes": json.dumps(raw),
            }
        )
    return rows, stats


async def _resolve_or_register_jurisdiction(conn: asyncpg.Connection) -> uuid.UUID:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if existing:
        return existing["id"]
    new_jid = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, zoning_endpoint, coverage_level
        ) VALUES (
            $1::uuid, $2, $3, $4, $5, 'partial'::coverage_level_enum
        )
        """,
        str(new_jid),
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
        ZONING_LAYER_URL,
    )
    return new_jid


async def _split_parcels_from_arapahoe(
    conn: asyncpg.Connection,
    jid: uuid.UUID,
    city_boundary_wkt: str,
) -> int:
    status = await conn.execute(
        """
        UPDATE parcels
           SET jurisdiction_id = $2::uuid,
               city = $3,
               state = 'CO',
               updated_at = NOW()
         WHERE jurisdiction_id = $1::uuid
           AND geom IS NOT NULL
           AND ST_Within(
               ST_Centroid(geom),
               ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326)))
           )
        """,
        ARAPAHOE_JID,
        str(jid),
        PROD_CITY_VALUE,
        city_boundary_wkt,
    )
    return int(status.split()[-1])


async def _insert_zoning_rows(
    conn: asyncpg.Connection,
    jid: uuid.UUID,
    rows: list[dict[str, Any]],
) -> int:
    records = [
        (
            str(jid),
            row["zone_code"],
            row["zone_name"],
            row["geom_wkt"],
            row["raw_attributes"],
        )
        for row in rows
    ]
    await conn.executemany(
        """
        INSERT INTO zoning_districts (
            jurisdiction_id, zone_code, zone_name, zone_class,
            geom, raw_attributes, source
        ) VALUES (
            $1::uuid, $2, $3, 'unknown'::zone_class_enum,
            ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
            $5::jsonb, 'arcgis'::zone_source_enum
        )
        """,
        records,
    )
    return len(rows)


async def _spatial_backfill(
    conn: asyncpg.Connection,
    jid: uuid.UUID,
    nearest_meters: float,
) -> tuple[int, int]:
    contained_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
          FROM (
              SELECT p.id AS parcel_id, z.zone_class, z.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                      FROM zoning_districts zd
                     WHERE zd.jurisdiction_id = $1::uuid
                       AND zd.geom IS NOT NULL
                       AND ST_Within(ST_Centroid(p.geom), zd.geom)
                     ORDER BY zd.id
                     LIMIT 1
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        str(jid),
    )
    binding_label = f"nearest_{int(round(nearest_meters))}m"
    nearest_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = $2,
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
          FROM (
              SELECT p.id AS parcel_id, z.zone_class, z.zone_code
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
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        str(jid),
        binding_label,
        float(nearest_meters),
    )
    return int(contained_status.split()[-1]), int(nearest_status.split()[-1])


async def _update_bbox(conn: asyncpg.Connection, jid: uuid.UUID) -> list[float]:
    row = await conn.fetchrow(
        """
        SELECT
            ST_XMin(ST_Extent(geom)) AS minx,
            ST_YMin(ST_Extent(geom)) AS miny,
            ST_XMax(ST_Extent(geom)) AS maxx,
            ST_YMax(ST_Extent(geom)) AS maxy
          FROM parcels
         WHERE jurisdiction_id = $1::uuid
           AND geom IS NOT NULL
        """,
        str(jid),
    )
    if row is None or row["minx"] is None:
        raise RuntimeError("no parcel geometry for Englewood bbox")
    bbox = [float(row["minx"]), float(row["miny"]), float(row["maxx"]), float(row["maxy"])]
    if not (
        BBOX_LON_RANGE[0] <= bbox[0] <= BBOX_LON_RANGE[1]
        and BBOX_LAT_RANGE[0] <= bbox[1] <= BBOX_LAT_RANGE[1]
    ):
        raise RuntimeError(
            f"bbox {bbox} outside Englewood envelope "
            f"(lon {BBOX_LON_RANGE}, lat {BBOX_LAT_RANGE})"
        )
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        str(jid),
        json.dumps(bbox),
    )
    return bbox


async def _summarize(conn: asyncpg.Connection, jid: uuid.UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        WITH p AS (
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (
                    WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                )::int AS bound,
                COUNT(*) FILTER (WHERE zone_binding_method='contained')::int AS contained,
                COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%')::int AS nearest,
                COUNT(*) FILTER (WHERE raw IS NULL OR raw='{}'::jsonb)::int AS parcel_raw_empty
              FROM parcels
             WHERE jurisdiction_id = $1::uuid
        ),
        z AS (
            SELECT
                COUNT(*)::int AS districts,
                COUNT(DISTINCT zone_code)::int AS codes,
                COUNT(*) FILTER (
                    WHERE raw_attributes IS NULL OR raw_attributes='{}'::jsonb
                )::int AS zoning_raw_empty
              FROM zoning_districts
             WHERE jurisdiction_id = $1::uuid
        )
        SELECT * FROM p, z
        """,
        str(jid),
    )
    return dict(row)


async def _run(dry_run: bool, nearest_meters: float) -> int:
    started = time.monotonic()
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Englewood CO Class B per-muni zoning ===")
    print(f"source zoning : {ZONING_LAYER_URL}")
    print(f"source city   : {CITY_BOUNDARY_LAYER_URL}")
    print(f"source parcel : existing Arapahoe County, CO JID {ARAPAHOE_JID}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        zoning_count = await _fetch_count(client, ZONING_LAYER_URL, ZONING_WHERE)
        boundary_features = await _fetch_arcgis_features(
            client, CITY_BOUNDARY_LAYER_URL, "City_Name = 'Englewood'"
        )
        zoning_features = await _fetch_arcgis_features(
            client, ZONING_LAYER_URL, ZONING_WHERE
        )

    boundary = _build_city_boundary(boundary_features)

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        zoning_rows, zoning_stats = _build_zoning_rows(zoning_features)
        distinct_codes = sorted({r["zone_code"] for r in zoning_rows})

        print("\n[source]")
        print(f"  Englewood zoning source count : {zoning_count:,}")
        print(f"  zoning features fetched       : {len(zoning_features):,}")
        print(f"  zoning rows built             : {len(zoning_rows):,}")
        print(f"  zoning build stats            : {zoning_stats}")
        print(f"  zoning distinct codes         : {len(distinct_codes)}")
        print(f"  city boundary features        : {len(boundary_features):,}")
        print(f"  boundary bounds               : {list(boundary.bounds)}")
        try:
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = 0")

                jid = await _resolve_or_register_jurisdiction(conn)
                print(f"\n[jurisdiction] {JURISDICTION_NAME} -> {jid}")

                cleared_zoning = await conn.execute(
                    "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                    str(jid),
                )
                print(f"[idempotency] cleared {cleared_zoning.split()[-1]} zoning rows")

                reset_status = await conn.execute(
                    """
                    UPDATE parcels
                       SET zoning_code = NULL,
                           zone_class = NULL,
                           zone_binding_method = NULL,
                           updated_at = NOW()
                     WHERE jurisdiction_id = $1::uuid
                    """,
                    str(jid),
                )
                print(f"[idempotency] reset {reset_status.split()[-1]} Englewood parcels")

                moved = await _split_parcels_from_arapahoe(conn, jid, boundary.wkt)
                print(f"[parcels] moved from Arapahoe by city boundary: {moved:,}")

                parcel_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
                    str(jid),
                )
                if int(parcel_count or 0) < MIN_PARCELS_FOR_FIRE:
                    raise RuntimeError(
                        f"only {parcel_count} parcels under Englewood JID; "
                        f"minimum gate {MIN_PARCELS_FOR_FIRE}"
                    )
                print(f"[parcels] total under Englewood JID: {int(parcel_count):,}")

                inserted_zoning = await _insert_zoning_rows(conn, jid, zoning_rows)
                print(f"[zoning] inserted rows: {inserted_zoning:,}")

                contained, nearest = await _spatial_backfill(conn, jid, nearest_meters)
                print(f"[spatial] contained UPDATEd {contained:,}")
                print(f"[spatial] nearest_{int(round(nearest_meters))}m UPDATEd {nearest:,}")

                bbox = await _update_bbox(conn, jid)
                print(f"[bbox] {bbox}")

                summary = await _summarize(conn, jid)
                cov = 100.0 * summary["bound"] / summary["total"] if summary["total"] else 0.0
                near_pct = (
                    100.0 * summary["nearest"] / summary["total"]
                    if summary["total"]
                    else 0.0
                )
                print("\n=== 5-GATE PREVIEW ===")
                print(f"GATE 1 cov {cov:.1f}% (>=70%) — {'PASS' if cov >= 70 else 'SUB'}")
                print(f"GATE 2 near {near_pct:.1f}% (<30%) — {'PASS' if near_pct < 30 else 'OVER'}")
                print(
                    "GATE 3 parcel raw empty "
                    f"{summary['parcel_raw_empty']} — "
                    f"{'PASS' if summary['parcel_raw_empty'] == 0 else 'FAIL'}"
                )
                print(
                    "GATE 4 zoning raw empty "
                    f"{summary['zoning_raw_empty']} — "
                    f"{'PASS' if summary['zoning_raw_empty'] == 0 else 'FAIL'}"
                )
                print(
                    "GATE 5 districts "
                    f"{summary['districts']} / codes {summary['codes']} — "
                    f"{'PASS' if summary['districts'] > 0 and summary['codes'] > 0 else 'FAIL'}"
                )
                print(
                    f"  parcels {summary['total']:,} bound {summary['bound']:,} "
                    f"contained {summary['contained']:,} nearest {summary['nearest']:,}"
                )

                codes = await conn.fetch(
                    """
                    SELECT zoning_code, COUNT(*) AS n
                      FROM parcels
                     WHERE jurisdiction_id=$1::uuid
                       AND zoning_code IS NOT NULL
                     GROUP BY 1
                     ORDER BY 2 DESC, zoning_code
                     LIMIT 30
                    """,
                    str(jid),
                )
                print("\nTop zoning-code distribution:")
                for r in codes:
                    print(f"  {r['zoning_code']:15s} {r['n']:>8,}")

                if dry_run:
                    raise _RollbackForDryRun()

        except _RollbackForDryRun:
            print("\n(DRY-RUN — transaction rolled back; no prod writes survived)")

    finally:
        await conn.close()

    print(f"\ncompleted in {(time.monotonic() - started) / 60:.1f} min")
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the tx context manager to trigger rollback."""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline inside one transaction, then roll back.",
    )
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing — pass --dry-run for transactional rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_run(args.dry_run, args.nearest_within_meters)))
