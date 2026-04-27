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
        text("SELECT ST_AsText(centroid) FROM parcels WHERE id = :id"),
        {"id": parcel_id},
    )
    row = result.fetchone()
    if not row or not row[0]:
        return None
    centroid_wkt = row[0]

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
    """
    if not parcel_ids:
        return {}

    # Get all centroids in one query
    result = await db.execute(
        text("""
            SELECT id, ST_AsText(centroid) as centroid_wkt
            FROM parcels
            WHERE id = ANY(:ids) AND centroid IS NOT NULL
        """),
        {"ids": parcel_ids},
    )
    rows = result.fetchall()

    output: dict[int, dict] = {}
    for row in rows:
        pid, centroid_wkt = row[0], row[1]
        ring = await _compute_single_ring(centroid_wkt, ring_miles, db)
        output[pid] = {
            "sqft_per_person": ring.sqft_per_person,
            "color": _saturation_color(ring.sqft_per_person),
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
