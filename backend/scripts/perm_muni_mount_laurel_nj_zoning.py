"""Mount Laurel NJ Class B per-muni GovPilot adapter (PREP - DO NOT FIRE).

NACHE HAND-OFF proof for the first GovPilot-backed municipal adapter.

Pattern: PR #334 Winnetka Class B adapter + PATH 1 per-muni jurisdiction
move from the Burlington County umbrella.

Context from diagnostic PR #369:
  - Burlington County umbrella remains denominator-wedged.
  - Mount Laurel has 18,518 Burlington parcels, 0 populated zoning_code.
  - GovPilot public map exposes a parcel-detail `ZONING` field and a
    queryable `ZM` / `Zoning Map` polygon layer.

GovPilot source pattern:
  - Public map page: https://map.govpilot.com/map/NJ/mountlaurel
  - MAPDATA values from the page:
      uid=6968, pst=NJ, GCID=14, GMID=136, center=(-74.88995399, 39.96492797)
  - Layer list:
      POST /api/v1/cmd/get/017 with body [136]
      returns CODE="ZM", DESC="Zoning Map".
  - Zoning polygons:
      POST /api/v1/cmd/get/015 with body [136, "ZM", "<area ring>"]
      where area ring is raw "lon lat,lon lat,..." text, not WKT.
      Records carry `geoshape` JSON plus `DESC` text like
      `ZONE:B Business|ZONE2:B|`.
  - Parcel shells:
      POST /api/v1/cmd/get/GET-PARCELS with body [6968, "NJ", 14, 136, area]
  - Parcel details:
      POST /api/v1/cmd/get/025S with body ["MPNJ", "<parcel ID>"]
      Details include `ZONING`, but the polygon ZONE2 codes are the
      authoritative district-code source for this adapter. Parcel-detail
      sampling is retained in --preflight as a freshness check.

This script:
  1. Registers/updates `Mount Laurel Township, NJ` as a per-muni jurisdiction.
  2. Moves Burlington umbrella parcels with `city='Mount Laurel township'`.
  3. Extracts GovPilot `ZM` zoning polygons from the target parcel extent.
  4. Deletes/reinserts Mount Laurel zoning_districts.
  5. Resets parcel zoning bindings and spatially backfills by centroid.
  6. Updates the Mount Laurel bbox from moved parcels.

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
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("mount_laurel_nj")

ADAPTER_NAME = "perm_muni_mount_laurel_nj_zoning"
SOURCE_DATE = "2026-06-24"

BURLINGTON_JID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"
JURISDICTION_NAME = "Mount Laurel Township, NJ"
JURISDICTION_STATE = "NJ"
JURISDICTION_COUNTY = "Burlington"
MUNI_NAME = "Mount Laurel township"
MUNI_TYPE = "township"
PROD_CITY_VALUE = "Mount Laurel township"

GOVPILOT_MAP_URL = "https://map.govpilot.com/map/NJ/mountlaurel"
GOVPILOT_CMD_BASE = "https://map.govpilot.com/api/v1/cmd/get"
GOVPILOT_UID = 6968
GOVPILOT_PST = "NJ"
GOVPILOT_GCID = 14
GOVPILOT_GMID = 136
GOVPILOT_LAYER_CODE = "ZM"
GOVPILOT_DETAIL_TABLE = "MPNJ"
GOVPILOT_CENTER_LON = -74.889953993705475
GOVPILOT_CENTER_LAT = 39.964927968460294
GOVPILOT_PREFLIGHT_DELTA = 0.05

ORDINANCE_URL = "https://ecode360.com/MO0610"
MIN_PARCELS_FOR_FIRE = 100

# Broad Mount Laurel sanity envelope.
BBOX_LON = (-75.02, -74.75)
BBOX_LAT = (39.86, 40.08)


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


def _area_ring_from_bounds(
    bounds: tuple[float, float, float, float],
    buffer: float = 0.002,
) -> str:
    minx, miny, maxx, maxy = bounds
    minx -= buffer
    miny -= buffer
    maxx += buffer
    maxy += buffer
    return (
        f"{maxx} {miny},"
        f"{maxx} {maxy},"
        f"{minx} {maxy},"
        f"{minx} {miny},"
        f"{maxx} {miny}"
    )


def _preflight_area_ring(delta: float = GOVPILOT_PREFLIGHT_DELTA) -> str:
    return _area_ring_from_bounds(
        (
            GOVPILOT_CENTER_LON - delta,
            GOVPILOT_CENTER_LAT - delta,
            GOVPILOT_CENTER_LON + delta,
            GOVPILOT_CENTER_LAT + delta,
        ),
        buffer=0.0,
    )


def _shape_from_govpilot(
    geoshape: str | dict[str, Any] | None,
) -> Polygon | MultiPolygon | None:
    if not geoshape:
        return None
    try:
        payload = json.loads(geoshape) if isinstance(geoshape, str) else geoshape
        rings = payload.get("Rings") or []
        polygons: list[Polygon] = []
        for ring in rings:
            pts = ring.get("Points") or []
            coords = [
                (float(pt["X"]), float(pt["Y"]))
                for pt in pts
                if "X" in pt and "Y" in pt
            ]
            if len(coords) < 4:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            poly = Polygon(coords)
            if poly.is_empty:
                continue
            polygons.append(poly)
        if not polygons:
            return None
        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        geom = make_valid(geom)
        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            return geom
        if isinstance(geom, GeometryCollection):
            parts = [
                part
                for part in geom.geoms
                if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
            ]
            if parts:
                flat: list[Polygon] = []
                for part in parts:
                    if isinstance(part, Polygon):
                        flat.append(part)
                    else:
                        flat.extend(list(part.geoms))
                return MultiPolygon(flat)
    except Exception:
        return None
    return None


def _desc_parts(desc: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (desc or "").split("|"):
        if ":" in part:
            key, value = part.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def _zone_class(zone: str) -> str:
    z = zone.upper().strip()
    if z.startswith("R") or z in {"MH-MF", "BR-MF", "FR-MX"}:
        return "residential"
    if z in {"B", "NC", "MCD", "ORC", "O-2", "O-3"}:
        return "commercial"
    if z in {"I", "SRI"}:
        return "industrial"
    if z in {"SAAD"}:
        return "special"
    return "unknown"


async def _govpilot_post(
    client: httpx.AsyncClient,
    command: str,
    body: list[Any],
) -> list[dict[str, Any]]:
    response = await client.post(f"{GOVPILOT_CMD_BASE}/{command}", json=body)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"GovPilot {command} failed: {payload}")
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise RuntimeError(f"GovPilot {command} returned non-list data: {payload}")
    return data


async def _fetch_layers(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return await _govpilot_post(client, "017", [GOVPILOT_GMID])


async def _fetch_zoning_polygons(
    client: httpx.AsyncClient,
    area_ring: str,
) -> list[dict[str, Any]]:
    return await _govpilot_post(
        client,
        "015",
        [GOVPILOT_GMID, GOVPILOT_LAYER_CODE, area_ring],
    )


async def _fetch_parcel_shells(
    client: httpx.AsyncClient,
    area_ring: str,
) -> list[dict[str, Any]]:
    return await _govpilot_post(
        client,
        "GET-PARCELS",
        [GOVPILOT_UID, GOVPILOT_PST, GOVPILOT_GCID, GOVPILOT_GMID, area_ring],
    )


async def _fetch_parcel_detail(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> dict[str, Any] | None:
    data = await _govpilot_post(client, "025S", [GOVPILOT_DETAIL_TABLE, parcel_id])
    return data[0] if data else None


def _zoning_rows(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    stats = {"missing_zone_or_geom": 0}
    seen: set[tuple[str, bytes]] = set()
    for rec in records:
        parts = _desc_parts(_text(rec.get("DESC")))
        zone = (
            _text(parts.get("ZONE2"))
            or _text(parts.get("ZONE"))
            or _text(rec.get("LABEL"))
        )
        geom = _shape_from_govpilot(rec.get("geoshape"))
        if not zone or geom is None:
            stats["missing_zone_or_geom"] += 1
            continue
        geom_wkb = wkb_dumps(geom, hex=False, srid=4326)
        dedupe_key = (zone, geom_wkb)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        raw = {
            "adapter": ADAPTER_NAME,
            "source_url": GOVPILOT_MAP_URL,
            "source_kind": "govpilot_zoning_map",
            "source_command": "015",
            "source_layer_code": GOVPILOT_LAYER_CODE,
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": MUNI_TYPE,
            "prod_city_value": PROD_CITY_VALUE,
            "ordinance_url": ORDINANCE_URL,
            "desc_parts": parts,
            "source_attributes": rec,
        }
        rows.append({
            "zone_code": zone,
            "zone_name": _text(parts.get("ZONE")) or zone,
            "zone_class": _zone_class(zone),
            "geom_wkb": geom_wkb,
            "raw": json.dumps(raw),
        })
    return rows, stats


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
                       SELECT parcel_endpoint FROM jurisdictions WHERE id=$5::uuid
                   ),
                   zoning_endpoint=$3,
                   ordinance_url=$4,
                   coverage_level='partial'::coverage_level_enum
             WHERE id=$1::uuid
            """,
            jid,
            JURISDICTION_COUNTY,
            GOVPILOT_MAP_URL,
            ORDINANCE_URL,
            BURLINGTON_JID,
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
        GOVPILOT_MAP_URL,
        ORDINANCE_URL,
        BURLINGTON_JID,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _target_extent(
    conn: asyncpg.Connection,
    target_jid: str | None = None,
) -> tuple[float, float, float, float]:
    rows = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy,
               COUNT(*) AS n
          FROM parcels
         WHERE geom IS NOT NULL
           AND (
                (
                  jurisdiction_id=$1::uuid
                  AND lower(btrim(city)) = lower($2)
                )
                OR (
                  $3::uuid IS NOT NULL
                  AND jurisdiction_id=$3::uuid
                )
           )
        """,
        BURLINGTON_JID,
        PROD_CITY_VALUE,
        target_jid,
    )
    if not rows or rows["minx"] is None:
        raise SystemExit("No Mount Laurel parcel geometry found for GovPilot extent")
    return (float(rows["minx"]), float(rows["miny"]), float(rows["maxx"]), float(rows["maxy"]))


async def _path1_move_parcels(conn: asyncpg.Connection, target_jid: str) -> tuple[int, int]:
    candidates = await conn.fetchval(
        """
        SELECT COUNT(*)
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
           AND lower(btrim(city)) = lower($2)
        """,
        BURLINGTON_JID,
        PROD_CITY_VALUE,
    )
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        target_jid,
    )
    print(f"[path1] Burlington candidates city=Mount Laurel township: {int(candidates or 0):,}")
    print(f"[path1] existing Mount Laurel parcels: {int(existing or 0):,}")
    if int(candidates or 0) == 0 and int(existing or 0) < MIN_PARCELS_FOR_FIRE:
        raise SystemExit(
            "REFUSE - no Burlington Mount Laurel candidates and target JID has "
            f"{int(existing or 0)} parcels; expected about 18,518"
        )

    status = await conn.execute(
        """
        UPDATE parcels
           SET jurisdiction_id=$2::uuid,
               city=$3,
               state='NJ',
               updated_at=NOW()
         WHERE jurisdiction_id=$1::uuid
           AND lower(btrim(city)) = lower($3)
        """,
        BURLINGTON_JID,
        target_jid,
        PROD_CITY_VALUE,
    )
    moved = int(status.split()[-1])
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        target_jid,
    )
    if int(total or 0) < MIN_PARCELS_FOR_FIRE:
        raise RuntimeError(
            f"only {int(total or 0)} Mount Laurel parcels after PATH 1; aborting"
        )
    print(f"[path1] moved {moved:,}; Mount Laurel total now {int(total):,}")
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
                $6::jsonb, 'manual'::zone_source_enum
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
                     ORDER BY ST_Area(z.geom) ASC, z.id
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
        raise RuntimeError("no Mount Laurel parcel geometry after PATH 1")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
        and BBOX_LON[0] <= bbox[2] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[3] <= BBOX_LAT[1]
    ):
        raise RuntimeError(
            f"bbox {bbox} outside Mount Laurel envelope lon={BBOX_LON} lat={BBOX_LAT}"
        )
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


async def _preflight(sample_details: int) -> int:
    print("\n=== PRE-FLIGHT: Mount Laurel NJ GovPilot source shape (NO DB WRITES) ===\n")
    area = _preflight_area_ring()
    async with httpx.AsyncClient(timeout=120.0) as client:
        layers = await _fetch_layers(client)
        zoning_records = await _fetch_zoning_polygons(client, area)
        parcel_shells = await _fetch_parcel_shells(client, area)
        details = []
        for shell in parcel_shells[:sample_details]:
            detail = await _fetch_parcel_detail(client, str(shell.get("ID")))
            if detail:
                details.append(detail)

    rows, stats = _zoning_rows(zoning_records)
    zones = sorted({row["zone_code"] for row in rows})
    detail_zoning = [_text(detail.get("ZONING")) for detail in details]
    detail_nonnull = sum(1 for value in detail_zoning if value)

    print(f"layers returned       : {len(layers):,}")
    has_zm_layer = any(layer.get("CODE") == GOVPILOT_LAYER_CODE for layer in layers)
    print(f"has ZM layer          : {has_zm_layer}")
    print(f"zoning records fetched: {len(zoning_records):,}")
    print(f"zoning rows built     : {len(rows):,}")
    print(f"zoning build stats    : {stats}")
    print(f"zoning distinct codes : {len(zones)}")
    print(f"zoning sample codes   : {zones[:25]}")
    print(f"parcel shells fetched : {len(parcel_shells):,}")
    print(f"parcel details sampled: {len(details):,}")
    print(f"detail ZONING nonnull : {detail_nonnull:,}/{len(details):,}")
    print(f"detail ZONING sample  : {sorted({z for z in detail_zoning if z})[:20]}")
    print("\n(NO DB WRITES - source-only validation.)")
    return 0


async def _run(*, dry_run: bool, nearest_meters: float) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Mount Laurel NJ GovPilot per-muni adapter ===\n")
    started = time.time()

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
            JURISDICTION_NAME,
            JURISDICTION_STATE,
        )
        extent = await _target_extent(conn, str(existing["id"]) if existing else None)
        area = _area_ring_from_bounds(extent, buffer=0.004)
        print(f"[source] target extent {extent}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            zoning_records = await _fetch_zoning_polygons(client, area)
        rows, stats = _zoning_rows(zoning_records)
        print(f"[zoning] GovPilot records fetched: {len(zoning_records):,}")
        print(f"[zoning] build stats: {stats}")
        print(
            f"[zoning] rows built: {len(rows):,}; "
            f"distinct codes: {len({row['zone_code'] for row in rows})}"
        )
        if not rows:
            raise SystemExit("REFUSE - no Mount Laurel zoning rows built")

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
            print(f"[zoning] inserted {inserted:,} Mount Laurel zoning rows")

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
        help="Fetch and summarize public GovPilot sources only; no DB connection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run PATH 1 + zoning in one transaction, then roll back.",
    )
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    parser.add_argument("--sample-details", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.preflight:
        return asyncio.run(_preflight(args.sample_details))
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
