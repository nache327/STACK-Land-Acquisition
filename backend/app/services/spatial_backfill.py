"""
Spatial backfills used by the ingestion pipeline and operational recovery.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

    Disables Supabase's server-side statement_timeout via SET LOCAL so the
    query isn't cancelled prematurely on large cities.
    """
    zone_code_set = (
        ", zoning_code = COALESCE(NULLIF(p.zoning_code, ''), ranked.zone_code)"
        if fill_missing_zone_code
        else ""
    )
    await db.execute(text("SET LOCAL statement_timeout = 0"))
    result = await db.execute(
        text(
            f"""
            WITH ranked AS (
                SELECT
                    p.id AS parcel_id,
                    zd.zone_class,
                    zd.zone_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.id
                        ORDER BY zd.id
                    ) AS rn
                FROM parcels p
                JOIN zoning_districts zd
                  ON zd.jurisdiction_id = p.jurisdiction_id
                 AND p.jurisdiction_id = :jid
                 AND p.geom IS NOT NULL
                 AND zd.geom IS NOT NULL
                 AND ST_Within(ST_Centroid(p.geom), zd.geom)
            )
            UPDATE parcels p
            SET zone_class = ranked.zone_class
                {zone_code_set}
            FROM ranked
            WHERE p.id = ranked.parcel_id
              AND ranked.rn = 1
            """
        ),
        {"jid": jurisdiction_id},
    )
    await db.flush()
    return result.rowcount or 0


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
