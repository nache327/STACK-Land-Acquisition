"""Greenwood Village CO Class B per-muni zoning adapter.

PREP ONLY - DO NOT FIRE until Master merges/fires the CO Front Range trio.

Greenwood Village is a Phase 6 secondary municipality adjacent to the Cherry
Hills / Denver Tech Center cluster. Agent 9's PR #360 identified a likely
viable city-owned source:

  - City maps page: https://greenwoodvillage.com/593/Maps
  - City parcel layer:
    https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/
    Parcel_City_and_County_Data/FeatureServer/0
  - City-owned Urban public-view Zones layer:
    https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/
    b16e6a436dc24550b521986d2a71f11a_public_view_1593194820169/FeatureServer/1

Authority caveat:
The zoning-like service is an Urban "Zones" layer, not a plain "Zoning
District Boundaries" service. This adapter refuses source preflight unless
sample rows carry `PlanningMethod='zoning'`, `PlanningHorizon='existing'`,
and GreenwoodVillage editor provenance. Treat it as Class B until a human
accepts the authority signal.

PATH 1 jurisdiction pattern:
Greenwood Village gets its own jurisdiction under the Arapahoe County umbrella.
After PR #355 is merged and fired, this script moves parcels from
`Arapahoe County, CO` to `Greenwood Village, CO` by spatial containment inside
the city-owned parcel layer, then inserts city zoning polygons and backfills
parcel zoning.

Hard guards:
  - no write path without `fire --dry-run` or `fire --i-know-this-writes-to-prod`
  - refuses if the Arapahoe County umbrella JID is missing
  - dry-run wraps the full DB sequence in one transaction and rolls it back
  - raw_attributes preserve Urban source fields and authority QA fields
  - no matrix authoring; substrates/matrix remain orchestrator's domain
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkb import dumps as wkb_dumps


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("greenwood_village_co")

STATE = "CO"
COUNTY = "Arapahoe"
PARENT_JURISDICTION = "Arapahoe County, CO"
MUNI_JURISDICTION = "Greenwood Village, CO"
PROD_CITY_VALUE = "Greenwood Village"

CO_PUBLIC_PARCELS_LAYER = (
    "https://gis.colorado.gov/public/rest/services/Address_and_Parcel/"
    "Colorado_Public_Parcels/FeatureServer/0"
)
CITY_PARCEL_LAYER = (
    "https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/"
    "Parcel_City_and_County_Data/FeatureServer/0"
)
ZONES_LAYER = (
    "https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/"
    "b16e6a436dc24550b521986d2a71f11a_public_view_1593194820169/FeatureServer/1"
)

ARCGIS_PAGE_SIZE = 1000
REQUEST_TIMEOUT = httpx.Timeout(120.0)
MIN_SOURCE_ZONES = 1000
MIN_CITY_PARCELS = 500
MIN_MOVED_PARCELS = 500
BBOX_LON = (-105.00, -104.83)
BBOX_LAT = (39.57, 39.66)

ZONE_RAW_KEYS = (
    "OBJECTID",
    "GlobalID",
    "CustomID",
    "ZoneTypeID",
    "BranchID",
    "PlanningMethod",
    "PlanningHorizon",
    "Shape__Area",
    "Shape__Length",
    "CreationDate",
    "Creator",
    "EditDate",
    "Editor",
)
PARCEL_RAW_KEYS = (
    "OBJECTID",
    "PARCEL_ID",
    "PIN",
    "Folio",
    "Situs_Address",
    "Situs_City_State_Zip",
    "Owner",
    "Classification",
    "Appr_Value",
    "Imp_Value",
    "Land_Value",
    "Assd_Value",
    "PUC_Code",
    "PUC",
    "DATA_DATE",
    "UNIQUE_ID",
)


class _RollbackForDryRun(Exception):
    """Raised inside the transaction to force rollback."""


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://",
        "postgresql://",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _trim(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _signed_area(coords: list[tuple[float, float]]) -> float:
    area = 0.0
    for idx in range(len(coords) - 1):
        x1, y1 = coords[idx]
        x2, y2 = coords[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _ring_to_coords(ring: list[list[float]]) -> list[tuple[float, float]]:
    coords = [(float(point[0]), float(point[1])) for point in ring if len(point) >= 2]
    if len(coords) < 3:
        return []
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _arcgis_rings_to_geom(rings: list[list[list[float]]]) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    holes_by_outer: list[list[list[tuple[float, float]]]] = []

    for ring in rings:
        coords = _ring_to_coords(ring)
        if not coords:
            continue
        if _signed_area(coords) < 0:
            outers.append(coords)
            holes_by_outer.append([])
        elif outers:
            holes_by_outer[-1].append(coords)
        else:
            outers.append(coords)
            holes_by_outer.append([])

    polygons: list[Polygon] = []
    for outer, holes in zip(outers, holes_by_outer):
        try:
            polygon = Polygon(outer, holes)
        except ValueError:
            continue
        if not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        return None

    geom: BaseGeometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    geom = make_valid(geom)
    return None if geom.is_empty else geom


def _feature_geom(feature: dict[str, Any]) -> BaseGeometry | None:
    geometry = feature.get("geometry") or {}
    rings = geometry.get("rings") or []
    if not rings:
        return None
    return _arcgis_rings_to_geom(rings)


def _geom_hash(geom: BaseGeometry) -> str:
    return hashlib.sha256(wkb_dumps(geom, hex=False, srid=4326)).hexdigest()


async def _request_json(
    client: httpx.AsyncClient,
    layer_url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = await client.get(f"{layer_url}/query", params=params)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS error from {layer_url}: {data['error']}")
    return data


async def _fetch_count(client: httpx.AsyncClient, layer_url: str, where: str = "1=1") -> int:
    data = await _request_json(
        client,
        layer_url,
        {
            "f": "json",
            "where": where,
            "returnCountOnly": "true",
        },
    )
    return int(data.get("count") or 0)


async def _fetch_features(
    client: httpx.AsyncClient,
    layer_url: str,
    *,
    where: str = "1=1",
    page_size: int = ARCGIS_PAGE_SIZE,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        if limit is not None and len(features) >= limit:
            break
        current = page_size
        if limit is not None:
            current = min(current, limit - len(features))
        data = await _request_json(
            client,
            layer_url,
            {
                "f": "json",
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "returnTrueCurves": "false",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": current,
                "orderByFields": "OBJECTID",
            },
        )
        batch = list(data.get("features") or [])
        if not batch:
            break
        features.extend(batch)
        logger.info("fetched %d from %s offset=%d", len(batch), layer_url, offset)
        if len(batch) < current:
            break
        offset += len(batch)
    return features


def _validate_zone_authority(features: list[dict[str, Any]]) -> None:
    if not features:
        raise RuntimeError("Zones source returned no features")
    bad: list[dict[str, Any]] = []
    for feature in features[: min(len(features), 50)]:
        attrs = feature.get("attributes") or {}
        method = _trim(attrs.get("PlanningMethod"))
        horizon = _trim(attrs.get("PlanningHorizon"))
        creator = (_trim(attrs.get("Creator")) or "").lower()
        editor = (_trim(attrs.get("Editor")) or "").lower()
        if method != "zoning" or horizon != "existing":
            bad.append(attrs)
            continue
        if "greenwoodvillage" not in creator and "greenwoodvillage" not in editor:
            bad.append(attrs)
    if bad:
        raise RuntimeError(
            "Authority QA failed: expected PlanningMethod='zoning', "
            "PlanningHorizon='existing', and GreenwoodVillage provenance"
        )


def _build_zoning_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes") or {}
        geom = _feature_geom(feature)
        zone_code = _trim(attrs.get("CustomID"))
        if geom is None or not zone_code:
            continue
        raw = {
            "source_url": ZONES_LAYER,
            "source_kind": "greenwood_village_urban_zones",
            "source_authority_status": (
                "Class B; Urban existing zoning layer passed script QA; "
                "human authority QA still required"
            ),
            "source_maps_page": "https://greenwoodvillage.com/593/Maps",
            "muni_name": PROD_CITY_VALUE,
            "muni_type": "city",
            "county": COUNTY,
            "ingested_at": _now_iso(),
        }
        for key in ZONE_RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]
        rows.append(
            {
                "zone_code": zone_code,
                "zone_name": zone_code,
                "zone_class": "unknown",
                "wkt": geom.wkt,
                "geom_hash": _geom_hash(geom),
                "raw": json.dumps(raw, sort_keys=True),
            }
        )
    return rows


def _build_city_parcel_rows(features: list[dict[str, Any]]) -> list[tuple[str | None, str]]:
    rows: list[tuple[str | None, str]] = []
    for feature in features:
        attrs = feature.get("attributes") or {}
        geom = _feature_geom(feature)
        if geom is None:
            continue
        pin = _trim(attrs.get("PIN")) or _trim(attrs.get("PARCEL_ID"))
        rows.append((pin, geom.wkt))
    return rows


async def _source_preflight(args: argparse.Namespace) -> int:
    print("Greenwood Village CO source preflight")
    print("READ-ONLY: no DB connection, no writes")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        zone_count = await _fetch_count(client, ZONES_LAYER)
        parcel_count = await _fetch_count(client, CITY_PARCEL_LAYER)
        zone_features = await _fetch_features(client, ZONES_LAYER, limit=args.sample_size)
        parcel_features = await _fetch_features(client, CITY_PARCEL_LAYER, limit=args.sample_size)
    _validate_zone_authority(zone_features)
    zone_rows = _build_zoning_rows(zone_features)
    parcel_rows = _build_city_parcel_rows(parcel_features)
    distinct = sorted({row["zone_code"] for row in zone_rows})
    print(f"zones_count={zone_count:,} expected_min={MIN_SOURCE_ZONES:,}")
    print(f"city_parcel_count={parcel_count:,} expected_min={MIN_CITY_PARCELS:,}")
    print(f"sample_zones={len(zone_features)} payload_rows={len(zone_rows)}")
    print(f"sample_city_parcels={len(parcel_features)} boundary_rows={len(parcel_rows)}")
    print(f"sample_zone_codes={distinct[:20]}")
    if zone_rows:
        sample = dict(zone_rows[0])
        sample["wkt"] = sample["wkt"][:96] + "..."
        print("sample_payload=" + json.dumps(sample, sort_keys=True)[:1200])
    if zone_count < MIN_SOURCE_ZONES or parcel_count < MIN_CITY_PARCELS:
        raise SystemExit("Source preflight failed count gates")
    return 0


async def _resolve_parent_jid(conn: asyncpg.Connection) -> str:
    jid = await conn.fetchval(
        """
        SELECT id
        FROM jurisdictions
        WHERE name = $1 AND state = $2 AND county = $3
        ORDER BY id ASC
        LIMIT 1
        """,
        PARENT_JURISDICTION,
        STATE,
        COUNTY,
    )
    if not jid:
        raise SystemExit(
            f"REFUSE FIRE - missing {PARENT_JURISDICTION}. "
            "Merge/fire PR #355 CO Front Range trio first."
        )
    return str(jid)


async def _register_or_get_muni_jid(conn: asyncpg.Connection) -> str:
    jid = await conn.fetchval(
        """
        SELECT id
        FROM jurisdictions
        WHERE name = $1 AND state = $2 AND county = $3
        ORDER BY id ASC
        LIMIT 1
        """,
        MUNI_JURISDICTION,
        STATE,
        COUNTY,
    )
    if jid:
        jid_s = str(jid)
        await conn.execute(
            """
            UPDATE jurisdictions
            SET
                parcel_source = COALESCE($2::parcel_source_enum, parcel_source),
                parcel_endpoint = COALESCE($3, parcel_endpoint),
                zoning_endpoint = COALESCE($4, zoning_endpoint),
                coverage_level = COALESCE($5::coverage_level_enum, coverage_level)
            WHERE id = $1::uuid
            """,
            jid_s,
            "county_gis",
            CO_PUBLIC_PARCELS_LAYER,
            ZONES_LAYER,
            "partial",
        )
        print(f"[register] existing {MUNI_JURISDICTION}: {jid_s}")
        return jid_s

    new_jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id,
            name,
            state,
            county,
            parcel_source,
            parcel_endpoint,
            zoning_endpoint,
            coverage_level,
            created_at
        )
        VALUES (
            $1::uuid,
            $2,
            $3,
            $4,
            $5::parcel_source_enum,
            $6,
            $7,
            $8::coverage_level_enum,
            NOW()
        )
        """,
        new_jid,
        MUNI_JURISDICTION,
        STATE,
        COUNTY,
        "county_gis",
        CO_PUBLIC_PARCELS_LAYER,
        ZONES_LAYER,
        "partial",
    )
    print(f"[register] new {MUNI_JURISDICTION}: {new_jid}")
    return new_jid


async def _stage_city_boundary(
    conn: asyncpg.Connection,
    city_parcels: list[tuple[str | None, str]],
) -> None:
    await conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS _gv_city_parcels (
            pin TEXT,
            geom_wkt TEXT NOT NULL
        ) ON COMMIT DROP
        """
    )
    await conn.execute("TRUNCATE _gv_city_parcels")
    await conn.copy_records_to_table(
        "_gv_city_parcels",
        records=city_parcels,
        columns=["pin", "geom_wkt"],
    )
    await conn.execute("DROP TABLE IF EXISTS _gv_city_geom")
    await conn.execute(
        """
        CREATE TEMP TABLE _gv_city_geom ON COMMIT DROP AS
        SELECT
            ST_UnaryUnion(
                ST_Collect(ST_MakeValid(ST_GeomFromText(geom_wkt, 4326)))
            ) AS geom
        FROM _gv_city_parcels
        WHERE geom_wkt IS NOT NULL
        """
    )


async def _move_parcels_to_muni(
    conn: asyncpg.Connection,
    *,
    parent_jid: str,
    muni_jid: str,
) -> dict[str, int]:
    duplicate_merged = int(
        await conn.fetchval(
            """
            WITH candidates AS (
                SELECT src.*
                FROM parcels src
                CROSS JOIN _gv_city_geom city
                WHERE src.jurisdiction_id = $1::uuid
                  AND src.geom IS NOT NULL
                  AND ST_Covers(city.geom, ST_PointOnSurface(src.geom))
            ),
            updated_existing AS (
                UPDATE parcels target
                SET
                    address = candidates.address,
                    city = $3,
                    state = $4,
                    owner_name = candidates.owner_name,
                    acres = candidates.acres,
                    land_use_code = candidates.land_use_code,
                    improvement_value = candidates.improvement_value,
                    assessed_value = candidates.assessed_value,
                    is_residential = candidates.is_residential,
                    has_structure = candidates.has_structure,
                    county_link = candidates.county_link,
                    geom = candidates.geom,
                    centroid = candidates.centroid,
                    raw = candidates.raw,
                    updated_at = NOW()
                FROM candidates
                WHERE target.jurisdiction_id = $2::uuid
                  AND target.apn = candidates.apn
                RETURNING candidates.id
            ),
            deleted_source_duplicates AS (
                DELETE FROM parcels src
                USING updated_existing
                WHERE src.id = updated_existing.id
                RETURNING 1
            )
            SELECT COUNT(*)::INTEGER FROM deleted_source_duplicates
            """,
            parent_jid,
            muni_jid,
            PROD_CITY_VALUE,
            STATE,
        )
    )
    moved = int(
        await conn.fetchval(
            """
            WITH moved AS (
                UPDATE parcels src
                SET
                    jurisdiction_id = $2::uuid,
                    city = $3,
                    state = $4,
                    updated_at = NOW()
                FROM _gv_city_geom city
                WHERE src.jurisdiction_id = $1::uuid
                  AND src.geom IS NOT NULL
                  AND ST_Covers(city.geom, ST_PointOnSurface(src.geom))
                  AND NOT EXISTS (
                      SELECT 1
                      FROM parcels existing
                      WHERE existing.jurisdiction_id = $2::uuid
                        AND existing.apn = src.apn
                  )
                RETURNING 1
            )
            SELECT COUNT(*)::INTEGER FROM moved
            """,
            parent_jid,
            muni_jid,
            PROD_CITY_VALUE,
            STATE,
        )
    )
    total = moved + duplicate_merged
    print(f"[PATH 1] moved={moved:,} merged_duplicate_rows={duplicate_merged:,}")
    if total < MIN_MOVED_PARCELS:
        raise RuntimeError(
            f"PATH 1 moved/merged only {total:,} parcels; expected at least "
            f"{MIN_MOVED_PARCELS:,}. Refusing zoning ingest."
        )
    return {"moved": moved, "merged_duplicate_rows": duplicate_merged}


async def _insert_zoning_rows(
    conn: asyncpg.Connection,
    *,
    muni_jid: str,
    rows: list[dict[str, Any]],
) -> int:
    await conn.execute(
        """
        DELETE FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
        """,
        muni_jid,
    )
    await conn.execute(
        """
        UPDATE parcels
        SET zoning_code = NULL,
            zone_class = NULL,
            zone_binding_method = NULL,
            updated_at = NOW()
        WHERE jurisdiction_id = $1::uuid
        """,
        muni_jid,
    )
    inserted = 0
    for row in rows:
        inserted += int(
            await conn.fetchval(
                """
                WITH inserted AS (
                    INSERT INTO zoning_districts (
                        jurisdiction_id,
                        zone_code,
                        zone_name,
                        zone_class,
                        raw_attributes,
                        geom,
                        centroid,
                        source,
                        confidence,
                        human_reviewed,
                        geom_hash,
                        updated_at
                    )
                    VALUES (
                        $1::uuid,
                        $2,
                        $3,
                        $4::zone_class_enum,
                        $5::jsonb,
                        ST_Multi(ST_MakeValid(ST_GeomFromText($6, 4326))),
                        ST_PointOnSurface(ST_MakeValid(ST_GeomFromText($6, 4326))),
                        'arcgis'::zone_source_enum,
                        0.82,
                        FALSE,
                        $7,
                        NOW()
                    )
                    ON CONFLICT ON CONSTRAINT uq_zoning_districts_jur_code_hash
                    DO UPDATE SET
                        zone_name = EXCLUDED.zone_name,
                        zone_class = EXCLUDED.zone_class,
                        raw_attributes = EXCLUDED.raw_attributes,
                        geom = EXCLUDED.geom,
                        centroid = EXCLUDED.centroid,
                        source = EXCLUDED.source,
                        confidence = EXCLUDED.confidence,
                        updated_at = NOW()
                    RETURNING 1
                )
                SELECT COUNT(*)::INTEGER FROM inserted
                """,
                muni_jid,
                row["zone_code"],
                row["zone_name"],
                row["zone_class"],
                row["raw"],
                row["wkt"],
                row["geom_hash"],
            )
        )
    print(f"[zoning] inserted/upserted {inserted:,} districts")
    return inserted


async def _backfill_zoning(
    conn: asyncpg.Connection,
    *,
    muni_jid: str,
    nearest_meters: float,
) -> dict[str, int]:
    contained = int(
        await conn.fetchval(
            """
            WITH contained AS (
                SELECT DISTINCT ON (p.id)
                    p.id AS parcel_id,
                    zd.zone_code,
                    zd.zone_class
                FROM parcels p
                JOIN zoning_districts zd
                  ON zd.jurisdiction_id = $1::uuid
                 AND zd.raw_attributes->>'source_kind' = 'greenwood_village_urban_zones'
                 AND p.geom IS NOT NULL
                 AND ST_Covers(zd.geom, ST_PointOnSurface(p.geom))
                WHERE p.jurisdiction_id = $1::uuid
                  AND (p.zone_binding_method IS NULL OR p.zoning_code IS NULL)
                ORDER BY p.id, ST_Area(zd.geom) ASC
            ),
            updated AS (
                UPDATE parcels p
                SET
                    zoning_code = contained.zone_code,
                    zone_class = contained.zone_class,
                    zone_binding_method = 'contained',
                    updated_at = NOW()
                FROM contained
                WHERE p.id = contained.parcel_id
                RETURNING 1
            )
            SELECT COUNT(*)::INTEGER FROM updated
            """,
            muni_jid,
        )
    )
    label = f"nearest_{int(round(nearest_meters))}m"
    nearest = int(
        await conn.fetchval(
            """
            WITH remaining AS (
                SELECT p.id, p.geom, ST_PointOnSurface(p.geom) AS point_geom
                FROM parcels p
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
                  AND (p.zone_binding_method IS NULL OR p.zoning_code IS NULL)
            ),
            nearest AS (
                SELECT DISTINCT ON (r.id)
                    r.id AS parcel_id,
                    zd.zone_code,
                    zd.zone_class
                FROM remaining r
                JOIN zoning_districts zd
                  ON zd.jurisdiction_id = $1::uuid
                 AND zd.raw_attributes->>'source_kind' = 'greenwood_village_urban_zones'
                 AND ST_DWithin(
                     r.point_geom::geography,
                     ST_ClosestPoint(zd.geom, r.point_geom)::geography,
                     $2
                 )
                ORDER BY
                    r.id,
                    ST_Distance(
                        r.point_geom::geography,
                        ST_ClosestPoint(zd.geom, r.point_geom)::geography
                    )
            ),
            updated AS (
                UPDATE parcels p
                SET
                    zoning_code = nearest.zone_code,
                    zone_class = nearest.zone_class,
                    zone_binding_method = $3,
                    updated_at = NOW()
                FROM nearest
                WHERE p.id = nearest.parcel_id
                RETURNING 1
            )
            SELECT COUNT(*)::INTEGER FROM updated
            """,
            muni_jid,
            float(nearest_meters),
            label,
        )
    )
    print(f"[spatial] contained={contained:,} {label}={nearest:,}")
    return {"contained": contained, label: nearest}


async def _update_bbox(conn: asyncpg.Connection, muni_jid: str) -> list[float]:
    bbox = await conn.fetchrow(
        """
        WITH extent AS (
            SELECT ST_Extent(geom) AS box
            FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
        )
        SELECT
            ST_XMin(box::geometry) AS min_lng,
            ST_YMin(box::geometry) AS min_lat,
            ST_XMax(box::geometry) AS max_lng,
            ST_YMax(box::geometry) AS max_lat
        FROM extent
        WHERE box IS NOT NULL
        """,
        muni_jid,
    )
    if not bbox:
        raise RuntimeError("No parcel geometry after Greenwood PATH 1 move")
    value = [
        float(bbox["min_lng"]),
        float(bbox["min_lat"]),
        float(bbox["max_lng"]),
        float(bbox["max_lat"]),
    ]
    if not (BBOX_LON[0] <= value[0] <= BBOX_LON[1] and BBOX_LAT[0] <= value[1] <= BBOX_LAT[1]):
        raise RuntimeError(f"bbox {value} outside Greenwood Village envelope")
    await conn.execute(
        "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
        muni_jid,
        json.dumps(value),
    )
    print(f"[bbox] {value}")
    return value


async def _report(conn: asyncpg.Connection, muni_jid: str) -> None:
    stats = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (
                WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
            ) AS bound,
            COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
            COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
        FROM parcels
        WHERE jurisdiction_id = $1::uuid
        """,
        muni_jid,
    )
    districts = await conn.fetchval(
        "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
        muni_jid,
    )
    empty_raw = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
          AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)
        """,
        muni_jid,
    )
    total = int(stats["total"] or 0)
    bound = int(stats["bound"] or 0)
    nearest = int(stats["nearest"] or 0)
    coverage = Decimal(bound * 100) / Decimal(total) if total else Decimal("0")
    nearest_pct = Decimal(nearest * 100) / Decimal(total) if total else Decimal("0")
    print("\n=== 5-GATE SNAPSHOT ===")
    print(f"parcels={total:,} bound={bound:,} coverage={coverage:.1f}%")
    print(
        f"contained={int(stats['contained'] or 0):,} "
        f"nearest={nearest:,} nearest_pct={nearest_pct:.1f}%"
    )
    print(f"zoning_districts={int(districts or 0):,} empty_raw={int(empty_raw or 0):,}")
    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
        FROM parcels
        WHERE jurisdiction_id = $1::uuid AND zoning_code IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC, 1
        LIMIT 40
        """,
        muni_jid,
    )
    print("top zoning_code distribution:")
    for row in codes:
        print(f"  {row['zoning_code']:16s} {int(row['n']):>6,}")


async def _fire(args: argparse.Namespace) -> int:
    mode = "DRY-RUN (ROLLBACK)" if args.dry_run else "FIRE"
    print(f"\n=== {mode}: Greenwood Village CO Class B zoning ===\n")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        zone_features = await _fetch_features(client, ZONES_LAYER)
        city_parcel_features = await _fetch_features(client, CITY_PARCEL_LAYER)
    _validate_zone_authority(zone_features)
    zoning_rows = _build_zoning_rows(zone_features)
    city_parcels = _build_city_parcel_rows(city_parcel_features)
    if len(zoning_rows) < MIN_SOURCE_ZONES:
        raise RuntimeError(f"only {len(zoning_rows):,} zoning rows built")
    if len(city_parcels) < MIN_CITY_PARCELS:
        raise RuntimeError(f"only {len(city_parcels):,} city parcel boundary rows built")
    print(f"[source] zoning_rows={len(zoning_rows):,} city_boundary_rows={len(city_parcels):,}")

    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=3600)
    try:
        try:
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = 0")
                parent_jid = await _resolve_parent_jid(conn)
                muni_jid = await _register_or_get_muni_jid(conn)
                await _stage_city_boundary(conn, city_parcels)
                await _move_parcels_to_muni(
                    conn,
                    parent_jid=parent_jid,
                    muni_jid=muni_jid,
                )
                await _insert_zoning_rows(conn, muni_jid=muni_jid, rows=zoning_rows)
                await _backfill_zoning(
                    conn,
                    muni_jid=muni_jid,
                    nearest_meters=args.nearest_within_meters,
                )
                await _update_bbox(conn, muni_jid)
                await _report(conn, muni_jid)
                if args.dry_run:
                    raise _RollbackForDryRun()
        except _RollbackForDryRun:
            print("\n(DRY-RUN - transaction rolled back; no writes survived)")
    finally:
        await conn.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Read-only source probe")
    preflight.add_argument("--sample-size", type=int, default=50)
    preflight.set_defaults(func=_source_preflight)

    fire = subparsers.add_parser("fire", help="Guarded DB write path")
    fire.add_argument("--dry-run", action="store_true")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)
    fire.set_defaults(func=_fire)
    return parser


async def _main_async() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "fire" and not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass fire --dry-run for rehearsal or "
            "fire --i-know-this-writes-to-prod to actually write.",
            file=sys.stderr,
        )
        return 2
    return await args.func(args)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
