"""
Environmental overlay service — Phase 4 full implementation.

Computes in_flood_zone and in_wetland flags for all parcels in a jurisdiction
via spatial join against FEMA NFHL and USFWS NWI ArcGIS FeatureServices.

avg_slope_pct is computed from USGS 3DEP DEM tiles (deferred to Phase 7 —
requires rasterstats and DEM tile download; stubbed here).

Approach:
  1. Get parcel bbox for the jurisdiction from PostGIS.
  2. Query the overlay ArcGIS service within that bbox.
  3. Take the unary_union of all returned hazard polygons.
  4. Bulk-UPDATE parcels where centroid falls within the union geometry.
"""
from __future__ import annotations

import logging
import uuid

from shapely.ops import unary_union
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

# FEMA Special Flood Hazard Area zone codes (100-year floodplain)
SFHA_ZONES: frozenset[str] = frozenset({"A", "AE", "AH", "AO", "AR", "V", "VE"})

# Slope threshold for "steep" classification (percent)
STEEP_SLOPE_PCT: float = 15.0

# FEMA NFHL layer 28 = S_Fld_Haz_Ar (Special Flood Hazard Areas)
_NFHL_LAYER = 28
# USFWS NWI layer 1 = Wetlands
_NWI_LAYER = 1


# ─── Public API ──────────────────────────────────────────────────────────────

async def apply_flood_overlay(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Spatial join parcels against FEMA NFHL Special Flood Hazard Area polygons.
    Sets in_flood_zone = TRUE on matching parcels.
    Returns number of parcels updated.
    """
    bbox = await _get_bbox(jurisdiction_id, db)
    if bbox is None:
        logger.warning("No parcel bbox for jurisdiction %s — skipping flood overlay", jurisdiction_id)
        return 0

    layer_url = settings.fema_nfhl_url.rstrip("/") + f"/{_NFHL_LAYER}"
    logger.info("Querying FEMA NFHL flood zones for bbox %s …", bbox)

    try:
        gdf = await _download_bbox_features(layer_url, bbox)
    except Exception as exc:
        logger.warning("FEMA NFHL query failed (non-fatal): %s", exc)
        return 0

    if gdf is None or gdf.empty:
        logger.info("No FEMA flood zone features in bbox — all parcels non-flood")
        return 0

    # Filter to SFHA zones only
    fld_col = next(
        (c for c in gdf.columns if c.upper() in ("FLD_ZONE", "ZONE", "FLOOD_ZONE")),
        None,
    )
    if fld_col:
        gdf = gdf[gdf[fld_col].str.upper().isin(SFHA_ZONES)]

    if gdf.empty:
        return 0

    count = await _bulk_flag_by_geometry(
        jurisdiction_id, gdf, column="in_flood_zone", db=db
    )
    logger.info("Flood overlay: %d parcels flagged in %s", count, jurisdiction_id)
    return count


async def apply_wetland_overlay(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Spatial join parcels against USFWS NWI wetland polygons.
    Sets in_wetland = TRUE on matching parcels.
    Returns number of parcels updated.
    """
    bbox = await _get_bbox(jurisdiction_id, db)
    if bbox is None:
        return 0

    layer_url = settings.usfws_nwi_url.rstrip("/") + f"/{_NWI_LAYER}"
    logger.info("Querying USFWS NWI wetlands for bbox %s …", bbox)

    try:
        gdf = await _download_bbox_features(layer_url, bbox)
    except Exception as exc:
        logger.warning("USFWS NWI query failed (non-fatal): %s", exc)
        return 0

    if gdf is None or gdf.empty:
        return 0

    count = await _bulk_flag_by_geometry(
        jurisdiction_id, gdf, column="in_wetland", db=db
    )
    logger.info("Wetland overlay: %d parcels flagged in %s", count, jurisdiction_id)
    return count


async def apply_slope_overlay(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    dem_cache_dir: str = "/tmp/dem_cache",
) -> int:
    """
    Compute per-parcel mean slope % from USGS 3DEP 10 m DEM.
    Deferred to Phase 7 — requires rasterstats + DEM tile download.
    """
    logger.info("Slope overlay deferred to Phase 7 — skipping for jurisdiction %s", jurisdiction_id)
    return 0


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_bbox(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[float, float, float, float] | None:
    """Return (minX, minY, maxX, maxY) bounding box of all parcels in EPSG:4326."""
    result = await db.execute(
        text("""
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels
            WHERE jurisdiction_id = :jid
              AND geom IS NOT NULL
        """),
        {"jid": jurisdiction_id},
    )
    row = result.one_or_none()
    if row is None or row.minx is None:
        return None
    return (float(row.minx), float(row.miny), float(row.maxx), float(row.maxy))


async def _download_bbox_features(url: str, bbox: tuple[float, float, float, float]):
    """
    Download all features from an ArcGIS FeatureServer within the given bbox.
    Uses the ArcGIS geometry filter (esriGeometryEnvelope).
    """
    import asyncio
    import httpx
    import geopandas as gpd

    minx, miny, maxx, maxy = bbox
    # Add 10% buffer so edge-parcels don't miss overlapping flood/wetland zones
    dx = (maxx - minx) * 0.1
    dy = (maxy - miny) * 0.1
    geom_filter = f"{minx - dx},{miny - dy},{maxx + dx},{maxy + dy}"

    params = {
        "geometry": geom_filter,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
        "outSR": "4326",
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": 2000,
    }
    query_url = url.rstrip("/") + "/query"

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        resp = await client.get(query_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    if not features:
        return None

    return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")


async def _bulk_flag_by_geometry(
    jurisdiction_id: uuid.UUID,
    gdf,
    column: str,
    db: AsyncSession,
) -> int:
    """
    Update parcels.{column} = TRUE for all parcels whose centroid falls within
    the union of the provided GeoDataFrame geometries.
    """
    import asyncio

    # Build union of overlay polygons.
    # Simplify to ~10 m precision first — dramatically reduces vertex count and
    # WKT string size, which is the main source of slowness on large datasets.
    valid_geoms = [
        g.simplify(0.0001, preserve_topology=True)
        for g in gdf.geometry.dropna()
        if g is not None and not g.is_empty
    ]
    if not valid_geoms:
        return 0

    union = unary_union(valid_geoms)
    if union is None or union.is_empty:
        return 0

    wkt = union.wkt

    result = await db.execute(
        text(f"""
            UPDATE parcels
            SET {column} = TRUE
            WHERE jurisdiction_id = :jid
              AND centroid IS NOT NULL
              AND ST_Within(centroid, ST_GeomFromText(:geom, 4326))
        """),
        {"jid": jurisdiction_id, "geom": wkt},
    )
    await db.flush()
    return result.rowcount
