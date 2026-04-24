"""
Vacancy detection service.

Determines whether a parcel has an existing structure using (in priority order):
  1. Assessor improvement value (improvement_value > 0  →  has_structure = True)
  2. Microsoft Building Footprints or OSM buildings in PostGIS
     (ST_Intersects with parcel geometry)
  3. Land-use code keywords (VACANT LAND, VACANT RES, VACANT COMM …)
  4. NULL → caveat surfaced in UI

Phase 1: constants and interface defined.
Phase 4: full PostGIS intersection logic.
"""
from __future__ import annotations

import logging
import uuid

from shapely.ops import unary_union
from sqlalchemy import text

from app.services.arcgis_bbox import download_bbox_features, get_parcel_bbox

logger = logging.getLogger(__name__)

# Land-use code values that indicate a vacant parcel (case-insensitive)
VACANT_LANDUSE_CODES: frozenset[str] = frozenset({
    "vacant land",
    "vacant res",
    "vacant residential",
    "vacant comm",
    "vacant commercial",
    "vacant industrial",
    "unimproved land",
    "bare land",
    "undeveloped",
    "vac land",
    "vac res",
    "vac comm",
    "vacnt",
})


def is_vacant_by_landuse(land_use_code: str | None) -> bool | None:
    """
    Returns True if the land-use code clearly indicates vacancy,
    False if it clearly indicates a structure, None if indeterminate.
    """
    if land_use_code is None:
        return None
    return land_use_code.lower().strip() in VACANT_LANDUSE_CODES


def is_vacant_by_improvement_value(improvement_value: float | None) -> bool | None:
    """
    Returns True if improvement_value == 0, False if > 0, None if unknown.
    """
    if improvement_value is None:
        return None
    return improvement_value == 0


async def backfill_vacancy_by_heuristics(
    jurisdiction_id: uuid.UUID,
    db: object,  # AsyncSession
) -> dict[str, int]:
    """
    Fill easy vacancy cases using parcel attributes already stored in Postgres.
    """
    stats: dict[str, int] = {}

    true_from_improvement = await db.execute(  # type: ignore[attr-defined]
        text(
            """
            UPDATE parcels
            SET has_structure = TRUE
            WHERE jurisdiction_id = :jid
              AND improvement_value > 0
              AND COALESCE(has_structure, FALSE) IS DISTINCT FROM TRUE
            """
        ),
        {"jid": jurisdiction_id},
    )
    stats["true_from_improvement"] = true_from_improvement.rowcount or 0

    false_from_zero_improvement = await db.execute(  # type: ignore[attr-defined]
        text(
            """
            UPDATE parcels
            SET has_structure = FALSE
            WHERE jurisdiction_id = :jid
              AND has_structure IS NULL
              AND improvement_value = 0
            """
        ),
        {"jid": jurisdiction_id},
    )
    stats["false_from_zero_improvement"] = false_from_zero_improvement.rowcount or 0

    false_from_land_use = await db.execute(  # type: ignore[attr-defined]
        text(
            """
            UPDATE parcels
            SET has_structure = FALSE
            WHERE jurisdiction_id = :jid
              AND has_structure IS NULL
              AND land_use_code IS NOT NULL
              AND (
                    lower(land_use_code) LIKE '%vacant%'
                 OR lower(land_use_code) LIKE '%unimproved%'
                 OR lower(land_use_code) LIKE '%undeveloped%'
                 OR lower(land_use_code) LIKE '%bare land%'
              )
            """
        ),
        {"jid": jurisdiction_id},
    )
    stats["false_from_land_use"] = false_from_land_use.rowcount or 0
    await db.flush()  # type: ignore[attr-defined]
    return stats


async def backfill_vacancy_from_buildings(
    jurisdiction_id: uuid.UUID,
    db: object,  # AsyncSession
    *,
    source_url: str,
    where: str = "1=1",
) -> int:
    """
    Mark parcels as having structures when they intersect a building footprint.
    """
    bbox = await get_parcel_bbox(jurisdiction_id, db)  # type: ignore[arg-type]
    if bbox is None:
        return 0

    gdf = await download_bbox_features(source_url, bbox, where=where)
    if gdf is None or gdf.empty:
        return 0

    valid_geoms = [
        geom.simplify(0.000005, preserve_topology=True)
        for geom in gdf.geometry.dropna()
        if geom is not None and not geom.is_empty
    ]
    if not valid_geoms:
        return 0

    total = 0
    batch_size = 400
    for offset in range(0, len(valid_geoms), batch_size):
        union = unary_union(valid_geoms[offset : offset + batch_size])
        if union is None or union.is_empty:
            continue

        result = await db.execute(  # type: ignore[attr-defined]
            text(
                """
                UPDATE parcels
                SET has_structure = TRUE
                WHERE jurisdiction_id = :jid
                  AND geom IS NOT NULL
                  AND COALESCE(has_structure, FALSE) IS DISTINCT FROM TRUE
                  AND ST_Intersects(geom, ST_GeomFromText(:geom, 4326))
                """
            ),
            {"jid": jurisdiction_id, "geom": union.wkt},
        )
        total += result.rowcount or 0

    await db.flush()  # type: ignore[attr-defined]
    return total


async def finalize_vacancy_backfill(
    jurisdiction_id: uuid.UUID,
    db: object,  # AsyncSession
    *,
    strict: bool = False,
) -> int:
    """
    For strict operational runs, force any unresolved parcels to `FALSE`.
    """
    if not strict:
        return 0
    result = await db.execute(  # type: ignore[attr-defined]
        text(
            """
            UPDATE parcels
            SET has_structure = FALSE
            WHERE jurisdiction_id = :jid
              AND has_structure IS NULL
            """
        ),
        {"jid": jurisdiction_id},
    )
    await db.flush()  # type: ignore[attr-defined]
    return result.rowcount or 0


async def compute_vacancy_batch(
    parcel_ids: list[int],
    db: object,  # AsyncSession — typed as object to avoid circular import
) -> dict[int, bool | None]:
    """
    Compute has_structure for a batch of parcels using PostGIS building-footprint
    intersection. Returns {parcel_id: has_structure | None}.

    Phase 4 implementation.
    """
    if not parcel_ids:
        return {}

    result = await db.execute(  # type: ignore[attr-defined]
        text(
            """
            SELECT id, has_structure
            FROM parcels
            WHERE id = ANY(:parcel_ids)
            """
        ),
        {"parcel_ids": parcel_ids},
    )
    return {int(row.id): row.has_structure for row in result}
