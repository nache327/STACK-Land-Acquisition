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
  5. Bulk-UPDATE parcels where parcel geometry intersects the union geometry.
"""
from __future__ import annotations

import logging
import uuid

from geoalchemy2 import WKTElement
from shapely.ops import unary_union
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.arcgis_bbox import download_bbox_features, get_parcel_bbox
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
    bbox = await get_parcel_bbox(jurisdiction_id, db)
    if bbox is None:
        logger.warning("No parcel bbox for jurisdiction %s — skipping flood overlay", jurisdiction_id)
        return 0

    layer_url = settings.fema_nfhl_url.rstrip("/") + f"/{_NFHL_LAYER}"
    logger.info("Querying FEMA NFHL flood zones for bbox %s …", bbox)

    # Pre-filter to SFHA zones server-side — reduces page count and avoids HTTP 500
    # on FEMA's service when paginating all flood zone types over large urban bboxes.
    sfha_where = "FLD_ZONE IN ('A','AE','AH','AO','AR','V','VE')"
    try:
        gdf = await download_bbox_features(layer_url, bbox, where=sfha_where)
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
    bbox = await get_parcel_bbox(jurisdiction_id, db)
    if bbox is None:
        return 0

    layer_url = settings.usfws_nwi_url.rstrip("/") + f"/{_NWI_LAYER}"
    logger.info("Querying USFWS NWI wetlands for bbox %s …", bbox)

    try:
        gdf = await download_bbox_features(layer_url, bbox)
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

async def _bulk_flag_by_geometry(
    jurisdiction_id: uuid.UUID,
    gdf,
    column: str,
    db: AsyncSession,
) -> int:
    """
    Update parcels.{column} = TRUE for all parcels whose geometry intersects
    the union of the provided GeoDataFrame geometries.
    """
    import asyncio

    valid_geoms = [
        g.simplify(0.00001, preserve_topology=True)
        for g in gdf.geometry.dropna()
        if g is not None and not g.is_empty
    ]
    if not valid_geoms:
        return 0

    total = 0
    batch_size = 250
    for offset in range(0, len(valid_geoms), batch_size):
        union = unary_union(valid_geoms[offset : offset + batch_size])
        if union is None or union.is_empty:
            continue

        result = await db.execute(
            text(f"""
                UPDATE parcels
                SET {column} = TRUE
                WHERE jurisdiction_id = :jid
                  AND geom IS NOT NULL
                  AND COALESCE({column}, FALSE) IS DISTINCT FROM TRUE
                  AND ST_Intersects(geom, ST_GeomFromText(:geom, 4326))
            """),
            {"jid": jurisdiction_id, "geom": union.wkt},
        )
        total += result.rowcount or 0

    await db.flush()
    return total


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
