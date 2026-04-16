"""
ArcGIS FeatureServer query client.

Pulls parcel and zoning polygon features from ArcGIS REST FeatureServers in
pages (default 1 000 features per request) and converts them to GeoDataFrames.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Default page size for ArcGIS /query requests.
# Most FeatureServers cap at 1 000 or 2 000 per request.
_PAGE_SIZE = 1_000


async def query_feature_layer(
    endpoint_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    result_offset: int = 0,
    result_record_count: int = _PAGE_SIZE,
) -> dict[str, Any]:
    """
    Single paged /query call to an ArcGIS FeatureServer layer.
    Returns the raw GeoJSON response dict.
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "outSR": out_sr,
        "f": "geojson",
        "resultOffset": result_offset,
        "resultRecordCount": result_record_count,
        "returnGeometry": "true",
    }
    url = endpoint_url.rstrip("/") + "/query"
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_layer_count(endpoint_url: str, where: str = "1=1") -> int:
    """Return total feature count for a layer (used to drive pagination)."""
    params: dict[str, str | int] = {
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }
    url = endpoint_url.rstrip("/") + "/query"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return int(data.get("count", 0))


async def get_layer_metadata(endpoint_url: str) -> dict[str, Any]:
    """
    Fetch the layer metadata JSON (fields, geometry type, name, etc.)
    Used by arcgis_discovery to identify layer purposes.
    """
    url = endpoint_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, params={"f": "json"})
        resp.raise_for_status()
        return resp.json()


async def download_all_features(
    endpoint_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = _PAGE_SIZE,
    progress_callback: Any = None,
) -> gpd.GeoDataFrame:
    """
    Download ALL features from an ArcGIS FeatureServer layer by paginating
    through results. Returns a GeoDataFrame in EPSG:4326.

    Args:
        endpoint_url: Full URL to the FeatureServer layer (e.g., .../FeatureServer/11)
        where: SQL WHERE clause filter (default "1=1" = all features)
        out_fields: Comma-separated field names, or "*" for all
        page_size: Max features per request (most servers cap at 1 000–2 000)
        progress_callback: Optional async callable(downloaded, total) for progress

    Returns:
        GeoDataFrame with all features, CRS = EPSG:4326.
        Empty GeoDataFrame if no features returned.

    Raises:
        httpx.HTTPStatusError: On non-2xx response from the FeatureServer.
        ValueError: If the layer returns no usable features.
    """
    logger.info("Getting feature count from %s", endpoint_url)
    total = await get_layer_count(endpoint_url, where)
    logger.info("Total features to download: %d", total)

    if total == 0:
        return gpd.GeoDataFrame()

    pages = math.ceil(total / page_size)
    gdfs: list[gpd.GeoDataFrame] = []
    downloaded = 0

    for page_idx in range(pages):
        offset = page_idx * page_size
        logger.debug("Fetching page %d/%d (offset=%d)", page_idx + 1, pages, offset)

        data = await query_feature_layer(
            endpoint_url,
            where=where,
            out_fields=out_fields,
            result_offset=offset,
            result_record_count=page_size,
        )

        features = data.get("features", [])
        if not features:
            logger.warning("Empty page at offset %d — stopping pagination", offset)
            break

        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        gdfs.append(gdf)
        downloaded += len(features)
        logger.info("Downloaded %d / %d features", downloaded, total)

        if progress_callback is not None:
            await progress_callback(downloaded, total)

        # Brief pause to be polite to the ArcGIS server
        if page_idx < pages - 1:
            await asyncio.sleep(0.1)

    if not gdfs:
        return gpd.GeoDataFrame()

    combined = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True), crs="EPSG:4326"
    )
    logger.info(
        "Downloaded %d total features from %s", len(combined), endpoint_url
    )
    return combined
