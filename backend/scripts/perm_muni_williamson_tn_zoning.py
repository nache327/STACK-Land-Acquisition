"""Phase 5 PREP - Williamson TN Class B per-muni zoning adapter.

Prep-only adapter derived from PR #334's Winnetka IL Class B pattern.
DO NOT FIRE without explicit Master/Lane A greenlight.

Targets from docs/WILLIAMSON_TN_ACQUISITION_SPEC.md:

  - Williamson County parcels:
      Tennessee statewide parcels explicitly EXCLUDE Williamson County.
      Use Williamson County's direct Parcels FeatureServer.

  - Brentwood per-muni proof:
      County parcels are spatially partitioned by Williamson incorporated
      areas where NAME='BRENTWOOD'. Zoning source is Brentwood GIS
      AdministrativeAreas/MapServer/9, zone-code field `Zoning`.
      prod_city_value = 'Brentwood' (PR #233 discipline).

  - Franklin per-muni proof:
      County parcels are spatially partitioned by Williamson incorporated
      areas where NAME='FRANKLIN'. Zoning source is Franklin publicmaps
      ZoningWebMercator/MapServer/9, zone-code field `ZONECLASS`.
      prod_city_value = 'Franklin' (PR #233 discipline).

Hard rules honored:
  - PREP script only; default CLI refuses writes.
  - --preflight is source-only/read-only.
  - --dry-run performs transactional rehearsal then rolls back.
  - Fire gate refuses if Williamson County, TN JID is missing.
  - Fire gate refuses if county parcel ingest produces <100 parcels.
  - Full DB pipeline runs inside one transaction.
  - DELETE-then-INSERT inside tx for zoning_districts.
  - COALESCE-guarded parcel binding UPDATEs.
  - raw_attributes preserved with ArcGIS passthrough + provenance.
  - parcels.city and zoning raw_attributes.municipality use prod_city_value,
    not raw authority/muni name.
  - No zone_use_matrix writes. Orchestrator owns Williamson substrate.
  - No audit refresh.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import shape
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("williamson_tn_zoning")

ADAPTER_ID = "perm_muni_williamson_tn_zoning"
WILLIAMSON_JURISDICTION_NAME = "Williamson County, TN"
MIN_PARCELS_FOR_FIRE = 100
ARCGIS_PAGE_SIZE = 750

PARCEL_LAYER_URL = (
    "https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/"
    "Parcels/FeatureServer/0"
)
INCORPORATED_AREAS_URL = (
    "https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/"
    "CountyMap_gdb/FeatureServer/2"
)
BRENTWOOD_ZONING_URL = (
    "https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/"
    "AdministrativeAreas/MapServer/9"
)
FRANKLIN_ZONING_URL = (
    "https://publicmaps.franklintn.gov/arcgis/rest/services/Maps/"
    "ZoningWebMercator/MapServer/9"
)

# Gross Williamson County envelope from source probes. Used only to catch
# wrong-county fires, not as a tight-fit geography check.
BBOX_LON_RANGE = (-87.30, -86.45)
BBOX_LAT_RANGE = (35.65, 36.20)

_STAGE_COLUMNS = [
    "jurisdiction_id", "apn", "address", "city", "owner_name",
    "zoning_code", "zone_class", "land_use_code", "acres",
    "county_link", "in_flood_zone", "in_wetland", "avg_slope_pct",
    "has_structure", "improvement_value",
    "assessed_value", "is_residential",
    "geom_wkb", "centroid_wkb", "raw_json",
]

_CREATE_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_parcels (
    jurisdiction_id uuid, apn text, address text, city text,
    owner_name text, zoning_code text, zone_class text,
    land_use_code text, acres double precision, county_link text,
    in_flood_zone boolean, in_wetland boolean, avg_slope_pct double precision,
    has_structure boolean, improvement_value double precision,
    assessed_value double precision, is_residential boolean,
    geom_wkb bytea, centroid_wkb bytea, raw_json text
)
"""
_TRUNCATE_STAGE_SQL = "TRUNCATE _stage_parcels"
_MERGE_SQL = """
INSERT INTO parcels (
    jurisdiction_id, apn, address, city, owner_name, zoning_code, zone_class,
    land_use_code, acres, county_link, in_flood_zone, in_wetland,
    avg_slope_pct, has_structure, improvement_value,
    assessed_value, is_residential,
    geom, centroid, raw
)
SELECT
    s.jurisdiction_id, s.apn, s.address, s.city, s.owner_name,
    s.zoning_code, s.zone_class::zone_class_enum,
    s.land_use_code, s.acres, s.county_link,
    s.in_flood_zone, s.in_wetland, s.avg_slope_pct,
    s.has_structure, s.improvement_value,
    s.assessed_value, s.is_residential,
    ST_GeomFromEWKB(s.geom_wkb),
    ST_GeomFromEWKB(s.centroid_wkb),
    s.raw_json::jsonb
FROM _stage_parcels s
ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn DO UPDATE SET
    address = EXCLUDED.address,
    city = COALESCE(EXCLUDED.city, parcels.city),
    owner_name = EXCLUDED.owner_name,
    land_use_code = EXCLUDED.land_use_code,
    acres = EXCLUDED.acres,
    county_link = EXCLUDED.county_link,
    has_structure = EXCLUDED.has_structure,
    improvement_value = EXCLUDED.improvement_value,
    assessed_value = COALESCE(EXCLUDED.assessed_value, parcels.assessed_value),
    is_residential = COALESCE(EXCLUDED.is_residential, parcels.is_residential),
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid,
    raw = EXCLUDED.raw,
    updated_at = NOW()
"""


@dataclass(frozen=True)
class MuniConfig:
    scope: str
    prod_city_value: str
    jurisdiction_name: str
    muni_type: str
    boundary_name: str
    zoning_url: str
    zone_field: str
    zone_name_field: str | None
    authority_name: str
    ordinance_url: str


@dataclass(frozen=True)
class DistrictRow:
    scope: str
    prod_city_value: str
    zone_code: str
    zone_name: str
    geom_wkt: str
    raw_attributes: str


MUNIS = [
    MuniConfig(
        scope="brentwood",
        prod_city_value="Brentwood",
        jurisdiction_name="Brentwood, TN",
        muni_type="city",
        boundary_name="BRENTWOOD",
        zoning_url=BRENTWOOD_ZONING_URL,
        zone_field="Zoning",
        zone_name_field=None,
        authority_name="City of Brentwood",
        ordinance_url="https://www.brentwoodtn.gov/Departments/Planning-and-Codes/Planning-Section",
    ),
    MuniConfig(
        scope="franklin",
        prod_city_value="Franklin",
        jurisdiction_name="Franklin, TN",
        muni_type="city",
        boundary_name="FRANKLIN",
        zoning_url=FRANKLIN_ZONING_URL,
        zone_field="ZONECLASS",
        zone_name_field="ZONEDESC",
        authority_name="City of Franklin",
        ordinance_url="https://web.franklintn.gov/flippingbook/FranklinZoningOrdinance/",
    ),
]


class _RollbackForDryRun(Exception):
    """Sentinel raised inside transaction context to force rollback."""


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _trim(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_bool_has_structure(attrs: dict[str, Any]) -> bool | None:
    improvement = None
    for key in ("IMP_VAL", "IMP_VALUE", "IMP_ASSES", "IMP_ASSESS"):
        improvement = _safe_float(attrs.get(key))
        if improvement is not None:
            break
    if improvement is None:
        return None
    return improvement > 0


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


def _parse_geojson_geom(geom_json: dict[str, Any] | None):
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


def _raw_attrs(attrs: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    raw = dict(extra)
    for key, value in attrs.items():
        if value is None:
            continue
        raw[key] = value
    return raw


def _county_link(attrs: dict[str, Any]) -> str | None:
    direct = _trim(attrs.get("URL_LINK") or attrs.get("WEBLINK"))
    if direct:
        return direct
    lrsn = _trim(attrs.get("LRSN") or attrs.get("LRSN_WEB"))
    if lrsn:
        return f"https://inigo.williamson-tn.org/property_search/#{lrsn}"
    return None


def _map_parcel_row(
    attrs: dict[str, Any],
    geom,
    williamson_jid: str,
) -> dict[str, Any] | None:
    apn = _trim(attrs.get("PIN") or attrs.get("PARCEL_ID"))
    if not apn:
        return None

    raw = _raw_attrs(
        attrs,
        {
            "adapter": ADAPTER_ID,
            "source_url": PARCEL_LAYER_URL,
            "source_kind": "arcgis_feature_server",
            "source_role": "county_parcels",
            "authority_name": "Williamson County GIS",
            "note": "TN statewide parcel layer excludes Williamson; county-direct source used.",
        },
    )

    assessed = _safe_float(attrs.get("TOTAL_MARK") or attrs.get("TOTAL_ASSE"))
    improvement = _safe_float(
        attrs.get("IMP_VAL")
        or attrs.get("IMP_VALUE")
        or attrs.get("IMP_ASSES")
        or attrs.get("IMP_ASSESS")
    )

    return {
        "jurisdiction_id": williamson_jid,
        "apn": apn,
        "address": _trim(attrs.get("ADDRESS") or attrs.get("PROP_STREE")),
        # Keep source city code on umbrella rows; per-muni rows are reset to
        # prod_city_value during PATH 1 transparent UPDATE.
        "city": _trim(attrs.get("CITY")),
        "owner_name": _trim(attrs.get("OWNER_1") or attrs.get("OWNER1")),
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": _trim(attrs.get("PROP_TYP") or attrs.get("PROP_TYPE") or attrs.get("PARCEL_TYP")),
        "acres": _safe_float(attrs.get("AC") or attrs.get("Acreage") or attrs.get("Calculated")),
        "county_link": _county_link(attrs),
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": _safe_bool_has_structure(attrs),
        "improvement_value": improvement,
        "assessed_value": assessed if assessed and assessed > 0 else None,
        "is_residential": None,
        "geom": geom,
        "centroid": geom.centroid,
        "raw": raw,
    }


def _row_to_record(row: dict[str, Any]) -> tuple:
    return (
        row["jurisdiction_id"],
        row["apn"],
        row.get("address"),
        row.get("city"),
        row.get("owner_name"),
        row.get("zoning_code"),
        row.get("zone_class"),
        row.get("land_use_code"),
        row.get("acres"),
        row.get("county_link"),
        row.get("in_flood_zone"),
        bool(row.get("in_wetland")),
        row.get("avg_slope_pct"),
        row.get("has_structure"),
        row.get("improvement_value"),
        row.get("assessed_value"),
        row.get("is_residential"),
        wkb_dumps(row["geom"], hex=False, srid=4326),
        wkb_dumps(row["centroid"], hex=False, srid=4326),
        json.dumps(row["raw"]),
    )


async def _fetch_arcgis_features(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str = "1=1",
    *,
    geojson: bool = False,
    page_size: int = ARCGIS_PAGE_SIZE,
    max_features: int | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        remaining = None if max_features is None else max_features - len(features)
        if remaining is not None and remaining <= 0:
            break
        requested_count = page_size if remaining is None else min(page_size, remaining)
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": requested_count,
            "f": "geojson" if geojson else "json",
            "orderByFields": "OBJECTID",
        }
        if geojson:
            # Hosted Williamson parcel layer uses FID as OID; OBJECTID order
            # can fail on some FeatureServers. Omit ordering for GeoJSON pulls.
            params.pop("orderByFields", None)
        r = await client.get(f"{layer_url}/query", params=params)
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(f"ArcGIS query failed for {layer_url}: {payload['error']}")
        batch = payload.get("features", [])
        if max_features is not None and len(features) + len(batch) > max_features:
            batch = batch[: max_features - len(features)]
        features.extend(batch)
        logger.info("fetched %d (cum %d) layer=%s", len(batch), len(features), layer_url)
        if len(batch) < requested_count:
            break
        if max_features is not None and len(features) >= max_features:
            break
        offset += requested_count
    return features


async def _fetch_count(client: httpx.AsyncClient, layer_url: str, where: str = "1=1") -> int:
    r = await client.get(
        f"{layer_url}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS count failed for {layer_url}: {payload['error']}")
    return int(payload.get("count") or 0)


async def _source_freshness_check(client: httpx.AsyncClient, muni: MuniConfig) -> None:
    """PR #319 lesson: probe-time source viability is not fire-time viability."""
    meta = await client.get(f"{muni.zoning_url}", params={"f": "json"})
    meta.raise_for_status()
    meta_payload = meta.json()
    if "error" in meta_payload:
        raise SystemExit(f"HALT source freshness: {muni.prod_city_value} metadata error {meta_payload['error']}")
    fields = {f.get("name") for f in meta_payload.get("fields", [])}
    if muni.zone_field not in fields:
        raise SystemExit(
            f"HALT source freshness: {muni.prod_city_value} zone-code field "
            f"{muni.zone_field!r} missing from {muni.zoning_url}"
        )

    sample = await client.get(
        f"{muni.zoning_url}/query",
        params={
            "where": "1=1",
            "outFields": muni.zone_field,
            "returnGeometry": "false",
            "resultRecordCount": 50,
            "f": "json",
        },
    )
    sample.raise_for_status()
    payload = sample.json()
    if "error" in payload:
        raise SystemExit(f"HALT source freshness: {muni.prod_city_value} sample error {payload['error']}")
    features = payload.get("features", [])
    if not features:
        raise SystemExit(f"HALT source freshness: {muni.prod_city_value} returned 0 sample rows")
    non_null = 0
    for feature in features:
        attrs = feature.get("attributes", {})
        if _trim(attrs.get(muni.zone_field)):
            non_null += 1
    pct = 100.0 * non_null / len(features)
    print(
        f"[freshness] {muni.prod_city_value}: field={muni.zone_field} "
        f"sample_non_null={non_null}/{len(features)} ({pct:.1f}%)"
    )
    if pct < 70.0:
        raise SystemExit(
            f"HALT source freshness: {muni.prod_city_value} {muni.zone_field} "
            f"sample non-null {pct:.1f}% < 70%"
        )


async def _run_source_freshness_checks(client: httpx.AsyncClient) -> None:
    for muni in MUNIS:
        await _source_freshness_check(client, muni)


def _build_boundary_rows(features: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        name = _trim(attrs.get("NAME"))
        if not name or not geom or "rings" not in geom:
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip boundary OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue
        rows.append((name.upper(), name.title(), wkt))
    return rows


def _build_district_rows(
    features: list[dict[str, Any]],
    muni: MuniConfig,
) -> list[DistrictRow]:
    rows: list[DistrictRow] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        zone_code = _trim(attrs.get(muni.zone_field))
        if not geom or "rings" not in geom:
            continue
        if not zone_code:
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip %s OBJECTID=%s: %s", muni.prod_city_value, attrs.get("OBJECTID"), exc)
            continue

        zone_name = _trim(attrs.get(muni.zone_name_field)) if muni.zone_name_field else None
        raw = _raw_attrs(
            attrs,
            {
                "adapter": ADAPTER_ID,
                "scope": muni.scope,
                "source_url": muni.zoning_url,
                "source_filter": "1=1",
                "source_kind": "arcgis_map_server",
                "authority_name": muni.authority_name,
                "muni_name": muni.authority_name,
                "prod_city_value": muni.prod_city_value,
                "municipality": muni.prod_city_value,
                "muni_type": muni.muni_type,
                "zone_code_field": muni.zone_field,
                "ordinance_url": muni.ordinance_url,
                "note": "Class B per-muni Williamson TN proof; parcels.city set to prod_city_value.",
            },
        )
        rows.append(
            DistrictRow(
                scope=muni.scope,
                prod_city_value=muni.prod_city_value,
                zone_code=zone_code,
                zone_name=zone_name or zone_code,
                geom_wkt=wkt,
                raw_attributes=json.dumps(raw),
            )
        )
    return rows


def _build_parcel_rows(
    features: list[dict[str, Any]],
    williamson_jid: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows_by_apn: dict[str, dict[str, Any]] = {}
    stats = {"geom_skipped": 0, "apn_skipped": 0}
    for feature in features:
        attrs = feature.get("properties") or {}
        geom = _parse_geojson_geom(feature.get("geometry"))
        if geom is None:
            stats["geom_skipped"] += 1
            continue
        row = _map_parcel_row(attrs, geom, williamson_jid)
        if row is None:
            stats["apn_skipped"] += 1
            continue
        rows_by_apn[row["apn"]] = row
    return list(rows_by_apn.values()), stats


async def _copy_upsert_parcels(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> int:
    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute(_TRUNCATE_STAGE_SQL)
    chunk_size = 25_000
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        await conn.copy_records_to_table(
            "_stage_parcels",
            records=[_row_to_record(row) for row in chunk],
            columns=_STAGE_COLUMNS,
        )
    inserted = await conn.fetchval(
        "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
    )
    return int(inserted or 0)


async def _lookup_williamson_jid(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state='TN'",
        WILLIAMSON_JURISDICTION_NAME,
    )
    if not row:
        raise SystemExit(
            f"REFUSE FIRE - jurisdiction {WILLIAMSON_JURISDICTION_NAME!r} "
            "is missing. Register the Williamson umbrella first."
        )
    return str(row["id"])


async def _resolve_or_register_muni(
    conn: asyncpg.Connection,
    muni: MuniConfig,
) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state='TN'",
        muni.jurisdiction_name,
    )
    if existing:
        return str(existing["id"])
    new_id = str(uuid.uuid4())
    new_id = await conn.fetchval(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, parcel_source, parcel_endpoint,
            zoning_endpoint, ordinance_url, coverage_level
        )
        VALUES (
            $1::uuid, $2, 'TN', 'Williamson',
            'county_gis'::parcel_source_enum, $3, $4, $5,
            'partial'::coverage_level_enum
        )
        RETURNING id
        """,
        new_id,
        muni.jurisdiction_name,
        PARCEL_LAYER_URL,
        muni.zoning_url,
        muni.ordinance_url,
    )
    return str(new_id)


async def _stage_boundaries(
    conn: asyncpg.Connection,
    boundary_rows: list[tuple[str, str, str]],
) -> None:
    await conn.execute(
        """
        CREATE TEMP TABLE _williamson_muni_boundaries (
            boundary_name text,
            source_name text,
            geom geometry(MultiPolygon, 4326)
        ) ON COMMIT DROP
        """
    )
    for boundary_name, source_name, wkt in boundary_rows:
        await conn.execute(
            """
            INSERT INTO _williamson_muni_boundaries (boundary_name, source_name, geom)
            VALUES ($1, $2, ST_Multi(ST_MakeValid(ST_GeomFromText($3, 4326))))
            """,
            boundary_name,
            source_name,
            wkt,
        )


async def _prepare_idempotent_parcel_base(
    conn: asyncpg.Connection,
    williamson_jid: str,
    muni_jids: dict[str, str],
) -> None:
    """Move prior sibling rows back to umbrella before county upsert.

    This keeps the PATH 1 transparent UPDATE pattern idempotent while avoiding
    duplicate (jurisdiction_id, apn) conflicts when the county source is
    re-upserted after a previous per-muni move.
    """
    sibling_ids = list(muni_jids.values())
    if not sibling_ids:
        return
    deleted = await conn.execute(
        """
        DELETE FROM parcels umbrella
        USING parcels sibling
        WHERE umbrella.jurisdiction_id=$1::uuid
          AND sibling.jurisdiction_id = ANY($2::uuid[])
          AND umbrella.apn = sibling.apn
        """,
        williamson_jid,
        sibling_ids,
    )
    moved = await conn.execute(
        """
        UPDATE parcels
           SET jurisdiction_id=$1::uuid,
               city = raw->>'CITY',
               zoning_code=NULL,
               zone_class=NULL,
               zone_binding_method=NULL,
               updated_at=NOW()
         WHERE jurisdiction_id = ANY($2::uuid[])
        """,
        williamson_jid,
        sibling_ids,
    )
    print(
        "[idempotency] sibling->umbrella reset: "
        f"deleted_conflicting_umbrella={deleted.split()[-1]} "
        f"moved_back={moved.split()[-1]}"
    )


async def _move_target_parcels(
    conn: asyncpg.Connection,
    williamson_jid: str,
    muni: MuniConfig,
    muni_jid: str,
) -> int:
    status = await conn.execute(
        """
        UPDATE parcels p
           SET jurisdiction_id=$2::uuid,
               city=$3,
               zoning_code=NULL,
               zone_class=NULL,
               zone_binding_method=NULL,
               updated_at=NOW()
         WHERE p.jurisdiction_id=$1::uuid
           AND p.geom IS NOT NULL
           AND EXISTS (
               SELECT 1
               FROM _williamson_muni_boundaries b
               WHERE b.boundary_name=$4
                 AND ST_Within(ST_Centroid(p.geom), b.geom)
           )
        """,
        williamson_jid,
        muni_jid,
        muni.prod_city_value,
        muni.boundary_name,
    )
    return int(status.split()[-1])


async def _clear_and_insert_zoning(
    conn: asyncpg.Connection,
    muni_jid: str,
    rows: list[DistrictRow],
) -> int:
    cleared = await conn.execute(
        "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
        muni_jid,
    )
    print(f"[idempotency] cleared {cleared.split()[-1]} prior zoning_districts for {muni_jid}")
    await conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS _stage_williamson_zoning (
            jurisdiction_id uuid,
            zone_code text,
            zone_name text,
            geom_wkt text,
            raw_attributes text
        ) ON COMMIT DROP
        """
    )
    await conn.execute("TRUNCATE _stage_williamson_zoning")
    await conn.copy_records_to_table(
        "_stage_williamson_zoning",
        records=[
            (
                muni_jid,
                row.zone_code,
                row.zone_name,
                row.geom_wkt,
                row.raw_attributes,
            )
            for row in rows
        ],
        columns=[
            "jurisdiction_id",
            "zone_code",
            "zone_name",
            "geom_wkt",
            "raw_attributes",
        ],
    )
    inserted = await conn.fetchval(
        """
        WITH ins AS (
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class,
                geom, raw_attributes, source
            )
            SELECT
                s.jurisdiction_id,
                s.zone_code,
                s.zone_name,
                'unknown'::zone_class_enum,
                ST_Multi(ST_MakeValid(ST_GeomFromText(s.geom_wkt, 4326))),
                s.raw_attributes::jsonb,
                'arcgis'::zone_source_enum
            FROM _stage_williamson_zoning s
            RETURNING 1
        )
        SELECT COUNT(*) FROM ins
        """
    )
    return int(inserted or 0)


async def _spatial_backfill(
    conn: asyncpg.Connection,
    muni_jid: str,
    prod_city_value: str,
    nearest_within_meters: float,
) -> tuple[int, int]:
    contained = await conn.execute(
        """
        UPDATE parcels target SET
            zone_class=sub.zone_class,
            zone_binding_method='contained',
            zoning_code=COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id=$1::uuid
                  AND zd.raw_attributes->>'municipality'=$2
                  AND zd.geom IS NOT NULL
                  AND ST_Within(ST_Centroid(p.geom), zd.geom)
                ORDER BY zd.id
                LIMIT 1
            ) m
            WHERE p.jurisdiction_id=$1::uuid
              AND p.city=$2
              AND p.geom IS NOT NULL
        ) sub
        WHERE target.id=sub.parcel_id
        """,
        muni_jid,
        prod_city_value,
    )
    label = f"nearest_{int(round(nearest_within_meters))}m"
    nearest = await conn.execute(
        """
        UPDATE parcels target SET
            zone_class=sub.zone_class,
            zone_binding_method=$3,
            zoning_code=COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id=$1::uuid
                  AND zd.raw_attributes->>'municipality'=$2
                  AND zd.geom IS NOT NULL
                  AND ST_DWithin(
                      zd.geom::geography,
                      ST_Centroid(p.geom)::geography,
                      $4
                  )
                ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography)
                LIMIT 1
            ) m
            WHERE p.jurisdiction_id=$1::uuid
              AND p.city=$2
              AND p.geom IS NOT NULL
              AND p.zone_binding_method IS NULL
        ) sub
        WHERE target.id=sub.parcel_id
        """,
        muni_jid,
        prod_city_value,
        label,
        float(nearest_within_meters),
    )
    return int(contained.split()[-1]), int(nearest.split()[-1])


async def _update_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
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
        raise RuntimeError(f"no parcel geometry for bbox update jid={jid}")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    lon_lo, lon_hi = BBOX_LON_RANGE
    lat_lo, lat_hi = BBOX_LAT_RANGE
    if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
        raise RuntimeError(f"bbox {bbox} outside Williamson envelope")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _print_muni_verdict(conn: asyncpg.Connection, muni: MuniConfig, muni_jid: str) -> None:
    parcels = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
               COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
        FROM parcels WHERE jurisdiction_id=$1::uuid
        """,
        muni_jid,
    )
    districts = await conn.fetchval(
        "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
        muni_jid,
    )
    empty_raw = await conn.fetchval(
        """
        SELECT COUNT(*) FROM zoning_districts
        WHERE jurisdiction_id=$1::uuid
          AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)
        """,
        muni_jid,
    )
    coverage = 100.0 * parcels["bound"] / parcels["total"] if parcels["total"] else 0.0
    nearest_pct = 100.0 * parcels["nearest"] / parcels["total"] if parcels["total"] else 0.0
    print(f"\n=== {muni.prod_city_value} 5-GATE PREVIEW ===")
    print(f"GATE 1 cov {coverage:.1f}% (>=70%) - {'PASS' if coverage >= 70 else 'SUB'}")
    print(f"GATE 2 near {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
    print(f"GATE 3 raw empty {empty_raw} - {'PASS' if empty_raw == 0 else 'FAIL'}")
    print(f"GATE 4 districts {districts} - {'PASS' if districts and districts > 0 else 'FAIL'}")
    print("GATE 5 bbox populated")
    print(
        f"  parcels={parcels['total']:,} bound={parcels['bound']:,} "
        f"contained={parcels['contained']:,} nearest={parcels['nearest']:,}"
    )
    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
        FROM parcels
        WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
        """,
        muni_jid,
    )
    print(f"  distribution ({len(codes)} codes):")
    for row in codes[:20]:
        print(f"    {row['zoning_code']:18s} {row['n']:>6,}")


async def _preflight(max_parcels: int = 1000) -> int:
    print("\n=== PRE-FLIGHT: Williamson TN source checks (NO DB WRITES) ===\n")
    async with httpx.AsyncClient(timeout=180.0) as client:
        await _run_source_freshness_checks(client)
        parcel_count = await _fetch_count(client, PARCEL_LAYER_URL)
        print(f"[source] county parcel count: {parcel_count:,}")
        parcel_features = await _fetch_arcgis_features(
            client,
            PARCEL_LAYER_URL,
            geojson=True,
            max_features=max_parcels,
        )
        boundary_features = await _fetch_arcgis_features(
            client,
            INCORPORATED_AREAS_URL,
            "upper(NAME) in ('BRENTWOOD','FRANKLIN')",
        )
        zoning_counts = {}
        zoning_samples = {}
        for muni in MUNIS:
            zoning_counts[muni.prod_city_value] = await _fetch_count(client, muni.zoning_url)
            zoning_samples[muni.prod_city_value] = await _fetch_arcgis_features(
                client,
                muni.zoning_url,
                max_features=5,
            )

    parcel_rows, parcel_stats = _build_parcel_rows(
        parcel_features,
        "00000000-0000-0000-0000-000000000000",
    )
    boundary_rows = _build_boundary_rows(boundary_features)
    print(f"[build] parcel sample fetched={len(parcel_features):,} built={len(parcel_rows):,} stats={parcel_stats}")
    if parcel_rows:
        raw_keys = sorted(parcel_rows[0]["raw"].keys())
        print(f"[build] sample parcel raw keys: {len(raw_keys)} ({raw_keys[:12]}...)")
    print(f"[build] boundary rows: {len(boundary_rows)} {[row[0] for row in boundary_rows]}")
    for muni in MUNIS:
        district_rows = _build_district_rows(zoning_samples[muni.prod_city_value], muni)
        print(
            f"[source] {muni.prod_city_value} zoning count: "
            f"{zoning_counts[muni.prod_city_value]:,}; "
            f"sample_district_rows={len(district_rows)}/5"
        )
        if not district_rows:
            raise SystemExit(f"HALT preflight: {muni.prod_city_value} zoning geometry sample built 0 rows")
    print("\n(NO DB WRITES - source freshness and pipeline shape validated)")
    return 0


async def _run_pipeline(
    *,
    dry_run: bool,
    nearest_within_meters: float,
    max_parcels: int | None,
) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Williamson TN Class B per-muni adapter ===\n")
    started = time.time()

    async with httpx.AsyncClient(timeout=240.0) as client:
        await _run_source_freshness_checks(client)
        source_count = await _fetch_count(client, PARCEL_LAYER_URL)
        print(f"[source] Williamson county parcel count: {source_count:,}")
        if source_count < MIN_PARCELS_FOR_FIRE:
            raise SystemExit(f"REFUSE FIRE - parcel source count {source_count} < {MIN_PARCELS_FOR_FIRE}")

        parcel_features = await _fetch_arcgis_features(
            client,
            PARCEL_LAYER_URL,
            geojson=True,
            max_features=max_parcels,
        )
        boundary_features = await _fetch_arcgis_features(
            client,
            INCORPORATED_AREAS_URL,
            "upper(NAME) in ('BRENTWOOD','FRANKLIN')",
        )
        zoning_features: dict[str, list[dict[str, Any]]] = {}
        for muni in MUNIS:
            zoning_features[muni.scope] = await _fetch_arcgis_features(client, muni.zoning_url)

    boundary_rows = _build_boundary_rows(boundary_features)
    if not any(row[0] == "BRENTWOOD" for row in boundary_rows):
        raise SystemExit("HALT - Brentwood incorporated-area boundary missing")
    if not any(row[0] == "FRANKLIN" for row in boundary_rows):
        raise SystemExit("HALT - Franklin incorporated-area boundary missing")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=7200,
    )
    try:
        williamson_jid = await _lookup_williamson_jid(conn)
        print(f"[jurisdiction] Williamson umbrella: {williamson_jid}")

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            muni_jids = {
                muni.scope: await _resolve_or_register_muni(conn, muni)
                for muni in MUNIS
            }
            for muni in MUNIS:
                print(f"[jurisdiction] {muni.jurisdiction_name}: {muni_jids[muni.scope]}")

            await _prepare_idempotent_parcel_base(conn, williamson_jid, muni_jids)

            parcel_rows, parcel_stats = _build_parcel_rows(parcel_features, williamson_jid)
            print(
                "[build] county parcel rows: "
                f"features={len(parcel_features):,} rows={len(parcel_rows):,} stats={parcel_stats}"
            )
            if len(parcel_rows) < MIN_PARCELS_FOR_FIRE:
                raise RuntimeError(
                    f"county parcel build produced {len(parcel_rows)} rows; "
                    f"threshold {MIN_PARCELS_FOR_FIRE}"
                )
            upserted = await _copy_upsert_parcels(conn, parcel_rows)
            print(f"[parcels] COPY/upsert rows: {upserted:,}")

            county_count = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
                williamson_jid,
            )
            if county_count < MIN_PARCELS_FOR_FIRE:
                raise RuntimeError(
                    f"REFUSE FIRE - only {county_count} parcels under Williamson JID "
                    f"after county ingest; threshold {MIN_PARCELS_FOR_FIRE}"
                )
            print(f"[gate] {county_count:,} parcels under Williamson umbrella before per-muni split")

            await _stage_boundaries(conn, boundary_rows)
            moved_counts: dict[str, int] = {}
            for muni in MUNIS:
                moved = await _move_target_parcels(
                    conn,
                    williamson_jid,
                    muni,
                    muni_jids[muni.scope],
                )
                moved_counts[muni.scope] = moved
                print(f"[path1] moved {moved:,} parcels to {muni.prod_city_value}")
                if moved < MIN_PARCELS_FOR_FIRE:
                    raise RuntimeError(
                        f"{muni.prod_city_value}: only {moved} parcels moved; "
                        f"threshold {MIN_PARCELS_FOR_FIRE}"
                    )

            for muni in MUNIS:
                district_rows = _build_district_rows(zoning_features[muni.scope], muni)
                distinct = sorted({row.zone_code for row in district_rows})
                print(
                    f"[build] {muni.prod_city_value} districts: "
                    f"features={len(zoning_features[muni.scope]):,} "
                    f"rows={len(district_rows):,} distinct={len(distinct)}"
                )
                if not district_rows:
                    raise RuntimeError(f"{muni.prod_city_value}: zero district rows built")
                inserted = await _clear_and_insert_zoning(
                    conn,
                    muni_jids[muni.scope],
                    district_rows,
                )
                print(f"[zoning] {muni.prod_city_value}: inserted {inserted:,} zoning_districts")

                contained, nearest = await _spatial_backfill(
                    conn,
                    muni_jids[muni.scope],
                    muni.prod_city_value,
                    nearest_within_meters,
                )
                print(
                    f"[spatial] {muni.prod_city_value}: "
                    f"contained={contained:,} nearest={nearest:,}"
                )
                bbox = await _update_bbox(conn, muni_jids[muni.scope])
                print(f"[bbox] {muni.prod_city_value}: {bbox}")

            county_bbox = await _update_bbox(conn, williamson_jid)
            print(f"[bbox] Williamson residual umbrella: {county_bbox}")

            for muni in MUNIS:
                await _print_muni_verdict(conn, muni, muni_jids[muni.scope])

            residual = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
                williamson_jid,
            )
            print(f"\n[summary] Williamson residual parcels after split: {residual:,}")
            print(
                "[summary] moved target parcels: "
                + ", ".join(f"{m.scope}={moved_counts[m.scope]:,}" for m in MUNIS)
            )

            if dry_run:
                raise _RollbackForDryRun()

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    elapsed = time.time() - started
    print(f"\ncompleted in {elapsed / 60:.1f} min")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    parser.add_argument(
        "--max-parcels",
        type=int,
        help="Limit county parcel fetch for source-shape testing. Allowed only with --preflight or --dry-run.",
    )
    args = parser.parse_args()

    if args.max_parcels is not None and not (args.preflight or args.dry_run):
        print("--max-parcels is allowed only with --preflight or --dry-run", file=sys.stderr)
        return 2
    if args.preflight and (args.dry_run or args.i_know_this_writes_to_prod):
        print("--preflight cannot be combined with fire/dry-run flags", file=sys.stderr)
        return 2
    if not args.preflight and not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass --preflight for source checks, --dry-run for "
            "transactional rehearsal, or --i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.preflight:
        return asyncio.run(_preflight(max_parcels=args.max_parcels or 1000))
    return asyncio.run(
        _run_pipeline(
            dry_run=args.dry_run,
            nearest_within_meters=args.nearest_within_meters,
            max_parcels=args.max_parcels,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
