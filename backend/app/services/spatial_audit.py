"""Per-jurisdiction spatial-correctness audit.

Reads (does not mutate) the jurisdiction's `zoning_sources` rows, runs the
live `spatial_check_for_url` probe against each, joins the result with the
stored `confidence_breakdown`, and reports:

  - source bucket counts: stored validation_status × live verdict
  - stale-score rows: stored breakdown lacks `bbox_overlap_*` but the live
    probe now returns a non-None verdict (evidence that the persisted
    score predates the pyproj + bbox-overlap fix that landed
    2026-05-12)
  - blocking rows: validation_status='verified' but live verdict is
    'disjoint' or 'tiny' — the ingest pre-flight gate will refuse these
    (or already did) and the operator can re-review with current data
  - district + parcel-overlap stats: how many ZoningDistrict rows exist,
    how many parcels carry a zone_code

Outputs a flat dict so the same shape powers the HTTP endpoint and the
CLI script.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zoning_district import ZoningDistrict
from app.models.zoning_source import ZoningSource
from app.services.zoning_discovery import spatial_check_for_url

logger = logging.getLogger(__name__)

# Cap concurrent probes so one audit doesn't hammer an upstream service.
_DEFAULT_CONCURRENCY = 8

# Component-F-related names we expect in confidence_breakdown when scoring
# v2 has fired the bbox-overlap signal at discovery time.
_BBOX_OVERLAP_COMPONENT_NAMES = (
    "bbox_overlap_strong",
    "bbox_overlap_tiny",
    "bbox_overlap_disjoint",
)


async def audit_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    include_district_stats: bool = True,
) -> dict[str, Any]:
    """Run the full spatial audit for one jurisdiction.

    Live probes use a single AsyncClient with a semaphore-bounded
    fan-out. Read-only — no DB mutations, no operator-visible side
    effects.
    """
    juris = await db.get(Jurisdiction, jurisdiction_id)
    if juris is None:
        return {"error": "jurisdiction not found", "jurisdiction_id": str(jurisdiction_id)}

    rows = (
        await db.execute(
            select(ZoningSource).where(ZoningSource.jurisdiction_id == jurisdiction_id)
        )
    ).scalars().all()

    source_probes = await _probe_sources(rows, juris.bbox, concurrency)

    by_status_x_verdict: dict[str, dict[str, int]] = {}
    stale_breakdown: list[dict[str, Any]] = []
    blocking_verified: list[dict[str, Any]] = []
    crs_failures: list[dict[str, Any]] = []

    for row, probe in zip(rows, source_probes):
        status = row.validation_status or "pending"
        verdict = (probe or {}).get("verdict") or "error"
        by_status_x_verdict.setdefault(status, {}).setdefault(verdict, 0)
        by_status_x_verdict[status][verdict] += 1

        breakdown = row.confidence_breakdown or {}
        has_bbox_component = any(
            k in breakdown for k in _BBOX_OVERLAP_COMPONENT_NAMES
        )
        # Stale: live probe has a verdict but stored breakdown didn't
        # record a Component F entry. Strongest evidence is when the
        # live verdict is disjoint (the row would now be -60 instead
        # of the current score).
        if not has_bbox_component and verdict in ("disjoint", "tiny", "good", "partial"):
            stale_breakdown.append({
                "source_id": str(row.id),
                "municipality_name": row.municipality_name,
                "title": row.title,
                "validation_status": status,
                "stored_score": row.confidence_score,
                "live_verdict": verdict,
                "live_overlap_ratio": probe.get("bbox_overlap_ratio"),
                "zoning_endpoint": row.zoning_endpoint,
            })

        # Blocking: verified row that the current spatial guard would reject.
        if status == "verified" and verdict in ("disjoint", "tiny"):
            blocking_verified.append({
                "source_id": str(row.id),
                "municipality_name": row.municipality_name,
                "title": row.title,
                "live_verdict": verdict,
                "live_overlap_ratio": probe.get("bbox_overlap_ratio"),
                "layer_extent_srid": probe.get("layer_extent_srid"),
                "zoning_endpoint": row.zoning_endpoint,
            })

        # CRS failure: layer extent is published but reprojection produced
        # None (unsupported SRID, corrupt extent, or missing SR metadata).
        if (
            probe
            and probe.get("layer_extent_raw") is not None
            and probe.get("layer_extent_wgs84") is None
        ):
            crs_failures.append({
                "source_id": str(row.id),
                "municipality_name": row.municipality_name,
                "title": row.title,
                "layer_extent_raw": probe.get("layer_extent_raw"),
                "layer_extent_srid": probe.get("layer_extent_srid"),
                "zoning_endpoint": row.zoning_endpoint,
            })

    out: dict[str, Any] = {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": juris.name,
        "jurisdiction_bbox": juris.bbox,
        "source_count_total": len(rows),
        "by_status_x_verdict": by_status_x_verdict,
        "stale_breakdown_count": len(stale_breakdown),
        "stale_breakdown_sample": stale_breakdown[:25],
        "blocking_verified_count": len(blocking_verified),
        "blocking_verified": blocking_verified,
        "crs_failure_count": len(crs_failures),
        "crs_failures": crs_failures[:25],
    }

    if include_district_stats:
        out["districts"] = await _district_stats(jurisdiction_id, db)
        out["parcel_overlap"] = await _parcel_overlap_stats(jurisdiction_id, db)

    return out


async def _probe_sources(
    rows: list[ZoningSource],
    jurisdiction_bbox: list[float] | None,
    concurrency: int,
) -> list[dict[str, Any] | None]:
    """Run spatial_check_for_url across every source row, capped at `concurrency`
    in-flight calls. Returns one result per input row, in input order.
    Rows without a zoning_endpoint yield None (skipped)."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(row: ZoningSource, client: httpx.AsyncClient) -> dict[str, Any] | None:
        if not row.zoning_endpoint:
            return None
        async with sem:
            try:
                return await spatial_check_for_url(
                    row.zoning_endpoint, jurisdiction_bbox, client=client,
                )
            except Exception as exc:
                logger.warning("spatial probe failed for %s: %r", row.id, exc)
                return {"verdict": "error", "error": repr(exc)[:200]}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        return await asyncio.gather(*[_one(r, client) for r in rows])


async def _district_stats(
    jurisdiction_id: uuid.UUID, db: AsyncSession,
) -> dict[str, Any]:
    """Count of zoning_districts rows + how many have invalid PostGIS geometry.
    Lightweight — runs two scalar queries."""
    total = (await db.execute(
        select(func.count(ZoningDistrict.id))
        .where(ZoningDistrict.jurisdiction_id == jurisdiction_id)
    )).scalar_one()
    if total == 0:
        return {"total": 0, "invalid_geom": 0, "extent_wgs84": None}

    invalid = (await db.execute(
        text(
            "SELECT COUNT(*) FROM zoning_districts "
            "WHERE jurisdiction_id = :jid AND NOT ST_IsValid(geom)"
        ).bindparams(jid=jurisdiction_id)
    )).scalar_one()

    extent_row = (await db.execute(
        text(
            "SELECT ST_XMin(ST_Extent(geom)), ST_YMin(ST_Extent(geom)), "
            "       ST_XMax(ST_Extent(geom)), ST_YMax(ST_Extent(geom)) "
            "FROM zoning_districts WHERE jurisdiction_id = :jid"
        ).bindparams(jid=jurisdiction_id)
    )).first()
    extent = list(extent_row) if extent_row and extent_row[0] is not None else None

    return {"total": total, "invalid_geom": invalid, "extent_wgs84": extent}


async def _parcel_overlap_stats(
    jurisdiction_id: uuid.UUID, db: AsyncSession,
) -> dict[str, Any]:
    """Parcel coverage: how many parcels exist for this jurisdiction and
    what fraction carry a zoning_code (i.e. the spatial overlay succeeded
    in writing back). Cheap — two integer queries."""
    parcel_total = (await db.execute(
        select(func.count(Parcel.id))
        .where(Parcel.jurisdiction_id == jurisdiction_id)
    )).scalar_one()
    if parcel_total == 0:
        return {"total": 0, "with_zoning": 0, "ratio": None}

    with_zoning = (await db.execute(
        select(func.count(Parcel.id))
        .where(Parcel.jurisdiction_id == jurisdiction_id)
        .where(Parcel.zoning_code.is_not(None))
    )).scalar_one()

    ratio = with_zoning / parcel_total if parcel_total else None
    return {"total": parcel_total, "with_zoning": with_zoning, "ratio": ratio}
