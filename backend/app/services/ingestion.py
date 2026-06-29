"""
ArcGIS GeoDataFrame → PostGIS Parcel ingestion service.

Maps ArcGIS feature fields to the Parcel ORM schema.
Handles geometry validation and bulk insertion.

Field mapping is jurisdiction-aware: Draper uses specific field names (PARCEL,
PROP_LOC, ZONING, etc.).  Future jurisdictions add their own field maps below.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import asyncpg
import geopandas as gpd
from pyproj import Geod
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.wkb import dumps as wkb_dumps
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.classification import classify_zone_code
from app.services.overlays import SFHA_ZONES
from app.services.vacancy import is_vacant_by_landuse

logger = logging.getLogger(__name__)

# ─── Candidate field-name lists (first match wins) ─────────────────────────

_APN_FIELDS = [
    # MD MDProperty View ACCTID is a county-prefixed SDAT account number that
    # is unique statewide. The MD parcel layer ALSO publishes a `PARCEL` field
    # carrying a 4-digit subdivision-lot label (sparse, ~1.2% distinct), which
    # the generic `PARCEL` candidate below would otherwise win. Keep ACCTID
    # first so MD layers map every row to its true unique key.
    "ACCTID",
    "PARCEL", "APN", "PARCELNO", "PARCEL_NO",
    # PIN before PARCEL_ID: Philadelphia PWD_PARCELS uses `pin` as the OPA account number
    # while `parcel_id` on that service is just a row-ID (1, 2, 3…).
    "PIN", "PARCEL_ID",
    "SERIAL", "Serial", "serial",
    # NJ MOD-IV (statewide Parcels_Composite_NJ_WM + county services)
    "PAMS_PIN", "GIS_PIN", "PIN_NODUP", "pams_pin",
    # NYC MapPLUTO
    "BBL", "bbl",
    # NYS ITS county tax-parcel layers (Westchester full schema + Nassau 10-char
    # truncated schema). PRINT_KEY is the municipal assessor-roll parcel ID and
    # collides across municipalities within a county (e.g. PRINT_KEY '6.10-1-1'
    # exists in both Ardsley and Somers in Westchester); only the SWIS-prefixed
    # composite (SWIS_PRINT_KEY_ID full / SWIS_PRINT truncated) is unique
    # county-wide. Order the composites first so they win the _first() match.
    "SWIS_PRINT_KEY_ID", "SWIS_PRINT",
    "MUNI_PARCEL_ID", "MUNI_PARCE",
    "PRINT_KEY",
    "SBL",
    # CT 2024 CAMA + Parcel statewide. `link_1` (CAMA join key) is populated
    # for ~93% of Fairfield rows; `Parcel_ID` is sparse (~66%); both predate
    # the more general `PARCEL_ID` candidate above which would otherwise miss
    # `link_1`. Keep them ordered link → parcel for best coverage.
    "link_1",
    # Philadelphia OPA / PWD_PARCELS BRT identifier
    "parcel_number", "PARCEL_NUMBER", "opa_account_num", "PARCELID", "brt_id", "BRT_ID",
    # Allentown PA City_Landuse service
    "WARDACCTNO",
    # Loudoun County, VA — LandRecords MapServer/5 publishes the master
    # cadastral PIN as PA_MCPI (12-char numeric). No other unique key on layer.
    "PA_MCPI",
    # Montgomery County, PA — TAXPIN is the 12-digit county-unique tax PIN.
    "TAXPIN",
    # Chester County, PA — UPI (Uniform Parcel Identifier, e.g. "43-9-1.7") is the
    # county-unique parcel key. The layer's PIN_MAP/PIN_COMMON/PIN_ASMNT are NOT
    # bare "PIN" so they don't match the generic candidate above — without UPI here
    # every Chester row maps to no APN and is dropped (0 parcels). (catch #34)
    "UPI",
    # Bucks County, PA — PARCEL_NUM (e.g. "54-010-001-914"; first 2 digits = muni
    # code). Distinct from the generic "PARCEL" candidate. (catch #34 inheritance)
    "PARCEL_NUM",
]
_ADDRESS_FIELDS = [
    "PROP_LOC", "ST_ADDRESS", "SITUS", "SITUS_ADDRESS", "ADDRESS", "FULL_ADDRESS",
    # NYS ITS county schema (PARCEL_ADDR full / PARCEL_ADD truncated on Nassau)
    "PARCEL_ADDR", "PARCEL_ADD",
    "PROPERTY_ADDRESS_1", "property_address_1",
    # NYC MapPLUTO
    "Address", "ADDRESS1",
    # Fairfax County, VA — Parcels_with_Address_points uses ADDRESS_1
    "ADDRESS_1",
    # Philadelphia OPA / NJ Passaic county / CT 2024 CAMA (Location_1)
    "location", "LOCATION", "Location_1", "street_address",
    # Allentown PA City_Landuse service
    "PROPERTYADDR",
]
_ZONE_FIELDS = [
    "ZONING", "ZONE", "ZONE_CODE", "ZONING_CODE", "ZONE_DIST",
    # NYC MapPLUTO
    "ZONEDIST", "ZoneDist1",
    # Philadelphia OPA
    "zoning",
    # Allentown PA CityZoning service
    "ZONINGCODE",
    # Fairfax County, VA Zoning service (FeatureServer/0)
    "ZONECODE",
    # Loudoun County, VA Zoning service (MapServer/3)
    "ZO_ZONE",
]
_LANDUSE_FIELDS = [
    "LANDUSE", "LAND_USE", "LAND_USE_CODE", "USE_CODE", "CLASS",
    # NJ MOD-IV building/property description fields
    "BLDG_CLASS", "BLDG_DESC",
    # NYC MapPLUTO
    "LandUse", "LAND_USE_DESC",
    # Philadelphia OPA
    "category_code_description", "building_code_description",
    # NYS ITS Property Class Code (3-digit ORPTS code, e.g. 210=1-family,
    # 311=vacant residential land, 962=county park). USED_AS_DESC carries
    # the human-readable label when populated.
    "PROP_CLASS", "USED_AS_DESC",
    # CT 2024 CAMA: State_Use carries the 3-letter code (e.g. RA3, COM, IND);
    # State_Use_Description has the human label.
    "State_Use", "State_Use_Description",
    # Maryland MDProperty View — LU is single-letter code (R/C/I/A/E/F),
    # DESCLU is human label ("Residential", "Commercial Office", …).
    "LU", "DESCLU",
]
_PROPTYPE_FIELDS = ["PROP_TYPE", "PROPERTY_TYPE", "PROPTYPE"]
_ACRES_FIELDS = [
    "CALC_ACRE", "PARCEL_ACR", "ACRES", "GIS_ACRES", "ACREAGE",
    # NYS ITS schema CALC_ACRES (full) — calculated from geometry by NYS GPO.
    "CALC_ACRES",
    # CT 2024 CAMA
    "Land_Acres",
    # NJ Passaic county service uses lot_size
    "lot_size",
    # Loudoun County, VA — PA_LEGAL_ACRE is the assessor-published lot acreage.
    "PA_LEGAL_ACRE",
    # Montgomery County, PA — both fields published; CALCACREAGE is canonical.
    "CALCACREAGE", "TrueCalculatedAcres",
    # NYC/Philly don't publish acres directly — see _AREA_SQM_FIELDS fallback.
]
_IMPROVEMENT_FIELDS = [
    # NJ MOD-IV statewide
    "IMPRVT_VAL",
    # NJ Passaic county service
    "impr_value",
    # CT 2024 CAMA — appraised building value (separate from land + outbuilding)
    "Appraised_Building", "Assessed_Building",
    # Maryland MDProperty View — NFMIMPVL is the structure portion of the
    # Next Full Market Value assessment (separate from NFMLNDVL land value).
    "NFMIMPVL",
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
    # NYS ITS county schema (Westchester PRIMARY_OWNER full / Nassau PRIMARY_OW truncated)
    "PRIMARY_OWNER", "PRIMARY_OW",
    # CT 2024 CAMA
    "Co_Owner",
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
_CITY_FIELDS = [
    # UGRC (UT) county parcel layers carry the municipality per parcel — this is
    # what makes a county-as-jurisdiction ingest hold real per-city values.
    "PARCEL_CITY",
    # Common municipality/city field names across county/state services.
    "CITY", "City", "city",
    "MUNICIPALITY", "Municipality", "municipality", "MUNI", "MUNI_NAME",
    "TOWN", "Town", "TOWN_NAME", "TOWNSHIP", "PLACE_NAME",
    # NYS ITS county schema
    "MUNI_NAME_FULL",
    # Contra Costa CCMAP — situs (site address) city. ALL-CAPS in source
    # (e.g. "WALNUT CREEK"); ingest script normalises to title case before
    # building the GeoDataFrame so prod_city_value matches the CA Statewide
    # Zoning North layer's `Jurisdiction` field convention.
    "s_city",
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
        for key, candidate in lookup.items():
            if key.rsplit(".", 1)[-1] == f.lower():
                if candidate is not None and str(candidate).strip() not in ("", "nan", "None"):
                    return candidate
    return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _resolve_muni_name(
    row: Any, muni_field: str | None, muni_name_map: dict[int, str] | None
) -> str | None:
    """Map a numeric muni code (e.g. PA county assessor MUNI=43) to its muni name
    via a baked code→name map sourced from the county boundary layer (catch #33
    scale-up). Returns None when not configured or the code doesn't resolve."""
    if not muni_field or not muni_name_map:
        return None
    code = _first(row, [muni_field])
    if code is None or str(code).strip() == "":
        return None
    try:
        return muni_name_map.get(int(float(str(code).strip())))
    except (ValueError, TypeError):
        return muni_name_map.get(str(code).strip())  # type: ignore[arg-type]


def _row_geometry(row: Any) -> Any:
    if isinstance(row, dict):
        return row.get("geometry")
    return getattr(row, "geometry", None)


# Square-foot fields used by NYC MapPLUTO (LotArea) and Philadelphia OPA (total_area).
_AREA_SQFT_FIELDS = [
    "LotArea", "LOT_AREA", "total_area", "TotalArea", "LOTAREA",
    "Shape_Area", "SHAPE_AREA", "shape_area",
]
_SQM_PER_ACRE = 4046.856
_SQFT_PER_ACRE = 43_560.0

# WGS84 ellipsoid for geodetic area calculation. geometry_area_perimeter() takes
# a Shapely geometry in lon/lat degrees and returns area in square meters.
_geod = Geod(ellps="WGS84")


def _geom_acres(geom: Any) -> float | None:
    """Compute acreage from a WGS84 Shapely geometry using geodetic area on the ellipsoid."""
    try:
        area_sqm, _ = _geod.geometry_area_perimeter(geom)
        area_sqm = abs(area_sqm)
        if area_sqm > 0:
            return round(area_sqm / _SQM_PER_ACRE, 4)
    except Exception:
        pass
    return None


def _resolve_acres(row: Any, geom: Any) -> float | None:
    """Return parcel acreage.

    Priority:
      1. Explicit acres field from source (assessor value, already in acres).
      2. Explicit square-foot field (NYC LotArea, Philly total_area).
      3. Geodetic area from the WGS84 geometry — always correct regardless of
         source CRS, replacing the old Shape__Area fallback whose units were
         ambiguous (sq ft vs sq m depending on the native layer CRS).

    Output is clamped to the parcels.acres column's numeric(10,3) capacity
    (~9,999,999.999). Source data occasionally has bad rows — Mont PA's
    Parcels FeatureServer/10 includes one or two CALCACREAGE values past 10^7
    (acreage rolled over from a prior schema), which would otherwise overflow
    the merge with `numeric field overflow … precision 10, scale 3`.
    """
    v = _safe_float(_first(row, _ACRES_FIELDS))
    if v is not None and v > 0:
        return _clamp_acres(round(v, 4))
    sqft = _safe_float(_first(row, _AREA_SQFT_FIELDS))
    if sqft is not None and sqft > 0:
        return _clamp_acres(round(sqft / _SQFT_PER_ACRE, 4))
    if geom is not None:
        v = _geom_acres(geom)
        return _clamp_acres(v) if v is not None else None
    return None


# parcels.acres is numeric(10,3); max safe magnitude is just under 10^7. The
# largest real US parcel (King Ranch, TX) is ~825K acres, so clamping at this
# level only ever bites bad source rows.
_ACRES_MAX = 9_999_999.0


def _clamp_acres(v: float) -> float:
    if v is None:
        return v
    if v > _ACRES_MAX:
        return _ACRES_MAX
    if v < 0:
        return 0.0
    return v


def _is_in_flood_zone(raw_value: Any) -> bool | None:
    """Return True if the source row carries an SFHA flood code, False if it
    carries a non-SFHA code, or **None** if the source publishes no flood field
    at all. The None case is what gates apply_flood_overlay (its WHERE clause
    is `in_flood_zone IS NULL`); writing False unconditionally here was the
    Phase 1/2 bug that suppressed the FEMA NFHL spatial overlay for every
    NJ/NY/CT/VA/MD/PA jurisdiction whose source omits flood data."""
    if raw_value is None:
        return None
    code = str(raw_value).strip().upper()
    base = code.split("-")[0].split(" ")[0]
    return base in SFHA_ZONES


def _normalize_geom(geom: Any) -> Polygon | MultiPolygon | None:
    """Return a valid Polygon/MultiPolygon or None."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return None
    return geom


def _map_row(
    row: Any,
    jurisdiction_id: uuid.UUID,
    state: str | None = None,
    city_override: str | None = None,
    muni_field: str | None = None,
    muni_name_map: dict[int, str] | None = None,
) -> dict | None:
    """
    Convert a single GeoDataFrame row to a dict ready for Parcel bulk insert.
    Returns None if the row has no usable geometry or APN.

    ``state`` (two-letter postal code) is used by parcel_value_mapper to
    extract assessed_value + is_residential from the per-state source schema.
    Passed in by the caller so it's looked up once per ingest, not per row.
    """
    geom = _normalize_geom(_row_geometry(row))
    if geom is None:
        return None

    apn = _first(row, _APN_FIELDS)
    if not apn:
        return None
    apn = str(apn).strip()
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

    # Build raw property snapshot (strip geometry, coerce to str).
    # The bulk-ingest caller now passes a plain ``dict`` (from
    # ``dict(zip(columns, gdf.itertuples()))``), so the namedtuple
    # `_asdict` / pandas `to_dict` branches no longer fire and raw was
    # being persisted as ``{}``. Handle dict directly first.
    if isinstance(row, dict):
        props = {k: v for k, v in row.items() if k != "geometry"}
    elif hasattr(row, "_asdict"):
        props = {k: v for k, v in row._asdict().items() if k != "geometry"}
    elif hasattr(row, "to_dict"):
        props = {k: v for k, v in row.to_dict().items() if k != "geometry"}
    else:
        props = {}
    raw = {k: str(v) if v is not None else None for k, v in props.items()}

    zoning_code_val = str(z).strip() if (z := _first(row, _ZONE_FIELDS)) else None
    zone_class_val = classify_zone_code(zoning_code_val).value if zoning_code_val else None

    centroid = geom.centroid

    # Per-state assessed-value + residential mapping. Centralized in
    # parcel_value_mapper so we never scatter PROP_CLASS / DOR_UC / JV
    # checks through the ingest path.
    from app.services.parcel_value_mapper import map_value_and_residential
    assessed_value, is_residential = map_value_and_residential(state, raw)

    return {
        "jurisdiction_id": jurisdiction_id,
        "apn": apn,
        "address": str(a).strip() if (a := _first(row, _ADDRESS_FIELDS)) else None,
        # City resolution precedence (catch #35 / #33 chain):
        #   1. city_override — fixed muni, the "scope to one muni" shortcut.
        #   2. muni_name_map[MUNI] — the "scale to all munis" crosswalk: PA county
        #      assessor layers expose only an integer MUNI code; resolve it to the
        #      muni name via the baked boundary-layer map (else `_CITY_FIELDS`'s
        #      "MUNI" candidate would capture a bogus city="43").
        #   3. native _CITY_FIELDS — layers that carry a real city/muni NAME.
        "city": city_override or _resolve_muni_name(row, muni_field, muni_name_map)
        or (str(ct).strip() if (ct := _first(row, _CITY_FIELDS)) else None),
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
        "assessed_value": assessed_value,
        "is_residential": is_residential,
        "geom": geom,
        "centroid": centroid,
        "raw": raw,
    }


# ─── Public API ─────────────────────────────────────────────────────────────

async def ingest_parcels(
    gdf: gpd.GeoDataFrame,
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    progress_callback: Any = None,
    city_override: str | None = None,
    muni_field: str | None = None,
    muni_name_map: dict[int, str] | None = None,
) -> int:
    """
    Convert a GeoDataFrame of ArcGIS parcels to Parcel rows and bulk-insert
    into PostGIS, replacing any existing parcels for the jurisdiction.

    Returns number of parcels inserted.
    """
    if gdf.empty:
        logger.warning("Empty GeoDataFrame — nothing to ingest")
        return 0

    # Look up the jurisdiction's state once so parcel_value_mapper can
    # extract assessed_value + is_residential from the per-state source
    # schema without a per-row DB hit.
    from app.models.jurisdiction import Jurisdiction
    from sqlalchemy import select as _sa_select
    state: str | None = await db.scalar(
        _sa_select(Jurisdiction.state).where(Jurisdiction.id == jurisdiction_id)
    )

    logger.info("Mapping %d GDF rows → Parcel dicts …", len(gdf))
    rows_by_apn: dict[str, dict] = {}
    duplicate_apns = 0
    columns = list(gdf.columns)
    for idx, values in enumerate(gdf.itertuples(index=False, name=None), start=1):
        row = dict(zip(columns, values))
        mapped = _map_row(row, jurisdiction_id, state=state, city_override=city_override,
                          muni_field=muni_field, muni_name_map=muni_name_map)
        if mapped is not None:
            apn = mapped["apn"]
            if apn in rows_by_apn:
                duplicate_apns += 1
            rows_by_apn[apn] = mapped
        # Catch #12: this mapping loop is a long synchronous CPU block (shapely
        # make_valid per row) — on a 300-420k-parcel county it can run for minutes
        # without yielding. The locked_at heartbeat coroutine shares this event
        # loop, so without an explicit yield it gets starved, locked_at freezes,
        # and the watchdog re-claims the live job. sleep(0) always yields control.
        if idx % 500 == 0:
            await asyncio.sleep(0)
        if progress_callback is not None and idx % 1000 == 0:
            await progress_callback("mapping", idx, len(gdf))

    if progress_callback is not None:
        await progress_callback("mapping", len(gdf), len(gdf))

    rows = list(rows_by_apn.values())
    skipped = len(gdf) - len(rows) - duplicate_apns
    if skipped:
        logger.warning("Skipped %d rows (null geometry or missing APN)", skipped)
    if duplicate_apns:
        logger.warning(
            "Collapsed %d duplicate APN rows before parcel upsert for jurisdiction %s",
            duplicate_apns,
            jurisdiction_id,
        )

    if not rows:
        logger.error("No usable rows after mapping — aborting ingestion")
        return 0

    total_inserted = await _copy_upsert_parcels(rows, progress_callback)

    logger.info(
        "Ingested %d parcels for jurisdiction %s", total_inserted, jurisdiction_id
    )
    return total_inserted


# ─── COPY-based bulk upsert ────────────────────────────────────────────────

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
    jurisdiction_id uuid,
    apn text,
    address text,
    city text,
    owner_name text,
    zoning_code text,
    zone_class text,
    land_use_code text,
    acres double precision,
    county_link text,
    in_flood_zone boolean,
    in_wetland boolean,
    avg_slope_pct double precision,
    has_structure boolean,
    improvement_value double precision,
    assessed_value double precision,
    is_residential boolean,
    geom_wkb bytea,
    centroid_wkb bytea,
    raw_json text
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
    zoning_code = COALESCE(EXCLUDED.zoning_code, parcels.zoning_code),
    zone_class = COALESCE(EXCLUDED.zone_class, parcels.zone_class),
    land_use_code = EXCLUDED.land_use_code,
    acres = EXCLUDED.acres,
    county_link = EXCLUDED.county_link,
    in_flood_zone = EXCLUDED.in_flood_zone,
    in_wetland = EXCLUDED.in_wetland,
    avg_slope_pct = EXCLUDED.avg_slope_pct,
    has_structure = EXCLUDED.has_structure,
    improvement_value = EXCLUDED.improvement_value,
    assessed_value = COALESCE(EXCLUDED.assessed_value, parcels.assessed_value),
    is_residential = COALESCE(EXCLUDED.is_residential, parcels.is_residential),
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid,
    raw = EXCLUDED.raw,
    updated_at = NOW()
"""


def _row_to_record(r: dict) -> tuple:
    raw = r.get("raw")
    return (
        r["jurisdiction_id"],
        r["apn"],
        r.get("address"),
        r.get("city"),
        r.get("owner_name"),
        r.get("zoning_code"),
        r.get("zone_class"),
        r.get("land_use_code"),
        r.get("acres"),
        r.get("county_link"),
        # Preserve tri-state: True / False / None. None means the source has no
        # flood field, signalling apply_flood_overlay to compute it spatially.
        r.get("in_flood_zone"),
        bool(r.get("in_wetland")),
        r.get("avg_slope_pct"),
        r.get("has_structure"),
        r.get("improvement_value"),
        r.get("assessed_value"),
        r.get("is_residential"),
        wkb_dumps(r["geom"], hex=False, srid=4326),
        wkb_dumps(r["centroid"], hex=False, srid=4326),
        json.dumps(raw) if raw is not None else None,
    )


def _raw_dsn() -> str:
    """Return a plain asyncpg DSN.

    For long-lived ingest connections (COPY + MERGE wrapped in a single
    transaction), route to Supabase's *session*-pool port (5432) instead of
    the default *transaction*-pool port (6543). pgbouncer's transaction-mode
    pool releases the underlying server backend at every statement boundary,
    which both kills session-local TEMP tables across implicit-tx boundaries
    and silently drops the underlying conn during the multi-minute COPY +
    MERGE phase for 290K-row Mont MD / 310K-row Mont PA. Session-mode pins
    one server backend to one client connection for its full lifetime.
    """
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return dsn.replace(":6543/", ":5432/")


async def _copy_upsert_parcels(rows: list[dict], progress_callback: Any) -> int:
    """COPY rows into a temp table, then INSERT...SELECT...ON CONFLICT into parcels.

    Uses a raw asyncpg connection (no SQLAlchemy session) to bypass the
    32,767 bind-parameter cap that limits batched INSERT to ~1,800 rows.
    COPY streams data with no parameter cap, so the entire jurisdiction
    can be staged in a handful of chunks.
    """
    # statement_cache_size=0: Supabase routes through pgbouncer; stale
    # prepared statements across asyncpg client connections cause
    # DuplicatePreparedStatementError on the second call.
    conn = await asyncpg.connect(_raw_dsn(), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        # Wrap CREATE TEMP + COPY + MERGE in a single transaction. Without
        # this, every implicit-tx boundary lets pgbouncer return the
        # underlying server backend to another client; the next statement
        # arrives on a fresh backend that has never seen `_stage_parcels`
        # and fails with "relation _stage_parcels does not exist". Holding
        # one tx keeps the same backend pinned. CREATE TEMP TABLE IF NOT
        # EXISTS + TRUNCATE handles the case where pooling kept the temp
        # table from a previous client.
        async with conn.transaction():
            await conn.execute(_CREATE_STAGE_SQL)
            await conn.execute(_TRUNCATE_STAGE_SQL)

            CHUNK = 25_000
            total = len(rows)
            for i in range(0, total, CHUNK):
                chunk = rows[i : i + CHUNK]
                records = [_row_to_record(r) for r in chunk]
                try:
                    await conn.copy_records_to_table(
                        "_stage_parcels", records=records, columns=_STAGE_COLUMNS
                    )
                except Exception as exc:
                    logger.exception(
                        "COPY chunk %d (%d rows) failed: %s",
                        i // CHUNK + 1, len(chunk), exc,
                    )
                    raise
                staged = min(i + CHUNK, total)
                logger.info("COPY staged %d/%d parcels", staged, total)
                if progress_callback is not None:
                    await progress_callback("upserting", staged, total)

            staged_count = await conn.fetchval("SELECT COUNT(*) FROM _stage_parcels")
            logger.info(
                "Stage table populated: %d rows (input=%d). Running merge …",
                staged_count, total,
            )
            try:
                result = await conn.execute(_MERGE_SQL)
            except Exception as exc:
                logger.exception("MERGE INTO parcels failed: %s", exc)
                raise

        logger.info("Merge result: %r", result)
        try:
            inserted = int(result.split()[-1])
        except (ValueError, IndexError):
            inserted = total
        return inserted
    finally:
        await conn.close()
