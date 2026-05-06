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

import asyncio
import logging
import socket
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select as sa_select

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import CoverageLevel, Jurisdiction, ParcelSource
from app.models.parcel import Parcel
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels
from app.services.job_tracking import (
    JobCancelled,
    add_job_artifact,
    check_cancelled,
    complete_job_step,
    fail_job_step,
    mark_job_failed,
    now_utc,
    start_job_step,
)
from app.services.matrix_bootstrap import bootstrap_zone_use_matrix
from app.services.spatial_backfill import (
    backfill_parcel_zoning_from_districts,
    refresh_jurisdiction_bbox,
    refresh_jurisdiction_coverage_level,
)
from app.services.zoning_ingestion import ingest_zoning_districts
from app.services.zoning_system import bulk_ingest_zoning_for_jurisdiction, enqueue_missing_zoning_for_jurisdiction

logger = logging.getLogger(__name__)

PARCEL_FETCH_TIMEOUT_SECONDS = 180
PARCEL_INGEST_TIMEOUT_SECONDS = 300
ZONING_TIMEOUT_SECONDS = 600
ENRICHMENT_TIMEOUT_SECONDS = 240
ORDINANCE_TIMEOUT_SECONDS = 240
MAX_JOB_ERROR_LENGTH = 2000


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_extra(extra: dict[str, Any]) -> str:
    if not extra:
        return ""
    return " " + " ".join(f"{key}={value!r}" for key, value in extra.items())


def _safe_job_id(job: Job) -> Any:
    """Return job.id without triggering a sync ORM lazy-load.

    After a transaction rollback the ORM attribute is expired; reading
    `job.id` would synchronously emit a SELECT to refresh it, which fails
    in the Dramatiq worker context with MissingGreenlet. Pulling the
    cached value out of `__dict__` bypasses the InstrumentedAttribute
    descriptor entirely.
    """
    return job.__dict__.get("id", "unknown")


def _stage_started(job: Job, stage: str, **extra: Any) -> float:
    started_at = time.perf_counter()
    logger.info(
        "pipeline_event timestamp=%s job_id=%s stage=%s event=started duration_ms=0%s",
        _timestamp(),
        _safe_job_id(job),
        stage,
        _format_extra(extra),
    )
    return started_at


def _stage_completed(job: Job, stage: str, started_at: float, **extra: Any) -> None:
    duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
    logger.info(
        "pipeline_event timestamp=%s job_id=%s stage=%s event=completed duration_ms=%s%s",
        _timestamp(),
        _safe_job_id(job),
        stage,
        duration_ms,
        _format_extra(extra),
    )


def _stage_failed(job: Job, stage: str, started_at: float, exc: Exception) -> None:
    duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
    logger.exception(
        "pipeline_event timestamp=%s job_id=%s stage=%s event=failed duration_ms=%s error=%r",
        _timestamp(),
        _safe_job_id(job),
        stage,
        duration_ms,
        str(exc),
    )


def _job_error_message(exc: Exception) -> str:
    message = str(exc)
    if len(message) <= MAX_JOB_ERROR_LENGTH:
        return message
    return f"{message[:MAX_JOB_ERROR_LENGTH]}... [truncated]"


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
    """Build all NJ county entries (avoids repeating the same config dict twice).

    City-keyed aliases route the priority NJ cities (Newark, Jersey City,
    Paterson, Elizabeth, New Brunswick, Marlboro, Hoboken) to their county's
    statewide MOD-IV slice instead of falling through to live ArcGIS
    discovery — which has been miscoding city→county pairs (Paterson sent to
    Bergen, Elizabeth/New Brunswick/Paterson stamped state='NE').
    """
    hudson    = _nj("Hudson",    "Hudson County, NJ",    _NJ_JC_LANDUSE)
    essex     = _nj("Essex",     "Essex County, NJ",     _NJ_NEWARK_ZONING)
    union     = _nj("Union",     "Union County, NJ")
    midsx     = _nj("Middlesex", "Middlesex County, NJ")
    passaic   = _nj("Passaic",   "Passaic County, NJ")
    monmouth  = _nj("Monmouth",  "Monmouth County, NJ")
    return {
        "hudson county":          hudson,
        "hudson county, nj":      hudson,
        "jersey city":            hudson,
        "jersey city, nj":        hudson,
        "hoboken":                hudson,
        "hoboken, nj":            hudson,
        "essex county":           essex,
        "essex county, nj":       essex,
        "newark":                 essex,
        "newark, nj":             essex,
        "union county":           union,
        "union county, nj":       union,
        "elizabeth":              union,
        "elizabeth, nj":          union,
        "middlesex county":       midsx,
        "middlesex county, nj":   midsx,
        "new brunswick":          midsx,
        "new brunswick, nj":      midsx,
        "passaic county":         passaic,
        "passaic county, nj":     passaic,
        "paterson":               passaic,
        "paterson, nj":           passaic,
        "monmouth county":        monmouth,
        "monmouth county, nj":    monmouth,
        "marlboro":               monmouth,
        "marlboro, nj":           monmouth,
    }


KNOWN_JURISDICTIONS: dict[str, JurisdictionConfig] = {
    # ── Draper (city-specific layer with zoning codes — keep as-is) ───────────
    "draper": JurisdictionConfig(
        name="Draper City, UT",
        state="UT",
        county="Salt Lake",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=(
            "https://services2.arcgis.com/nAPVXppTJAHM40Se/arcgis/rest"
            "/services/Public_Parcels/FeatureServer/11"
        ),
        zoning_endpoint=(
            "https://services2.arcgis.com/nAPVXppTJAHM40Se/arcgis/rest"
            "/services/Zoning/FeatureServer/5"
        ),
        ordinance_url="https://library.municode.com/ut/draper/codes/code_of_ordinances",
    ),
    # ── Salt Lake County (Parcels_SaltLake) ──────────────────────────────────
    "sandy":            _ugrc("Parcels_SaltLake", "Sandy",            "Sandy, UT",            "Salt Lake"),
    "west jordan":      _ugrc("Parcels_SaltLake", "West Jordan",      "West Jordan, UT",      "Salt Lake"),
    "west valley city": _ugrc("Parcels_SaltLake", "West Valley City", "West Valley City, UT", "Salt Lake"),
    "west valley":      _ugrc("Parcels_SaltLake", "West Valley City", "West Valley City, UT", "Salt Lake"),
    "south jordan":     _ugrc("Parcels_SaltLake", "South Jordan",     "South Jordan, UT",     "Salt Lake"),
    "midvale":          _ugrc("Parcels_SaltLake", "Midvale",          "Midvale, UT",          "Salt Lake"),
    "millcreek":        _ugrc("Parcels_SaltLake", "Millcreek",        "Millcreek, UT",        "Salt Lake"),
    "cottonwood heights": _ugrc("Parcels_SaltLake", "Cottonwood Heights", "Cottonwood Heights, UT", "Salt Lake"),
    "murray":           _ugrc("Parcels_SaltLake", "Murray",           "Murray, UT",           "Salt Lake"),
    "taylorsville":     _ugrc("Parcels_SaltLake", "Taylorsville",     "Taylorsville, UT",     "Salt Lake"),
    "herriman":         _ugrc("Parcels_SaltLake", "Herriman",         "Herriman, UT",         "Salt Lake"),
    "riverton":         _ugrc("Parcels_SaltLake", "Riverton",         "Riverton, UT",         "Salt Lake"),
    "holladay":         _ugrc("Parcels_SaltLake", "Holladay",         "Holladay, UT",         "Salt Lake"),
    "south salt lake":  _ugrc("Parcels_SaltLake", "South Salt Lake",  "South Salt Lake, UT",  "Salt Lake"),
    "bluffdale":        _ugrc("Parcels_SaltLake", "Bluffdale",        "Bluffdale, UT",        "Salt Lake"),
    "salt lake city":   _ugrc("Parcels_SaltLake", "Salt Lake City",   "Salt Lake City, UT",   "Salt Lake"),
    # ── Utah County (Parcels_Utah) ────────────────────────────────────────────
    "provo":         _ugrc("Parcels_Utah", "Provo",         "Provo, UT",         "Utah"),
    "orem":          _ugrc("Parcels_Utah", "Orem",          "Orem, UT",          "Utah"),
    "lehi": JurisdictionConfig(
        name="Lehi, UT", state="UT", county="Utah",
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause="PARCEL_CITY='Lehi'",
        zoning_polygon_endpoint=(
            "https://maps.utahcounty.gov/arcgis/rest/services/Assessor"
            "/CommercialAppraiser/MapServer/50"
        ),
    ),
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
    # ── Weber County (Parcels_Weber) ─────────────────────────────────────────
    "ogden": _ugrc("Parcels_Weber", "Ogden", "Ogden, UT", "Weber"),
    "roy":   _ugrc("Parcels_Weber", "Roy",   "Roy, UT",   "Weber"),
    # ── Davis County (Parcels_Davis) ─────────────────────────────────────────
    "layton":    _ugrc("Parcels_Davis", "Layton",    "Layton, UT",    "Davis"),
    "bountiful": _ugrc("Parcels_Davis", "Bountiful", "Bountiful, UT", "Davis"),
    "clearfield": _ugrc("Parcels_Davis", "Clearfield", "Clearfield, UT", "Davis"),
    "syracuse":  _ugrc("Parcels_Davis", "Syracuse",  "Syracuse, UT",  "Davis"),
    # ── Cache County (Parcels_Cache) ─────────────────────────────────────────
    "logan": _ugrc("Parcels_Cache", "Logan", "Logan, UT", "Cache"),
    # ── Washington County (Parcels_Washington) ────────────────────────────────
    "st. george":  _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "saint george": _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "st george":   _ugrc("Parcels_Washington", "St. George", "St George, UT", "Washington"),
    "washington":  _ugrc("Parcels_Washington", "Washington", "Washington, UT", "Washington"),
    "hurricane":   _ugrc("Parcels_Washington", "Hurricane",  "Hurricane, UT",  "Washington"),
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


async def _heartbeat_locked_at(job_id: uuid.UUID, interval: int = 60) -> None:
    """Refresh locked_at every interval seconds so the watchdog never kills an active job."""
    while True:
        await asyncio.sleep(interval)
        try:
            async with async_session_maker() as hb_db:
                result = await hb_db.execute(select(Job).where(Job.id == job_id))
                hb_job = result.scalar_one_or_none()
                if hb_job and hb_job.locked_at is not None:
                    hb_job.locked_at = now_utc()
                    await hb_db.commit()
                    logger.debug("Heartbeat refreshed locked_at for job %s", job_id)
        except Exception as exc:
            logger.debug("Heartbeat failed for job %s: %s", job_id, exc)


# ─── Public entry point ──────────────────────────────────────────────────────

async def run_job_pipeline(job_id: uuid.UUID) -> None:
    """
    Full pipeline for a single job.  Runs as a FastAPI BackgroundTask.

    Creates its own DB session (cannot share the request session after the
    request context ends).
    """
    async with async_session_maker() as db:
        try:
            result = await db.execute(
                select(Job).where(Job.id == job_id).with_for_update(nowait=True)
            )
        except OperationalError:
            logger.info("Job %s is already locked by another worker", job_id)
            return
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Job %s not found in DB", job_id)
            return
        if job.status in {JobStatus.ready, JobStatus.failed, JobStatus.cancelled}:
            logger.info("Skipping terminal job %s with status=%s", job_id, job.status.value)
            return
        if job.locked_by and job.status not in {JobStatus.queued, JobStatus.retrying, JobStatus.pending}:
            logger.info("Skipping locked job %s locked_by=%s", job_id, job.locked_by)
            return
        if job.cancel_requested_at is not None:
            job.status = JobStatus.cancelled
            job.finished_at = now_utc()
            await db.commit()
            return

        pipeline_started = _stage_started(
            job,
            "pipeline",
            jurisdiction_input=job.jurisdiction_input,
        )
        worker_id = socket.gethostname()
        job.status = JobStatus.running
        job.started_at = job.started_at or now_utc()
        job.locked_by = worker_id
        job.locked_at = now_utc()
        job.attempts = (job.attempts or 0) + 1
        await db.commit()

        heartbeat_task = asyncio.create_task(_heartbeat_locked_at(job_id))
        try:
            await _run(db, job)
            _stage_completed(job, "pipeline", pipeline_started, status=JobStatus.ready.value)
        except JobCancelled:
            _stage_completed(job, "pipeline", pipeline_started, status=JobStatus.cancelled.value)
            await db.commit()
        except Exception as exc:
            _stage_failed(job, "pipeline", pipeline_started, exc)
            await mark_job_failed(db, job_id, _job_error_message(exc))
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


async def _run(db: AsyncSession, job: Job) -> None:
    """Inner pipeline — raises on error so the outer handler can catch."""

    # ── Step 0: resolve jurisdiction config ──────────────────────────────
    discovery_started = _stage_started(job, "discover_layers")
    discovery_step = await start_job_step(db, job, "discover_layers")
    await _set_status(db, job, JobStatus.discovering_layers)
    await db.commit()
    await check_cancelled(db, job)

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
    _stage_completed(
        job,
        "discover_layers",
        discovery_started,
        jurisdiction=cfg.name,
        source=cfg.parcel_source.value,
    )
    await complete_job_step(
        db,
        discovery_step,
        {"jurisdiction": cfg.name, "source": cfg.parcel_source.value},
    )
    await add_job_artifact(
        db,
        job,
        "discover_layers",
        "source_layers",
        {
            "parcel_endpoint": cfg.parcel_endpoint,
            "zoning_endpoint": cfg.zoning_polygon_endpoint or cfg.zoning_endpoint,
            "where": cfg.where_clause or "1=1",
        },
    )

    # ── Step 1: get or create Jurisdiction row ────────────────────────────
    persistence_started = _stage_started(job, "jurisdiction_persistence", jurisdiction=cfg.name)
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
    _stage_completed(
        job,
        "jurisdiction_persistence",
        persistence_started,
        jurisdiction_id=str(jurisdiction.id),
    )

    # ── Step 2: download parcels ──────────────────────────────────────────
    parcel_fetch_started = _stage_started(
        job,
        "parcel_fetch",
        endpoint=cfg.parcel_endpoint,
        source=cfg.parcel_source.value,
        where=cfg.where_clause or "1=1",
    )
    parcel_fetch_step = await start_job_step(
        db,
        job,
        "download_parcels",
        {
            "endpoint": cfg.parcel_endpoint,
            "source": cfg.parcel_source.value,
            "where": cfg.where_clause or "1=1",
        },
    )
    await _set_status(
        db, job, JobStatus.downloading_parcels,
        progress={"jurisdiction_id": str(jurisdiction.id)},
    )
    await db.commit()
    await check_cancelled(db, job)

    existing_count = await db.scalar(
        select(func.count(Parcel.id)).where(Parcel.jurisdiction_id == jurisdiction.id)
    )
    # Always reuse cached parcels if they exist. force=True bypasses job dedup
    # and re-runs analysis (zoning, overlays, feasibility), but re-downloading
    # 30k+ geometries on every forced run spikes memory and kills the container.
    parcels_cached = (existing_count or 0) > 0

    if parcels_cached:
        logger.info(
            "Parcels already cached (%d) for jurisdiction %s — skipping download",
            existing_count,
            jurisdiction.id,
        )
        count = existing_count
        _stage_completed(job, "parcel_fetch", parcel_fetch_started, cached=True, existing_count=existing_count)
        await complete_job_step(db, parcel_fetch_step, {"cached": True, "existing_count": existing_count})
        await _set_status(
            db,
            job,
            JobStatus.ingesting_parcels,
            progress={
                "ingest_phase": "cached",
                "parcels_downloaded": existing_count,
                "parcels_total": existing_count,
                "parcels_ingested": existing_count,
            },
        )
        await db.commit()
        await check_cancelled(db, job)
    else:
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
            async with asyncio.timeout(PARCEL_FETCH_TIMEOUT_SECONDS):
                gdf = await download_parcels_by_path(cfg.parcel_endpoint)
            # Fake a progress update so the UI shows *something*
            await _progress(len(gdf), len(gdf))
        else:
            logger.info("Downloading parcels from ArcGIS: %s (where=%s)", cfg.parcel_endpoint, cfg.where_clause or "1=1")
            async with asyncio.timeout(PARCEL_FETCH_TIMEOUT_SECONDS):
                gdf = await download_all_features(
                    cfg.parcel_endpoint,
                    where=cfg.where_clause or "1=1",
                    progress_callback=_progress,
                )
        logger.info("Downloaded %d features", len(gdf))
        _stage_completed(job, "parcel_fetch", parcel_fetch_started, feature_count=len(gdf))
        await complete_job_step(db, parcel_fetch_step, {"feature_count": len(gdf)})
        await add_job_artifact(
            db,
            job,
            "download_parcels",
            "parcel_download_metadata",
            {
                "feature_count": len(gdf),
                "endpoint": cfg.parcel_endpoint,
                "source": cfg.parcel_source.value,
                "where": cfg.where_clause or "1=1",
            },
        )

        # ── Step 3: ingest into PostGIS ───────────────────────────────────────
        ingest_started = _stage_started(job, "ingest", parcel_count=len(gdf))
        ingest_step = await start_job_step(
            db,
            job,
            "ingest_parcels",
            {"downloaded_feature_count": len(gdf)},
        )
        logger.info("Ingesting parcels into PostGIS …")
        await _set_status(
            db,
            job,
            JobStatus.ingesting_parcels,
            progress={
                "ingest_phase": "mapping",
                "parcels_downloaded": len(gdf),
                "parcels_total": len(gdf),
                "parcels_mapped": 0,
                "parcels_ingested": 0,
            },
        )
        await db.commit()
        await check_cancelled(db, job)

        async def _ingest_progress(phase: str, completed: int, total: int) -> None:
            progress_key = "parcels_ingested" if phase == "upserting" else "parcels_mapped"
            job.progress = {
                **(job.progress or {}),
                "ingest_phase": phase,
                progress_key: completed,
                "parcels_total": total,
            }
            await db.flush()
            if completed % 2000 == 0 or completed == total:
                await db.commit()

        async with asyncio.timeout(PARCEL_INGEST_TIMEOUT_SECONDS):
            count = await ingest_parcels(
                gdf,
                jurisdiction.id,
                db,
                progress_callback=_ingest_progress,
            )
        _stage_completed(job, "ingest", ingest_started, parcels_ingested=count)
        await complete_job_step(
            db,
            ingest_step,
            {
                "parcels_downloaded": len(gdf),
                "parcels_ingested": count,
                "dedupe_count": max(len(gdf) - count, 0),
            },
        )
        await add_job_artifact(
            db,
            job,
            "ingest_parcels",
            "parcel_ingest_metadata",
            {
                "parcels_downloaded": len(gdf),
                "parcels_ingested": count,
                "dedupe_count": max(len(gdf) - count, 0),
            },
        )

    # Advance status so the frontend navigates to the map immediately while
    # bbox / matrix / coverage finish in the background.
    await _set_status(db, job, JobStatus.downloading_zoning, progress={
        **(job.progress or {}),
        "phase": "post_ingest",
    })
    await db.commit()
    await check_cancelled(db, job)

    # Update last_indexed_at + compute bbox from ingested parcels
    bbox_started = _stage_started(job, "parcel_bbox_refresh", jurisdiction_id=str(jurisdiction.id))
    jurisdiction.last_indexed_at = datetime.now(timezone.utc)
    async with asyncio.timeout(30):
        await refresh_jurisdiction_bbox(jurisdiction, db)
    await db.flush()
    _stage_completed(job, "parcel_bbox_refresh", bbox_started, bbox=jurisdiction.bbox)

    # zoning_overlays/zoning_rules/enrichment_cache are not read by any API endpoint —
    # they were scaffolded for a future authoritative zoning service. Skip the step
    # entirely; it was the sole source of every pipeline hang.

    # ── Step 3a: zoning district polygons → spatial backfill ─────────────
    # Download zoning district polygons from the GIS endpoint (if configured),
    # ingest them into zoning_districts, then spatial-join to set zone_code on
    # every parcel.
    zoning_count = 0
    zoning_endpoint = cfg.zoning_polygon_endpoint
    if zoning_endpoint:
        from app.models.zoning_district import ZoningDistrict as _ZD
        _zd_count = await db.scalar(
            select(func.count(_ZD.id)).where(_ZD.jurisdiction_id == jurisdiction.id)
        )
        _unzoned = await db.scalar(
            select(func.count(Parcel.id)).where(
                Parcel.jurisdiction_id == jurisdiction.id,
                or_(Parcel.zoning_code.is_(None), Parcel.zoning_code == ""),
            )
        )
        # Skip the ArcGIS download if districts are already cached — even if some
        # parcels are still unzoned (backfill runs separately below regardless).
        _skip_zd_download = (_zd_count or 0) > 0
        logger.info(
            "Zoning districts cache check: cached=%d unzoned=%d skip_download=%s",
            _zd_count or 0, _unzoned or 0, _skip_zd_download,
        )
    if zoning_endpoint and not _skip_zd_download:
        zoning_started = _stage_started(job, "zoning_fetch", endpoint=zoning_endpoint)
        zoning_fetch_step = await start_job_step(
            db,
            job,
            "download_zoning",
            {"endpoint": zoning_endpoint},
        )
        await _set_status(
            db, job, JobStatus.downloading_zoning,
            progress={"zoning_endpoint": zoning_endpoint},
        )
        await db.commit()
        await check_cancelled(db, job)
        try:
            logger.info("Downloading zoning districts from %s", zoning_endpoint)
            async with asyncio.timeout(ZONING_TIMEOUT_SECONDS):
                zgdf = await download_all_features(
                    zoning_endpoint,
                    where=cfg.zoning_where_clause or "1=1",
            )
            _stage_completed(job, "zoning_fetch", zoning_started, feature_count=len(zgdf))
            await complete_job_step(db, zoning_fetch_step, {"feature_count": len(zgdf)})
            await add_job_artifact(
                db,
                job,
                "download_zoning",
                "zoning_download_metadata",
                {"feature_count": len(zgdf), "endpoint": zoning_endpoint},
            )

            zoning_ingest_started = _stage_started(job, "zoning_ingest", feature_count=len(zgdf))
            zoning_ingest_step = await start_job_step(
                db,
                job,
                "ingest_zoning",
                {"feature_count": len(zgdf)},
            )
            async with asyncio.timeout(ZONING_TIMEOUT_SECONDS):
                zoning_count = await ingest_zoning_districts(zgdf, jurisdiction.id, db)
            await db.commit()
            _stage_completed(job, "zoning_ingest", zoning_ingest_started, districts_ingested=zoning_count)
            await complete_job_step(db, zoning_ingest_step, {"districts_ingested": zoning_count})
            await add_job_artifact(
                db,
                job,
                "ingest_zoning",
                "zoning_ingest_metadata",
                {"districts_ingested": zoning_count},
            )

            zoning_backfill_started = _stage_started(job, "zoning_backfill", jurisdiction_id=str(jurisdiction.id))
            zoning_backfill_step = await start_job_step(
                db,
                job,
                "backfill_zoning",
                {"jurisdiction_id": str(jurisdiction.id)},
            )
            updated = await backfill_parcel_zoning_from_districts(jurisdiction.id, db)
            logger.info("zone_class backfill updated %d parcels", updated)
            await db.commit()
            _stage_completed(job, "zoning_backfill", zoning_backfill_started, parcels_updated=updated)
            await complete_job_step(db, zoning_backfill_step, {"parcels_updated": updated})

            logger.info("Zoning district backfill complete — skipping zoning_overlays (not used by API)")
        except Exception as exc:
            _stage_failed(job, "zoning", zoning_started, exc)
            logger.warning("Zoning ingest failed (non-fatal): %s", exc)
            try:
                async with asyncio.timeout(5):
                    await db.rollback()
            except Exception:
                pass
            zoning_fetch_step = await db.merge(zoning_fetch_step)
            await fail_job_step(db, zoning_fetch_step, exc, status="warning")
            await db.commit()

    # Cache-hit path: districts exist but some parcels may still be unzoned
    if zoning_endpoint and _skip_zd_download and (_unzoned or 0) > 0:
        logger.info("Zoning districts cached but %d unzoned parcels remain — running backfill only", _unzoned)
        try:
            cached_backfill = await backfill_parcel_zoning_from_districts(jurisdiction.id, db)
            await db.commit()
            logger.info("Cached-hit backfill: %d parcels updated", cached_backfill)
        except Exception as exc:
            logger.warning("Cached-hit backfill failed (non-fatal): %s", exc)
            try:
                async with asyncio.timeout(5):
                    await db.rollback()
            except Exception:
                pass
            # After rollback, ORM attributes on previously-loaded rows are
            # expired. The very next stage call site reads `jurisdiction.id`
            # synchronously when building log args, which would emit an
            # implicit SELECT and crash with MissingGreenlet inside this
            # Dramatiq worker. Refresh the two ORM objects we still need
            # downstream so their attributes are fresh and synchronous reads
            # are pure cache hits.
            try:
                async with asyncio.timeout(5):
                    await db.refresh(job)
                    await db.refresh(jurisdiction)
            except Exception:
                pass

    matrix_started = _stage_started(job, "zone_matrix_bootstrap", jurisdiction_id=str(jurisdiction.id))
    async with asyncio.timeout(30):
        seeded_matrix = await bootstrap_zone_use_matrix(
            jurisdiction.id,
            db,
            missing_only=True,
        )
    if seeded_matrix:
        logger.info("Bootstrapped %d zone_use_matrix rows", seeded_matrix)
        await db.commit()
    _stage_completed(job, "zone_matrix_bootstrap", matrix_started, rows_seeded=seeded_matrix)

    coverage_started = _stage_started(job, "coverage_refresh", jurisdiction_id=str(jurisdiction.id))
    async with asyncio.timeout(30):
        await refresh_jurisdiction_coverage_level(jurisdiction, db)
    await db.flush()
    _stage_completed(job, "coverage_refresh", coverage_started, coverage_level=jurisdiction.coverage_level.value)

    # ── Step 3b: apply overlays (flood + wetland, non-fatal) ─────────────
    enrichment_started = _stage_started(job, "enrichment")
    enrichment_step = await start_job_step(db, job, "run_overlays")
    await _set_status(db, job, JobStatus.running_overlays)
    await db.commit()
    await check_cancelled(db, job)
    try:
        from app.services.overlays import apply_flood_overlay, apply_wetland_overlay
        overlay_started = _stage_started(job, "overlays", jurisdiction_id=str(jurisdiction.id))
        async with asyncio.timeout(ENRICHMENT_TIMEOUT_SECONDS):
            flood_count, wetland_count = await asyncio.gather(
                apply_flood_overlay(jurisdiction.id, db),
                apply_wetland_overlay(jurisdiction.id, db),
            )
        _stage_completed(job, "overlays", overlay_started, flood=flood_count, wetland=wetland_count)
        await db.commit()
        logger.info(
            "Overlays: %d flood parcels, %d wetland parcels", flood_count, wetland_count
        )
        _stage_completed(
            job,
            "enrichment",
            enrichment_started,
            flood_parcels=flood_count,
            wetland_parcels=wetland_count,
        )
        await complete_job_step(
            db,
            enrichment_step,
            {"flood_parcels": flood_count, "wetland_parcels": wetland_count},
        )
        await add_job_artifact(
            db,
            job,
            "run_overlays",
            "overlay_metadata",
            {"flood_parcels": flood_count, "wetland_parcels": wetland_count},
        )
    except Exception as exc:
        _stage_failed(job, "enrichment", enrichment_started, exc)
        logger.warning("Overlay step failed (non-fatal): %s", exc)
        await db.rollback()
        enrichment_step = await db.merge(enrichment_step)
        await fail_job_step(db, enrichment_step, exc, status="warning")
        await db.commit()

    # ── Step 4: parse ordinance (optional — non-fatal if it fails) ───────
    ordinance_discovery_started = _stage_started(job, "ordinance_source")
    # Only use an explicitly-provided ordinance URL. Auto-discovery via Playwright
    # spikes memory (headless Chromium) and crashes the worker container on Railway.
    ordinance_url = job.ordinance_url or cfg.ordinance_url
    _stage_completed(
        job,
        "ordinance_source",
        ordinance_discovery_started,
        ordinance_url=ordinance_url,
    )
    if ordinance_url:
        ordinance_started = _stage_started(job, "ordinance_parse", ordinance_url=ordinance_url)
        ordinance_step = await start_job_step(
            db,
            job,
            "parse_ordinance",
            {"ordinance_url": ordinance_url},
        )
        await _set_status(db, job, JobStatus.parsing_ordinance)
        await db.commit()
        await check_cancelled(db, job)
        try:
            async with asyncio.timeout(ORDINANCE_TIMEOUT_SECONDS):
                await _parse_and_save_ordinance(db, jurisdiction, ordinance_url)
            _stage_completed(job, "ordinance_parse", ordinance_started)
            await complete_job_step(db, ordinance_step, {"ordinance_url": ordinance_url})
            await add_job_artifact(
                db,
                job,
                "parse_ordinance",
                "ordinance_parse_metadata",
                {"ordinance_url": ordinance_url},
            )
        except Exception as exc:
            _stage_failed(job, "ordinance_parse", ordinance_started, exc)
            logger.warning(
                "Ordinance parsing failed (non-fatal) for job %s: %s",
                _safe_job_id(job),
                exc,
            )
            await db.rollback()
            # Refresh ORM objects after rollback so the next stage's
            # synchronous attribute reads don't trigger MissingGreenlet.
            try:
                await db.refresh(job)
                await db.refresh(jurisdiction)
            except Exception:
                pass
            ordinance_step = await db.merge(ordinance_step)
            await fail_job_step(db, ordinance_step, exc, status="warning")
            await db.commit()
            # Non-fatal — job continues to ready state

    # ── Step 5: mark ready ────────────────────────────────────────────────
    feasibility_started = _stage_started(job, "feasibility_complete", jurisdiction_id=str(jurisdiction.id))
    feasibility_step = await start_job_step(
        db,
        job,
        "complete_feasibility",
        {"jurisdiction_id": str(jurisdiction.id)},
    )
    await _set_status(
        db, job, JobStatus.ready,
        progress={
            "parcels_ingested": count,
            "jurisdiction_id": str(jurisdiction.id),
        },
    )
    job.finished_at = now_utc()
    job.locked_by = None
    job.locked_at = None
    await db.commit()
    _stage_completed(job, "feasibility_complete", feasibility_started, status=JobStatus.ready.value)
    await complete_job_step(db, feasibility_step, {"status": JobStatus.ready.value})
    await db.commit()
    logger.info(
        "Job %s complete — %d parcels for %s", _safe_job_id(job), count, cfg.name
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
