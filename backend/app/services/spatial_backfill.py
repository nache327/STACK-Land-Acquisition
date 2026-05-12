"""
Spatial backfills used by the ingestion pipeline and operational recovery.
"""
from __future__ import annotations

import uuid

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.jurisdiction import CoverageLevel, Jurisdiction


async def refresh_jurisdiction_bbox(
    jurisdiction: Jurisdiction, db: AsyncSession
) -> list[float] | None:
    """Persist [minLng, minLat, maxLng, maxLat] from parcel geometry."""
    result = await db.execute(
        text(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels
            WHERE jurisdiction_id = :jid
              AND geom IS NOT NULL
            """
        ),
        {"jid": jurisdiction.id},
    )
    row = result.one_or_none()
    if row is None or row.minx is None:
        return None
    bbox = [float(row.minx), float(row.miny), float(row.maxx), float(row.maxy)]
    jurisdiction.bbox = bbox
    return bbox


async def backfill_parcel_zoning_from_districts(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    fill_missing_zone_code: bool = True,
) -> int:
    """
    Backfill `parcels.zone_class` using parcel centroid containment.

    Uses ST_Within(centroid, district) instead of full polygon intersection —
    10-100x faster on large jurisdictions (point-in-polygon vs polygon-polygon).
    Accurate for normal parcels; a parcel straddling a zone boundary gets the
    zone that contains its centroid.

    Runs on a fresh raw asyncpg connection (session-mode 5432 + command_timeout
    7200s + server-side statement_timeout=0) so Supabase doesn't cancel the
    query mid-flight on jurisdictions with hundreds of thousands of parcels.
    SQLAlchemy's asyncpg dialect imposes a much shorter per-statement timeout
    that has killed this UPDATE on Philadelphia (547k parcels × 29k districts).
    """
    zone_code_set = (
        ", zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)"
        if fill_missing_zone_code
        else ""
    )
    session_url = settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(
        session_url, statement_cache_size=0, command_timeout=7200
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        # LATERAL + LIMIT 1 instead of CTE + ROW_NUMBER. The earlier
        # ROW_NUMBER OVER (PARTITION BY p.id ORDER BY zd.id) query
        # materialised every parcel/district overlap (≈ N_parcels × 6 on
        # Fairfax) and sorted that 2.2M-row, 988-byte-wide result for the
        # window function — the sort spilled to disk and hung Fairfax for
        # the full 30-min dramatiq time_limit.
        # The LATERAL must live inside a subquery in the FROM clause —
        # PostgreSQL refuses to let a top-level LATERAL reference the
        # UPDATE target table directly ("invalid reference to FROM-clause
        # entry for table p"). Pulling parcels into the inner FROM lets
        # the lateral see p.geom while UPDATE joins target.id =
        # sub.parcel_id at the outer level.
        status = await conn.execute(
            f"""
            UPDATE parcels target
            SET zone_class = sub.zone_class
                {zone_code_set}
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            jurisdiction_id,
        )
    finally:
        await conn.close()
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


async def refresh_jurisdiction_coverage_level(
    jurisdiction: Jurisdiction,
    db: AsyncSession,
) -> CoverageLevel:
    """
    Set a stricter-but-still-compact coverage enum on the jurisdiction row.
    """
    result = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid) AS parcel_count,
                (SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = :jid) AS matrix_count,
                (SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = :jid) AS zoning_count,
                (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid AND has_structure IS NULL) AS null_vacancy_count
            """
        ),
        {"jid": jurisdiction.id},
    )
    row = result.one()
    if row.parcel_count > 0 and row.matrix_count > 0 and row.zoning_count > 0 and jurisdiction.bbox and row.null_vacancy_count == 0:
        jurisdiction.coverage_level = CoverageLevel.full
    elif row.parcel_count > 0 and (row.matrix_count > 0 or row.zoning_count > 0):
        jurisdiction.coverage_level = CoverageLevel.partial
    elif row.parcel_count > 0:
        jurisdiction.coverage_level = CoverageLevel.parcels_only
    elif row.matrix_count > 0 or row.zoning_count > 0:
        jurisdiction.coverage_level = CoverageLevel.zoning_only
    else:
        jurisdiction.coverage_level = CoverageLevel.partial
    return jurisdiction.coverage_level
