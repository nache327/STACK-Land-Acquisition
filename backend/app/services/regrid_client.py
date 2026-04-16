"""
Regrid API v2 client — nationwide parcel fallback.

Used when ArcGIS layer discovery fails or the jurisdiction has no public GIS.
Requires REGRID_API_KEY in environment (.env / Docker Compose env_file).

API docs: https://regrid.com/developers
Pricing:  charged per parcel; enable only when you have a key.

Field mapping (Regrid → our ingestion layer column names):
  parcelnumb  → APN
  mailadd     → PROP_LOC
  zoning      → ZONING
  ll_gisacre  → CALC_ACRE
  owner       → OWNER_NAME
  improvval   → used to infer has_structure
"""
from __future__ import annotations

import logging

import geopandas as gpd
import httpx
from shapely.geometry import shape

from app.config import settings

logger = logging.getLogger(__name__)

_REGRID_BASE = "https://app.regrid.com"
_PAGE_LIMIT = 1_000


async def download_parcels_by_path(path: str) -> gpd.GeoDataFrame:
    """
    Fetch all parcels for a Regrid path (e.g. "ut/salt_lake/draper").

    Pages through the /api/v2/parcels/path endpoint until exhausted.

    Raises:
        RuntimeError: If REGRID_API_KEY is not configured.
        httpx.HTTPStatusError: On API errors (bad key, path not found, etc.).
        RuntimeError: If no parcels are returned.
    """
    if not settings.regrid_enabled:
        raise RuntimeError(
            "REGRID_API_KEY is not configured. "
            "Add REGRID_API_KEY=<your-key> to backend/.env to enable the Regrid fallback."
        )

    features: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(
        base_url=_REGRID_BASE,
        headers={"Authorization": f"Token {settings.regrid_api_key}"},
        timeout=60.0,
    ) as client:
        while True:
            resp = await client.get(
                "/api/v2/parcels/path",
                params={
                    "path": path,
                    "limit": _PAGE_LIMIT,
                    "offset": offset,
                    "return_geometry": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("parcels", {}).get("features", [])
            features.extend(batch)
            logger.info("Regrid: fetched %d parcels (offset=%d)", len(features), offset)

            if len(batch) < _PAGE_LIMIT:
                break  # last page
            offset += _PAGE_LIMIT

    if not features:
        raise RuntimeError(
            f"Regrid returned 0 parcels for path {path!r}. "
            "Verify the path format: state/county_slug/city_slug (e.g. ut/salt_lake/draper)."
        )

    logger.info("Regrid: converting %d features to GeoDataFrame", len(features))
    return _features_to_gdf(features)


def _features_to_gdf(features: list[dict]) -> gpd.GeoDataFrame:
    """
    Convert Regrid GeoJSON features to a GeoDataFrame with column names
    that our ingestion layer already recognises (_APN_FIELDS, _ADDRESS_FIELDS, etc.).
    """
    records = []
    geometries = []

    for feat in features:
        props = feat.get("properties", {})
        geom_dict = feat.get("geometry")

        # Map Regrid fields to canonical names used by ingestion._first()
        records.append({
            "APN": props.get("parcelnumb") or props.get("ll_uuid", ""),
            "PROP_LOC": props.get("mailadd"),
            "ZONING": props.get("zoning"),
            "CALC_ACRE": props.get("ll_gisacre"),
            "OWNER_NAME": props.get("owner"),
            # improvval > 0 → parcel has an improvement (structure)
            "LANDUSE": "IMPROVED" if (props.get("improvval") or 0) > 0 else None,
        })
        geometries.append(shape(geom_dict) if geom_dict else None)

    return gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
