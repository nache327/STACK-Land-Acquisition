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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select as sa_select

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction, ParcelSource
from app.models.parcel import Parcel
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels

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
    ordinance_url: str | None = None


KNOWN_JURISDICTIONS: dict[str, JurisdictionConfig] = {
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
    jurisdiction = result.scalar_one_or_none()

    if jurisdiction is None:
        jurisdiction = Jurisdiction(
            name=cfg.name,
            state=cfg.state,
            county=cfg.county,
            parcel_source=cfg.parcel_source,
            parcel_endpoint=cfg.parcel_endpoint,
            zoning_endpoint=cfg.zoning_endpoint,
        )
        db.add(jurisdiction)
        await db.flush()
        logger.info("Created new Jurisdiction row: %s (%s)", cfg.name, jurisdiction.id)
    else:
        # Update endpoints in case they changed
        jurisdiction.parcel_endpoint = cfg.parcel_endpoint
        jurisdiction.zoning_endpoint = cfg.zoning_endpoint
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
        logger.info("Downloading parcels from ArcGIS: %s", cfg.parcel_endpoint)
        gdf = await download_all_features(
            cfg.parcel_endpoint,
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
    count = await ingest_parcels(gdf, jurisdiction.id, db, replace=True)

    # Update last_indexed_at
    from datetime import datetime, timezone
    jurisdiction.last_indexed_at = datetime.now(timezone.utc)
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

    # ── Step 5: mark ready ────────────────────────────────────────────────
    await _set_status(
        db, job, JobStatus.ready,
        progress={
            "parcels_ingested": count,
            "jurisdiction_id": str(jurisdiction.id),
        },
    )
    await db.commit()
    logger.info(
        "Job %s complete — %d parcels for %s", job.id, count, cfg.name
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

    from sqlalchemy import delete

    from app.models.zone_use_matrix import ZoneUseMatrix
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

    # Replace existing matrix rows for this jurisdiction
    await db.execute(
        delete(ZoneUseMatrix).where(ZoneUseMatrix.jurisdiction_id == jurisdiction.id)
    )

    for zone in deduped_zones:
        db.add(ZoneUseMatrix(
            jurisdiction_id=jurisdiction.id,
            zone_code=zone.code,
            zone_name=zone.name,
            self_storage=zone.self_storage,
            mini_warehouse=zone.mini_warehouse,
            light_industrial=zone.light_industrial,
            luxury_garage_condo=zone.luxury_garage_condo,
            citations=[c.model_dump() for c in zone.citations] if zone.citations else None,
            confidence=zone.confidence,
            notes=zone.notes,
        ))

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
