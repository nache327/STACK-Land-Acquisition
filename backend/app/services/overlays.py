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

import json
import logging
import urllib.parse
import uuid

import httpx
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
    # Skip if no parcels still need flood data
    unset = await db.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM parcels WHERE jurisdiction_id = :jid AND geom IS NOT NULL AND in_flood_zone IS NULL)"
    ), {"jid": jurisdiction_id})
    if not unset:
        logger.info("Flood overlay already complete for %s — skipping API call", jurisdiction_id)
        return 0

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
    # Skip if no parcels still need wetland data
    unset = await db.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM parcels WHERE jurisdiction_id = :jid AND geom IS NOT NULL AND in_wetland IS NULL)"
    ), {"jid": jurisdiction_id})
    if not unset:
        logger.info("Wetland overlay already complete for %s — skipping API call", jurisdiction_id)
        return 0

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

    Builds a single unary_union in Python then issues ONE UPDATE — avoids the
    N/250 round-trips the old batched approach required.
    """
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

    result = await db.execute(
        text(f"""
            UPDATE parcels
            SET {column} = TRUE
            WHERE jurisdiction_id = :jid
              AND geom IS NOT NULL
              AND COALESCE({column}, FALSE) IS DISTINCT FROM TRUE
              AND ST_Intersects(geom, ST_GeomFromText(:geom, 4326))
        """),
        {"jid": str(jurisdiction_id), "geom": union.wkt},
    )
    await db.flush()
    return result.rowcount or 0


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


# ─── AADT overlay ─────────────────────────────────────────────────────────────

# OSM highway class → estimated AADT (annual average daily traffic)
_HIGHWAY_AADT: dict[str, int] = {
    "motorway":       50_000,
    "motorway_link":  30_000,
    "trunk":          50_000,
    "trunk_link":     30_000,
    "primary":        25_000,
    "primary_link":   15_000,
    "secondary":      12_000,
    "secondary_link":  8_000,
    "tertiary":        5_000,
    "tertiary_link":   3_000,
    "residential":     2_000,
    "living_street":   1_000,
    "service":         1_000,
    "unclassified":    1_000,
}

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


async def apply_aadt_overlay(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Assign estimated AADT to parcels based on the nearest OSM road within ~150 m.

    Uses a single Overpass API call to download all major roads in the jurisdiction
    bbox, then a single PostGIS UPDATE to assign each parcel the AADT of its
    closest road (highest class wins when multiple roads are equidistant).

    Returns the number of parcels updated.
    """
    bbox = await get_parcel_bbox(jurisdiction_id, db)
    if bbox is None:
        logger.warning("No parcel bbox for %s — skipping AADT overlay", jurisdiction_id)
        return 0

    # bbox = [minLng, minLat, maxLng, maxLat]
    west, south, east, north = bbox

    overpass_query = (
        f"[out:json][timeout:60];"
        f'way({south},{west},{north},{east})'
        f'[highway~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link'
        f'|secondary|secondary_link|tertiary|tertiary_link|residential|living_street'
        f'|service|unclassified)$"];'
        f"out tags center;"
    )

    logger.info("Querying Overpass API for roads in bbox %s …", bbox)
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                _OVERPASS_URL,
                content=f"data={urllib.parse.quote(overpass_query)}".encode(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "ParcelLogic/1.0",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Overpass API query failed (non-fatal): %s", exc)
        return 0

    elements = data.get("elements", [])
    if not elements:
        logger.info("No roads found in Overpass response for %s", jurisdiction_id)
        return 0

    # Build list of (lng, lat, aadt) for each road center point
    road_rows: list[tuple[float, float, int]] = []
    for el in elements:
        hw = (el.get("tags") or {}).get("highway", "")
        aadt_val = _HIGHWAY_AADT.get(hw)
        if aadt_val is None:
            continue
        center = el.get("center")
        if not center:
            continue
        road_rows.append((center["lon"], center["lat"], aadt_val))

    if not road_rows:
        logger.info("No mappable road centers found for %s", jurisdiction_id)
        return 0

    logger.info("Assigning AADT from %d road segments to parcels in %s …", len(road_rows), jurisdiction_id)

    # Write roads to a temp table in batches to avoid a single massive SQL string
    await db.execute(text(
        "CREATE TEMPORARY TABLE IF NOT EXISTS _aadt_roads "
        "(lng double precision, lat double precision, aadt integer)"
    ))
    await db.execute(text("TRUNCATE _aadt_roads"))

    BATCH = 500
    for i in range(0, len(road_rows), BATCH):
        batch = road_rows[i : i + BATCH]
        vals = ", ".join(f"({lng}, {lat}, {aadt})" for lng, lat, aadt in batch)
        await db.execute(text(f"INSERT INTO _aadt_roads VALUES {vals}"))

    result = await db.execute(
        text("""
            WITH best AS (
                SELECT DISTINCT ON (p.id)
                    p.id AS parcel_id,
                    r.aadt
                FROM parcels p
                JOIN _aadt_roads r
                  ON ST_DWithin(
                       COALESCE(p.centroid, ST_Centroid(p.geom))::geography,
                       ST_SetSRID(ST_MakePoint(r.lng, r.lat), 4326)::geography,
                       150
                     )
                WHERE p.jurisdiction_id = :jid
                  AND (p.centroid IS NOT NULL OR p.geom IS NOT NULL)
                ORDER BY p.id, r.aadt DESC
            )
            UPDATE parcels p
            SET aadt = best.aadt
            FROM best
            WHERE p.id = best.parcel_id
        """),
        {"jid": str(jurisdiction_id)},
    )
    await db.flush()
    updated = result.rowcount or 0
    logger.info("AADT overlay: %d parcels updated for %s", updated, jurisdiction_id)
    return updated
