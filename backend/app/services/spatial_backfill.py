"""
Spatial backfills used by the ingestion pipeline and operational recovery.
"""
from __future__ import annotations

import logging
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
    nearest_within_meters: float | None = None,
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

    nearest_within_meters: when set, parcels not contained by any district
    after the ST_Within pass are bound to the *nearest* district within N
    meters via a second ST_DWithin pass. Off by default — the contained-only
    behavior is fully preserved. Op-5 needs this fallback because vendor
    zoning PDFs digitized to polygons typically leave 20-40% of parcels just
    outside any single polygon (street-frontage gaps, gutters between
    overlay districts) even when the human reader can unambiguously assign
    them to the visually-adjacent zone.

    Every write from this service stamps `parcels.zone_binding_method`
    ('contained' or 'nearest_<N>m') so the audit can split contained-vs-
    inferred coverage without changing the ≥70% operational gate.
    """
    logger = logging.getLogger(__name__)
    # Skip the heavy UPDATE entirely when virtually every parcel already
    # has zoning_code populated. NYC hit this: 13 unzoned parcels of 856,670
    # caused a 49-min UPDATE that rewrote all 856k rows for ~0 useful work.
    # The 1% threshold leaves plenty of headroom for jurisdictions that
    # genuinely need a sweep (where 5-100% of parcels need zoning attached).
    pre_counts = await db.execute(text(
        "SELECT "
        " (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid) AS total,"
        " (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid AND (zoning_code IS NULL OR zoning_code = '')) AS unzoned"
    ), {"jid": jurisdiction_id})
    row = pre_counts.one()
    total = int(row.total or 0)
    unzoned = int(row.unzoned or 0)
    if total > 0 and unzoned / total < 0.01:
        # >99% already zoned — bail. Logged so the operator can tell the
        # difference between "skipped because already done" and "failed".
        logger.info(
            "backfill_parcel_zoning_from_districts skipping %s — "
            "%d/%d parcels (%.2f%%) already have zoning_code",
            jurisdiction_id, total - unzoned, total,
            (total - unzoned) / total * 100,
        )
        return 0

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
    contained_updated = 0
    nearest_updated = 0
    try:
        await conn.execute("SET statement_timeout = 0")
        # ── Pass 1: ST_Within (centroid contained in district) ──────────────
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
        contained_status = await conn.execute(
            f"""
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = 'contained'
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
        try:
            contained_updated = int(contained_status.split()[-1])
        except (ValueError, IndexError):
            contained_updated = 0

        # ── Pass 2: ST_DWithin fallback (optional) ──────────────────────────
        # Snap parcels not contained by any district to their *nearest*
        # district within N meters. Uses geography casts so $N is meters
        # (not degrees) and ORDER BY ST_Distance for tie-breaking on the
        # short list returned by the GIST index probe.
        if nearest_within_meters is not None and nearest_within_meters > 0:
            radius = float(nearest_within_meters)
            binding_label = f"nearest_{int(round(radius))}m"
            nearest_status = await conn.execute(
                f"""
                UPDATE parcels target
                SET zone_class = sub.zone_class,
                    zone_binding_method = $2
                    {zone_code_set}
                FROM (
                    SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT zd.zone_class, zd.zone_code
                        FROM zoning_districts zd
                        WHERE zd.jurisdiction_id = $1
                          AND zd.geom IS NOT NULL
                          AND ST_DWithin(
                              zd.geom::geography,
                              ST_Centroid(p.geom)::geography,
                              $3
                          )
                        ORDER BY ST_Distance(
                            zd.geom::geography,
                            ST_Centroid(p.geom)::geography
                        )
                        LIMIT 1
                    ) m
                    WHERE p.jurisdiction_id = $1
                      AND p.geom IS NOT NULL
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id = sub.parcel_id
                """,
                jurisdiction_id,
                binding_label,
                radius,
            )
            try:
                nearest_updated = int(nearest_status.split()[-1])
            except (ValueError, IndexError):
                nearest_updated = 0
            logger.info(
                "backfill_parcel_zoning_from_districts %s: contained=%d, "
                "nearest_within_%.1fm=%d",
                jurisdiction_id, contained_updated, radius, nearest_updated,
            )
    finally:
        await conn.close()
    return contained_updated + nearest_updated


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
