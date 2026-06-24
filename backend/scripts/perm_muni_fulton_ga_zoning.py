"""Phase 5 PREP - Fulton GA Class B per-muni zoning adapter.

Prep-only adapter derived from PR #334's Winnetka IL Class B pattern.
DO NOT FIRE without explicit Master/Lane A greenlight.

Targets from docs/FULTON_GA_ACQUISITION_SPEC.md:

  - Sandy Springs full-muni proof:
      Fulton parcels spatial-prefiltered by Sandy Springs city limit.
      Zoning source is City of Sandy Springs GIS layer 127.
      prod_city_value = 'Sandy Springs' (PR #233 discipline).

  - Atlanta/Buckhead subarea proof:
      Fulton parcels spatial-prefiltered by Atlanta city boundary and
      approved Buckhead neighborhood geometry.
      Zoning source is City of Atlanta ZoningHosted layer 0.
      prod_city_value = 'Buckhead'; raw authority remains City of Atlanta.

Source layers:
  - Sandy Springs zoning:
      https://gis2.sandyspringsga.gov/arcgis/rest/services/
      OpenData/General_Reference/FeatureServer/127
  - Sandy Springs city limit:
      https://gis2.sandyspringsga.gov/arcgis/rest/services/
      OpenData/General_Reference/FeatureServer/107
  - Atlanta zoning:
      https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/
      ZoningHosted/FeatureServer/0
  - Atlanta city boundary:
      https://gis.atlantaga.gov/dpcd/rest/services/
      OpenDataService1/MapServer/1
  - Atlanta official neighborhoods:
      https://gis.atlantaga.gov/dpcd/rest/services/
      AdministrativeArea/GeopoliticalArea/MapServer/1

Hard rules honored:
  - PREP script only; default CLI refuses writes.
  - --dry-run performs transactional rehearsal then rolls back.
  - Fire gate refuses if Fulton JID is missing or has <100 parcels.
  - DELETE-then-INSERT inside one tx for this adapter's zoning_districts.
  - COALESCE-guarded UPDATEs for parcels.zoning_code.
  - raw_attributes preserved with ArcGIS passthrough + provenance.
  - parcels.city is set to prod_city_value, not raw authority/muni name.
  - No zone_use_matrix writes. Orchestrator owns matrix substrate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
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

logger = logging.getLogger("fulton_ga_zoning")

ADAPTER_ID = "perm_muni_fulton_ga_zoning"
FULTON_JURISDICTION_NAME = "Fulton County, GA"
MIN_PARCELS_FOR_FIRE = 100
ARCGIS_PAGE_SIZE = 1000

SANDY_SPRINGS_ZONING_URL = (
    "https://gis2.sandyspringsga.gov/arcgis/rest/services/"
    "OpenData/General_Reference/FeatureServer/127"
)
SANDY_SPRINGS_LIMIT_URL = (
    "https://gis2.sandyspringsga.gov/arcgis/rest/services/"
    "OpenData/General_Reference/FeatureServer/107"
)
ATLANTA_ZONING_URL = (
    "https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/"
    "ZoningHosted/FeatureServer/0"
)
ATLANTA_CITY_LIMIT_URL = (
    "https://gis.atlantaga.gov/dpcd/rest/services/"
    "OpenDataService1/MapServer/1"
)
ATLANTA_NEIGHBORHOODS_URL = (
    "https://gis.atlantaga.gov/dpcd/rest/services/"
    "AdministrativeArea/GeopoliticalArea/MapServer/1"
)

SANDY_RAW_KEYS = (
    "OBJECTID", "ParcelID", "Address", "Zoning", "ZoningDistrict",
    "FrontSetback", "RearSetback", "SideSetback", "SideSetbackCornerLot",
    "municode", "LotCoverage_Pct", "Shape__Area", "Shape__Length",
)
ATLANTA_RAW_KEYS = (
    "OBJECTID", "ZONECLASS", "ZONEDESC", "BASEELEV", "HEIGHT",
    "LASTUPDATE", "LASTEDITOR", "SPI", "SUBAREA", "TSA", "STATUS",
    "CASEIN", "CASEOUT", "SUNRISE", "SUNSET", "GLOBALID",
    "Shape__Area", "Shape__Length",
)
BOUNDARY_RAW_KEYS = (
    "OBJECTID", "NAME", "OLDNAME", "NPU", "ACRES", "SQMILES",
    "LOCALID", "GEOTYPE", "FULLFIPS", "SRCREF", "GLOBALID",
)

# Fulton County source envelope from the accepted acquisition spec.
BBOX_LON_RANGE = (-84.90, -84.05)
BBOX_LAT_RANGE = (33.45, 34.25)

BUCKHEAD_FILTERS = {
    "broad-npu-ab": {
        "where": "NPU IN ('A','B')",
        "description": "Official Atlanta neighborhoods in NPU A+B",
        "expected_min": 10,
    },
    "narrow-name": {
        "where": "UPPER(NAME) LIKE '%BUCKHEAD%'",
        "description": "Official Atlanta neighborhoods with Buckhead in NAME",
        "expected_min": 1,
    },
}


@dataclass(frozen=True)
class DistrictRow:
    scope: str
    prod_city_value: str
    zone_code: str
    zone_name: str
    geom_wkt: str
    raw_attributes: str


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """PR #334-compatible ArcGIS rings to WKT.

    Each valid ring becomes a polygon body; ST_MakeValid/ST_Multi in
    PostGIS handles topology normalization. Degenerate rings are skipped.
    """
    ring_wkts = []
    for ring in rings:
        if len(ring) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


async def _fetch_features(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str = "1=1",
    page_size: int = ARCGIS_PAGE_SIZE,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "json",
            "orderByFields": "OBJECTID",
        }
        r = await client.get(f"{layer_url}/query", params=params)
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(f"ArcGIS query failed for {layer_url}: {payload['error']}")
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info(
            "fetched %d (cum %d) layer=%s where=%r offset=%d",
            len(batch), len(features), layer_url, where, offset,
        )
        if len(batch) < page_size:
            break
        offset += page_size
    return features


def _build_sandy_rows(features: list[dict[str, Any]]) -> list[DistrictRow]:
    rows: list[DistrictRow] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        zone_code = attrs.get("ZoningDistrict") or attrs.get("Zoning")
        if not geom or "rings" not in geom:
            continue
        if not zone_code or not str(zone_code).strip():
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip Sandy Springs OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue
        raw = {
            "adapter": ADAPTER_ID,
            "scope": "sandy_springs",
            "source_url": SANDY_SPRINGS_ZONING_URL,
            "source_filter": "1=1",
            "source_kind": "arcgis_feature_server",
            "ingested_at": "2026-06-23",
            "authority_name": "City of Sandy Springs",
            "muni_name": "City of Sandy Springs",
            "prod_city_value": "Sandy Springs",
            "muni_type": "city",
            "ordinance_url": "https://library.municode.com/ga/sandy_springs/codes/development_code",
            "note": "Full-muni Fulton GA Class B proof; parcels.city set to prod_city_value.",
        }
        for key in SANDY_RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]
        rows.append(
            DistrictRow(
                scope="sandy_springs",
                prod_city_value="Sandy Springs",
                zone_code=str(zone_code).strip(),
                zone_name=str(attrs.get("Zoning") or zone_code).strip(),
                geom_wkt=wkt,
                raw_attributes=json.dumps(raw),
            )
        )
    return rows


def _build_atlanta_rows(features: list[dict[str, Any]], buckhead_scope: str) -> list[DistrictRow]:
    rows: list[DistrictRow] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        zone_code = attrs.get("ZONECLASS")
        if not geom or "rings" not in geom:
            continue
        if not zone_code or not str(zone_code).strip():
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip Atlanta OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue
        zone_name = attrs.get("ZONEDESC") or zone_code
        raw = {
            "adapter": ADAPTER_ID,
            "scope": "buckhead",
            "source_url": ATLANTA_ZONING_URL,
            "source_filter": "1=1, intersected with Buckhead boundary in SQL",
            "source_kind": "arcgis_feature_server",
            "ingested_at": "2026-06-23",
            "authority_name": "City of Atlanta",
            "muni_name": "City of Atlanta",
            "subarea": "Buckhead",
            "prod_city_value": "Buckhead",
            "buckhead_scope": buckhead_scope,
            "muni_type": "city_subarea",
            "ordinance_url": "https://library.municode.com/ga/atlanta/codes/code_of_ordinances",
            "note": "Atlanta authority; Buckhead is a neighborhood/subarea, not a municipality.",
        }
        for key in ATLANTA_RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]
        rows.append(
            DistrictRow(
                scope="buckhead",
                prod_city_value="Buckhead",
                zone_code=str(zone_code).strip(),
                zone_name=str(zone_name).strip(),
                geom_wkt=wkt,
                raw_attributes=json.dumps(raw),
            )
        )
    return rows


def _boundary_rows(
    features: list[dict[str, Any]],
    layer_url: str,
    source_filter: str,
    scope: str,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        if not geom or "rings" not in geom:
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip %s boundary OBJECTID=%s: %s", scope, attrs.get("OBJECTID"), exc)
            continue
        raw = {
            "adapter": ADAPTER_ID,
            "scope": scope,
            "source_url": layer_url,
            "source_filter": source_filter,
            "source_kind": "arcgis_boundary_layer",
        }
        for key in BOUNDARY_RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]
        rows.append((wkt, json.dumps(raw)))
    return rows


async def _lookup_fulton_jid(conn: asyncpg.Connection) -> str:
    jid = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state='GA'",
        FULTON_JURISDICTION_NAME,
    )
    if not jid:
        raise SystemExit(
            f"REFUSE FIRE - jurisdiction '{FULTON_JURISDICTION_NAME}' not registered."
        )
    return str(jid)


async def _gate_check(conn: asyncpg.Connection, jid: str) -> None:
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    if n < MIN_PARCELS_FOR_FIRE:
        raise SystemExit(
            f"REFUSE FIRE - only {n} parcels under Fulton JID; "
            f"threshold is {MIN_PARCELS_FOR_FIRE}."
        )
    print(f"[gate] {n:,} parcels under Fulton JID - proceeding")


async def _stage_boundary(
    conn: asyncpg.Connection,
    table_name: str,
    rows: list[tuple[str, str]],
) -> None:
    await conn.execute(
        f"""
        CREATE TEMP TABLE {table_name} (
            geom geometry(MultiPolygon, 4326),
            raw_attributes jsonb
        ) ON COMMIT DROP
        """
    )
    for wkt, raw in rows:
        await conn.execute(
            f"""
            INSERT INTO {table_name} (geom, raw_attributes)
            VALUES (
                ST_Multi(ST_MakeValid(ST_GeomFromText($1, 4326))),
                $2::jsonb
            )
            """,
            wkt, raw,
        )


async def _insert_district_rows(
    conn: asyncpg.Connection,
    jid: str,
    rows: list[DistrictRow],
    *,
    boundary_table: str | None = None,
) -> int:
    inserted = 0
    for row in rows:
        if boundary_table:
            status = await conn.execute(
                f"""
                INSERT INTO zoning_districts (
                    jurisdiction_id, zone_code, zone_name, zone_class,
                    geom, raw_attributes, source
                )
                SELECT $1::uuid, $2, $3, 'unknown'::zone_class_enum,
                    ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                    $5::jsonb, 'arcgis'::zone_source_enum
                WHERE EXISTS (
                    SELECT 1 FROM {boundary_table} b
                    WHERE ST_Intersects(
                        ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                        b.geom
                    )
                )
                """,
                jid, row.zone_code, row.zone_name, row.geom_wkt, row.raw_attributes,
            )
        else:
            status = await conn.execute(
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
                jid, row.zone_code, row.zone_name, row.geom_wkt, row.raw_attributes,
            )
        try:
            inserted += int(status.split()[-1])
        except (IndexError, ValueError):
            pass
    return inserted


async def _reset_target_parcels(conn: asyncpg.Connection, jid: str) -> int:
    status = await conn.execute(
        """
        UPDATE parcels p
           SET city = NULL,
               zoning_code = NULL,
               zone_class = NULL,
               zone_binding_method = NULL
         WHERE p.jurisdiction_id=$1::uuid
           AND (
                p.city IN ('Sandy Springs', 'Buckhead')
                OR EXISTS (
                    SELECT 1 FROM _fulton_sandy_limit b
                    WHERE ST_Within(ST_Centroid(p.geom), b.geom)
                )
                OR (
                    EXISTS (
                        SELECT 1 FROM _fulton_atlanta_limit a
                        WHERE ST_Within(ST_Centroid(p.geom), a.geom)
                    )
                    AND EXISTS (
                        SELECT 1 FROM _fulton_buckhead_boundary b
                        WHERE ST_Within(ST_Centroid(p.geom), b.geom)
                    )
                )
           )
        """,
        jid,
    )
    return int(status.split()[-1])


async def _assign_target_city_values(conn: asyncpg.Connection, jid: str) -> tuple[int, int]:
    sandy = await conn.execute(
        """
        UPDATE parcels p
           SET city = 'Sandy Springs'
         WHERE p.jurisdiction_id=$1::uuid
           AND p.geom IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM _fulton_sandy_limit b
               WHERE ST_Within(ST_Centroid(p.geom), b.geom)
           )
        """,
        jid,
    )
    buckhead = await conn.execute(
        """
        UPDATE parcels p
           SET city = 'Buckhead'
         WHERE p.jurisdiction_id=$1::uuid
           AND p.geom IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM _fulton_atlanta_limit a
               WHERE ST_Within(ST_Centroid(p.geom), a.geom)
           )
           AND EXISTS (
               SELECT 1 FROM _fulton_buckhead_boundary b
               WHERE ST_Within(ST_Centroid(p.geom), b.geom)
           )
        """,
        jid,
    )
    return int(sandy.split()[-1]), int(buckhead.split()[-1])


async def _spatial_backfill_scope(
    conn: asyncpg.Connection,
    jid: str,
    *,
    scope: str,
    prod_city_value: str,
    boundary_sql: str,
    nearest_within_meters: float,
) -> tuple[int, int]:
    s1 = await conn.execute(
        f"""
        UPDATE parcels target
           SET city = $2,
               zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id=$1::uuid
                  AND zd.geom IS NOT NULL
                  AND zd.raw_attributes->>'adapter' = $3
                  AND zd.raw_attributes->>'scope' = $4
                  AND ST_Within(ST_Centroid(p.geom), zd.geom)
                ORDER BY zd.id LIMIT 1
            ) m
            WHERE p.jurisdiction_id=$1::uuid
              AND p.geom IS NOT NULL
              AND {boundary_sql}
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        jid, prod_city_value, ADAPTER_ID, scope,
    )
    n1 = int(s1.split()[-1])

    binding_label = f"nearest_{int(round(nearest_within_meters))}m"
    s2 = await conn.execute(
        f"""
        UPDATE parcels target
           SET city = $2,
               zone_class = sub.zone_class,
               zone_binding_method = $5,
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id=$1::uuid
                  AND zd.geom IS NOT NULL
                  AND zd.raw_attributes->>'adapter' = $3
                  AND zd.raw_attributes->>'scope' = $4
                  AND ST_DWithin(
                      zd.geom::geography,
                      ST_Centroid(p.geom)::geography,
                      $6
                  )
                ORDER BY ST_Distance(
                    zd.geom::geography,
                    ST_Centroid(p.geom)::geography
                ) LIMIT 1
            ) m
            WHERE p.jurisdiction_id=$1::uuid
              AND p.geom IS NOT NULL
              AND p.zone_binding_method IS NULL
              AND {boundary_sql}
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        jid, prod_city_value, ADAPTER_ID, scope, binding_label,
        float(nearest_within_meters),
    )
    n2 = int(s2.split()[-1])
    return n1, n2


async def _update_fulton_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    ext = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy
        FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL
        """,
        jid,
    )
    if not ext or ext["minx"] is None:
        raise RuntimeError("Fulton JID has no parcel geometry")
    bbox = [
        float(ext["minx"]), float(ext["miny"]),
        float(ext["maxx"]), float(ext["maxy"]),
    ]
    if not (
        BBOX_LON_RANGE[0] <= bbox[0] <= BBOX_LON_RANGE[1]
        and BBOX_LAT_RANGE[0] <= bbox[1] <= BBOX_LAT_RANGE[1]
    ):
        raise RuntimeError(f"Fulton bbox {bbox} outside expected envelope")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid, json.dumps(bbox),
    )
    return bbox


async def _print_verdict(conn: asyncpg.Connection, jid: str) -> None:
    print("\n=== 5-GATE PREP VERDICT ===")
    empty = await conn.fetchval(
        """
        SELECT COUNT(*) FROM zoning_districts
        WHERE jurisdiction_id=$1::uuid
          AND raw_attributes->>'adapter' = $2
          AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)
        """,
        jid, ADAPTER_ID,
    )
    districts = await conn.fetch(
        """
        SELECT raw_attributes->>'scope' AS scope, COUNT(*) AS n,
               COUNT(DISTINCT zone_code) AS codes
        FROM zoning_districts
        WHERE jurisdiction_id=$1::uuid
          AND raw_attributes->>'adapter' = $2
        GROUP BY 1 ORDER BY 1
        """,
        jid, ADAPTER_ID,
    )
    for city in ("Sandy Springs", "Buckhead"):
        p = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (
                       WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                   ) AS bound,
                   COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                   COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
            FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2
            """,
            jid, city,
        )
        total = p["total"] or 0
        bound = p["bound"] or 0
        cov = 100.0 * bound / total if total else 0.0
        near_pct = 100.0 * (p["nearest"] or 0) / total if total else 0.0
        print(
            f"{city}: parcels={total:,} bound={bound:,} "
            f"cov={cov:.1f}% contained={p['contained']:,} "
            f"nearest={p['nearest']:,} near_pct={near_pct:.1f}%"
        )
    print(f"GATE raw_attributes empty: {empty} - {'PASS' if empty == 0 else 'FAIL'}")
    for row in districts:
        print(f"districts[{row['scope']}]: {row['n']:,} rows, {row['codes']:,} codes")


async def _fire(nearest_within_meters: float, dry_run: bool, buckhead_scope: str) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Fulton GA Class B zoning adapter ===")
    print(f"buckhead_scope={buckhead_scope}: {BUCKHEAD_FILTERS[buckhead_scope]['description']}\n")

    async with httpx.AsyncClient(timeout=180.0) as client:
        sandy_zoning, sandy_limit, atlanta_zoning, atlanta_limit, buckhead_boundary = (
            await asyncio.gather(
                _fetch_features(client, SANDY_SPRINGS_ZONING_URL),
                _fetch_features(client, SANDY_SPRINGS_LIMIT_URL),
                _fetch_features(client, ATLANTA_ZONING_URL),
                _fetch_features(client, ATLANTA_CITY_LIMIT_URL),
                _fetch_features(
                    client,
                    ATLANTA_NEIGHBORHOODS_URL,
                    where=BUCKHEAD_FILTERS[buckhead_scope]["where"],
                ),
            )
        )

    if len(sandy_limit) < 1:
        raise SystemExit("REFUSE FIRE - Sandy Springs city-limit boundary not fetched")
    if len(atlanta_limit) < 1:
        raise SystemExit("REFUSE FIRE - Atlanta city boundary not fetched")
    if len(buckhead_boundary) < BUCKHEAD_FILTERS[buckhead_scope]["expected_min"]:
        raise SystemExit(
            "REFUSE FIRE - Buckhead boundary returned "
            f"{len(buckhead_boundary)} rows for scope {buckhead_scope}"
        )

    sandy_rows = _build_sandy_rows(sandy_zoning)
    atlanta_rows = _build_atlanta_rows(atlanta_zoning, buckhead_scope)
    print(
        "source rows: "
        f"sandy_zoning={len(sandy_zoning):,}->{len(sandy_rows):,}, "
        f"atlanta_zoning={len(atlanta_zoning):,}->{len(atlanta_rows):,}, "
        f"sandy_limit={len(sandy_limit):,}, atlanta_limit={len(atlanta_limit):,}, "
        f"buckhead_boundary={len(buckhead_boundary):,}"
    )
    print(f"sandy distinct codes: {len({r.zone_code for r in sandy_rows})}")
    atlanta_distinct = len({r.zone_code for r in atlanta_rows})
    print(f"atlanta distinct codes before Buckhead SQL filter: {atlanta_distinct}")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        jid = await _lookup_fulton_jid(conn)
        await _gate_check(conn, jid)

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            await _stage_boundary(
                conn, "_fulton_sandy_limit",
                _boundary_rows(sandy_limit, SANDY_SPRINGS_LIMIT_URL, "1=1", "sandy_springs_limit"),
            )
            await _stage_boundary(
                conn, "_fulton_atlanta_limit",
                _boundary_rows(atlanta_limit, ATLANTA_CITY_LIMIT_URL, "1=1", "atlanta_limit"),
            )
            await _stage_boundary(
                conn, "_fulton_buckhead_boundary",
                _boundary_rows(
                    buckhead_boundary,
                    ATLANTA_NEIGHBORHOODS_URL,
                    BUCKHEAD_FILTERS[buckhead_scope]["where"],
                    "buckhead_boundary",
                ),
            )

            cleared = await conn.execute(
                """
                DELETE FROM zoning_districts
                WHERE jurisdiction_id=$1::uuid
                  AND raw_attributes->>'adapter' = $2
                """,
                jid, ADAPTER_ID,
            )
            print(f"[idempotency] cleared {cleared.split()[-1]} prior adapter zoning_districts")

            reset = await _reset_target_parcels(conn, jid)
            print(f"[idempotency] reset {reset:,} Sandy Springs/Buckhead parcel bindings")
            sandy_city, buckhead_city = await _assign_target_city_values(conn, jid)
            print(
                "[prefilter] assigned prod city values: "
                f"Sandy Springs={sandy_city:,}, Buckhead={buckhead_city:,}"
            )

            sandy_inserted = await _insert_district_rows(conn, jid, sandy_rows)
            buckhead_inserted = await _insert_district_rows(
                conn, jid, atlanta_rows, boundary_table="_fulton_buckhead_boundary",
            )
            print(f"[insert] Sandy Springs districts: {sandy_inserted:,}")
            print(f"[insert] Buckhead-intersecting Atlanta districts: {buckhead_inserted:,}")
            if sandy_inserted == 0 or buckhead_inserted == 0:
                raise RuntimeError("zero district insert for one or more Fulton target scopes")

            sandy_boundary_sql = (
                "EXISTS (SELECT 1 FROM _fulton_sandy_limit b "
                "WHERE ST_Within(ST_Centroid(p.geom), b.geom))"
            )
            buckhead_boundary_sql = (
                "EXISTS (SELECT 1 FROM _fulton_atlanta_limit a "
                "WHERE ST_Within(ST_Centroid(p.geom), a.geom)) "
                "AND EXISTS (SELECT 1 FROM _fulton_buckhead_boundary b "
                "WHERE ST_Within(ST_Centroid(p.geom), b.geom))"
            )
            s1, s2 = await _spatial_backfill_scope(
                conn, jid, scope="sandy_springs", prod_city_value="Sandy Springs",
                boundary_sql=sandy_boundary_sql,
                nearest_within_meters=nearest_within_meters,
            )
            print(f"[spatial] Sandy Springs contained={s1:,} nearest={s2:,}")
            b1, b2 = await _spatial_backfill_scope(
                conn, jid, scope="buckhead", prod_city_value="Buckhead",
                boundary_sql=buckhead_boundary_sql,
                nearest_within_meters=nearest_within_meters,
            )
            print(f"[spatial] Buckhead contained={b1:,} nearest={b2:,}")

            bbox = await _update_fulton_bbox(conn, jid)
            print(f"[bbox] Fulton bbox verified+updated: {bbox}")
            await _print_verdict(conn, jid)

            if dry_run:
                raise _RollbackForDryRun()

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside transaction context to force rollback."""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    parser.add_argument(
        "--buckhead-scope",
        choices=sorted(BUCKHEAD_FILTERS),
        default="broad-npu-ab",
        help=(
            "Buckhead boundary interpretation. Default follows the broad "
            "north-side NPU A+B filter."
        ),
    )
    args = parser.parse_args()
    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass --dry-run for transactional rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(
        asyncio.run(
            _fire(
                nearest_within_meters=args.nearest_within_meters,
                dry_run=args.dry_run,
                buckhead_scope=args.buckhead_scope,
            )
        )
    )
