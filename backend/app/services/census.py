"""
US Census ACS population data service.

Fetches census tract geometries (TIGER/Line shapefiles) and population estimates
(ACS 5-year API) for a bounding box and caches them in the census_tracts table.
Data is re-fetched if older than 90 days.

Population within a radius is computed via area-weighted areal interpolation:
  estimated_population = SUM(tract_population * overlap_area / tract_area)
across all census tracts that intersect the radius circle.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

import geopandas as gpd
import httpx
from geoalchemy2 import WKTElement
from shapely.geometry import MultiPolygon
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# TIGER/Line shapefiles hosted at Census Bureau FTP — works from cloud IPs.
# TigerWeb ArcGIS REST API blocks Railway outbound IPs.
_TIGER_BASE = "https://www2.census.gov/geo/tiger/TIGER2022/TRACT"
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

    # Check if we have fresh coverage for this bbox with population data.
    # Filter on population IS NOT NULL — older fetches may have inserted
    # geometries without successfully merging ACS population (e.g. ACS API
    # timed out partway through a batch). Treat those rows as not-cached so
    # a refetch heals them via the ON CONFLICT DO UPDATE upsert below.
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM census_tracts
            WHERE fetched_at > :cutoff
              AND population IS NOT NULL
              AND ST_Intersects(
                geom,
                ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
              )
        """),
        {"cutoff": cutoff, "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
    )
    existing = result.scalar() or 0

    # discipline-catch #16: presence != completeness. The bbox ST_Intersects
    # check above also counts NEIGHBORING-county tracts already loaded from
    # other jurisdictions, so a target whose OWN tracts are absent still tripped
    # the old `if existing > 0: return` cache path. Westchester loaded only 14
    # of ~223 tracts because 111 adjacent NYC/Bergen/Rockland tracts intersected
    # its bbox. Always fetch the full bbox set + upsert (idempotent via
    # ON CONFLICT DO UPDATE); one job-level Census call, negligible vs the
    # isochrone pass it precedes — guarantees complete coverage regardless of
    # partial prior loads. (Forward risk this prevents: the Maryland MDP
    # statewide bbox would intersect thousands of pre-loaded tracts and skip.)
    logger.info(
        "Census tracts: %d already intersect bbox; fetching full set to ensure "
        "complete coverage (presence != completeness)", existing,
    )
    tracts = await _fetch_tracts_with_population(bbox)

    if not tracts:
        # Fetch failed/empty — keep whatever coverage we already have rather
        # than reporting zero (don't regress a populated bbox on a transient).
        logger.warning(
            "No census tracts returned for bbox %s; keeping %d existing", bbox, existing,
        )
        return existing

    # Bulk upsert with ON CONFLICT DO NOTHING to handle concurrent requests
    # inserting the same tracts simultaneously (race condition on geoid unique constraint).
    for t in tracts:
        await db.execute(
            text("""
                INSERT INTO census_tracts
                    (geoid, state_fips, county_fips, tract_fips, name, population, geom, fetched_at)
                VALUES
                    (:geoid, :state_fips, :county_fips, :tract_fips, :name, :population,
                     ST_GeomFromText(:wkt, 4326), NOW())
                ON CONFLICT (geoid) DO UPDATE SET
                    population = EXCLUDED.population,
                    geom = EXCLUDED.geom,
                    fetched_at = EXCLUDED.fetched_at
            """),
            {
                "geoid": t["geoid"],
                "state_fips": t["geoid"][:2],
                "county_fips": t["geoid"][2:5],
                "tract_fips": t["geoid"][5:],
                "name": t.get("name"),
                "population": t.get("population"),
                "wkt": t["wkt"],
            },
        )

    await db.flush()
    logger.info("Cached %d census tracts for bbox %s", len(tracts), bbox)
    return len(tracts)


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
    Fetch census tract geometries from TIGER/Line shapefiles + population from ACS API.
    Returns list of dicts: {geoid, name, population, wkt}.
    """
    xmin, ymin, xmax, ymax = bbox

    # Step 1: determine which state covers this bbox via Census geocoder
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    state_fips = await _geocode_state_fips(cx, cy)
    if not state_fips:
        logger.warning("Could not determine state FIPS for bbox %s", bbox)
        return []

    # Step 2: download TIGER/Line shapefile and extract tracts in bbox
    geom_data = await _fetch_tiger_tracts_for_state(state_fips, xmin, ymin, xmax, ymax)

    if not geom_data:
        return []

    # Step 3: collect unique state+county combinations to query ACS API
    state_county_pairs: set[tuple[str, str]] = set()
    for tract in geom_data:
        geoid = tract["geoid"]
        state_county_pairs.add((geoid[:2], geoid[2:5]))

    # Step 4: fetch population from ACS API for each state+county
    pop_map: dict[str, int] = {}
    for state_fips, county_fips in state_county_pairs:
        pops = await _fetch_acs_population(state_fips, county_fips)
        pop_map.update(pops)

    # Step 5: merge geometries with population
    result = []
    for tract in geom_data:
        geoid = tract["geoid"]
        tract["population"] = pop_map.get(geoid)
        result.append(tract)

    return result



async def _geocode_state_fips(lon: float, lat: float) -> str | None:
    """Use Census Geocoder to determine state FIPS for a coordinate."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
                params={
                    "x": lon, "y": lat,
                    "benchmark": "Public_AR_Current",
                    "vintage": "Current_Current",
                    "layers": "States",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            states = data.get("result", {}).get("geographies", {}).get("States", [])
            if states:
                return states[0].get("STATE")
    except Exception as exc:
        logger.warning("Census geocoder failed: %s", exc)
    return None


async def _fetch_tiger_tracts_for_state(
    state_fips: str,
    xmin: float, ymin: float, xmax: float, ymax: float,
) -> list[dict]:
    """
    Download TIGER/Line tract shapefile ZIP for the given state from Census Bureau,
    spatial-filter to bbox, return list of {geoid, name, wkt}.
    """
    url = f"{_TIGER_BASE}/tl_2022_{state_fips}_tract.zip"
    logger.warning("Downloading TIGER/Line tracts for state %s from %s", state_fips, url)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            zip_bytes = resp.content
    except Exception as exc:
        logger.warning("TIGER/Line download failed for state %s: %s", state_fips, exc)
        return []

    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(zip_bytes)
            tmp_path = tmp.name
        try:
            gdf = gpd.read_file(f"zip://{tmp_path}")
        finally:
            os.unlink(tmp_path)
    except Exception as exc:
        logger.warning("TIGER/Line parse failed for state %s: %s", state_fips, exc)
        return []

    from shapely.geometry import box as shapely_box
    bbox_geom = shapely_box(xmin, ymin, xmax, ymax)
    gdf = gdf[gdf.geometry.intersects(bbox_geom)]

    logger.warning("TIGER/Line state %s: %d tracts in bbox", state_fips, len(gdf))

    tracts = []
    for _, row in gdf.iterrows():
        geoid = str(row.get("GEOID", "") or row.get("GEOID20", ""))
        if len(geoid) != 11:
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        tracts.append({
            "geoid": geoid,
            "name": str(row.get("NAME", "") or row.get("NAMELSAD", "")),
            "wkt": geom.wkt,
        })

    return tracts




async def _fetch_acs_population(state_fips: str, county_fips: str) -> dict[str, int]:
    """
    Fetch ACS 5-year total population (B01003_001E) for all tracts in a county.
    Returns {geoid: population} mapping.
    """
    from app.config import settings

    params: dict = {
        "get": "B01003_001E,GEO_ID",
        "for": "tract:*",
        "in": f"state:{state_fips} county:{county_fips}",
    }
    if settings.census_api_key:
        params["key"] = settings.census_api_key

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
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
