"""
Zoning-district GeoDataFrame → PostGIS ZoningDistrict ingestion.

Mirrors the pattern in services/ingestion.py:
  - Field-candidate lists (first match wins) handle the NYC / Philadelphia /
    county differences in attribute naming.
  - Calls classification.classify_zone_code when the source layer doesn't carry
    an explicit class attribute.

One zoning layer can contain many small polygons per zone code (e.g., NYC has
~40k polygons across ~100 distinct codes). We preserve the polygons verbatim
but compute a stable geom_hash for de-dup.
"""
from __future__ import annotations

import hashlib
import logging
import math
import uuid
from typing import Any

import geopandas as gpd
from geoalchemy2 import WKTElement
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.zoning_district import ZoneSource, ZoningDistrict
from app.services.classification import classify_zone_code

logger = logging.getLogger(__name__)

# ── Candidate field-name lists (first match wins) ───────────────────────────

_ZONE_CODE_FIELDS = [
    # Bucks County, PA — Municipal_Zoning FeatureServer/0 short code = `ZoningAbbr`
    # (e.g. "LI", "PI", "M-1"); the long name lives in `Zoning`. MUST precede the
    # generic "ZONING" below — _first() case-normalizes both to "zoning", so without
    # this first-match Bucks would pick the long name ("Light Industrial") as the code.
    "ZoningAbbr",
    "ZONEDIST", "ZONE_DIST", "ZONING", "ZONINGCODE", "ZONE", "CODE",
    # "TYPE" is a weak/generic fallback and MUST stay AFTER the specific code
    # fields (specific-field-first convention — catch #34 family, cf. the Bucks
    # ZoningAbbr-before-Zoning fix above). Montgomery County PA's
    # Municipal_Zoning/FeatureServer/11 carries a constant Type="District" field
    # alongside the real district code in `Code`; with "TYPE" ahead of "CODE"
    # _first() would bind every Montgomery parcel to zone_code "District".
    "TYPE",
    "ZONE_CODE", "ZONING_CODE", "zoning", "zonecode",
    "LONG_CODE", "ZONE_CODE_LABEL", "BASEZONE",
    "ZONINGCODE", "ZONECLASS", "ZONE_OR_LABEL",
    "ZONE_LE_LABEL",  # Utah County / Lehi zoning service
    # Fairfax County, VA Zoning service (FeatureServer/0)
    "ZONECODE",
    # Loudoun County, VA Zoning service (MapServer/3) — short district code
    # (e.g. "CCNC"); full text label lives in ZD_ZONE_NAME below.
    "ZO_ZONE",
    # Montgomery County, PA — 180420_zoning_districts FeatureServer/1
    # publishes the short code as `Districts` (e.g. "R-A", "C-1").
    "Districts",
    # Chester County, PA — Zoning_Edit_Working FeatureServer/0 publishes the
    # short district code as `ZONE_ABBR` (e.g. "PIP", "LI", "O", "R1"); the
    # long name lives in `ZONE_DISTRICT` (added to _ZONE_NAME_FIELDS below).
    "ZONE_ABBR",
    # NJ municipal layers (Paramus Zoning, etc.) — short code lives in
    # `CLASS` ("R-100", "CR", "C-1") or its duplicate `Label`. Trailing
    # entries so jurisdictions with proper ZONEDIST keep priority.
    "Label",
    # New Milford NJ "New_Milford_zoning_shapefiles" — uses `ZoningDist`
    # (camelCase). _first() normalizes to lowercase, so "zonedist" above
    # does NOT match "zoningdist". Add as distinct candidate.
    "ZoningDist",
    "ZoningDistrict",
    # NJTPA regional zoning aggregate (gis.njtpa.org LandUse/NJTPA_Zoning) —
    # each per-county layer has its OWN schema for the short district code:
    "ZON_ID",       # Monmouth (layer 3)  e.g. "R-80", "C-1", "LBC"
    "MUNZonCode",   # Bergen (layer 0)    e.g. "A", "ML-5", "D-1"
    "MUN_SYMBOL",   # Hunterdon (layer 1) e.g. "B-2", "R-3" (MUN_ZONE is the long name)
    "Zone_",        # Morris (layer 4)    e.g. "TH", "R-MF3" (ZoneID is "1430_TH" prefixed)
]
_ZONE_NAME_FIELDS = [
    "ZONE_NAME", "LONG_NAME", "DISTRICT_NAME", "LABEL",
    "DESCRIPTION", "DESC", "NAME", "CODE_DEF",
    "ZONE_LE_DESC",   # Utah County / Lehi zoning service
    "ZD_ZONE_NAME",   # Loudoun County zoning long name
    # Mont PA layer publishes the human label as `Name`
    # (e.g. "RURAL RESIDENCE"). NAME is already in the list above as
    # uppercase; this lowercase variant is for callers whose dict keys
    # weren't case-normalised at the source.
    "Name",
    # Paramus Zoning publishes the long human label as `Text`
    # (e.g. "Residential One Family", "Conservation / Recreation").
    "Text",
    # NJTPA regional zoning aggregate — per-county district description fields.
    "ZoneDesc",    # Monmouth
    "MUNZonDef",   # Bergen   e.g. "Single Family Residential"
    "MUN_ZONE",    # Hunterdon e.g. "Highway Business" (long name; MUN_SYMBOL is code)
    "ZoneLabel",   # Morris    e.g. "TH - Townhouse Residence Zone"
    "ZONE_DISTRICT",  # Chester County PA — long district name (ZONE_ABBR is the code)
    "Zoning",         # Bucks County PA — long district name (ZoningAbbr is the code)
]
_ZONE_CLASS_FIELDS = [
    "ZONE_CLASS", "CATEGORY", "ZONE_TYPE", "CLASS", "ZONE_CATEGORY",
]
_FAR_FIELDS = ["MAX_FAR", "FAR", "MaxFAR", "FARCOMM", "FARRES"]
_HEIGHT_FIELDS = ["MAX_HEIGHT", "HEIGHT_MAX", "BLDG_HT", "MAX_BLDG_HT", "HEIGHT"]
_DENSITY_FIELDS = ["MAX_DU_ACRE", "DENSITY", "DU_ACRE", "MAX_DENSITY"]
_MIN_LOT_FIELDS = ["MIN_LOT_AREA", "MIN_LOT_SQFT", "MIN_LOT_SF", "MIN_LOT"]


def _first(row: Any, fields: list[str]) -> Any:
    """Case-insensitive first-match lookup. Tries each candidate field in its
    original case, lowercase, and uppercase — source layers publish in any of
    the three (MapPLUTO uses mixed case, Philly OPA uses lowercase, UGRC uses
    uppercase)."""
    # Build a case-insensitive row accessor once.
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


def _normalize_geom(geom: Any) -> Polygon | MultiPolygon | None:
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


def _geom_hash(geom: Polygon | MultiPolygon) -> str:
    wkb = geom.wkb
    return hashlib.sha1(wkb).hexdigest()[:32]


def _map_row(row: Any, jurisdiction_id: uuid.UUID) -> dict | None:
    geom = _normalize_geom(row.geometry)
    if geom is None:
        return None

    code = _first(row, _ZONE_CODE_FIELDS)
    if not code:
        return None
    code = str(code).strip()

    zone_name = _first(row, _ZONE_NAME_FIELDS)
    source_class = _first(row, _ZONE_CLASS_FIELDS)
    zone_class = classify_zone_code(
        code,
        zone_name=str(zone_name) if zone_name else None,
        source_class=str(source_class) if source_class else None,
    )

    # Raw attribute snapshot
    if hasattr(row, "_asdict"):
        props = {k: v for k, v in row._asdict().items() if k != "geometry"}
    elif hasattr(row, "to_dict"):
        props = {k: v for k, v in row.to_dict().items() if k != "geometry"}
    else:
        props = {}
    raw = {k: (str(v) if v is not None else None) for k, v in props.items()}

    return {
        "jurisdiction_id": jurisdiction_id,
        "zone_code": code,
        "zone_name": str(zone_name).strip() if zone_name else None,
        "zone_class": zone_class,
        "allowed_uses": None,
        "max_far": _safe_float(_first(row, _FAR_FIELDS)),
        "max_height_ft": _safe_float(_first(row, _HEIGHT_FIELDS)),
        "max_density_dua": _safe_float(_first(row, _DENSITY_FIELDS)),
        "min_lot_area_sqft": _safe_float(_first(row, _MIN_LOT_FIELDS)),
        "raw_attributes": raw,
        "geom": WKTElement(geom.wkt, srid=4326),
        "centroid": WKTElement(geom.centroid.wkt, srid=4326),
        "source": ZoneSource.arcgis,
        "confidence": None,
        "human_reviewed": False,
        "geom_hash": _geom_hash(geom),
    }


async def ingest_zoning_districts(
    gdf: gpd.GeoDataFrame,
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    replace: bool = True,
) -> int:
    """Bulk-insert zoning districts for a jurisdiction. Returns inserted count."""
    if gdf.empty:
        logger.warning("Empty zoning GeoDataFrame — nothing to ingest")
        return 0

    logger.info("Mapping %d zoning GDF rows → ZoningDistrict dicts …", len(gdf))
    rows: list[dict] = []
    # iterrows preserves the original ArcGIS field names. itertuples sanitizes
    # dotted names like "GIS.landbase1_Zoning.ZONINGCODE" and breaks mapping.
    for _, row in gdf.iterrows():
        mapped = _map_row(row, jurisdiction_id)
        if mapped is not None:
            rows.append(mapped)

    skipped = len(gdf) - len(rows)
    if skipped:
        logger.warning("Skipped %d zoning rows (null geometry or missing code)", skipped)

    if not rows:
        logger.error("No usable zoning rows after mapping — aborting")
        return 0

    if replace:
        logger.info("Deleting existing zoning_districts for jurisdiction %s …", jurisdiction_id)
        await db.execute(
            delete(ZoningDistrict).where(
                ZoningDistrict.jurisdiction_id == jurisdiction_id
            )
        )
        # Flush the DELETE so PostgreSQL sees those rows gone before the
        # subsequent INSERT batches check the uq_zoning_districts_jur_code_hash
        # constraint. Without this flush, the batched executemany INSERT
        # statements in the same transaction can still see the pre-delete
        # state for constraint checking (observed on Fairfax 2026-05-11).
        await db.flush()

    # Use INSERT ... ON CONFLICT DO NOTHING so duplicates within the same
    # incoming GeoDataFrame don't crash the batch. Upstream zoning services
    # occasionally publish multiple polygons with identical (zone_code, geom)
    # under different OBJECTIDs (Fairfax's "I-3" zone shows up at least 4
    # times). Silently dropping the duplicates is the correct behaviour:
    # the (jurisdiction_id, zone_code, geom_hash) constraint is meant to
    # enforce uniqueness of the *spatial* district, not the source row id.
    BATCH = 1000
    total = 0
    num_batches = math.ceil(len(rows) / BATCH)
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        stmt = pg_insert(ZoningDistrict).on_conflict_do_nothing(
            constraint="uq_zoning_districts_jur_code_hash",
        )
        await db.execute(stmt, batch)
        total += len(batch)
        logger.info("Inserted zoning batch %d/%d (%d districts)", i // BATCH + 1, num_batches, total)

    logger.info("Ingested %d zoning districts for jurisdiction %s", total, jurisdiction_id)
    return total
