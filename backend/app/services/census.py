"""
US Census ACS population data service.

Fetches census tract geometries (TigerWeb) and population estimates (ACS 5-year)
for a bounding box and caches them in the census_tracts table. Data is re-fetched
if older than 90 days.

Population within a radius is computed via area-weighted areal interpolation:
  estimated_population = SUM(tract_population * overlap_area / tract_area)
across all census tracts that intersect the radius circle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from geoalchemy2 import WKTElement
from shapely.geometry import mapping, shape
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

_TIGERWEB_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/TIGERweb/tigerWMS_ACS2022/MapServer/8/query"
)
_ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
_CACHE_TTL_DAYS = 90
_MILES_TO_METERS = 1609.344


# ── Public API ────────────────────────────────────────────────────────────────

async def ensure_census_tracts(
    bbox: tuple[float, float, float, float],
    db: AsyncSession,
) -> int:
    """
    Ensure census tracts are loaded for the given bbox. Fetches from Census API
    if not already cached or if cache is older than 90 days.
    Returns count of tracts available for the area.
    """
    xmin, ymin, xmax, ymax = bbox
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS)

    # Check if we have fresh coverage for this bbox
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM census_tracts
            WHERE fetched_at > :cutoff
              AND ST_Intersects(
                geom,
                ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
              )
        """),
        {"cutoff": cutoff, "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
    )
    existing = result.scalar() or 0

    if existing > 0:
        logger.info("Census tracts: %d cached tracts cover bbox", existing)
        return existing

    logger.info("Fetching census tracts for bbox %s from Census API …", bbox)
    tracts = await _fetch_tracts_with_population(bbox)

    if not tracts:
        logger.warning("No census tracts returned for bbox %s", bbox)
        return 0

    # Delete stale tracts for the area first
    await db.execute(
        text("""
            DELETE FROM census_tracts
            WHERE ST_Intersects(
              geom,
              ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
            )
        """),
        {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
    )

    rows = [
        CensusTract(
            geoid=t["geoid"],
            state_fips=t["geoid"][:2],
            county_fips=t["geoid"][2:5],
            tract_fips=t["geoid"][5:],
            name=t.get("name"),
            population=t.get("population"),
            geom=WKTElement(t["wkt"], srid=4326),
        )
        for t in tracts
    ]

    db.add_all(rows)
    await db.flush()
    logger.info("Cached %d census tracts for bbox %s", len(rows), bbox)
    return len(rows)


async def compute_population_in_ring(
    centroid_wkt: str,
    radius_miles: float,
    db: AsyncSession,
) -> float:
    """
    Estimate population within radius_miles of centroid_wkt using area-weighted
    areal interpolation against cached census tract geometries.
    Returns 0.0 if no tract data is available.
    """
    radius_m = radius_miles * _MILES_TO_METERS

    result = await db.execute(
        text("""
            WITH ring AS (
                SELECT ST_Buffer(
                    ST_GeomFromText(:centroid_wkt, 4326)::geography,
                    :radius_meters
                )::geometry AS geom
            ),
            tract_intersections AS (
                SELECT
                    ct.population,
                    ST_Area(ST_Intersection(ct.geom, ring.geom)::geography) AS intersect_area,
                    ST_Area(ct.geom::geography) AS tract_area
                FROM census_tracts ct, ring
                WHERE ST_Intersects(ct.geom, ring.geom)
                  AND ct.population IS NOT NULL
                  AND ct.population > 0
            )
            SELECT COALESCE(
                SUM(population::float * intersect_area / NULLIF(tract_area, 0)),
                0.0
            ) AS estimated_population
            FROM tract_intersections
        """),
        {"centroid_wkt": centroid_wkt, "radius_meters": radius_m},
    )
    row = result.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


# ── Census API fetchers ────────────────────────────────────────────────────────

async def _fetch_tracts_with_population(
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    """
    Fetch census tract geometries from TigerWeb + population from ACS API.
    Returns list of dicts: {geoid, name, population, wkt}.
    """
    xmin, ymin, xmax, ymax = bbox

    # Step 1: get tract geometries from TigerWeb (ArcGIS FeatureServer)
    geom_data = await _fetch_tigerweb_tracts(xmin, ymin, xmax, ymax)
    if not geom_data:
        return []

    # Step 2: collect unique state+county combinations to query ACS API
    state_county_pairs: set[tuple[str, str]] = set()
    for tract in geom_data:
        geoid = tract["geoid"]
        state_county_pairs.add((geoid[:2], geoid[2:5]))

    # Step 3: fetch population from ACS API for each state+county
    pop_map: dict[str, int] = {}
    for state_fips, county_fips in state_county_pairs:
        pops = await _fetch_acs_population(state_fips, county_fips)
        pop_map.update(pops)

    # Step 4: merge geometries with population
    result = []
    for tract in geom_data:
        geoid = tract["geoid"]
        tract["population"] = pop_map.get(geoid)
        result.append(tract)

    return result


async def _fetch_tigerweb_tracts(
    xmin: float, ymin: float, xmax: float, ymax: float
) -> list[dict]:
    """
    Query TigerWeb ACS2022 census tracts (layer 8) by bounding box.
    Returns list of {geoid, name, wkt}.
    """
    params = {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "GEOID,NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": "2000",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(_TIGERWEB_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("TigerWeb tracts query failed: %s", exc)
        return []

    tracts = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geoid = props.get("GEOID", "")
        if len(geoid) != 11:
            continue

        geom = feature.get("geometry")
        if not geom:
            continue

        try:
            shapely_geom = shape(geom)
            if shapely_geom.is_empty:
                continue
            # Ensure MultiPolygon
            if shapely_geom.geom_type == "Polygon":
                from shapely.geometry import MultiPolygon
                shapely_geom = MultiPolygon([shapely_geom])
            wkt = shapely_geom.wkt
        except Exception:
            continue

        tracts.append({
            "geoid": geoid,
            "name": props.get("NAME"),
            "wkt": wkt,
        })

    return tracts


async def _fetch_acs_population(state_fips: str, county_fips: str) -> dict[str, int]:
    """
    Fetch ACS 5-year total population (B01003_001E) for all tracts in a county.
    Returns {geoid: population} mapping.
    """
    params = {
        "get": "B01003_001E,GEO_ID",
        "for": "tract:*",
        "in": f"state:{state_fips} county:{county_fips}",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_ACS_URL, params=params)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as exc:
        logger.warning("ACS population query failed for %s/%s: %s", state_fips, county_fips, exc)
        return {}

    if not rows or len(rows) < 2:
        return {}

    # First row is headers
    headers = rows[0]
    try:
        pop_idx = headers.index("B01003_001E")
        state_idx = headers.index("state")
        county_idx = headers.index("county")
        tract_idx = headers.index("tract")
    except ValueError:
        return {}

    result: dict[str, int] = {}
    for row in rows[1:]:
        try:
            geoid = row[state_idx] + row[county_idx] + row[tract_idx]
            pop = int(row[pop_idx]) if row[pop_idx] not in (None, "-1", "") else 0
            result[geoid] = max(0, pop)
        except (ValueError, IndexError):
            continue

    return result
