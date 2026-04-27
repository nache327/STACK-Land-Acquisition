"""
Google Places competitor sync service.

Fetches self-storage facilities from Google Places API within a bounding box
and upserts them into the competitor_facilities table. KMZ-sourced records
take precedence — any Google Places result within 200 ft of a KMZ pin is
skipped (deduplication by proximity).
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Any

import httpx
from geoalchemy2 import WKTElement
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.competitor_facility import CompetitorFacility

logger = logging.getLogger(__name__)

_PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_DEDUP_RADIUS_METERS = 60  # 200 ft ≈ 61 m


# ── Public API ────────────────────────────────────────────────────────────────

async def upsert_google_competitors(
    bbox: tuple[float, float, float, float],
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Fetch Google Places self-storage results for the bbox, skip duplicates
    of KMZ records, and upsert into competitor_facilities.
    Returns count of rows inserted/updated.
    """
    if not settings.google_places_enabled:
        logger.info("GOOGLE_PLACES_API_KEY not set — skipping competitor sync")
        return 0

    places = await _search_all_pages(bbox, settings.google_places_api_key)
    if not places:
        logger.info("No Google Places results for bbox %s", bbox)
        return 0

    inserted = 0
    for place in places:
        place_id = place.get("place_id")
        if not place_id:
            continue

        loc = place.get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is None or lng is None:
            continue

        # Skip if a KMZ record is within 200 ft of this location
        if await _near_kmz_record(lat, lng, db):
            continue

        name = place.get("name", "")
        address = place.get("vicinity", "")
        sq_ft, sqft_source = await _estimate_sqft(place, db)

        stmt = pg_insert(CompetitorFacility).values(
            name=name,
            operator=None,
            address=address,
            sq_ft=sq_ft,
            sqft_source=sqft_source,
            data_source="google_places",
            external_id=place_id,
            attributes={
                "types": place.get("types"),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "business_status": place.get("business_status"),
            },
            geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
            jurisdiction_id=jurisdiction_id,
        ).on_conflict_do_update(
            index_where=(CompetitorFacility.external_id.isnot(None)),
            constraint=None,
            # Use the unique index on (data_source, external_id)
            set_=dict(
                name=name,
                address=address,
                sq_ft=sq_ft,
                sqft_source=sqft_source,
                jurisdiction_id=jurisdiction_id,
            ),
        )
        await db.execute(stmt)
        inserted += 1

    await db.flush()
    logger.info("Google Places: upserted %d competitor facilities", inserted)
    return inserted


async def delete_jurisdiction_google_competitors(
    jurisdiction_id: uuid.UUID, db: AsyncSession
) -> int:
    """Remove all Google Places competitors for a jurisdiction (used before re-sync)."""
    result = await db.execute(
        delete(CompetitorFacility).where(
            CompetitorFacility.jurisdiction_id == jurisdiction_id,
            CompetitorFacility.data_source == "google_places",
        )
    )
    return result.rowcount or 0


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _search_all_pages(
    bbox: tuple[float, float, float, float],
    api_key: str,
) -> list[dict[str, Any]]:
    """
    Query Google Places Nearby Search for the bbox.
    Splits large bboxes into sub-cells to stay within the 50km search radius.
    Paginates up to 3 pages (60 results) per sub-cell.
    """
    xmin, ymin, xmax, ymax = bbox
    # Google Places uses a center + radius. Split bbox into cells if it's large.
    cells = _split_bbox_into_cells(xmin, ymin, xmax, ymax, max_radius_km=40)

    all_results: list[dict] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=30) as client:
        for cell_lat, cell_lng, radius_m in cells:
            params = {
                "location": f"{cell_lat},{cell_lng}",
                "radius": str(int(radius_m)),
                "type": "storage",
                "keyword": "self storage",
                "key": api_key,
            }
            page = 0
            next_token: str | None = None

            while page < 3:
                if next_token:
                    params = {"pagetoken": next_token, "key": api_key}

                try:
                    resp = await client.get(_PLACES_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning("Google Places request failed: %s", exc)
                    break

                status = data.get("status")
                if status not in ("OK", "ZERO_RESULTS"):
                    logger.warning("Google Places status=%s for cell (%s,%s)", status, cell_lat, cell_lng)
                    break

                for result in data.get("results", []):
                    pid = result.get("place_id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        all_results.append(result)

                next_token = data.get("next_page_token")
                if not next_token:
                    break
                page += 1
                # Google requires a short delay before using next_page_token
                import asyncio
                await asyncio.sleep(2)

    logger.info("Google Places: fetched %d total results", len(all_results))
    return all_results


def _split_bbox_into_cells(
    xmin: float, ymin: float, xmax: float, ymax: float,
    max_radius_km: float = 40,
) -> list[tuple[float, float, float]]:
    """
    Returns list of (center_lat, center_lng, radius_m) cells that cover the bbox.
    Each cell is sized so its circumscribed circle fits within max_radius_km.
    """
    # Half-diagonal of a cell (in degrees) that fits in max_radius_km
    # 1 degree ≈ 111 km, so max half-size ≈ max_radius_km / 111 / sqrt(2)
    cell_half = max_radius_km / 111.0 / math.sqrt(2)

    cells = []
    lat = ymin + cell_half
    while lat <= ymax + cell_half:
        lng = xmin + cell_half
        while lng <= xmax + cell_half:
            clat = min(lat, ymax)
            clng = min(lng, xmax)
            # Convert degrees to meters for the radius parameter
            radius_m = min(max_radius_km * 1000, 50_000)
            cells.append((clat, clng, radius_m))
            lng += cell_half * 2
        lat += cell_half * 2

    return cells


async def _near_kmz_record(lat: float, lng: float, db: AsyncSession) -> bool:
    """Return True if any KMZ competitor is within DEDUP_RADIUS_METERS of this point."""
    result = await db.execute(
        text("""
            SELECT 1 FROM competitor_facilities
            WHERE data_source = 'kmz'
              AND ST_DWithin(
                geom::geography,
                ST_MakePoint(:lng, :lat)::geography,
                :radius
              )
            LIMIT 1
        """),
        {"lat": lat, "lng": lng, "radius": _DEDUP_RADIUS_METERS},
    )
    return result.fetchone() is not None


async def _estimate_sqft(place: dict, db: AsyncSession) -> tuple[int | None, str]:
    """
    Estimate square footage for a Google Places result.
    Priority: OSM building outline → Regrid parcel match → return None (use default).
    """
    # Try OSM building outline via Overpass
    loc = place.get("geometry", {}).get("location", {})
    lat, lng = loc.get("lat"), loc.get("lng")
    if lat and lng:
        sqft = await _osm_building_sqft(lat, lng)
        if sqft:
            return sqft, "building_area"

    # Could add Regrid cross-reference here in future
    return None, "default"


async def _osm_building_sqft(lat: float, lng: float) -> int | None:
    """
    Query Overpass for a building way near the given point and compute its area in sq ft.
    Returns None if no building found or area calculation fails.
    """
    # Search within a 50m radius for a storage/warehouse building
    query = f"""
[out:json][timeout:15];
(
  way["building"~"warehouse|storage|commercial|yes"](around:50,{lat},{lng});
);
out body;
>;
out skel qt;
"""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(settings.overpass_url, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.debug("Overpass building query failed: %s", exc)
        return None

    elements = data.get("elements", [])
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in elements if e["type"] == "node"}
    ways = [e for e in elements if e["type"] == "way"]

    if not ways:
        return None

    # Take the first way and compute its polygon area
    way = ways[0]
    node_ids = way.get("nodes", [])
    coords = [nodes[n] for n in node_ids if n in nodes]
    if len(coords) < 3:
        return None

    try:
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        area_m2, _ = geod.polygon_area_perimeter(lngs, lats)
        area_sqft = abs(area_m2) * 10.7639  # m² → sq ft
        return max(1, int(area_sqft))
    except Exception as exc:
        logger.debug("Area calculation failed: %s", exc)
        return None
