"""
Saturation analysis service.

Computes self-storage market saturation for a given parcel centroid by:
  1. Querying competitor_facilities within each radius ring (1/3/5/10 miles)
  2. Computing population within each ring via census area-weighted interpolation
  3. Calculating sq_ft_per_person = total_sqft / population

Saturation color thresholds are configurable via settings:
  - green  : sq_ft_per_person < saturation_threshold_low  (underserved)
  - yellow : saturation_threshold_low ≤ sq_ft_per_person < saturation_threshold_high
  - red    : sq_ft_per_person ≥ saturation_threshold_high (oversupplied)
  - gray   : no data (no competitors found, or population is 0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.census import compute_population_in_ring

logger = logging.getLogger(__name__)

RING_RADII_MILES: list[float] = [1.0, 3.0, 5.0, 10.0]
_MILES_TO_METERS = 1609.344


@dataclass
class RingResult:
    radius_miles: float
    population: float
    facility_count: int
    total_sqft: int
    sqft_per_person: float | None


@dataclass
class SaturationResult:
    parcel_id: int
    centroid_wkt: str
    rings: list[RingResult]
    primary_sqft_per_person: float | None  # 3-mile ring value
    color: str  # "green" | "yellow" | "red" | "gray"


# ── Public API ────────────────────────────────────────────────────────────────

async def compute_ring_saturation(
    parcel_id: int,
    db: AsyncSession,
    ring_miles: float | None = None,
) -> SaturationResult | None:
    """
    Compute saturation rings for a parcel. Returns None if parcel not found.
    ring_miles: if specified, only compute that one ring (for batch endpoints).
    """
    # Get parcel centroid
    result = await db.execute(
        text("SELECT ST_AsText(centroid), "
             "ST_X(centroid) AS lng, ST_Y(centroid) AS lat "
             "FROM parcels WHERE id = :id"),
        {"id": parcel_id},
    )
    row = result.fetchone()
    if not row or not row[0]:
        return None
    centroid_wkt = row[0]
    parcel_lng = row[1]
    parcel_lat = row[2]

    # Lazy-fetch census tracts around this parcel if not already cached.
    # The single-parcel path used to rely on the bulk-saturation flow
    # having pre-warmed tracts for the area — that fell down for NJ
    # parcels in jurisdictions where the bulk flow hadn't run yet (e.g.
    # opening a parcel detail drawer was the first thing that touched
    # that geography). Symptom: Market Saturation showed competitor
    # counts but Pop=0 across all rings because the spatial join had
    # nothing to intersect.
    #
    # Use a 0.20° pad (~14 mi) — matches the bulk-path radius so the
    # 10-mile ring's edges still have tracts to intersect.
    try:
        from app.services.census import ensure_census_tracts
        if parcel_lng is not None and parcel_lat is not None:
            buf = 0.20
            tract_count = await ensure_census_tracts(
                (parcel_lng - buf, parcel_lat - buf,
                 parcel_lng + buf, parcel_lat + buf),
                db,
            )
            if tract_count:
                await db.commit()
    except Exception as exc:
        logger.warning(
            "Auto-fetch census tracts for parcel %s failed (non-fatal): %s",
            parcel_id, exc,
        )

    radii = [ring_miles] if ring_miles else RING_RADII_MILES
    rings: list[RingResult] = []

    for radius in radii:
        ring = await _compute_single_ring(centroid_wkt, radius, db)
        rings.append(ring)

    # Primary = 3-mile ring (index 1 when computing all rings)
    primary = next((r for r in rings if r.radius_miles == 3.0), rings[0] if rings else None)
    primary_sqft = primary.sqft_per_person if primary else None
    color = _saturation_color(primary_sqft)

    return SaturationResult(
        parcel_id=parcel_id,
        centroid_wkt=centroid_wkt,
        rings=rings,
        primary_sqft_per_person=primary_sqft,
        color=color,
    )


async def compute_batch_saturation(
    parcel_ids: list[int],
    ring_miles: float,
    db: AsyncSession,
) -> dict[int, dict]:
    """
    Compute saturation for multiple parcels at a single ring radius.
    Returns {parcel_id: {"sqft_per_person": float|None, "color": str}}.

    Uses a single bulk SQL query (not a per-parcel loop) so 1,000 parcels
    run in 1–5 seconds instead of timing out.
    """
    if not parcel_ids:
        return {}

    # Lazily ensure census tracts are loaded — one-time fetch per city,
    # cached 90 days. Must happen before the bulk query below.
    try:
        from app.services.census import ensure_census_tracts
        bbox_result = await db.execute(
            text("""
                SELECT
                    ST_XMin(ST_Extent(centroid)) AS xmin,
                    ST_YMin(ST_Extent(centroid)) AS ymin,
                    ST_XMax(ST_Extent(centroid)) AS xmax,
                    ST_YMax(ST_Extent(centroid)) AS ymax
                FROM parcels
                WHERE id = ANY(:ids) AND centroid IS NOT NULL
            """),
            {"ids": parcel_ids},
        )
        bbox_row = bbox_result.fetchone()
        if bbox_row and all(v is not None for v in bbox_row):
            xmin, ymin, xmax, ymax = bbox_row
            buf = 0.20  # ~14-mile pad so ring edges near bbox boundary have tracts
            tract_count = await ensure_census_tracts(
                (xmin - buf, ymin - buf, xmax + buf, ymax + buf), db
            )
            if tract_count:
                await db.commit()
    except Exception as exc:
        logger.warning("Auto-fetch census tracts failed (non-fatal): %s", exc)

    radius_m = ring_miles * _MILES_TO_METERS
    sqft_default = settings.competitor_sqft_default

    # Single bulk query: competitor counts + area-weighted census population
    # for all parcels in one shot — replaces 2,000 individual queries per 1,000 parcels.
    result = await db.execute(
        text("""
            WITH parcel_centroids AS (
                SELECT id, centroid
                FROM parcels
                WHERE id = ANY(:ids) AND centroid IS NOT NULL
            ),
            competitor_counts AS (
                SELECT
                    pc.id AS parcel_id,
                    COUNT(cf.id)::int AS facility_count,
                    COALESCE(SUM(COALESCE(cf.sq_ft, :sqft_default)), 0)::int AS total_sqft
                FROM parcel_centroids pc
                LEFT JOIN competitor_facilities cf
                    ON ST_DWithin(pc.centroid::geography, cf.geom::geography, :radius_m)
                GROUP BY pc.id
            ),
            ring_geoms AS (
                SELECT id, ST_Buffer(centroid::geography, :radius_m)::geometry AS ring_geom
                FROM parcel_centroids
            ),
            census_pop AS (
                SELECT
                    rg.id AS parcel_id,
                    COALESCE(SUM(
                        ct.population::float *
                        ST_Area(ST_Intersection(rg.ring_geom, ct.geom)::geography) /
                        NULLIF(ST_Area(ct.geom::geography), 0)
                    ), 0.0) AS population
                FROM ring_geoms rg
                JOIN census_tracts ct ON ST_Intersects(rg.ring_geom, ct.geom)
                WHERE ct.population IS NOT NULL AND ct.population > 0
                GROUP BY rg.id
            )
            SELECT
                cc.parcel_id,
                cc.facility_count,
                cc.total_sqft,
                COALESCE(cp.population, 0) AS population,
                CASE
                    WHEN COALESCE(cp.population, 0) > 0
                    THEN ROUND((cc.total_sqft::float / cp.population)::numeric, 2)
                    ELSE NULL
                END AS sqft_per_person
            FROM competitor_counts cc
            LEFT JOIN census_pop cp ON cp.parcel_id = cc.parcel_id
        """),
        {"ids": parcel_ids, "radius_m": radius_m, "sqft_default": sqft_default},
    )
    rows = result.fetchall()

    output: dict[int, dict] = {}
    for row in rows:
        pid, _facility_count, _total_sqft, _population, sqft_per_person = row
        spp = float(sqft_per_person) if sqft_per_person is not None else None
        output[pid] = {
            "sqft_per_person": spp,
            "color": _saturation_color(spp),
        }

    return output


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _compute_single_ring(
    centroid_wkt: str,
    radius_miles: float,
    db: AsyncSession,
) -> RingResult:
    radius_m = radius_miles * _MILES_TO_METERS
    sqft_default = settings.competitor_sqft_default

    # Competitor count + total sq ft within radius
    result = await db.execute(
        text("""
            SELECT
                COUNT(*)::int AS facility_count,
                COALESCE(
                    SUM(COALESCE(sq_ft, :sqft_default)),
                    0
                )::int AS total_sqft
            FROM competitor_facilities
            WHERE ST_DWithin(
                geom::geography,
                ST_GeomFromText(:centroid_wkt, 4326)::geography,
                :radius_meters
            )
        """),
        {
            "centroid_wkt": centroid_wkt,
            "radius_meters": radius_m,
            "sqft_default": sqft_default,
        },
    )
    comp_row = result.fetchone()
    facility_count = comp_row[0] if comp_row else 0
    total_sqft = comp_row[1] if comp_row else 0

    # Population via census area-weighted interpolation
    population = await compute_population_in_ring(centroid_wkt, radius_miles, db)

    sqft_per_person: float | None = None
    if population > 0 and total_sqft > 0:
        sqft_per_person = round(total_sqft / population, 2)
    elif population > 0:
        sqft_per_person = 0.0

    return RingResult(
        radius_miles=radius_miles,
        population=round(population, 0),
        facility_count=facility_count,
        total_sqft=total_sqft,
        sqft_per_person=sqft_per_person,
    )


def _saturation_color(sqft_per_person: float | None) -> str:
    if sqft_per_person is None:
        return "gray"
    if sqft_per_person < settings.saturation_threshold_low:
        return "green"
    if sqft_per_person < settings.saturation_threshold_high:
        return "yellow"
    return "red"
