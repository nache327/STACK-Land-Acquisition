"""Moorestown NJ Class B GovPilot zoning adapter (NACHE HAND-OFF).

PREP ONLY - DO NOT FIRE from this branch.

Diagnostic PR #369 found Moorestown Township is not a direct parcel-attribute
backfill like Mount Laurel:

  - GovPilot public map: https://map.govpilot.com/map/NJ/moorestown
  - GovPilot account uid=7555, GMID=139, GCID=14
  - Public layer code `ZM` / `Zoning Map`
  - Zoning polygons carry `M_ZoneCode:<code>|M_ZoneDesc:<description>|...`
  - GovPilot parcel detail exposes a `ZONING` field, but the diagnostic sample
    was 0/50 non-null. Therefore this adapter intentionally performs a
    polygon-to-parcel spatial join.

Operational shape:
  - Registers `Moorestown Township, NJ` as a per-muni jurisdiction under the
    Burlington umbrella shape (`county='Burlington'`).
  - PATH 1 moves existing Burlington parcels where `city='Moorestown township'`
    into the per-muni JID. It does not create a new parcel substrate.
  - Inserts GovPilot `ZM` polygons into `zoning_districts` with full
    `raw_attributes` preservation.
  - Backfills parcels by `ST_Covers(zone.geom, ST_PointOnSurface(parcel.geom))`,
    with a small nearest fallback for edge slivers.
  - Runs the whole write sequence in one transaction; `--dry-run` rolls it back.

Matrix note:
Existing Burlington matrix pre-stage rows use municipality
`Moorestown township` for `BP-1`, `BP-2`, `LTC`, and `SRC`. This adapter keeps
that exact municipality value in raw attributes and parcel city values so the
handoff aligns with nache's substrate/matrix review.
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
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.wkb import dumps as wkb_dumps


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("moorestown_nj")

ADAPTER_NAME = "perm_muni_moorestown_nj_zoning"
SOURCE_DATE = "2026-06-23"

STATE = "NJ"
COUNTY = "Burlington"
PARENT_JURISDICTION = "Burlington County, NJ"
PARENT_JID_FALLBACK = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"
MUNI_JURISDICTION = "Moorestown Township, NJ"
MUNI_MATRIX_VALUE = "Moorestown township"
MUNI_DISPLAY = "Moorestown Township"
PROD_CITY_VALUE = "Moorestown township"

BURLINGTON_PARCELS_LAYER = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
    "Parcels_Composite_NJ_WM/FeatureServer/0"
)
GOVPILOT_MAP_URL = "https://map.govpilot.com/map/NJ/moorestown"
GOVPILOT_API_BASE = "https://map.govpilot.com/api/v1/cmd/get"
GOVPILOT_UID = 7555
GOVPILOT_GMID = 139
GOVPILOT_GCID = 14
GOVPILOT_STATE = "NJ"
GOVPILOT_PAR_DETAIL_CLASS = "MPNJ"
ZONING_LAYER_CODE = "ZM"
ZONING_LAYER_NAME = "Zoning Map"

# Built the same way GovPilot's public JS builds its Google Maps bounds
# viewport: se, ne, nw, sw, se as "lng lat" pairs (no POLYGON wrapper).
MOORESTOWN_QUERY_AREA = (
    "-74.85 39.90,"
    "-74.85 40.05,"
    "-75.10 40.05,"
    "-75.10 39.90,"
    "-74.85 39.90"
)

MIN_SOURCE_POLYGONS = 50
MIN_DISTINCT_CODES = 10
MIN_PROD_PARCELS = 1_000
MIN_BOUND_COVERAGE_PCT = 70.0
BBOX_LON = (-75.12, -74.84)
BBOX_LAT = (39.88, 40.07)
REQUEST_TIMEOUT = httpx.Timeout(120.0)


class _RollbackForDryRun(Exception):
    """Raised inside a transaction to force rollback."""


def _session_db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL not set in environment")
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


def _parse_desc(desc: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in (desc or "").split("|"):
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _ring_coords(points: list[dict[str, Any]]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for point in points:
        if "X" not in point or "Y" not in point:
            continue
        coords.append((float(point["X"]), float(point["Y"])))
    if len(coords) < 3:
        return []
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _govpilot_geoshape_to_geom(geoshape: str | None) -> BaseGeometry | None:
    if not geoshape:
        return None
    try:
        payload = json.loads(geoshape)
    except json.JSONDecodeError:
        return None

    polygons: list[Polygon] = []
    for ring in payload.get("Rings") or []:
        coords = _ring_coords(list(ring.get("Points") or []))
        if not coords:
            continue
        try:
            polygon = Polygon(coords)
        except ValueError:
            continue
        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None
    geom = unary_union(polygons)
    geom = make_valid(geom)
    if geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    polygon_parts = [
        part for part in getattr(geom, "geoms", [])
        if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
    ]
    if not polygon_parts:
        return None
    return make_valid(unary_union(polygon_parts))


def _geom_hash(geom: BaseGeometry) -> str:
    return hashlib.sha256(wkb_dumps(geom, hex=False, srid=4326)).hexdigest()


def _zone_class(code: str) -> str:
    z = code.upper().strip()
    if z.startswith(("R", "AR", "L-MR")):
        return "residential"
    if z.startswith(("BP", "SRC", "LTC", "SC", "TC")):
        return "commercial"
    if z.startswith(("SRI", "I")):
        return "industrial"
    if z.startswith(("OS", "OPEN")):
        return "open_space"
    return "unknown"


async def _post_govpilot(
    client: httpx.AsyncClient,
    code: str,
    body: list[Any],
) -> list[dict[str, Any]]:
    response = await client.post(f"{GOVPILOT_API_BASE}/{code}", json=body)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"GovPilot {code} failed: {payload}")
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise RuntimeError(f"GovPilot {code} returned non-list data: {type(data)}")
    return data


async def _fetch_layers(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return await _post_govpilot(client, "017", [GOVPILOT_GMID])


async def _fetch_zoning_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return await _post_govpilot(
        client,
        "015",
        [GOVPILOT_GMID, ZONING_LAYER_CODE, MOORESTOWN_QUERY_AREA],
    )


async def _fetch_parcel_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return await _post_govpilot(
        client,
        "GET-PARCELS",
        [
            GOVPILOT_UID,
            GOVPILOT_STATE,
            GOVPILOT_GCID,
            GOVPILOT_GMID,
            MOORESTOWN_QUERY_AREA,
        ],
    )


async def _fetch_parcel_detail(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> dict[str, Any] | None:
    data = await _post_govpilot(
        client,
        "025S",
        [GOVPILOT_PAR_DETAIL_CLASS, parcel_id],
    )
    if not data:
        return None
    return data[0]


def _build_zoning_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        desc = _trim(feature.get("DESC"))
        parsed = _parse_desc(desc)
        code = _trim(parsed.get("M_ZoneCode"))
        geom = _govpilot_geoshape_to_geom(_trim(feature.get("geoshape")))
        if not code or geom is None:
            continue
        raw = {
            "adapter": ADAPTER_NAME,
            "source_kind": "govpilot_zoning_map_polygon",
            "source_authority_status": (
                "Class B per-muni GovPilot ZM polygons; parcel detail ZONING "
                "is blank in diagnostic sample, so parcel zoning is spatially joined"
            ),
            "source_map_url": GOVPILOT_MAP_URL,
            "source_endpoint": f"{GOVPILOT_API_BASE}/015",
            "source_query_body": [
                GOVPILOT_GMID,
                ZONING_LAYER_CODE,
                MOORESTOWN_QUERY_AREA,
            ],
            "source_date": SOURCE_DATE,
            "ingested_at": _now_iso(),
            "govpilot_uid": GOVPILOT_UID,
            "govpilot_gmid": GOVPILOT_GMID,
            "govpilot_gcid": GOVPILOT_GCID,
            "layer_code": ZONING_LAYER_CODE,
            "layer_name": ZONING_LAYER_NAME,
            "muni_name": MUNI_MATRIX_VALUE,
            "municipality": MUNI_MATRIX_VALUE,
            "municipality_display": MUNI_DISPLAY,
            "county": COUNTY,
            "desc_fields": parsed,
            "govpilot_code": feature.get("CODE"),
            "govpilot_fc": feature.get("FC"),
            "govpilot_desc": desc,
        }
        rows.append(
            {
                "zone_code": code,
                "zone_name": _trim(parsed.get("M_ZoneDesc")) or code,
                "zone_class": _zone_class(code),
                "wkt": geom.wkt,
                "geom_hash": _geom_hash(geom),
                "raw": json.dumps(raw, sort_keys=True),
            }
        )
    return rows


def _validate_source_rows(rows: list[dict[str, Any]]) -> None:
    distinct = {row["zone_code"] for row in rows}
    if len(rows) < MIN_SOURCE_POLYGONS:
        raise RuntimeError(
            f"GovPilot ZM returned only {len(rows)} usable polygons; "
            f"expected at least {MIN_SOURCE_POLYGONS}"
        )
    if len(distinct) < MIN_DISTINCT_CODES:
        raise RuntimeError(
            f"GovPilot ZM returned only {len(distinct)} distinct codes; "
            f"expected at least {MIN_DISTINCT_CODES}"
        )


async def _source_preflight(args: argparse.Namespace) -> int:
    print("Moorestown NJ GovPilot source preflight")
    print("READ-ONLY: no DB connection, no writes")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        layers = await _fetch_layers(client)
        layer = next((item for item in layers if item.get("CODE") == ZONING_LAYER_CODE), None)
        if not layer:
            raise SystemExit("Source preflight failed: GovPilot ZM layer not found")
        features = await _fetch_zoning_features(client)
        rows = _build_zoning_rows(features)
        _validate_source_rows(rows)

        parcels = await _fetch_parcel_features(client)
        sample_ids = [
            str(parcel["ID"])
            for parcel in parcels[: max(args.parcel_detail_sample, 0)]
            if parcel.get("ID")
        ]
        details: list[dict[str, Any]] = []
        for parcel_id in sample_ids:
            detail = await _fetch_parcel_detail(client, parcel_id)
            if detail is not None:
                details.append(detail)

    distinct = sorted({row["zone_code"] for row in rows})
    zoning_non_null = sum(1 for detail in details if _trim(detail.get("ZONING")))
    print(f"layer={layer.get('DESC')} code={layer.get('CODE')}")
    print(f"govpilot_zm_features={len(features):,} usable_rows={len(rows):,}")
    print(f"distinct_zone_codes={len(distinct)}: {distinct}")
    print(f"govpilot_parcels_in_viewport={len(parcels):,}")
    print(
        "parcel_detail_ZONING_non_null="
        f"{zoning_non_null}/{len(details)} "
        "(expected 0-ish per PR #369; adapter uses spatial join)"
    )
    sample = dict(rows[0])
    sample["wkt"] = sample["wkt"][:120] + "..."
    print("sample_payload=" + json.dumps(sample, sort_keys=True)[:1600])
    return 0


async def _resolve_parent_jid(conn: asyncpg.Connection) -> str:
    jid = await conn.fetchval(
        """
        SELECT id
        FROM jurisdictions
        WHERE name = $1 AND state = $2
        ORDER BY id ASC
        LIMIT 1
        """,
        PARENT_JURISDICTION,
        STATE,
    )
    if jid:
        return str(jid)

    fallback_name = await conn.fetchval(
        "SELECT name FROM jurisdictions WHERE id=$1::uuid",
        PARENT_JID_FALLBACK,
    )
    if fallback_name:
        print(
            f"[register] using Burlington fallback JID {PARENT_JID_FALLBACK} "
            f"({fallback_name})"
        )
        return PARENT_JID_FALLBACK

    raise SystemExit(
        f"REFUSE FIRE - missing {PARENT_JURISDICTION}. "
        "Burlington umbrella must exist before PATH 1 per-muni registration."
    )


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
                ordinance_url = COALESCE($5, ordinance_url),
                coverage_level = COALESCE($6::coverage_level_enum, coverage_level)
            WHERE id = $1::uuid
            """,
            jid_s,
            "county_gis",
            BURLINGTON_PARCELS_LAYER,
            GOVPILOT_MAP_URL,
            "https://ecode360.com/MO0214",
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
            ordinance_url,
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
            $8,
            $9::coverage_level_enum,
            NOW()
        )
        """,
        new_jid,
        MUNI_JURISDICTION,
        STATE,
        COUNTY,
        "county_gis",
        BURLINGTON_PARCELS_LAYER,
        GOVPILOT_MAP_URL,
        "https://ecode360.com/MO0214",
        "partial",
    )
    print(f"[register] new {MUNI_JURISDICTION}: {new_jid}")
    return new_jid


async def _move_parcels_to_muni(
    conn: asyncpg.Connection,
    *,
    parent_jid: str,
    muni_jid: str,
) -> dict[str, int]:
    existing_before = int(
        await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
            muni_jid,
        )
    )
    candidates = int(
        await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM parcels
            WHERE jurisdiction_id=$1::uuid
              AND lower(coalesce(city, '')) = lower($2)
            """,
            parent_jid,
            PROD_CITY_VALUE,
        )
    )
    print(
        f"[PATH 1] existing_muni={existing_before:,} "
        f"parent_candidates_city={candidates:,}"
    )
    if existing_before + candidates < MIN_PROD_PARCELS:
        raise RuntimeError(
            f"Only {existing_before + candidates:,} Moorestown parcels visible "
            f"across parent+muni; expected at least {MIN_PROD_PARCELS:,}"
        )

    duplicate_merged = int(
        await conn.fetchval(
            """
            WITH candidates AS (
                SELECT src.*
                FROM parcels src
                WHERE src.jurisdiction_id = $1::uuid
                  AND lower(coalesce(src.city, '')) = lower($3)
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
                WHERE src.jurisdiction_id = $1::uuid
                  AND lower(coalesce(src.city, '')) = lower($3)
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
    total_after = int(
        await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
            muni_jid,
        )
    )
    print(
        f"[PATH 1] moved={moved:,} merged_duplicate_rows={duplicate_merged:,} "
        f"total_muni_after={total_after:,}"
    )
    if total_after < MIN_PROD_PARCELS:
        raise RuntimeError(
            f"Moorestown JID has only {total_after:,} parcels after PATH 1 move"
        )
    return {
        "existing_before": existing_before,
        "parent_candidates": candidates,
        "moved": moved,
        "merged_duplicate_rows": duplicate_merged,
        "total_after": total_after,
    }


async def _insert_zoning_rows(
    conn: asyncpg.Connection,
    *,
    muni_jid: str,
    rows: list[dict[str, Any]],
) -> int:
    await conn.execute(
        "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
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
                 AND zd.raw_attributes->>'source_kind' = 'govpilot_zoning_map_polygon'
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
                 AND zd.raw_attributes->>'source_kind' = 'govpilot_zoning_map_polygon'
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
        raise RuntimeError("No parcel geometry after Moorestown PATH 1 move")
    value = [
        float(bbox["min_lng"]),
        float(bbox["min_lat"]),
        float(bbox["max_lng"]),
        float(bbox["max_lat"]),
    ]
    if not (
        BBOX_LON[0] <= value[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= value[1] <= BBOX_LAT[1]
    ):
        raise RuntimeError(f"bbox {value} outside Moorestown envelope")
    await conn.execute(
        "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
        muni_jid,
        json.dumps(value),
    )
    print(f"[bbox] {value}")
    return value


async def _report(conn: asyncpg.Connection, muni_jid: str) -> None:
    summary = await conn.fetchrow(
        """
        SELECT
            COUNT(*)::INTEGER AS total,
            COUNT(*) FILTER (
                WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
            )::INTEGER AS bound,
            COUNT(*) FILTER (WHERE zone_binding_method = 'contained')::INTEGER AS contained,
            COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%')::INTEGER AS nearest
        FROM parcels
        WHERE jurisdiction_id = $1::uuid
        """,
        muni_jid,
    )
    districts = int(
        await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
            muni_jid,
        )
    )
    raw_empty = int(
        await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM zoning_districts
            WHERE jurisdiction_id=$1::uuid
              AND (raw_attributes IS NULL OR raw_attributes = '{}'::jsonb)
            """,
            muni_jid,
        )
    )
    total = int(summary["total"] or 0)
    bound = int(summary["bound"] or 0)
    contained = int(summary["contained"] or 0)
    nearest = int(summary["nearest"] or 0)
    coverage = 100.0 * bound / total if total else 0.0
    nearest_pct = 100.0 * nearest / total if total else 0.0

    print("\n=== HAND-OFF GATES ===")
    print(
        f"GATE 1 parcel zoning coverage {coverage:.1f}% "
        f"(>= {MIN_BOUND_COVERAGE_PCT:.0f}%) - "
        f"{'PASS' if coverage >= MIN_BOUND_COVERAGE_PCT else 'SUB'}"
    )
    print(f"GATE 2 nearest fallback {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
    print(f"GATE 3 raw_attributes empty {raw_empty} - {'PASS' if raw_empty == 0 else 'FAIL'}")
    print(f"GATE 4 zoning districts {districts:,} - {'PASS' if districts > 0 else 'FAIL'}")
    print(f"  parcels={total:,} bound={bound:,} contained={contained:,} nearest={nearest:,}")

    distribution = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*)::INTEGER AS n
        FROM parcels
        WHERE jurisdiction_id = $1::uuid
          AND zoning_code IS NOT NULL
          AND btrim(zoning_code) <> ''
        GROUP BY 1
        ORDER BY 2 DESC, 1
        """,
        muni_jid,
    )
    print(f"\nDistribution ({len(distribution)} parcel-exposed codes):")
    for row in distribution:
        marker = ""
        if row["zoning_code"] in {"BP-1", "BP-2", "LTC", "SRC"}:
            marker = "  <-- pre-staged matrix row"
        print(f"  {row['zoning_code']:12s} {row['n']:>6,}{marker}")


async def _fire(args: argparse.Namespace) -> int:
    mode = "DRY-RUN (ROLLBACK)" if args.dry_run else "FIRE"
    print(f"\n=== {mode}: Moorestown NJ GovPilot polygon spatial join ===\n")
    print(
        "HAND-OFF WARNING: this adapter is for nache review. "
        "Do not production-fire without source freshness + matrix signoff."
    )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        features = await _fetch_zoning_features(client)
    zoning_rows = _build_zoning_rows(features)
    _validate_source_rows(zoning_rows)
    distinct = sorted({row["zone_code"] for row in zoning_rows})
    print(
        f"[source] GovPilot ZM features={len(features):,} "
        f"usable_rows={len(zoning_rows):,} distinct={len(distinct)}"
    )

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        parent_jid = await _resolve_parent_jid(conn)
        print(f"[register] parent {PARENT_JURISDICTION}: {parent_jid}")

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            muni_jid = await _register_or_get_muni_jid(conn)
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

        print("\nFIRE committed.")

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    preflight = sub.add_parser(
        "source-preflight",
        help="Read-only GovPilot source probe; no DB connection or writes.",
    )
    preflight.add_argument(
        "--parcel-detail-sample",
        type=int,
        default=20,
        help="Number of GovPilot parcel detail records to sample for ZONING nullness.",
    )
    preflight.set_defaults(func=_source_preflight)

    fire = sub.add_parser(
        "fire",
        help="Transactional PATH 1 + zoning ingest. PREP only; nache executes.",
    )
    fire.add_argument("--dry-run", action="store_true")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)
    fire.set_defaults(func=_fire)
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parsed = _build_parser().parse_args()
    if (
        parsed.cmd == "fire"
        and not parsed.dry_run
        and not parsed.i_know_this_writes_to_prod
    ):
        print(
            "Refusing - pass fire --dry-run for transactional rehearsal "
            "or fire --i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)
    raise SystemExit(asyncio.run(parsed.func(parsed)))
