"""
Job pipeline service.

Orchestrates the full data-collection workflow for a search job:
  1. Resolve the jurisdiction (create row if needed)
  2. Discover / validate FeatureServer endpoints
  3. Download parcels from ArcGIS (or Regrid)
  4. Ingest into PostGIS
  5. Parse ordinance → zone_use_matrix
  6. Apply overlays (flood / slope / wetland)

Phase 5: live ArcGIS layer discovery via Hub search + Web Map parsing.
Known jurisdictions remain as a fast-path cache to avoid network calls.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select as sa_select

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import CoverageLevel, Jurisdiction, ParcelSource
from app.models.parcel import Parcel
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels
from app.services.matrix_bootstrap import bootstrap_zone_use_matrix
from app.services.spatial_backfill import (
    backfill_parcel_zoning_from_districts,
    refresh_jurisdiction_bbox,
    refresh_jurisdiction_coverage_level,
)
from app.services.zoning_ingestion import ingest_zoning_districts

logger = logging.getLogger(__name__)


# ─── Known jurisdiction registry ────────────────────────────────────────────
# Fast-path cache.  Any other city falls through to live ArcGIS discovery.

@dataclass
class JurisdictionConfig:
    name: str
    state: str
    county: str
    parcel_source: ParcelSource
    parcel_endpoint: str          # FeatureServer URL  OR  Regrid path
    zoning_endpoint: str | None = None
    # Direct URL to a spatial zoning-district FeatureServer. Distinct from
    # `zoning_endpoint` (historical: zoning attribute on the parcel layer).
    zoning_polygon_endpoint: str | None = None
    ordinance_url: str | None = None
    where_clause: str | None = None   # SQL WHERE clause for filtered endpoints
    zoning_where_clause: str | None = None


# UGRC county-specific parcel layers (services1.arcgis.com, org 99lidPhWCzftIe9K)
# Each county has its own FeatureServer, filtered by PARCEL_CITY to get one city's parcels.
_UGRC = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services"


def _ugrc(county_service: str, city_name: str, full_name: str, county: str) -> JurisdictionConfig:
    """Build a UGRC county-backed JurisdictionConfig for a Utah city."""
    return JurisdictionConfig(
        name=full_name,
        state="UT",
        county=county,
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/{county_service}/FeatureServer/0",
        where_clause=f"PARCEL_CITY='{city_name}'",
    )


# ── NJ statewide MOD-IV composite parcel service (NJOGIS) ────────────────────
_NJ_STATEWIDE = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest"
    "/services/Parcels_Composite_NJ_WM/FeatureServer/0"
)
# Jersey City zoning: the JC Land Use FeatureServer (all layers 1-4) contains only
# tree canopy analysis polygons, not zoning districts — not usable. NJTPA zoning
# at gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning/FeatureServer/7
# exists but returns 403 externally. Hudson County zoning left as None pending
# a public zoning endpoint being identified.
_NJ_JC_LANDUSE = None
# Newark zoning districts (Layer 14 of Newark_NJ_Zoning service).
_NJ_NEWARK_ZONING = (
    "https://services7.arcgis.com/ZodPOMBKsdAsTqF4/arcgis/rest"
    "/services/Newark_NJ_Zoning/FeatureServer/14"
)


def _nj(county_name: str, full_name: str, zoning_endpoint: str | None = None) -> JurisdictionConfig:
    """Build a statewide-NJ-backed JurisdictionConfig for a NJ county."""
    return JurisdictionConfig(
        name=full_name,
        state="NJ",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=_NJ_STATEWIDE,
        where_clause=f"COUNTY='{county_name.upper()}'",
        zoning_polygon_endpoint=zoning_endpoint,
    )


def _build_nj_jurisdictions() -> dict[str, JurisdictionConfig]:
    """Build all NJ county entries (avoids repeating the same config dict twice)."""
    hudson  = _nj("Hudson",    "Hudson County, NJ",    _NJ_JC_LANDUSE)
    essex   = _nj("Essex",     "Essex County, NJ",     _NJ_NEWARK_ZONING)
    union   = _nj("Union",     "Union County, NJ")
    midsx   = _nj("Middlesex", "Middlesex County, NJ")
    passaic = _nj("Passaic",   "Passaic County, NJ")
    return {
        "hudson county":          hudson,
        "hudson county, nj":      hudson,
        "jersey city":            hudson,
        "essex county":           essex,
        "essex county, nj":       essex,
        "newark":                 essex,
        "union county":           union,
        "union county, nj":       union,
        "middlesex county":       midsx,
        "middlesex county, nj":   midsx,
        "passaic county":         passaic,
        "passaic county, nj":     passaic,
    }


KNOWN_JURISDICTIONS: dict[str, JurisdictionConfig] = {
    # ── Draper — UGRC SaltLake parcels; city name varies "Draper" / "Draper City" ──
    "draper": JurisdictionConfig(
        name="Draper City, UT",
        state="UT",
        county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause="PARCEL_CITY IN ('Draper', 'Draper City')",
        zoning_polygon_endpoint=(
            "https://services2.arcgis.com/nAPVXppTJAHM40Se/arcgis/rest"
            "/services/Zoning/FeatureServer/5"
        ),
        ordinance_url="https://library.municode.com/ut/draper/codes/code_of_ordinances",
    ),
    # ── Salt Lake County (Parcels_SaltLake) ──────────────────────────────────
    "sandy":            _ugrc("Parcels_SaltLake", "Sandy",            "Sandy, UT",            "Salt Lake"),
    "west jordan":      _ugrc("Parcels_SaltLake", "West Jordan",      "West Jordan, UT",      "Salt Lake"),
    # West Valley City — PARCEL_CITY varies "West Valley City" / "West Valley" in UGRC
    "west valley city": JurisdictionConfig(
        name="West Valley City, UT",
        state="UT",
        county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause="PARCEL_CITY IN ('West Valley City', 'West Valley')",
        ordinance_url="https://library.municode.com/ut/west_valley_city/codes/code_of_ordinances",
    ),
    "west valley": JurisdictionConfig(
        name="West Valley City, UT",
        state="UT",
        county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause="PARCEL_CITY IN ('West Valley City', 'West Valley')",
        ordinance_url="https://library.municode.com/ut/west_valley_city/codes/code_of_ordinances",
    ),
    "south jordan":     _ugrc("Parcels_SaltLake", "South Jordan",     "South Jordan, UT",     "Salt Lake"),
    "midvale":          _ugrc("Parcels_SaltLake", "Midvale",          "Midvale, UT",          "Salt Lake"),
    "millcreek":        _ugrc("Parcels_SaltLake", "Millcreek",        "Millcreek, UT",        "Salt Lake"),
    "cottonwood heights": _ugrc("Parcels_SaltLake", "Cottonwood Heights", "Cottonwood Heights, UT", "Salt Lake"),
    "murray": JurisdictionConfig(
        name="Murray, UT", state="UT", county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause="PARCEL_CITY='Murray'",
        ordinance_url="https://library.municode.com/ut/murray/codes/code_of_ordinances",
    ),
    "taylorsville":     _ugrc("Parcels_SaltLake", "Taylorsville",     "Taylorsville, UT",     "Salt Lake"),
    "herriman":         _ugrc("Parcels_SaltLake", "Herriman",         "Herriman, UT",         "Salt Lake"),
    "riverton":         _ugrc("Parcels_SaltLake", "Riverton",         "Riverton, UT",         "Salt Lake"),
    "holladay":         _ugrc("Parcels_SaltLake", "Holladay",         "Holladay, UT",         "Salt Lake"),
    "south salt lake":  _ugrc("Parcels_SaltLake", "South Salt Lake",  "South Salt Lake, UT",  "Salt Lake"),
    "bluffdale": JurisdictionConfig(
        name="Bluffdale, UT", state="UT", county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause="PARCEL_CITY='Bluffdale'",
        ordinance_url="https://library.municode.com/ut/bluffdale",
    ),
    "salt lake city":   _ugrc("Parcels_SaltLake", "Salt Lake City",   "Salt Lake City, UT",   "Salt Lake"),
    # ── Utah County (Parcels_Utah) ────────────────────────────────────────────
    "provo":         _ugrc("Parcels_Utah", "Provo",         "Provo, UT",         "Utah"),
    "orem": JurisdictionConfig(
        name="Orem, UT", state="UT", county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Orem'",
        zoning_polygon_endpoint=(
            "https://maps.utahcounty.gov/arcgis/rest/services"
            "/Assessor/CommercialAppraiser/MapServer/28"
        ),
    ),
    "lehi":          _ugrc("Parcels_Utah", "Lehi",          "Lehi, UT",          "Utah"),
    "lindon": JurisdictionConfig(
        name="Lindon, UT", state="UT", county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Lindon'",
        ordinance_url="https://lindon.municipal.codes/Code/AxA-Table",
    ),
    "american fork": _ugrc("Parcels_Utah", "American Fork", "American Fork, UT", "Utah"),
    "eagle mountain": _ugrc("Parcels_Utah", "Eagle Mountain", "Eagle Mountain, UT", "Utah"),
    "pleasant grove": _ugrc("Parcels_Utah", "Pleasant Grove", "Pleasant Grove, UT", "Utah"),
    "springville":   _ugrc("Parcels_Utah", "Springville",   "Springville, UT",   "Utah"),
    "spanish fork":  _ugrc("Parcels_Utah", "Spanish Fork",  "Spanish Fork, UT",  "Utah"),
    "payson": JurisdictionConfig(
        name="Payson, UT",
        state="UT",
        county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Payson'",
        zoning_polygon_endpoint=(
            "https://services8.arcgis.com/osUxz0Iq5jAvotbH/arcgis/rest"
            "/services/Zoning/FeatureServer/2"
        ),
    ),
    "payson, ut": JurisdictionConfig(
        name="Payson, UT",
        state="UT",
        county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Payson'",
        zoning_polygon_endpoint=(
            "https://services8.arcgis.com/osUxz0Iq5jAvotbH/arcgis/rest"
            "/services/Zoning/FeatureServer/2"
        ),
    ),
    "saratoga springs": JurisdictionConfig(
        name="Saratoga Springs, UT", state="UT", county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Saratoga Springs'",
        zoning_polygon_endpoint=(
            "https://gis.saratogaspringscity.com/arcgisweb/rest/services"
            "/Planning/Zoning/MapServer/1"
        ),
    ),
    # ── Weber County (Parcels_Weber) ─────────────────────────────────────────
    "ogden":     _ugrc("Parcels_Weber", "Ogden",     "Ogden, UT",     "Weber"),
    "roy":       _ugrc("Parcels_Weber", "Roy",       "Roy, UT",       "Weber"),
    "west haven": _ugrc("Parcels_Weber", "West Haven", "West Haven, UT", "Weber"),
    # ── Davis County (Parcels_Davis) ─────────────────────────────────────────
    "layton":    _ugrc("Parcels_Davis", "Layton",    "Layton, UT",    "Davis"),
    "bountiful": _ugrc("Parcels_Davis", "Bountiful", "Bountiful, UT", "Davis"),
    "clearfield": _ugrc("Parcels_Davis", "Clearfield", "Clearfield, UT", "Davis"),
    "syracuse":  _ugrc("Parcels_Davis", "Syracuse",  "Syracuse, UT",  "Davis"),
    "kaysville": _ugrc("Parcels_Davis", "Kaysville", "Kaysville, UT", "Davis"),
    # ── Cache County (Parcels_Cache) ─────────────────────────────────────────
    "logan": _ugrc("Parcels_Cache", "Logan", "Logan, UT", "Cache"),
    # ── Washington County (Parcels_Washington) ────────────────────────────────
    "st. george":  _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "saint george": _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "st george":   _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "washington":  _ugrc("Parcels_Washington", "Washington", "Washington, UT", "Washington"),
    "hurricane": JurisdictionConfig(
        name="Hurricane, UT", state="UT", county="Washington",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Washington/FeatureServer/0",
        where_clause="PARCEL_CITY='Hurricane'",
        zoning_polygon_endpoint=(
            "https://agisprodvm.washco.utah.gov/arcgis/rest/services"
            "/Zoning/MapServer/5"
        ),
        ordinance_url="https://library.municode.com/ut/hurricane/codes/code_of_ordinances",
    ),
    # ── Iron County (Parcels_Iron) ────────────────────────────────────────────
    "cedar city": _ugrc("Parcels_Iron", "Cedar City", "Cedar City, UT", "Iron"),

    # ── New York ─────────────────────────────────────────────────────────────
    # NYC — MapPLUTO (citywide parcels with ZONEDIST) + Zoning Districts polygons.
    # Both layers published by NYC Dept of City Planning on services5.arcgis.com.
    "new york city": JurisdictionConfig(
        name="New York, NY",
        state="NY",
        county="New York",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest"
            "/services/MAPPLUTO/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest"
            "/services/v_Zoning_Districts_NYZD/FeatureServer/0"
        ),
    ),
    "new york, ny": JurisdictionConfig(
        name="New York, NY",
        state="NY",
        county="New York",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest"
            "/services/MAPPLUTO/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest"
            "/services/v_Zoning_Districts_NYZD/FeatureServer/0"
        ),
    ),

    # ── Pennsylvania ─────────────────────────────────────────────────────────
    # Philadelphia — OPA parcels + Zoning Base Districts (separate layers).
    "philadelphia": JurisdictionConfig(
        name="Philadelphia, PA",
        state="PA",
        county="Philadelphia",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
            "/services/OPA_Properties_Public/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
            "/services/Zoning_BaseDistricts/FeatureServer/0"
        ),
    ),
    "philadelphia, pa": JurisdictionConfig(
        name="Philadelphia, PA",
        state="PA",
        county="Philadelphia",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
            "/services/OPA_Properties_Public/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
            "/services/Zoning_BaseDistricts/FeatureServer/0"
        ),
    ),
    "allentown": JurisdictionConfig(
        name="Allentown, PA",
        state="PA",
        county="Lehigh",
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=(
            "https://gis.dep.pa.gov/depgisprd/rest/services/Parcels/PA_Parcels/MapServer/0"
        ),
        where_clause="CITY='ALLENTOWN' AND COUNTY_NAME='LEHIGH'",
        zoning_polygon_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services/CityZoning/MapServer/0"
        ),
    ),
    "allentown, pa": JurisdictionConfig(
        name="Allentown, PA",
        state="PA",
        county="Lehigh",
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=(
            "https://gis.dep.pa.gov/depgisprd/rest/services/Parcels/PA_Parcels/MapServer/0"
        ),
        where_clause="CITY='ALLENTOWN' AND COUNTY_NAME='LEHIGH'",
        zoning_polygon_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services/CityZoning/MapServer/0"
        ),
    ),
    "park city": JurisdictionConfig(
        name="Park City, UT",
        state="UT",
        county="Summit",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://cityworks.parkcity.org/arcgis/rest/services/Parcels/MapServer/0"
        ),
        # Park City exposes parcels directly, but a production-grade zoning layer
        # still needs manual confirmation; recovery tooling handles candidate
        # source discovery separately instead of silently ingesting the wrong data.
        zoning_polygon_endpoint=None,
    ),
    "park city, ut": JurisdictionConfig(
        name="Park City, UT",
        state="UT",
        county="Summit",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://cityworks.parkcity.org/arcgis/rest/services/Parcels/MapServer/0"
        ),
        zoning_polygon_endpoint=None,
    ),

    # ── Allentown, PA ────────────────────────────────────────────────────────
    # City_Landuse FeatureServer: WARDACCTNO=APN, PROPERTYADDR=address.
    # ZONE_CODE is an integer land-use code; actual zoning district text codes
    # (e.g. R-L, C-1) come from the separate CityZoning FeatureServer via
    # spatial join (zoning_polygon_endpoint).
    "allentown": JurisdictionConfig(
        name="Allentown, PA",
        state="PA",
        county="Lehigh",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services"
            "/City_Landuse/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services"
            "/CityZoning/FeatureServer/0"
        ),
        ordinance_url=(
            "https://www.allentownpa.gov/Portals/0/files/Departments"
            "/PlanningZoning/Zoning%20Ordinance.pdf"
        ),
    ),
    "allentown, pa": JurisdictionConfig(
        name="Allentown, PA",
        state="PA",
        county="Lehigh",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services"
            "/City_Landuse/FeatureServer/0"
        ),
        zoning_polygon_endpoint=(
            "https://gisportal.allentownpa.gov/server/rest/services"
            "/CityZoning/FeatureServer/0"
        ),
        ordinance_url=(
            "https://www.allentownpa.gov/Portals/0/files/Departments"
            "/PlanningZoning/Zoning%20Ordinance.pdf"
        ),
    ),

    # ── New Jersey counties ───────────────────────────────────────────────────
    # Source: NJOGIS Parcels_Composite_NJ_WM — MOD-IV statewide composite.
    # Filtered per county via COUNTY='<NAME>' (uppercase full county name).
    # Note: OWNER_NAME is redacted in this service per NJ Daniel's Law.
    # Zoning is municipal-level; Hudson uses Jersey City land use layer,
    # Essex uses Newark zoning layer as best available coverage.
    **{k: v for k, v in _build_nj_jurisdictions().items()},
}


def _match_jurisdiction(input_str: str) -> JurisdictionConfig | None:
    """Check hard-coded registry first (fast path, no network)."""
    normalized = input_str.lower().strip()
    for key, cfg in KNOWN_JURISDICTIONS.items():
        if key in normalized or cfg.name.lower() in normalized:
            return cfg
    return None


# ─── Status helpers ──────────────────────────────────────────────────────────

async def _set_status(
    db: AsyncSession,
    job: Job,
    status: JobStatus,
    progress: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    job.status = status
    if progress:
        job.progress = {**(job.progress or {}), **progress}
    if error:
        job.error_message = error
    await db.flush()


# ─── Public entry point ──────────────────────────────────────────────────────

async def run_job_pipeline(job_id: uuid.UUID) -> None:
    """
    Full pipeline for a single job.  Runs as a FastAPI BackgroundTask.

    Creates its own DB session (cannot share the request session after the
    request context ends).
    """
    async with async_session_maker() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.error("Job %s not found in DB", job_id)
            return

        try:
            await _run(db, job)
        except Exception as exc:
            logger.exception("Pipeline failed for job %s", job_id)
            await _set_status(db, job, JobStatus.failed, error=str(exc))
            await db.commit()


async def _run(db: AsyncSession, job: Job) -> None:
    """Inner pipeline — raises on error so the outer handler can catch."""

    # ── Step 0: resolve jurisdiction config ──────────────────────────────
    await _set_status(db, job, JobStatus.discovering_layers)
    await db.commit()

    cfg = _match_jurisdiction(job.jurisdiction_input or "")
    if cfg is None:
        # Phase 5: live discovery for unknown jurisdictions
        cfg = await _discover_jurisdiction_config(job.jurisdiction_input or "")
        # Persist discovery source so the frontend can show it
        await _set_status(
            db, job, JobStatus.discovering_layers,
            progress={"discovery_source": cfg.parcel_source.value},
        )
        await db.commit()

    logger.info("Pipeline resolved jurisdiction: %s (source=%s)", cfg.name, cfg.parcel_source)

    # ── Step 1: get or create Jurisdiction row ────────────────────────────
    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.name == cfg.name)
    )
    jurisdiction = result.scalars().first()

    if jurisdiction is None:
        jurisdiction = Jurisdiction(
            name=cfg.name,
            state=cfg.state,
            county=cfg.county,
            parcel_source=cfg.parcel_source,
            parcel_endpoint=cfg.parcel_endpoint,
            zoning_endpoint=cfg.zoning_polygon_endpoint or cfg.zoning_endpoint,
        )
        db.add(jurisdiction)
        await db.flush()
        logger.info("Created new Jurisdiction row: %s (%s)", cfg.name, jurisdiction.id)
    else:
        # Update endpoints in case they changed
        jurisdiction.parcel_endpoint = cfg.parcel_endpoint
        jurisdiction.zoning_endpoint = cfg.zoning_polygon_endpoint or cfg.zoning_endpoint
        await db.flush()
        logger.info("Found existing Jurisdiction: %s (%s)", cfg.name, jurisdiction.id)

    # Link job to jurisdiction
    job.jurisdiction_id = jurisdiction.id
    await db.flush()

    # ── Step 2: download parcels ──────────────────────────────────────────
    await _set_status(
        db, job, JobStatus.downloading_parcels,
        progress={"jurisdiction_id": str(jurisdiction.id)},
    )
    await db.commit()

    downloaded_count = [0]
    total_count = [0]

    async def _progress(downloaded: int, total: int) -> None:
        downloaded_count[0] = downloaded
        total_count[0] = total
        job.progress = {
            **(job.progress or {}),
            "parcels_downloaded": downloaded,
            "parcels_total": total,
        }
        await db.flush()
        # Commit progress every 500 parcels so the frontend can see it
        if downloaded % 500 == 0:
            await db.commit()

    if cfg.parcel_source == ParcelSource.regrid:
        # Regrid path is stored in parcel_endpoint (e.g. "ut/salt_lake/draper")
        logger.info("Downloading parcels from Regrid path: %s", cfg.parcel_endpoint)
        from app.services.regrid_client import download_parcels_by_path
        gdf = await download_parcels_by_path(cfg.parcel_endpoint)
        # Fake a progress update so the UI shows *something*
        await _progress(len(gdf), len(gdf))
    else:
        logger.info("Downloading parcels from ArcGIS: %s (where=%s)", cfg.parcel_endpoint, cfg.where_clause or "1=1")
        gdf = await download_all_features(
            cfg.parcel_endpoint,
            where=cfg.where_clause or "1=1",
            progress_callback=_progress,
        )
    logger.info("Downloaded %d features", len(gdf))

    # ── Step 3: ingest into PostGIS ───────────────────────────────────────
    await _set_status(
        db, job, JobStatus.downloading_parcels,
        progress={"step": "ingesting", "parcels_downloaded": len(gdf)},
    )
    await db.commit()
    logger.info("Ingesting parcels into PostGIS …")

    async def _ingest_progress(ingested: int, total: int) -> None:
        job.progress = {
            **(job.progress or {}),
            "step": "ingesting",
            "parcels_ingested": ingested,
            "parcels_ingested_total": total,
        }
        await db.flush()
        await db.commit()

    count = await ingest_parcels(gdf, jurisdiction.id, db, progress_callback=_ingest_progress)

    # Commit last_indexed_at immediately so the cache check in jobs.py
    # can find this jurisdiction on the next search and return instantly.
    from datetime import datetime, timezone
    jurisdiction.last_indexed_at = datetime.now(timezone.utc)
    await refresh_jurisdiction_bbox(jurisdiction, db)

    # Mark job ready NOW so the dashboard unlocks without waiting for
    # zoning / ordinance / overlay steps (those enrich data in-place).
    await _set_status(
        db, job, JobStatus.ready,
        progress={
            "parcels_ingested": count,
            "jurisdiction_id": str(jurisdiction.id),
        },
    )
    await db.commit()
    logger.info("Parcels committed — job %s is ready with %d parcels", job.id, count)

    # ── Step 3a: download + ingest zoning polygons (non-fatal) ───────────
    zoning_count = 0
    zoning_endpoint = cfg.zoning_polygon_endpoint or cfg.zoning_endpoint
    if zoning_endpoint:
        await _set_status(
            db, job, JobStatus.downloading_zoning,
            progress={"zoning_endpoint": zoning_endpoint},
        )
        await db.commit()
        try:
            logger.info("Downloading zoning districts from %s", zoning_endpoint)
            zgdf = await download_all_features(
                zoning_endpoint,
                where=cfg.zoning_where_clause or "1=1",
            )
            zoning_count = await ingest_zoning_districts(zgdf, jurisdiction.id, db)
            await db.commit()

            updated = await backfill_parcel_zoning_from_districts(jurisdiction.id, db)
            logger.info("zone_class backfill updated %d parcels", updated)
            await db.commit()
        except Exception as exc:
            logger.warning("Zoning ingest failed (non-fatal): %s", exc)
            await db.rollback()

    seeded_matrix = await bootstrap_zone_use_matrix(
        jurisdiction.id,
        db,
        missing_only=True,
    )
    if seeded_matrix:
        logger.info("Bootstrapped %d zone_use_matrix rows", seeded_matrix)
        await db.commit()

    await refresh_jurisdiction_coverage_level(jurisdiction, db)
    await db.flush()

    # ── Step 3b: apply overlays (flood + wetland, non-fatal) ─────────────
    await _set_status(db, job, JobStatus.running_overlays)
    await db.commit()
    try:
        from app.services.overlays import apply_flood_overlay, apply_wetland_overlay
        flood_count = await apply_flood_overlay(jurisdiction.id, db)
        wetland_count = await apply_wetland_overlay(jurisdiction.id, db)
        await db.commit()
        logger.info(
            "Overlays: %d flood parcels, %d wetland parcels", flood_count, wetland_count
        )
    except Exception as exc:
        logger.warning("Overlay step failed (non-fatal): %s", exc)
        await db.rollback()

    # ── Step 4: parse ordinance (optional — non-fatal if it fails) ───────
    ordinance_url = job.ordinance_url or cfg.ordinance_url
    if not ordinance_url:
        # Auto-discover the ordinance URL from Municode / eCode360
        try:
            from app.services.ordinance_fetcher import discover_ordinance_url
            discovered = await discover_ordinance_url(cfg.name, cfg.state or "")
            if discovered:
                ordinance_url = discovered
                logger.info("Auto-discovered ordinance URL for %s: %s", cfg.name, discovered)
        except Exception as exc:
            logger.warning("Ordinance URL discovery failed (non-fatal): %s", exc)
    if ordinance_url:
        await _set_status(db, job, JobStatus.parsing_ordinance)
        await db.commit()
        try:
            await _parse_and_save_ordinance(db, jurisdiction, ordinance_url)
        except Exception as exc:
            logger.warning(
                "Ordinance parsing failed (non-fatal) for job %s: %s", job.id, exc
            )
            # Non-fatal — job continues to ready state

    logger.info(
        "Job %s fully enriched — %d parcels for %s", job.id, count, cfg.name
    )


# ─── Ordinance parsing helper ────────────────────────────────────────────────

async def _parse_and_save_ordinance(
    db: AsyncSession,
    jurisdiction: Jurisdiction,
    ordinance_url: str,
) -> None:
    """
    Fetch the ordinance, parse it with Claude, and upsert zone_use_matrix rows.
    Raises on any unrecoverable error; caller logs and continues to ready state.
    """
    from datetime import datetime, timezone

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.zone_use_matrix import ClassificationSource, ZoneUseMatrix
    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections

    # Discover known zone codes from already-ingested parcels
    rows = await db.execute(
        sa_select(Parcel.zoning_code)
        .where(
            Parcel.jurisdiction_id == jurisdiction.id,
            Parcel.zoning_code.isnot(None),
        )
        .distinct()
    )
    known_codes: list[str] = sorted(
        {r[0] for r in rows.fetchall() if r[0]}
    )

    logger.info("Fetching ordinance from %s …", ordinance_url)
    sections = await fetch_from_url(ordinance_url)

    combined = "\n\n".join(
        f"[Section {s.section_id}: {s.heading}]\n{s.text}"
        for s in sections
    )
    logger.info(
        "Sending %d sections (%d chars) to Claude for %s …",
        len(sections), len(combined), jurisdiction.name,
    )

    output = await parse_ordinance_sections(
        combined, jurisdiction.name, known_codes
    )

    # Deduplicate zones by code (keep highest confidence if Claude returns duplicates)
    seen: dict[str, Any] = {}
    for zone in output.zones:
        if zone.code not in seen or zone.confidence > seen[zone.code].confidence:
            seen[zone.code] = zone
    deduped_zones = list(seen.values())

    _LLM_CONF_THRESHOLD = 0.70

    # Upsert zone matrix rows — LLM output overwrites rule-based rows but never
    # overwrites human-reviewed rows or prior LLM rows marked human.
    for zone in deduped_zones:
        # Determine fine-grained classification source
        notes_str = zone.notes or ""
        if notes_str.startswith("[rule-fallback:"):
            source = ClassificationSource.rule
        elif notes_str.startswith("[llm+rule:"):
            source = ClassificationSource.llm_rule
        elif (zone.confidence or 0.0) < _LLM_CONF_THRESHOLD:
            source = ClassificationSource.llm_low_confidence
        else:
            source = ClassificationSource.llm

        citations_val = [c.model_dump() for c in zone.citations] if zone.citations else None
        stmt = pg_insert(ZoneUseMatrix).values(
            jurisdiction_id=jurisdiction.id,
            zone_code=zone.code,
            zone_name=zone.name,
            self_storage=zone.self_storage,
            mini_warehouse=zone.mini_warehouse,
            light_industrial=zone.light_industrial,
            luxury_garage_condo=zone.luxury_garage_condo,
            citations=citations_val,
            confidence=zone.confidence,
            notes=zone.notes,
            classification_source=source,
        ).on_conflict_do_update(
            constraint="uq_zone_matrix",
            set_=dict(
                zone_name=zone.name,
                self_storage=zone.self_storage,
                mini_warehouse=zone.mini_warehouse,
                light_industrial=zone.light_industrial,
                luxury_garage_condo=zone.luxury_garage_condo,
                citations=citations_val,
                confidence=zone.confidence,
                notes=zone.notes,
                classification_source=source,
            ),
            where=(
                (ZoneUseMatrix.human_reviewed == False) &
                (ZoneUseMatrix.classification_source != ClassificationSource.human) &
                (ZoneUseMatrix.confidence < zone.confidence)
            ),
        )
        await db.execute(stmt)

    jurisdiction.ordinance_url = ordinance_url
    await db.flush()
    logger.info(
        "Saved %d zone matrix rows for %s", len(deduped_zones), jurisdiction.name
    )


# ─── Phase 5: live discovery helpers ─────────────────────────────────────────

async def _discover_jurisdiction_config(input_str: str) -> JurisdictionConfig:
    """
    Try live ArcGIS discovery for an unknown jurisdiction, then Regrid fallback.
    Raises ValueError with a helpful message if everything fails.
    """
    from app.config import settings
    from app.services.arcgis_discovery import discover_layers, geocode_jurisdiction

    geo = None

    # ── Try ArcGIS discovery ──────────────────────────────────────────────────
    try:
        endpoints = await discover_layers(input_str)
        geo = endpoints.geocoded

        # If Hub/direct discovery didn't geocode, do it now for state/county
        if geo is None:
            try:
                geo = await geocode_jurisdiction(input_str)
            except Exception:
                pass

        name = (geo.city if geo else None) or input_str
        state = (geo.state if geo else None) or _parse_state(input_str)
        county = (geo.county if geo else "") or ""

        logger.info(
            "ArcGIS discovery succeeded via %s: parcel=%s",
            endpoints.source, endpoints.parcel_url,
        )
        return JurisdictionConfig(
            name=name,
            state=state,
            county=county,
            parcel_source=ParcelSource.city_gis,
            parcel_endpoint=endpoints.parcel_url,
            zoning_endpoint=endpoints.zoning_url,
        )

    except RuntimeError as discovery_err:
        logger.warning("ArcGIS discovery failed for %r: %s", input_str, discovery_err)

    # ── Regrid fallback ───────────────────────────────────────────────────────
    if settings.regrid_enabled:
        logger.info("Trying Regrid fallback for %r", input_str)
        try:
            geo = await geocode_jurisdiction(input_str)
        except Exception as exc:
            raise ValueError(
                f"Could not geocode {input_str!r} for Regrid fallback: {exc}"
            ) from exc

        regrid_path = _build_regrid_path(geo)
        logger.info("Regrid path: %s", regrid_path)
        return JurisdictionConfig(
            name=geo.city,
            state=geo.state,
            county=geo.county,
            parcel_source=ParcelSource.regrid,
            parcel_endpoint=regrid_path,
            zoning_endpoint=None,
        )

    raise ValueError(
        f"Unknown jurisdiction {input_str!r}. "
        "Paste a direct ArcGIS FeatureServer URL, or set REGRID_API_KEY "
        "to enable the Regrid fallback."
    )


def _parse_state(s: str) -> str:
    """Extract a 2-letter US state code from a string like 'Draper, UT'."""
    m = re.search(r",\s*([A-Z]{2})\b", s.upper())
    return m.group(1) if m else ""


def _build_regrid_path(geo: Any) -> str:
    """Convert geocoded place to Regrid API path: 'ut/salt_lake/draper'."""
    def slug(s: str) -> str:
        s = re.sub(r"\b(county|parish|borough|municipality)\b", "", s, flags=re.I).strip()
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    return f"{geo.state.lower()}/{slug(geo.county)}/{slug(geo.city)}"


# ─── Helpers added for NY/PA pivot ───────────────────────────────────────────

async def _refresh_jurisdiction_bbox(
    jurisdiction: Jurisdiction, db: AsyncSession
) -> None:
    await refresh_jurisdiction_bbox(jurisdiction, db)


async def _backfill_parcel_zone_class(
    jurisdiction_id: uuid.UUID, db: AsyncSession
) -> int:
    return await backfill_parcel_zoning_from_districts(jurisdiction_id, db)


def _coverage_level(
    *, parcel_count: int, zoning_count: int
) -> CoverageLevel:
    if parcel_count > 0 and zoning_count > 0:
        return CoverageLevel.full
    if parcel_count > 0:
        return CoverageLevel.parcels_only
    if zoning_count > 0:
        return CoverageLevel.zoning_only
    return CoverageLevel.partial
