"""
Job pipeline service.

Orchestrates the full data-collection workflow for a search job:
  1. Resolve the jurisdiction (create row if needed)
  2. Discover / validate FeatureServer endpoints
  3. Download parcels from ArcGIS
  4. Ingest into PostGIS
  5. Parse ordinance → zone_use_matrix
  6. Apply overlays (flood / slope / wetland)

Phase 5: live ArcGIS layer discovery via Hub search + Web Map parsing.
Known jurisdictions remain as a fast-path cache to avoid network calls.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import socket
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg

from sqlalchemy import func, literal_column, or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select as sa_select

from app.config import settings
from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.job_step import JobStep
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
from app.services.buybox_scoring import auto_score_jurisdiction
from app.services.matrix_bootstrap import bootstrap_zone_use_matrix
from app.services.spatial_backfill import (
    backfill_parcel_zoning_from_districts,
    refresh_jurisdiction_bbox,
    refresh_jurisdiction_coverage_level,
)
from app.services.zoning_ingestion import ingest_zoning_districts
from app.services.zoning_system import bulk_ingest_zoning_for_jurisdiction, enqueue_missing_zoning_for_jurisdiction

logger = logging.getLogger(__name__)

PARCEL_FETCH_TIMEOUT_SECONDS = 1800
PARCEL_INGEST_TIMEOUT_SECONDS = 1800
ZONING_TIMEOUT_SECONDS = 1800
ENRICHMENT_TIMEOUT_SECONDS = 240
ORDINANCE_TIMEOUT_SECONDS = 240
MAX_JOB_ERROR_LENGTH = 4000


async def _step_completed(db: AsyncSession, job: Job, step_name: str) -> bool:
    """Return True if this job already has a completed step with the given name."""
    result = await db.execute(
        select(JobStep).where(
            JobStep.job_id == job.__dict__.get("id"),
            JobStep.step == step_name,
            JobStep.status == "completed",
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


def _raw_asyncpg_url() -> str:
    """Strip the SQLAlchemy driver tag to get a plain asyncpg-compatible URL."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _progress_commit(job_id: uuid.UUID, progress: dict) -> None:
    """Write job.progress via a raw asyncpg connection that shares no state
    with the in-flight SQLAlchemy session.

    async_session_maker() still routes through the shared engine. Even with
    NullPool the engine's greenlet coordinator can re-enter the ingest
    transaction's greenlet context, raising MissingGreenlet. asyncpg.connect()
    opens a brand-new TCP socket — SQLAlchemy is not involved at all.

    statement_cache_size=0 is required because Supabase routes us through
    pgbouncer in transaction mode, which leaks prepared statements across
    asyncpg client connections.

    Best-effort by design: progress writes are telemetry and must not bring
    down the pipeline. Supabase's pgbouncer occasionally drops the underlying
    server conn between asyncpg.connect() and the first execute, surfacing
    as ConnectionDoesNotExistError. Losing one progress update is harmless;
    losing a 6-minute MapPLUTO download is not.
    """
    try:
        conn = await asyncpg.connect(_raw_asyncpg_url(), statement_cache_size=0)
    except Exception as exc:
        logger.warning("progress_commit connect failed (non-fatal): %r", exc)
        return
    try:
        await conn.execute("SET statement_timeout = 0")
        await conn.execute(
            "UPDATE jobs SET progress = $1::jsonb WHERE id = $2::uuid",
            _json.dumps(progress),
            str(job_id),
        )
    except Exception as exc:
        logger.warning("progress_commit write failed (non-fatal): %r", exc)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


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
    import traceback
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    message = tb if tb else str(exc)
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
    # Stamp a fixed municipality onto every ingested parcel when the source
    # parcel layer has no city/muni-NAME field (e.g. PA county assessor layers
    # that expose only an integer MUNI code). Pair with a muni-scoped
    # where_clause so all pulled parcels belong to that one muni. Catch #33.
    city_override: str | None = None


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


# ── NY county-level parcel services published via NYS ITS Geospatial Services
#    + Nassau County's separately-hosted feed (Nassau hasn't authorized inclusion
#    in the public NYS_Tax_Parcels_Public layer). Each layer is a single-county
#    polygon set, so no COUNTY filter is needed.
_NY_WESTCHESTER_PARCELS = (
    "https://services6.arcgis.com/EbVsqZ18sv1kVJ3k/arcgis/rest"
    "/services/Westchester_County_Parcels/FeatureServer/0"
)
_NY_NASSAU_PARCELS = (
    "https://services6.arcgis.com/a523XM128lX5Nsff/arcgis/rest"
    "/services/Nassau_parcels/FeatureServer/6"
)


def _ny_county(
    county_name: str,
    full_name: str,
    parcel_endpoint: str,
    where_clause: str | None = None,
    zoning_endpoint: str | None = None,
) -> JurisdictionConfig:
    """Build a NY-county-backed JurisdictionConfig from a county-specific
    FeatureServer (NYS ITS public service for Westchester, Nassau's own
    service for Nassau). NY parcels carry no zoning attribute — zoning is
    municipal, joined separately via zoning_polygon_endpoint when known."""
    return JurisdictionConfig(
        name=full_name,
        state="NY",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=parcel_endpoint,
        where_clause=where_clause,
        zoning_polygon_endpoint=zoning_endpoint,
    )


# ── CT statewide CAMA + Parcel Layer (CT OPM, hosted by CT GIS Office on
#    services3.arcgis.com/3FL1kr7L4LvwA2Kb). One layer covers all 169 CT towns;
#    Fairfield County is the historical 23-town list filtered via Town_Name IN.
#    CT abolished county-level government in 1960, so no COUNTY field exists.
_CT_STATEWIDE = (
    "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest"
    "/services/Connecticut_CAMA_and_Parcel_Layer_2024/FeatureServer/0"
)

# Fairfield County, CT — 23 towns. Source: CT Secretary of State + US Census
# historical county boundaries (county governance abolished 1960; planning
# regions replaced county functions in 2022).
_CT_FAIRFIELD_TOWNS: tuple[str, ...] = (
    "Bethel", "Bridgeport", "Brookfield", "Danbury", "Darien", "Easton",
    "Fairfield", "Greenwich", "Monroe", "New Canaan", "New Fairfield",
    "Newtown", "Norwalk", "Redding", "Ridgefield", "Shelton", "Sherman",
    "Stamford", "Stratford", "Trumbull", "Weston", "Westport", "Wilton",
)


def _ct(
    county_name: str,
    full_name: str,
    towns: tuple[str, ...],
    zoning_endpoint: str | None = None,
) -> JurisdictionConfig:
    """Build a CT-county JurisdictionConfig backed by the statewide CAMA layer.

    `towns` is the historical-county town list — CT zoning + assessor data is
    municipal, so the WHERE clause filters by Town_Name IN (...) instead of
    a (non-existent) county column.
    """
    quoted = ",".join(f"'{t}'" for t in towns)
    return JurisdictionConfig(
        name=full_name,
        state="CT",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=_CT_STATEWIDE,
        where_clause=f"Town_Name IN ({quoted})",
        zoning_polygon_endpoint=zoning_endpoint,
    )


# ── Virginia: Fairfax + Loudoun (Phase 3) ─────────────────────────────────
# VGIN's statewide composite is gated by a per-locality data-sharing agreement
# and many counties (incl. Fairfax) are absent. Each VA county we ingest uses
# its own AGOL/Server endpoint instead.
# Fairfax — boundary-only `Parcels/FeatureServer/0` (369K rows, 7 fields).
# The wider `Parcels_with_Address_points/FeatureServer/0` (391K, 50+ fields)
# returns 504 Gateway Timeout under bursty paginated load on its AGOL node;
# the boundary layer's leaner payload sits well under the timeout budget and
# still publishes PIN as the unique APN. Address backfill (if/when needed)
# can come from a separate spatial join against the address points layer.
_VA_FAIRFAX_PARCELS = (
    "https://services1.arcgis.com/ioennV6PpG5Xodq0/arcgis/rest"
    "/services/Parcels/FeatureServer/0"
)
_VA_FAIRFAX_ZONING = (
    "https://services1.arcgis.com/ioennV6PpG5Xodq0/arcgis/rest"
    "/services/Zoning/FeatureServer/0"
)
# Loudoun's authoritative parcel polygons live on the county-hosted ArcGIS
# Server (logis.loudoun.gov). The AGOL mirror lags by a few rows; the COL
# LandRecords MapServer/5 layer is what icare/inet pulls from internally.
_VA_LOUDOUN_PARCELS = (
    "https://logis.loudoun.gov/gis/rest/services/COL/LandRecords/MapServer/5"
)
_VA_LOUDOUN_ZONING = (
    "https://logis.loudoun.gov/gis/rest/services/COL/Zoning/MapServer/3"
)


def _va(
    county_name: str,
    full_name: str,
    parcel_endpoint: str,
    zoning_endpoint: str | None = None,
    where_clause: str | None = None,
) -> JurisdictionConfig:
    """Build a VA county-backed JurisdictionConfig.

    Each VA county publishes its own ArcGIS layer — no statewide composite
    covers Fairfax or Loudoun. Zoning is published as a separate spatial
    layer; the parcel layer carries no zoning code (Fairfax's Parcels_with_
    Address_points has only PIN + address; Loudoun's LandRecords/5 has only
    PA_MCPI + acres).
    """
    return JurisdictionConfig(
        name=full_name,
        state="VA",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=parcel_endpoint,
        where_clause=where_clause,
        zoning_polygon_endpoint=zoning_endpoint,
    )


# ── Maryland: MD iMAP statewide MD_ParcelBoundaries (Phase 3) ─────────────
# A single MapServer layer covers all 24 counties + Baltimore City. JURSCODE
# is the four-letter MDProperty View jurisdiction code (MONT, HOWA, BALT,
# BACO, AAC0…). ZONING + LU + DESCLU + ACRES + NFMIMPVL are inline; owner
# *name* is redacted statewide (~2017 policy) but mailing address remains.
_MD_STATEWIDE = (
    "https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre"
    "/MD_ParcelBoundaries/MapServer/0"
)


def _md(
    county_name: str,
    full_name: str,
    jurscode: str,
    zoning_endpoint: str | None = None,
) -> JurisdictionConfig:
    """Build an MD county-backed JurisdictionConfig from the statewide layer.

    `jurscode` is the four-letter MDProperty View county code (MONT, HOWA, …)
    used in the WHERE clause. Zoning is inline on the parcel layer, so
    `zoning_endpoint` defaults to None — pass an explicit per-county zoning
    polygon endpoint only when one exists separately and is more authoritative.
    """
    return JurisdictionConfig(
        name=full_name,
        state="MD",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=_MD_STATEWIDE,
        where_clause=f"JURSCODE='{jurscode}'",
        zoning_polygon_endpoint=zoning_endpoint,
    )


# ── Pennsylvania counties outside Philadelphia (Phase 3) ──────────────────
# PA has no statewide composite — each county hosts its own assessor service.
# Montgomery County PA's Parcels FeatureServer/10 publishes only TAXPIN +
# CALCACREAGE; address/owner/zoning/value are not on any public REST endpoint
# (the assessor exposes them only through propertyrecords.montcopa.org).
_PA_MONTGOMERY_PARCELS = (
    "https://gis.montcopa.org/arcgis/rest/services/Parcels"
    "/Montgomery_County_Parcels/FeatureServer/10"
)

# Chester County PA — countywide assessor parcels (194,341) in the county AGOL org.
# Layer carries `UPI` + integer `MUNI` (no city-NAME field) → needs city_override +
# a muni-scoped where_clause (catch #33). Tredyffrin Township = MUNI 43 (9,933 parcels).
_PA_CHESTER_PARCELS = (
    "https://services.arcgis.com/G4S1dGvn7PIgYd6Y/arcgis/rest/services"
    "/Parcels_owners/FeatureServer/0"
)
# Chester countywide zoning polygons; short code in `ZONE_ABBR` (e.g. PIP/LI/O),
# long name in `ZONE_DISTRICT`. `MUNI` matches the parcel layer's muni code.
_PA_CHESTER_ZONING = (
    "https://services.arcgis.com/G4S1dGvn7PIgYd6Y/arcgis/rest/services"
    "/Zoning_Edit_Working/FeatureServer/0"
)


def _pa_county(
    county_name: str,
    full_name: str,
    parcel_endpoint: str,
    zoning_endpoint: str | None = None,
    where_clause: str | None = None,
    zoning_where_clause: str | None = None,
    city_override: str | None = None,
) -> JurisdictionConfig:
    """Build a PA county-backed JurisdictionConfig (single-county FeatureServer).

    Distinct from the Philadelphia OPA / Allentown City_Landuse city services
    since these are county-wide assessor layers covering many municipalities.

    ``city_override`` + ``where_clause``/``zoning_where_clause`` support PA county
    assessor layers that expose only an integer MUNI code (no city-NAME field): a
    muni-scoped pull + a fixed city stamp keeps the per-muni model intact (catch #33).
    """
    return JurisdictionConfig(
        name=full_name,
        state="PA",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=parcel_endpoint,
        where_clause=where_clause,
        zoning_polygon_endpoint=zoning_endpoint,
        zoning_where_clause=zoning_where_clause,
        city_override=city_override,
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
    morris    = _nj("Morris",    "Morris County, NJ")
    hunterdon = _nj("Hunterdon", "Hunterdon County, NJ")
    # Counties with existing DB rows but no registry entry until now —
    # adding them here prevents future "Bergen County, NJ" / "Somerset
    # County, NJ" inputs from falling through to live-discovery (the
    # same path that miscoded Burlington → Ocean on 2026-05-20).
    bergen    = _nj("Bergen",    "Bergen County, NJ")
    somerset  = _nj("Somerset",  "Somerset County, NJ")
    # Ocean: jurisdiction row exists (id b26af20d-...) because a live-
    # discovery bug created it under the name "Burlington County, NJ".
    # Renamed in prod 2026-05-21 after APN inspection (PAMS_PIN '1501_*'
    # = Ocean county). Future "Ocean County, NJ" inputs now route to
    # the correct NJOGIS slice via the fast path.
    ocean     = _nj("Ocean",     "Ocean County, NJ")
    # Burlington is the original ask — adding it here so a fresh
    # "Burlington County, NJ" input routes to NJOGIS COUNTY='BURLINGTON'
    # instead of repeating the live-discovery → Ocean mistake.
    burlington = _nj("Burlington", "Burlington County, NJ")
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
        "morris county":          morris,
        "morris county, nj":      morris,
        "hunterdon county":       hunterdon,
        "hunterdon county, nj":   hunterdon,
        "flemington":             hunterdon,
        "flemington, nj":         hunterdon,
        "bergen county":          bergen,
        "bergen county, nj":      bergen,
        "somerset county":        somerset,
        "somerset county, nj":    somerset,
        "ocean county":           ocean,
        "ocean county, nj":       ocean,
        "burlington county":      burlington,
        "burlington county, nj":  burlington,
    }


# ── Virginia counties (Phase 3) ─────────────────────────────────────────────
# Each VA county publishes its own ArcGIS service; no statewide composite.
# Zoning lives on a separate spatial layer (parcel layer carries only PIN +
# address, with no zoning column).
_VA_FAIRFAX_PARCELS = (
    "https://services1.arcgis.com/ioennV6PpG5Xodq0/arcgis/rest"
    "/services/Parcels/FeatureServer/0"
)
_VA_FAIRFAX_ZONING = (
    "https://services1.arcgis.com/ioennV6PpG5Xodq0/arcgis/rest"
    "/services/Zoning/FeatureServer/0"
)
_VA_LOUDOUN_PARCELS = (
    "https://logis.loudoun.gov/gis/rest/services/COL/LandRecords/MapServer/5"
)
_VA_LOUDOUN_ZONING = (
    "https://logis.loudoun.gov/gis/rest/services/COL/Zoning/MapServer/3"
)


def _va(
    county_name: str,
    full_name: str,
    parcel_endpoint: str,
    zoning_endpoint: str | None = None,
    where_clause: str | None = None,
) -> JurisdictionConfig:
    """Build a VA county-backed JurisdictionConfig.

    Each VA county publishes its own ArcGIS layer — no statewide composite
    covers Fairfax or Loudoun. Zoning is published as a separate spatial
    layer; the parcel layer carries no zoning code (Fairfax's Parcels has
    only PIN + address; Loudoun's LandRecords/5 has only PA_MCPI + acres).
    """
    return JurisdictionConfig(
        name=full_name,
        state="VA",
        county=county_name,
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=parcel_endpoint,
        where_clause=where_clause,
        zoning_polygon_endpoint=zoning_endpoint,
    )


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
    # ── Salt Lake County as ONE jurisdiction ──────────────────────────────────
    # County-wide pull (no PARCEL_CITY filter); ingest maps PARCEL_CITY ->
    # parcels.city so the dashboard city filter drills into each city. This
    # supersedes the per-city SL County jurisdictions above — once it's
    # ingested + scored, retire those via scripts/retire_slco_city_jurisdictions.py
    # and re-key their zoning under municipality=<city>.
    "salt lake county": JurisdictionConfig(
        name="Salt Lake County, UT",
        state="UT",
        county="Salt Lake",
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_SaltLake/FeatureServer/0",
        where_clause=None,
    ),
    # ── Utah County as ONE jurisdiction (county-wide pull, like Salt Lake) ───
    # Brings every Utah County parcel under a single jurisdiction with
    # parcels.city populated per row from PARCEL_CITY. The 14 per-city
    # Utah County jurisdictions below act as crosswalk siblings for
    # zoning, so a fresh ingest auto-routes each parcel to its city's
    # zone matrix via the same pattern that worked for Salt Lake County.
    "utah county": JurisdictionConfig(
        name="Utah County, UT",
        state="UT",
        county="Utah",
        parcel_source=ParcelSource.county_gis,
        parcel_endpoint=f"{_UGRC}/Parcels_Utah/FeatureServer/0",
        where_clause=None,
    ),
    # ── Utah County (Parcels_Utah) — per-city sibling jurisdictions ──────────
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
    "cedar hills":   _ugrc("Parcels_Utah", "Cedar Hills",   "Cedar Hills, UT",   "Utah"),
    "highland":      _ugrc("Parcels_Utah", "Highland",      "Highland, UT",      "Utah"),
    "alpine":        _ugrc("Parcels_Utah", "Alpine",        "Alpine, UT",        "Utah"),
    "saratoga springs": _ugrc("Parcels_Utah", "Saratoga Springs", "Saratoga Springs, UT", "Utah"),
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

    # ── NY-adjacent counties (Phase 2) ────────────────────────────────────────
    # Westchester: NYS ITS public service (2024 assessment roll, ~258K parcels).
    # Nassau: county-hosted (services6.arcgis.com/a523XM128lX5Nsff, June 2021
    #   publication of 2020 assessment roll, ~420K parcels) — Nassau has not
    #   authorized inclusion in NYS_Tax_Parcels_Public, so this is the only
    #   public FeatureServer covering it.
    # Both layers share the NYS GPO schema (PRINT_KEY/PARCEL_ADDR/PRIMARY_OWNER),
    # but Nassau's column names are FileGDB-truncated to 10 chars (PARCEL_ADD,
    # PRIMARY_OW). The ingestion field-candidate lists handle both spellings.
    "westchester county": _ny_county("Westchester", "Westchester County, NY", _NY_WESTCHESTER_PARCELS),
    "westchester county, ny": _ny_county("Westchester", "Westchester County, NY", _NY_WESTCHESTER_PARCELS),
    "nassau county": _ny_county("Nassau", "Nassau County, NY", _NY_NASSAU_PARCELS),
    "nassau county, ny": _ny_county("Nassau", "Nassau County, NY", _NY_NASSAU_PARCELS),

    # ── Connecticut (Phase 2) ─────────────────────────────────────────────────
    # Fairfield County, CT — backed by CT statewide CAMA + Parcel Layer 2024.
    # Filtered by Town_Name IN (23-town list) since CT has no county column.
    # Zoning is per-municipality and not a single statewide layer; left None
    # for now, to be filled in case-by-case via spatial-join layers later.
    "fairfield county": _ct("Fairfield", "Fairfield County, CT", _CT_FAIRFIELD_TOWNS),
    "fairfield county, ct": _ct("Fairfield", "Fairfield County, CT", _CT_FAIRFIELD_TOWNS),

    # ── New Jersey counties ───────────────────────────────────────────────────
    # Source: NJOGIS Parcels_Composite_NJ_WM — MOD-IV statewide composite.
    # Filtered per county via COUNTY='<NAME>' (uppercase full county name).
    # Note: OWNER_NAME is redacted in this service per NJ Daniel's Law.
    # Zoning is municipal-level; Hudson uses Jersey City land use layer,
    # Essex uses Newark zoning layer as best available coverage.
    **{k: v for k, v in _build_nj_jurisdictions().items()},

    # ── Virginia counties (Phase 3) ──────────────────────────────────────────
    # Cherry-picked from orphan branch claude/agitated-khayyam-58c0d9 commit
    # e184052. Without these explicit entries, live discovery in main routed
    # Fairfax to a wrong (empty) zoning service id.
    "fairfax county":      _va("Fairfax", "Fairfax County, VA", _VA_FAIRFAX_PARCELS, _VA_FAIRFAX_ZONING),
    "fairfax county, va":  _va("Fairfax", "Fairfax County, VA", _VA_FAIRFAX_PARCELS, _VA_FAIRFAX_ZONING),
    "loudoun county":      _va("Loudoun", "Loudoun County, VA", _VA_LOUDOUN_PARCELS, _VA_LOUDOUN_ZONING),
    "loudoun county, va":  _va("Loudoun", "Loudoun County, VA", _VA_LOUDOUN_PARCELS, _VA_LOUDOUN_ZONING),

    # ── Maryland (Phase 3) ────────────────────────────────────────────────────
    # MD iMAP MD_ParcelBoundaries — single MapServer layer, JURSCODE-filtered.
    # Zoning is inline (ZONING field) so no separate zoning_polygon_endpoint
    # is needed for parcel-level ingestion. NFMIMPVL provides improvement
    # value; ACRES is the assessor-published lot acreage.
    # Owner name is redacted statewide (MDProperty View public-feed policy);
    # OWNADD1/OWNCITY/OWNSTATE remain as mailing address.
    "montgomery county, md": _md("Montgomery", "Montgomery County, MD", "MONT"),
    "howard county":         _md("Howard",     "Howard County, MD",     "HOWA"),
    "howard county, md":     _md("Howard",     "Howard County, MD",     "HOWA"),

    # ── Pennsylvania (Phase 3) ────────────────────────────────────────────────
    # Montgomery County PA — county-hosted Parcels FeatureServer/10. Note
    # there is *no* PA statewide composite; PASDA only mirrors per-county
    # uploads. Owner/address/zoning/value are not on this REST endpoint.
    "montgomery county, pa": _pa_county("Montgomery", "Montgomery County, PA", _PA_MONTGOMERY_PARCELS),
    # Chester County PA — registered Tredyffrin-SCOPED (MUNI=43) for the Main Line
    # validation anchor: the parcel layer has no city-NAME field, so city_override
    # stamps 'Tredyffrin Township' and where_clause/zoning_where_clause limit the
    # pull to that one muni (catch #33). Scale to all 73 munis later via a
    # MUNI→name crosswalk. Both keys route to the same scoped config.
    "chester county, pa": _pa_county(
        "Chester", "Chester County, PA", _PA_CHESTER_PARCELS,
        zoning_endpoint=_PA_CHESTER_ZONING,
        where_clause="MUNI=43",
        zoning_where_clause="MUNI=43",
        city_override="Tredyffrin Township",
    ),
    "tredyffrin township, pa": _pa_county(
        "Chester", "Chester County, PA", _PA_CHESTER_PARCELS,
        zoning_endpoint=_PA_CHESTER_ZONING,
        where_clause="MUNI=43",
        zoning_where_clause="MUNI=43",
        city_override="Tredyffrin Township",
    ),
}


def _match_jurisdiction(input_str: str) -> JurisdictionConfig | None:
    """Check hard-coded registry first (fast path, no network)."""
    normalized = input_str.lower().strip()
    for key, cfg in KNOWN_JURISDICTIONS.items():
        if key in normalized or cfg.name.lower() in normalized:
            return cfg
    return None


async def _match_jurisdiction_db(
    db: AsyncSession, input_str: str
) -> JurisdictionConfig | None:
    """Look up an existing jurisdiction row by name (case-insensitive)
    before falling through to live-discovery.

    Prevents the duplicate-creation pattern where a casing variant of an
    already-loaded county ("Morris COunty, NJ") triggers ArcGIS Hub
    discovery, which then geocodes the wrong Morris (state='NE') and
    inserts a phantom 0-parcel row.

    Strategy: exact ILIKE first, then prefix/contains, filtered by a
    state hint parsed from the input if one is present. Returns a
    JurisdictionConfig synthesized from the DB row so the rest of the
    pipeline (line ~822 SELECT WHERE name = cfg.name) resolves to the
    same row.
    """
    raw = (input_str or "").strip()
    if not raw:
        return None
    state_hint = _parse_state(raw)
    # Strip trailing ", XX" or ", State Name" so the name match doesn't
    # require the user to include the state suffix.
    name_query = re.sub(r",\s*[A-Za-z. ]+$", "", raw).strip() or raw

    stmt = text(
        """
        SELECT name, state, county, parcel_source, parcel_endpoint, zoning_endpoint
        FROM jurisdictions
        WHERE (name ILIKE :exact OR name ILIKE :contains)
          AND (:state_hint = '' OR state ILIKE :state_hint)
        ORDER BY
          CASE WHEN name ILIKE :exact THEN 0 ELSE 1 END,
          CASE WHEN state ILIKE :state_hint THEN 0 ELSE 1 END,
          last_indexed_at DESC NULLS LAST
        LIMIT 1
        """
    )
    result = await db.execute(
        stmt,
        {
            "exact": raw,
            "contains": f"%{name_query}%",
            "state_hint": state_hint or "",
        },
    )
    row = result.first()
    if row is None:
        return None
    try:
        source = ParcelSource(row.parcel_source) if row.parcel_source else ParcelSource.county_gis
    except ValueError:
        source = ParcelSource.county_gis
    logger.info(
        "Jurisdiction DB-lookup matched %r → %s (state=%s)",
        input_str, row.name, row.state,
    )
    return JurisdictionConfig(
        name=row.name,
        state=row.state or "",
        county=row.county or "",
        parcel_source=source,
        parcel_endpoint=row.parcel_endpoint or "",
        zoning_endpoint=row.zoning_endpoint,
    )


# ─── Status helpers ──────────────────────────────────────────────────────────

async def _set_status(
    db: AsyncSession,
    job: Job,
    status: JobStatus,
    progress: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Update job status/progress/error.

    Tries SQLAlchemy first; on ConnectionDoesNotExistError (Supabase pgbouncer
    silently drops the underlying server conn during long operations like a
    6-minute MapPLUTO download), invalidates the session and falls back to a
    raw asyncpg UPDATE so the pipeline can continue. The in-memory `job` ORM
    state is always updated regardless — only the DB write may take the
    fallback path.
    """
    job.status = status
    if progress:
        job.progress = {**(job.progress or {}), **progress}
    if error:
        job.error_message = error
    try:
        await db.flush()
    except Exception as exc:
        if "connection was closed in the middle of operation" in str(exc) \
                or "ConnectionDoesNotExist" in type(exc).__name__:
            logger.warning(
                "_set_status flush hit dead conn (Supabase pgbouncer drop) — "
                "falling back to raw asyncpg: %r", exc,
            )
            try:
                await db.rollback()
            except Exception:
                pass
            await _raw_status_update(
                _safe_job_id(job),
                status.value if hasattr(status, "value") else str(status),
                job.progress,
                job.error_message,
            )
        else:
            raise


async def _raw_status_update(
    job_id: Any,
    status: str,
    progress: dict | None,
    error: str | None,
) -> None:
    """Raw-asyncpg fallback for _set_status. Best-effort — swallows errors so
    a transient pooler glitch doesn't kill the whole pipeline."""
    try:
        conn = await asyncpg.connect(_raw_asyncpg_url(), statement_cache_size=0)
    except Exception as exc:
        logger.warning("raw_status_update connect failed (non-fatal): %r", exc)
        return
    try:
        await conn.execute("SET statement_timeout = 0")
        await conn.execute(
            "UPDATE jobs SET status = $1, progress = $2::jsonb, error_message = $3, updated_at = now() WHERE id = $4::uuid",
            status,
            _json.dumps(progress) if progress is not None else None,
            error,
            str(job_id),
        )
    except Exception as exc:
        logger.warning("raw_status_update write failed (non-fatal): %r", exc)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


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
        # DB lookup before live-discovery: an already-loaded jurisdiction
        # should resolve to its existing row even if not in the hard-coded
        # registry, so a casing variant doesn't trigger ArcGIS Hub
        # discovery and create a phantom duplicate.
        cfg = await _match_jurisdiction_db(db, job.jurisdiction_input or "")
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

    force_refresh = bool(getattr(job, "force", False))
    existing_count = 0
    if force_refresh:
        logger.info(
            "Forced job for jurisdiction %s — skipping parcel cache preflight count",
            jurisdiction.id,
        )
    else:
        existing_count = await db.scalar(
            select(func.count(Parcel.id)).where(Parcel.jurisdiction_id == jurisdiction.id)
        )
    # Skip download+ingest if this jurisdiction already has substantial parcel data.
    # Counting parcels directly is more reliable than checking job_steps state,
    # which can be inconsistent across retries/cancellations.
    # > 1000 threshold rules out empty or barely-started jurisdictions.
    # job.force bypasses the cache so a fresh download repopulates parcels.raw
    # (and via the inline mapper, assessed_value + is_residential).
    parcels_cached = (existing_count or 0) > 1000 and not force_refresh

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

        _job_id: uuid.UUID = job.__dict__["id"]

        async def _progress(downloaded: int, total: int) -> None:
            downloaded_count[0] = downloaded
            total_count[0] = total
            new_progress = {
                **(job.progress or {}),
                "parcels_downloaded": downloaded,
                "parcels_total": total,
            }
            # Do NOT mutate `job.progress` on the SQLAlchemy session entity
            # here. The download can take many minutes (NYC MapPLUTO ~6.6 min),
            # during which Supabase will silently kill the session's TCP
            # connection. Mutating `job.progress` makes the session dirty;
            # the next `db.flush()` after the download (in complete_job_step)
            # then tries to push the change against a dead conn and the whole
            # job fails with ConnectionDoesNotExistError. Write progress only
            # via the raw-asyncpg `_progress_commit` (a fresh socket each
            # call); the next _set_status will overwrite job.progress in the
            # session with the final counts via its own raw-asyncpg fallback.
            if downloaded % 500 == 0:
                await _progress_commit(_job_id, new_progress)

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

        # The session's underlying TCP connection may have been silently
        # killed during the multi-minute download (Supabase pgbouncer idle
        # timeout, or an intermediate proxy reset). Without intervention, the
        # next SQLAlchemy op blocks forever waiting on a dead socket — there
        # are no upstream signals to surface this as an error.
        # `session.close()` releases the dead conn back to NullPool which
        # discards it; the next op opens a fresh socket. Wrapped in
        # asyncio.timeout(5) so even the close call can't hang the worker
        # if the socket really is wedged.
        try:
            async with asyncio.timeout(5):
                await db.close()
        except Exception as exc:
            logger.warning("post-download session.close() failed (non-fatal): %r", exc)
        # Re-attach the in-memory job/jurisdiction to the fresh session so
        # downstream code can read job.id / jurisdiction.id without
        # triggering a lazy-load that would deadlock again.
        try:
            async with asyncio.timeout(10):
                job = await db.merge(job)
                jurisdiction = await db.merge(jurisdiction)
                parcel_fetch_step = await db.merge(parcel_fetch_step)
        except Exception as exc:
            logger.warning("post-download merge failed (will best-effort continue): %r", exc)

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
            new_progress = {
                **(job.progress or {}),
                "ingest_phase": phase,
                progress_key: completed,
                "parcels_total": total,
            }
            # Same caveat as _progress above — do NOT mutate the session
            # entity from inside a long-running ingest progress callback.
            if completed % 2000 == 0 or completed == total:
                await _progress_commit(_job_id, new_progress)

        count = await ingest_parcels(
            gdf,
            jurisdiction.id,
            db,
            progress_callback=_ingest_progress,
            city_override=cfg.city_override,
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

    # Update last_indexed_at + compute bbox from ingested parcels.
    # The close+merge pattern (PR #72) wasn't enough — Wake NC still failed
    # at refresh_jurisdiction_bbox because the long parcel-merge phase had
    # left the SQLAlchemy session in an unrecoverable state. Use a fresh
    # session for the bbox refresh; re-load jurisdiction into the main
    # session afterward.
    bbox_started = _stage_started(job, "parcel_bbox_refresh", jurisdiction_id=str(jurisdiction.id))
    try:
        async with asyncio.timeout(120):
            async with async_session_maker() as bbox_db:
                fresh_jur = await bbox_db.get(Jurisdiction, jurisdiction.id)
                if fresh_jur is not None:
                    fresh_jur.last_indexed_at = datetime.now(timezone.utc)
                    await refresh_jurisdiction_bbox(fresh_jur, bbox_db)
                    await bbox_db.commit()
                    # Pull the freshly-computed bbox + timestamp back into the
                    # ORM object the rest of the pipeline holds.
                    jurisdiction.last_indexed_at = fresh_jur.last_indexed_at
                    jurisdiction.bbox = fresh_jur.bbox
    except Exception as exc:
        logger.warning("bbox refresh failed (non-fatal); continuing: %r", exc)
    _stage_completed(job, "parcel_bbox_refresh", bbox_started, bbox=jurisdiction.bbox)

    # Pre-warm census tracts so the first parcel-drawer click in this new
    # jurisdiction doesn't pay the 10-30s TIGER+ACS lazy-fetch latency.
    # Non-fatal: ingest must succeed even if the Census API is unreachable.
    if jurisdiction.bbox and len(jurisdiction.bbox) == 4:
        census_started = _stage_started(
            job, "census_tracts_precompute", jurisdiction_id=str(jurisdiction.id)
        )
        try:
            from app.services.census import ensure_census_tracts
            bbox_tuple = (
                float(jurisdiction.bbox[0]),
                float(jurisdiction.bbox[1]),
                float(jurisdiction.bbox[2]),
                float(jurisdiction.bbox[3]),
            )
            async with asyncio.timeout(180):
                tract_count = await ensure_census_tracts(bbox_tuple, db)
            await db.commit()
            _stage_completed(
                job, "census_tracts_precompute", census_started, tract_count=tract_count
            )
        except Exception as exc:
            logger.warning(
                "census_tracts_precompute failed (non-fatal) for %s: %s",
                jurisdiction.id, exc,
            )
            try:
                await db.rollback()
            except Exception:
                pass

    # Fire-and-forget ring-metrics precompute. Runs in a separate Dramatiq
    # worker so the pipeline doesn't block the next ~5-10 min populating
    # parcel_ring_metrics. By the time the operator opens the dashboard,
    # the cache is warm and `loadServerRingMetrics()` returns the entire
    # jurisdiction in one call — no client-side Mapbox+Census loop.
    # Non-fatal: if Mapbox is down or the actor errors, the dashboard just
    # falls back to the original client-side compute (slow but working).
    try:
        from app.services.job_queue import enqueue_ring_metrics_precompute
        enqueue_ring_metrics_precompute(jurisdiction.id)
        logger.info(
            "ring_metrics_precompute: enqueued for jurisdiction %s",
            jurisdiction.id,
        )
    except Exception as exc:
        logger.warning(
            "ring_metrics_precompute enqueue failed (non-fatal) for %s: %s",
            jurisdiction.id, exc,
        )

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

            # Populate zoning_overlays so per-parcel scoring + frontend
            # storage_permission look-ups have an authoritative ZoningRule.
            # bulk_ingest_zoning_for_jurisdiction is bounded by its own
            # internal raw-asyncpg connection (commit 9c59baa) so this
            # can't hang the pipeline. The earlier comment claiming
            # zoning_overlays was "not used by API" was wrong — the
            # buybox scorer + the frontend filter panel both read it.
            zoning_overlays_started = _stage_started(
                job, "zoning_overlays_bulk", jurisdiction_id=str(jurisdiction.id)
            )
            try:
                overlays_inserted = await bulk_ingest_zoning_for_jurisdiction(
                    jurisdiction.id, db
                )
                await db.commit()
                _stage_completed(
                    job,
                    "zoning_overlays_bulk",
                    zoning_overlays_started,
                    overlays_inserted=overlays_inserted,
                )
            except Exception as exc:
                logger.warning("bulk_ingest_zoning_for_jurisdiction failed (non-fatal): %s", exc)
                try:
                    async with asyncio.timeout(5):
                        await db.rollback()
                        await db.refresh(job)
                        await db.refresh(jurisdiction)
                except Exception:
                    pass
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
            # Rollback expired job and jurisdiction — refresh so downstream
            # attribute access doesn't trigger a sync lazy-load (MissingGreenlet).
            try:
                async with asyncio.timeout(5):
                    await db.refresh(job)
                    await db.refresh(jurisdiction)
            except Exception:
                pass

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

    # Cache-hit path: also populate zoning_overlays if missing. The earlier
    # pipeline silently skipped this step under the assumption "not used by
    # API" — that was wrong. The buybox scorer + frontend storage_permission
    # both read zoning_overlays, so a cached re-run that doesn't refresh them
    # leaves the jurisdiction with stale or zero overlay coverage. Run
    # unconditionally on every cache-hit; bulk_ingest_zoning_for_jurisdiction
    # has its own internal skip-check (zoning_system.py: returns early when
    # overlay_count >= 0.99 × zoned_count) so this is cheap when complete.
    if existing_count and existing_count > 0:
        cached_overlays_started = _stage_started(
            job, "cached_zoning_overlays", jurisdiction_id=str(jurisdiction.id)
        )
        try:
            cached_overlays_inserted = await bulk_ingest_zoning_for_jurisdiction(
                jurisdiction.id, db
            )
            await db.commit()
            _stage_completed(
                job,
                "cached_zoning_overlays",
                cached_overlays_started,
                overlays_inserted=cached_overlays_inserted,
            )
        except Exception as exc:
            logger.warning("Cached-hit bulk_ingest_zoning failed (non-fatal): %s", exc)
            try:
                async with asyncio.timeout(5):
                    await db.rollback()
                    await db.refresh(job)
                    await db.refresh(jurisdiction)
            except Exception:
                pass

    # ── County-only: pair municipality zoning to county parcels ──────────
    # A county-wide parcel ingest leaves most parcels.zoning_code NULL and
    # the county jurisdiction with no per-city zone_use_matrix rows, so the
    # buybox LATERAL join fires no verdict (Hot Deals / Worth a Look return
    # zero in SLCo). The sibling-zoning backfill + city→county crosswalk fix
    # this, but historically they were manual endpoints an operator had to
    # remember to hit. Run them here automatically, county-only, BEFORE the
    # matrix bootstrap so the bootstrap sees the freshly-paired codes.
    # Both are idempotent (NULL-only backfill + ON CONFLICT crosswalk).
    if jurisdiction.parcel_source == ParcelSource.county_gis:
        # Skip the (expensive) sibling backfill when no parcel is unzoned.
        unzoned_count = await db.scalar(
            text(
                "SELECT COUNT(*) FROM parcels "
                "WHERE jurisdiction_id = :jid AND zoning_code IS NULL"
            ).bindparams(jid=jurisdiction.id)
        )
        if unzoned_count and unzoned_count > 0:
            from app.services.sibling_backfill import (
                backfill_zoning_from_siblings,
                NotACountyError,
            )
            sibling_started = _stage_started(
                job, "sibling_zoning_backfill", jurisdiction_id=str(jurisdiction.id)
            )
            try:
                # APN match first, spatial pass on the residual. The spatial
                # join can run for minutes on a large county; a single
                # statement keeps the connection active (no idle drop).
                async with asyncio.timeout(1800):
                    sib_result = await backfill_zoning_from_siblings(
                        jurisdiction.id, db, strategy="both"
                    )
                await db.commit()
                _stage_completed(
                    job,
                    "sibling_zoning_backfill",
                    sibling_started,
                    rows_updated=sib_result.get("rows_updated", 0),
                    siblings_seen=sib_result.get("siblings_seen", 0),
                )
            except NotACountyError:
                pass
            except Exception as exc:
                logger.warning("sibling_zoning_backfill failed (non-fatal): %s", exc)
                try:
                    async with asyncio.timeout(5):
                        await db.rollback()
                        await db.refresh(job)
                        await db.refresh(jurisdiction)
                except Exception:
                    pass
                _stage_completed(
                    job,
                    "sibling_zoning_backfill",
                    sibling_started,
                    rows_updated=0,
                    backfill_error=type(exc).__name__,
                )

        # Crosswalk sibling city matrices into the county (tagged with the
        # parcel's verbatim city), seeding inherited_pending stubs for cities
        # that have parcels but no sibling matrix so they surface in the
        # verifier instead of silently scoring nothing.
        from app.services.zone_matrix_crosswalk import crosswalk_county_from_cities
        crosswalk_started = _stage_started(
            job, "crosswalk_cities", jurisdiction_id=str(jurisdiction.id)
        )
        try:
            async with asyncio.timeout(300):
                xwalk_result = await crosswalk_county_from_cities(
                    jurisdiction.id, db, seed_stubs=True
                )
            await db.commit()
            _stage_completed(
                job,
                "crosswalk_cities",
                crosswalk_started,
                rows_written=xwalk_result.get("rows_written", 0),
                siblings_seen=xwalk_result.get("siblings_seen", 0),
                unmatched_cities=len(xwalk_result.get("unmatched_cities", [])),
            )
        except Exception as exc:
            logger.warning("crosswalk_cities failed (non-fatal): %s", exc)
            try:
                async with asyncio.timeout(5):
                    await db.rollback()
                    await db.refresh(job)
                    await db.refresh(jurisdiction)
            except Exception:
                pass
            _stage_completed(
                job,
                "crosswalk_cities",
                crosswalk_started,
                rows_written=0,
                crosswalk_error=type(exc).__name__,
            )

    matrix_started = _stage_started(job, "zone_matrix_bootstrap", jurisdiction_id=str(jurisdiction.id))
    try:
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
    except Exception as exc:
        logger.warning("Zone-use matrix bootstrap failed (non-fatal): %s", exc)
        try:
            async with asyncio.timeout(5):
                await db.rollback()
                await db.refresh(job)
                await db.refresh(jurisdiction)
        except Exception:
            pass
        _stage_completed(
            job,
            "zone_matrix_bootstrap",
            matrix_started,
            rows_seeded=0,
            bootstrap_error=type(exc).__name__,
        )

    # `bulk_ingest_zoning_for_jurisdiction` (cached path above) and
    # `bootstrap_zone_use_matrix` both run raw asyncpg work that can keep
    # this AsyncSession's underlying TCP connection idle for minutes on
    # large county jurisdictions (Monmouth 251k parcels, Bergen 281k, etc.).
    # Supabase pgbouncer drops idle sockets silently; the next SQLAlchemy
    # op (refresh_jurisdiction_coverage_level's SELECT 4 COUNT(*)) then
    # raises MissingGreenlet / ConnectionDoesNotExistError. Same pattern
    # as c7a687c (post-download); apply at this boundary too.
    try:
        async with asyncio.timeout(5):
            await db.close()
    except Exception as exc:
        logger.warning("pre-coverage-refresh session.close() failed (non-fatal): %r", exc)
    try:
        async with asyncio.timeout(60):
            job = await db.merge(job)
            jurisdiction = await db.merge(jurisdiction)
    except Exception as exc:
        logger.warning("pre-coverage-refresh merge failed (will best-effort continue): %r", exc)

    coverage_started = _stage_started(job, "coverage_refresh", jurisdiction_id=str(jurisdiction.id))
    async with asyncio.timeout(180):
        async with async_session_maker() as coverage_db:
            fresh_jurisdiction = await coverage_db.get(Jurisdiction, jurisdiction.id)
            if fresh_jurisdiction is None:
                raise RuntimeError(f"Jurisdiction {jurisdiction.id} not found for coverage refresh")
            coverage_level = await refresh_jurisdiction_coverage_level(
                fresh_jurisdiction,
                coverage_db,
            )
            await coverage_db.commit()
            jurisdiction.coverage_level = coverage_level
    _stage_completed(job, "coverage_refresh", coverage_started, coverage_level=coverage_level.value)

    # ── Step 3b: apply overlays (flood + wetland, non-fatal) ─────────────
    enrichment_started = _stage_started(job, "enrichment")
    enrichment_step = await start_job_step(db, job, "run_overlays")
    enrichment_step_id = enrichment_step.__dict__.get("id")
    overlay_job_id = job.__dict__["id"]
    await _set_status(db, job, JobStatus.running_overlays)
    await db.commit()
    await check_cancelled(db, job)
    try:
        from app.services.overlays import apply_flood_overlay, apply_wetland_overlay, apply_aadt_overlay
        overlay_started = _stage_started(job, "overlays", jurisdiction_id=str(jurisdiction.id))
        # Run all overlays SEQUENTIALLY against the shared AsyncSession.
        # asyncio.gather on the same session interleaves concurrent
        # await db.execute() calls at the asyncpg connection level, mangles
        # its greenlet binding, and the next operation (often apply_aadt_overlay
        # or backfill_parcel_zoning_from_districts in a downstream stage)
        # raises MissingGreenlet. AsyncSession is not concurrency-safe.
        async with asyncio.timeout(ENRICHMENT_TIMEOUT_SECONDS):
            try:
                flood_count = await apply_flood_overlay(jurisdiction.id, db)
            except Exception as flood_exc:
                logger.warning("Flood overlay failed (non-fatal): %s", flood_exc)
                flood_count = 0
            try:
                wetland_count = await apply_wetland_overlay(jurisdiction.id, db)
            except Exception as wetland_exc:
                logger.warning("Wetland overlay failed (non-fatal): %s", wetland_exc)
                wetland_count = 0
        # AADT runs on a SEPARATE raw asyncpg connection inside
        # apply_aadt_overlay (no shared state with the SQLAlchemy session).
        # If it raises, contain it so the rest of the pipeline still
        # completes cleanly — failing AADT is non-essential.
        try:
            aadt_count = await apply_aadt_overlay(jurisdiction.id, db)
        except Exception as aadt_exc:
            logger.warning("AADT overlay failed (non-fatal): %s", aadt_exc)
            aadt_count = 0
        _stage_completed(job, "overlays", overlay_started, flood=flood_count, wetland=wetland_count, aadt=aadt_count)
        await db.commit()
        logger.info(
            "Overlays: %d flood parcels, %d wetland parcels, %d aadt parcels",
            flood_count, wetland_count, aadt_count,
        )
        _stage_completed(
            job,
            "enrichment",
            enrichment_started,
            flood_parcels=flood_count,
            wetland_parcels=wetland_count,
            aadt_parcels=aadt_count,
        )
        await complete_job_step(
            db,
            enrichment_step,
            {"flood_parcels": flood_count, "wetland_parcels": wetland_count, "aadt_parcels": aadt_count},
        )
        await add_job_artifact(
            db,
            job,
            "run_overlays",
            "overlay_metadata",
            {"flood_parcels": flood_count, "wetland_parcels": wetland_count, "aadt_parcels": aadt_count},
        )
    except Exception as exc:
        _stage_failed(job, "enrichment", enrichment_started, exc)
        logger.warning("Overlay step failed (non-fatal): %s", exc)
        try:
            await db.rollback()
            enrichment_step = await db.merge(enrichment_step)
            await fail_job_step(db, enrichment_step, exc, status="warning")
            await db.commit()
        except Exception as warning_exc:
            logger.warning(
                "Overlay warning persistence failed on pipeline session "
                "(non-fatal); retrying with fresh session: %r",
                warning_exc,
            )
            try:
                async with asyncio.timeout(30):
                    async with async_session_maker() as overlay_warning_db:
                        warning_step = (
                            await overlay_warning_db.get(JobStep, enrichment_step_id)
                            if enrichment_step_id is not None
                            else None
                        )
                        if warning_step is not None:
                            await fail_job_step(
                                overlay_warning_db,
                                warning_step,
                                exc,
                                status="warning",
                            )
                        warning_job = await overlay_warning_db.get(Job, overlay_job_id)
                        if warning_job is not None:
                            warning_job.status = JobStatus.running
                        await overlay_warning_db.commit()
            except Exception as fallback_exc:
                logger.warning(
                    "Overlay warning fresh-session persistence failed "
                    "(non-fatal); continuing pipeline: %r",
                    fallback_exc,
                )
            try:
                async with asyncio.timeout(5):
                    await db.close()
            except Exception as close_exc:
                logger.warning(
                    "post-overlay session.close() failed (non-fatal): %r",
                    close_exc,
                )
            try:
                async with asyncio.timeout(60):
                    job = await db.merge(job)
                    jurisdiction = await db.merge(jurisdiction)
            except Exception as merge_exc:
                logger.warning(
                    "post-overlay merge failed (will best-effort continue): %r",
                    merge_exc,
                )
        try:
            async with asyncio.timeout(5):
                await db.refresh(job)
                await db.refresh(jurisdiction)
        except Exception:
            pass

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

    # ── Auto-rescore parcel_buybox_scores ────────────────────────────────
    # Refresh server-side scores for this jurisdiction so the dashboard's
    # Score column lights up immediately. Non-fatal: a scoring failure
    # logs an error and marks the stage failed but does NOT fail the job
    # — parcels + zoning are already persisted regardless.
    #
    # History: prior to fix/auto-score-loud-on-missing-default,
    # auto_score_jurisdiction silently returned 0 when no default filter
    # existed. That state went unnoticed across every new jurisdiction
    # ingest until the dashboard's "Computing N/M parcels" gauge
    # surfaced it. Now auto_score_jurisdiction raises, the stage is
    # marked failed in job state, and the operator can fix the config.
    score_started = _stage_started(job, "auto_score", jurisdiction_id=str(jurisdiction.id))
    try:
        async with asyncio.timeout(900):  # 15 min cap; typical run is <1 min
            scored = await auto_score_jurisdiction(jurisdiction.id)
        _stage_completed(job, "auto_score", score_started, parcels_scored=scored)
        if scored == 0 and count > 0:
            # Parcels exist but none scored — likely a data issue (no
            # eligible parcels matched the scorer's SELECT, e.g. no
            # zone_use_matrix rows yet). Worth flagging loudly.
            logger.error(
                "Auto-score returned 0 parcels for %s despite %d parcels ingested. "
                "Check zone_use_matrix coverage for this jurisdiction.",
                jurisdiction.name, count,
            )
        else:
            logger.info("Auto-scored %d parcels for %s", scored, jurisdiction.name)
    except Exception as exc:
        _stage_failed(job, "auto_score", score_started, exc)
        logger.error("Auto-scoring failed (non-fatal) for %s: %s", jurisdiction.name, exc)

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
            # uq_zone_matrix is a PARTIAL UNIQUE INDEX (not a constraint),
            # see zone_matrix_crosswalk.py for the long version. Using
            # constraint="uq_zone_matrix" here fails with UndefinedObjectError
            # the moment a county ordinance is LLM-parsed. Match the
            # indexed expression byte-for-byte: COALESCE(municipality, ''::text)
            # WHERE deleted_at IS NULL.
            index_elements=[
                ZoneUseMatrix.jurisdiction_id,
                ZoneUseMatrix.zone_code,
                func.coalesce(ZoneUseMatrix.municipality, literal_column("''::text")),
            ],
            index_where=ZoneUseMatrix.deleted_at.is_(None),
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
    Try live ArcGIS Hub discovery; if that fails or yields a token-protected /
    empty layer, fall back to state-level open data (UGRC for UT).
    Raises ValueError with a helpful message if everything fails.
    """
    from app.services.arcgis_discovery import discover_layers, geocode_jurisdiction

    geo = None

    # ── Try ArcGIS discovery (Hub / direct / webmap) ──────────────────────────
    try:
        endpoints = await discover_layers(input_str)
        geo = endpoints.geocoded

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

    # ── State-level open data fallback ────────────────────────────────────────
    try:
        geo = await geocode_jurisdiction(input_str)
    except Exception as exc:
        raise ValueError(
            f"Could not geocode {input_str!r} for state-level fallback: {exc}"
        ) from exc

    fallback = await _state_open_data_fallback(geo)
    if fallback is not None:
        logger.info(
            "State open-data fallback hit for %s, %s: %s (where=%s)",
            geo.city, geo.state, fallback.parcel_endpoint, fallback.where_clause,
        )
        return fallback

    raise ValueError(
        f"Unknown jurisdiction {input_str!r}. No public ArcGIS layer found and "
        f"no state-level fallback covers {geo.state!r}. Add it to "
        "KNOWN_JURISDICTIONS or extend _state_open_data_fallback()."
    )


def _parse_state(s: str) -> str:
    """Extract a 2-letter US state code from a string like 'Draper, UT'."""
    m = re.search(r",\s*([A-Z]{2})\b", s.upper())
    return m.group(1) if m else ""


# UGRC county-name → service-name (Parcels_<service>).
# Names taken from services1.arcgis.com/99lidPhWCzftIe9K (UGRC org).
_UGRC_COUNTY_SERVICES: dict[str, str] = {
    "salt lake":  "Parcels_SaltLake",
    "utah":       "Parcels_Utah",
    "weber":      "Parcels_Weber",
    "davis":      "Parcels_Davis",
    "cache":      "Parcels_Cache",
    "washington": "Parcels_Washington",
    "iron":       "Parcels_Iron",
}


async def _state_open_data_fallback(geo: Any) -> JurisdictionConfig | None:
    """Look up a state-managed open parcel layer for a geocoded place.

    Currently supports UT via UGRC. Returns None if no fallback is configured
    for the state, or if the candidate layer returns 0 features for the city
    (so we never silently land on an empty download).
    """
    if not geo or not geo.state:
        return None

    state = geo.state.upper()
    if state == "UT":
        return await _ut_ugrc_fallback(geo)
    return None


async def _ut_ugrc_fallback(geo: Any) -> JurisdictionConfig | None:
    county_norm = re.sub(r"\s+county\s*$", "", (geo.county or "").lower()).strip()
    service = _UGRC_COUNTY_SERVICES.get(county_norm)
    if not service:
        logger.warning(
            "UT UGRC fallback: county %r not in UGRC service map", geo.county
        )
        return None

    parcel_endpoint = f"{_UGRC}/{service}/FeatureServer/0"
    where = f"PARCEL_CITY='{geo.city}'"

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{parcel_endpoint}/query",
                params={"where": where, "returnCountOnly": "true", "f": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("UGRC count probe failed for %s: %s", geo.city, exc)
        return None

    count = data.get("count") if isinstance(data, dict) else None
    if not count:
        logger.warning(
            "UGRC %s/PARCEL_CITY='%s' returned %s parcels — skipping",
            service, geo.city, count,
        )
        return None

    logger.info(
        "UGRC fallback verified: %s parcels for %s (county=%s)",
        count, geo.city, county_norm,
    )
    return JurisdictionConfig(
        name=f"{geo.city}, UT",
        state="UT",
        county=county_norm.title(),
        parcel_source=ParcelSource.city_gis,
        parcel_endpoint=parcel_endpoint,
        where_clause=where,
    )


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
