"""
Environmental overlay service.

Computes in_flood_zone and in_wetland flags for all parcels in a jurisdiction
via spatial join against FEMA NFHL and USFWS NWI ArcGIS FeatureServices, and
persists the hazard polygons into the `overlays` table for map rendering.

Approach:
  1. Get parcel bbox for the jurisdiction from PostGIS.
  2. Query the overlay ArcGIS service within that bbox.
  3. Persist polygons into the overlays table (one row per source feature).
  4. Take the unary_union of all returned hazard polygons.
  5. Bulk-UPDATE parcels where centroid falls within the union geometry.
"""
from __future__ import annotations

import logging
import uuid

from geoalchemy2 import WKTElement
from shapely.ops import unary_union
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.overlay import Overlay, OverlayType

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

# FEMA Special Flood Hazard Area zone codes (100-year floodplain)
SFHA_ZONES: frozenset[str] = frozenset({"A", "AE", "AH", "AO", "AR", "V", "VE"})

# FEMA NFHL layer 28 = S_Fld_Haz_Ar (Special Flood Hazard Areas)
_NFHL_LAYER = 28
# USFWS NWI layer 0 = Wetlands (AGOL USA_Wetlands FeatureServer)
_NWI_LAYER = 0


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

    # Pre-filter to SFHA zones server-side — reduces page count and avoids HTTP 500
    # on FEMA's service when paginating all flood zone types over large urban bboxes.
    sfha_where = "FLD_ZONE IN ('A','AE','AH','AO','AR','V','VE')"
    try:
        gdf = await _download_bbox_features(layer_url, bbox, where=sfha_where)
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

    # Persist polygons into overlays table (for map rendering via pg_tileserv)
    await _persist_overlay_polygons(
        jurisdiction_id=jurisdiction_id,
        gdf=gdf,
        overlay_type=OverlayType.flood_sfha,
        source="FEMA NFHL S_Fld_Haz_Ar",
        db=db,
    )

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

    await _persist_overlay_polygons(
        jurisdiction_id=jurisdiction_id,
        gdf=gdf,
        overlay_type=OverlayType.wetland_nwi,
        source="USFWS NWI Wetlands",
        db=db,
    )

    count = await _bulk_flag_by_geometry(
        jurisdiction_id, gdf, column="in_wetland", db=db
    )
    logger.info("Wetland overlay: %d parcels flagged in %s", count, jurisdiction_id)
    return count


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


async def _download_bbox_features(
    url: str,
    bbox: tuple[float, float, float, float],
    where: str = "1=1",
):
    """
    Paginate through all features from an ArcGIS FeatureServer within the given
    bbox. Asking for too many records at once returns HTTP 500 from FEMA NFHL
    over large urban bboxes, so we request 500 per page and loop via
    resultOffset until the server stops returning features.

    Pass a server-side ``where`` clause to pre-filter features (e.g. SFHA zones
    only for FEMA) so each page stays well under the server's result limit.
    """
    import httpx
    import geopandas as gpd

    minx, miny, maxx, maxy = bbox
    # Add 10% buffer so edge-parcels don't miss overlapping flood/wetland zones
    dx = (maxx - minx) * 0.1
    dy = (maxy - miny) * 0.1
    geom_filter = f"{minx - dx},{miny - dy},{maxx + dx},{maxy + dy}"

    page_size = 500
    all_features: list[dict] = []
    offset = 0
    query_url = url.rstrip("/") + "/query"

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
            try:
                resp = await client.get(query_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as page_exc:
                logger.warning(
                    "Overlay page fetch failed at offset=%d (returning %d features collected so far): %s",
                    offset, len(all_features), page_exc,
                )
                break

            batch = data.get("features", [])
            if not batch:
                break
            all_features.extend(batch)
            logger.info(
                "Overlay bbox fetch: %d features (offset=%d)",
                len(all_features), offset,
            )
            if len(batch) < page_size:
                break  # last page
            offset += page_size
            # Safety cap: most urban bboxes have <50k features; anything beyond
            # that is likely a misconfigured query.
            if offset > 200_000:
                logger.warning("Overlay page cap hit at offset %d", offset)
                break

    if not all_features:
        return None

    return gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")


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
    # Simplify to ~1 m precision — small enough not to misclassify urban parcels
    # (the 11 m tolerance used previously could shift flood boundaries off
    # narrow city lots).
    valid_geoms = [
        g.simplify(0.00001, preserve_topology=True)
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


async def _persist_overlay_polygons(
    *,
    jurisdiction_id: uuid.UUID,
    gdf,
    overlay_type: OverlayType,
    source: str,
    db: AsyncSession,
) -> int:
    """
    Upsert overlay polygons into the `overlays` table so they can be rendered
    as map layers via pg_tileserv. Replaces any existing rows of the same type
    for this jurisdiction.
    """
    # Clear prior rows for this (type, jurisdiction) pair
    await db.execute(
        delete(Overlay).where(
            Overlay.jurisdiction_id == jurisdiction_id,
            Overlay.overlay_type == overlay_type,
        )
    )

    rows: list[dict] = []
    for _, feat in gdf.iterrows():
        geom = feat.geometry
        if geom is None or geom.is_empty:
            continue
        # Collect non-geom attributes into JSONB
        attrs = {
            k: (str(v) if v is not None else None)
            for k, v in feat.items()
            if k != "geometry"
        }
        rows.append({
            "jurisdiction_id": jurisdiction_id,
            "overlay_type": overlay_type,
            "source": source,
            "attributes": attrs,
            "geom": WKTElement(geom.wkt, srid=4326),
        })

    if not rows:
        return 0

    await db.execute(insert(Overlay), rows)
    await db.flush()
    logger.info(
        "Persisted %d %s overlay polygons for %s",
        len(rows), overlay_type.value, jurisdiction_id,
    )
    return len(rows)
