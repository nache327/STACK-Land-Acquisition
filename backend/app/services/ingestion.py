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
from app.services.classification import classify_zone_code
from app.services.overlays import SFHA_ZONES
from app.services.vacancy import is_vacant_by_landuse

logger = logging.getLogger(__name__)

# ─── Candidate field-name lists (first match wins) ─────────────────────────

_APN_FIELDS = [
    "PARCEL", "APN", "PARCELNO", "PARCEL_NO", "PARCEL_ID", "PIN",
    # NJ MOD-IV (statewide Parcels_Composite_NJ_WM + county services)
    "PAMS_PIN", "GIS_PIN", "PIN_NODUP", "pams_pin",
    # NYC MapPLUTO
    "BBL", "bbl",
    # Philadelphia OPA
    "parcel_number", "PARCEL_NUMBER", "opa_account_num", "PARCELID",
]
_ADDRESS_FIELDS = [
    "PROP_LOC", "ST_ADDRESS", "SITUS", "SITUS_ADDRESS", "ADDRESS", "FULL_ADDRESS", "PARCEL_ADD",
    # NYC MapPLUTO
    "Address", "ADDRESS1",
    # Philadelphia OPA / NJ Passaic county service
    "location", "LOCATION", "street_address",
]
_ZONE_FIELDS = [
    "ZONING", "ZONE", "ZONE_CODE", "ZONING_CODE", "ZONE_DIST",
    # NYC MapPLUTO
    "ZONEDIST", "ZoneDist1",
    # Philadelphia OPA
    "zoning",
]
_LANDUSE_FIELDS = [
    "LANDUSE", "LAND_USE", "LAND_USE_CODE", "USE_CODE", "CLASS",
    # NJ MOD-IV building/property description fields
    "BLDG_CLASS", "BLDG_DESC",
    # NYC MapPLUTO
    "LandUse", "LAND_USE_DESC",
    # Philadelphia OPA
    "category_code_description", "building_code_description",
]
_PROPTYPE_FIELDS = ["PROP_TYPE", "PROPERTY_TYPE", "PROP_CLASS", "PROPTYPE"]
_ACRES_FIELDS = [
    "CALC_ACRE", "PARCEL_ACR", "ACRES", "GIS_ACRES", "ACREAGE",
    # NJ Passaic county service uses lot_size
    "lot_size",
    # NYC/Philly don't publish acres directly — see _AREA_SQM_FIELDS fallback.
]
_IMPROVEMENT_FIELDS = [
    # NJ MOD-IV statewide
    "IMPRVT_VAL",
    # NJ Passaic county service
    "impr_value",
    # Generic fallbacks
    "IMPRVT_VALUE", "IMP_VALUE", "IMPRV_VALUE", "FMV_IMPRV",
]
_LINK_FIELDS = [
    "LINK", "COUNTY_LINK", "PARCEL_URL", "URL", "WEB_LINK", "CoParcel_URL",
]
_FLOOD_FIELDS = ["FLOODZONE", "FLOOD_ZONE", "FLD_ZONE", "SFHA"]
_OWNER_FIELDS = [
    "OWNER_NAME", "OWNERNAME", "OWNER",
    # NYC MapPLUTO
    "OwnerName",
    # Philadelphia OPA
    "owner_1", "owner_2",
    # County assessor / tax roll variants (common across US counties)
    "TAXPAYER", "TAXPAYER_NM", "TAXPAYERNM", "TAX_PAYER", "TAX_NAME",
    "TAXPAYER_NAME", "TAXPAYER1", "TAXPAYER_1",
    # Full-name fields used by many Midwest/Southeast counties
    "OWN_FULL", "OWN_NAME", "OWN1", "OWN_1", "OWN_NAME1",
    "OWNER_NAME_1", "OWNER_FULL",
    # Grantee/deed-based fields
    "GRANTEE", "GRANTEE_NAME", "DEED_NAME",
    # Generic party / name fields used in some state-level services
    "PARTY_1", "PARTY1", "LANDOWNER", "LAND_OWNER",
    # Regrid normalized field
    "owner",
    # Texas / Southeast county variants
    "PROP_OWNER", "PROPERTY_OWNER", "OWNER_NAM",
    # Lowercase variants (some county services return lowercase field names)
    "owner_name", "ownername", "taxpayer", "taxpayer_nm",
    "grantee", "own_full", "own1",
]

# ─── Helpers ────────────────────────────────────────────────────────────────

def _first(row: Any, fields: list[str]) -> Any:
    """Return the value of the first field that exists and is non-null.

    Case-insensitive: MapPLUTO publishes fields in mixed case (`ZoneDist1`),
    Philly OPA in lowercase (`zoning`), UGRC in uppercase (`ZONING`). We
    normalize both sides to lowercase for lookup.
    """
    if isinstance(row, dict):
        lookup = {k.lower(): v for k, v in row.items()}
    elif hasattr(row, "_asdict"):
        lookup = {k.lower(): v for k, v in row._asdict().items()}
    elif hasattr(row, "to_dict"):
        lookup = {k.lower(): v for k, v in row.to_dict().items()}
    else:
        lookup = {}

    for f in fields:
        v = lookup.get(f.lower())
        if v is not None and str(v).strip() not in ("", "nan", "None"):
            return v
    return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


_AREA_SQM_FIELDS = ["Shape__Area", "SHAPE__AREA", "shape_Area", "SHAPE_Area"]
# Square-foot fields used by NYC MapPLUTO (LotArea) and Philadelphia OPA (total_area).
_AREA_SQFT_FIELDS = ["LotArea", "LOT_AREA", "total_area", "TotalArea", "LOTAREA"]
_SQM_PER_ACRE = 4046.856
_SQFT_PER_ACRE = 43_560.0


def _resolve_acres(row: Any, geom: Any) -> float | None:
    """Return parcel acreage, preferring explicit fields then Shape__Area (sq m)."""
    v = _safe_float(_first(row, _ACRES_FIELDS))
    if v is not None and v > 0:
        return round(v, 4)
    sqft = _safe_float(_first(row, _AREA_SQFT_FIELDS))
    if sqft is not None and sqft > 0:
        return round(sqft / _SQFT_PER_ACRE, 4)
    sqm = _safe_float(_first(row, _AREA_SQM_FIELDS))
    if sqm is not None and sqm > 0:
        return round(sqm / _SQM_PER_ACRE, 4)
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

    prop_type = _first(row, _PROPTYPE_FIELDS)
    prop_type_str = str(prop_type).strip().upper() if prop_type else ""

    vacant = is_vacant_by_landuse(land_use)
    if vacant is None and prop_type_str:
        if "VACANT" in prop_type_str or "VAC LAND" in prop_type_str:
            vacant = True
        elif prop_type_str and "VACANT" not in prop_type_str:
            # Known non-vacant property types
            vacant = False

    has_structure: bool | None = None if vacant is None else (not vacant)

    # Build raw property snapshot (strip geometry, coerce to str)
    if hasattr(row, "_asdict"):
        props = {k: v for k, v in row._asdict().items() if k != "geometry"}
    elif hasattr(row, "to_dict"):
        props = {k: v for k, v in row.to_dict().items() if k != "geometry"}
    else:
        props = {}
    raw = {k: str(v) if v is not None else None for k, v in props.items()}

    zoning_code_val = str(z).strip() if (z := _first(row, _ZONE_FIELDS)) else None
    zone_class_val = classify_zone_code(zoning_code_val).value if zoning_code_val else None

    return {
        "jurisdiction_id": jurisdiction_id,
        "apn": str(apn),
        "address": str(a).strip() if (a := _first(row, _ADDRESS_FIELDS)) else None,
        "owner_name": str(o).strip() if (o := _first(row, _OWNER_FIELDS)) else None,
        "zoning_code": zoning_code_val,
        "zone_class": zone_class_val,
        "land_use_code": land_use,
        "acres": _resolve_acres(row, geom),
        "county_link": str(lk).strip() if (lk := _first(row, _LINK_FIELDS)) else None,
        "in_flood_zone": _is_in_flood_zone(_first(row, _FLOOD_FIELDS)),
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": _safe_float(_first(row, _IMPROVEMENT_FIELDS)),
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
