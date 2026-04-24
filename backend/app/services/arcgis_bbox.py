"""
ArcGIS bbox query helpers shared by overlays and recovery backfills.
"""
from __future__ import annotations

import logging
import uuid

import geopandas as gpd
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_parcel_bbox(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[float, float, float, float] | None:
    """Return (minx, miny, maxx, maxy) for a jurisdiction's parcel geometry."""
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
        {"jid": jurisdiction_id},
    )
    row = result.one_or_none()
    if row is None or row.minx is None:
        return None
    return (float(row.minx), float(row.miny), float(row.maxx), float(row.maxy))


async def download_bbox_features(
    url: str,
    bbox: tuple[float, float, float, float],
    *,
    where: str = "1=1",
    page_size: int = 500,
    buffer_ratio: float = 0.1,
) -> gpd.GeoDataFrame | None:
    """
    Download all features intersecting a bbox from an ArcGIS layer.

    The bbox is buffered slightly so edge-touching features are not lost on
    source systems that clip or quantize geometry aggressively.
    """
    minx, miny, maxx, maxy = bbox
    dx = (maxx - minx) * buffer_ratio
    dy = (maxy - miny) * buffer_ratio
    geom_filter = f"{minx - dx},{miny - dy},{maxx + dx},{maxy + dy}"
    query_url = url.rstrip("/") + "/query"

    all_features: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        while True:
            params = {
                "geometry": geom_filter,
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": "4326",
                "outSR": "4326",
                "outFields": "*",
                "where": where,
                "f": "geojson",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            }
            resp = await client.get(query_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("features", [])
            if not batch:
                break

            all_features.extend(batch)
            logger.info(
                "ArcGIS bbox fetch %s: %d features collected (offset=%d)",
                url,
                len(all_features),
                offset,
            )
            if len(batch) < page_size:
                break
            offset += page_size
            if offset > 200_000:
                logger.warning("ArcGIS bbox fetch hit safety cap at offset %d", offset)
                break

    if not all_features:
        return None

    return gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
