"""
ArcGIS GeoDataFrame → PostGIS Parcel ingestion service.

Maps ArcGIS feature fields to the Parcel ORM schema.
Handles geometry validation and bulk insertion.

Field mapping is jurisdiction-aware: Draper uses specific field names (PARCEL,
PROP_LOC, ZONING, etc.).  Future jurisdictions add their own field maps below.
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Any

import geopandas as gpd
from geoalchemy2 import WKTElement
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcel import Parcel
from app.services.overlays import SFHA_ZONES
from app.services.vacancy import is_vacant_by_landuse

logger = logging.getLogger(__name__)

# ─── Candidate field-name lists (first match wins) ─────────────────────────

_APN_FIELDS = ["PARCEL", "APN", "PARCELNO", "PARCEL_NO", "PARCEL_ID", "PIN"]
_ADDRESS_FIELDS = ["PROP_LOC", "SITUS", "SITUS_ADDRESS", "ADDRESS", "FULL_ADDRESS"]
_ZONE_FIELDS = ["ZONING", "ZONE", "ZONE_CODE", "ZONING_CODE", "ZONE_DIST"]
_LANDUSE_FIELDS = ["LANDUSE", "LAND_USE", "LAND_USE_CODE", "USE_CODE", "CLASS"]
_ACRES_FIELDS = ["CALC_ACRE", "PARCEL_ACR", "ACRES", "GIS_ACRES", "ACREAGE"]
_LINK_FIELDS = ["LINK", "COUNTY_LINK", "PARCEL_URL", "URL", "WEB_LINK"]
_FLOOD_FIELDS = ["FLOODZONE", "FLOOD_ZONE", "FLD_ZONE", "SFHA"]

# ─── Helpers ────────────────────────────────────────────────────────────────

def _first(row: Any, fields: list[str]) -> Any:
    """Return the value of the first field that exists and is non-null."""
    for f in fields:
        v = row.get(f) if isinstance(row, dict) else getattr(row, f, None)
        if v is not None and str(v).strip() not in ("", "nan", "None"):
            return v
    return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _is_in_flood_zone(raw_value: Any) -> bool:
    if raw_value is None:
        return False
    code = str(raw_value).strip().upper()
    base = code.split("-")[0].split(" ")[0]
    return base in SFHA_ZONES


def _normalize_geom(geom: Any) -> Polygon | MultiPolygon | None:
    """Return a valid Polygon/MultiPolygon or None."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return None
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
    return geom


def _map_row(row: Any, jurisdiction_id: uuid.UUID) -> dict | None:
    """
    Convert a single GeoDataFrame row to a dict ready for Parcel bulk insert.
    Returns None if the row has no usable geometry or APN.
    """
    geom = _normalize_geom(row.geometry)
    if geom is None:
        return None

    apn = _first(row, _APN_FIELDS)
    if not apn:
        return None

    land_use = _first(row, _LANDUSE_FIELDS)
    if land_use:
        land_use = str(land_use).strip() or None

    vacant = is_vacant_by_landuse(land_use)
    has_structure: bool | None = False if vacant is True else None

    # Build raw property snapshot (strip geometry, coerce to str)
    if hasattr(row, "_asdict"):
        props = {k: v for k, v in row._asdict().items() if k != "geometry"}
    elif hasattr(row, "to_dict"):
        props = {k: v for k, v in row.to_dict().items() if k != "geometry"}
    else:
        props = {}
    raw = {k: str(v) if v is not None else None for k, v in props.items()}

    return {
        "jurisdiction_id": jurisdiction_id,
        "apn": str(apn),
        "address": str(a).strip() if (a := _first(row, _ADDRESS_FIELDS)) else None,
        "zoning_code": str(z).strip() if (z := _first(row, _ZONE_FIELDS)) else None,
        "land_use_code": land_use,
        "acres": _safe_float(_first(row, _ACRES_FIELDS)),
        "county_link": str(lk).strip() if (lk := _first(row, _LINK_FIELDS)) else None,
        "in_flood_zone": _is_in_flood_zone(_first(row, _FLOOD_FIELDS)),
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": None,
        "geom": WKTElement(geom.wkt, srid=4326),
        "centroid": WKTElement(geom.centroid.wkt, srid=4326),
        "raw": raw,
    }


# ─── Public API ─────────────────────────────────────────────────────────────

async def ingest_parcels(
    gdf: gpd.GeoDataFrame,
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    replace: bool = True,
) -> int:
    """
    Convert a GeoDataFrame of ArcGIS parcels to Parcel rows and bulk-insert
    into PostGIS, replacing any existing parcels for the jurisdiction.

    Returns number of parcels inserted.
    """
    if gdf.empty:
        logger.warning("Empty GeoDataFrame — nothing to ingest")
        return 0

    logger.info("Mapping %d GDF rows → Parcel dicts …", len(gdf))
    rows: list[dict] = []
    for row in gdf.itertuples(index=False):
        mapped = _map_row(row, jurisdiction_id)
        if mapped is not None:
            rows.append(mapped)

    skipped = len(gdf) - len(rows)
    if skipped:
        logger.warning("Skipped %d rows (null geometry or missing APN)", skipped)

    if not rows:
        logger.error("No usable rows after mapping — aborting ingestion")
        return 0

    if replace:
        logger.info("Deleting existing parcels for jurisdiction %s …", jurisdiction_id)
        await db.execute(
            delete(Parcel).where(Parcel.jurisdiction_id == jurisdiction_id)
        )

    BATCH = 2000
    total_inserted = 0
    num_batches = math.ceil(len(rows) / BATCH)
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        await db.execute(insert(Parcel), batch)
        total_inserted += len(batch)
        logger.info("Inserted batch %d/%d (%d parcels)", i // BATCH + 1, num_batches, total_inserted)

    logger.info(
        "Ingested %d parcels for jurisdiction %s", total_inserted, jurisdiction_id
    )
    return total_inserted
