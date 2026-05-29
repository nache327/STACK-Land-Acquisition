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

import asyncpg
import httpx
from geoalchemy2 import WKTElement
from shapely.ops import unary_union
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.arcgis_bbox import download_bbox_features, get_parcel_bbox
from app.config import settings
from app.models.overlay import Overlay, OverlayType


def _raw_asyncpg_url() -> str:
    """Strip the SQLAlchemy driver tag for plain asyncpg.connect()."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

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
    """Update parcels.{column} = TRUE for all parcels whose geometry intersects
    the union of the provided GeoDataFrame geometries.

    Performance note (why this isn't the obvious one-liner):

    The naive `WHERE ST_Intersects(parcels.geom, <huge union>)` can't
    effectively use the GiST index on parcels.geom because PostGIS's index
    bound is the union's overall bbox — which for a county-wide flood-zone
    union covers nearly every parcel in the bbox. The planner falls back to
    a sequential scan and ST_Intersects per row. On SLCo (397k parcels) that
    took several minutes per overlay.

    Fix: ST_Subdivide the union into ≤256-vertex pieces, materialize them
    into a temp table with a GiST index, then EXISTS-join. Now each parcel
    only checks the few subpieces whose bbox overlaps its own bbox — both
    sides indexed, fast nested-loop spatial join. Standard PostGIS pattern
    for big-polygon vs many-small-polygon intersections.
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

    # Unique per-call name so concurrent overlays (flood + wetland running
    # in parallel) don't collide on the temp table.
    pieces_tbl = f"_overlay_pieces_{uuid.uuid4().hex[:12]}"

    try:
        # ON COMMIT PRESERVE ROWS: keep the temp table alive across the
        # SQLAlchemy session's auto-commits so the UPDATE below sees it.
        # The explicit DROP at the end cleans up. ON COMMIT DROP would
        # vanish the table before we get to the UPDATE if commit lands
        # between statements.
        await db.execute(text(
            f"CREATE TEMP TABLE {pieces_tbl} "
            f"(geom geometry(Geometry, 4326)) ON COMMIT PRESERVE ROWS"
        ))
        await db.execute(
            text(
                f"INSERT INTO {pieces_tbl} (geom) "
                f"SELECT (ST_Dump(ST_Subdivide("
                f"  ST_GeomFromText(:geom, 4326), 256))).geom"
            ),
            {"geom": union.wkt},
        )
        await db.execute(text(
            f"CREATE INDEX ON {pieces_tbl} USING GIST (geom)"
        ))
        # ANALYZE so the planner knows the temp table's row count + selectivity.
        await db.execute(text(f"ANALYZE {pieces_tbl}"))

        result = await db.execute(
            text(
                f"""
                UPDATE parcels p
                SET {column} = TRUE
                WHERE p.jurisdiction_id = :jid
                  AND p.geom IS NOT NULL
                  AND COALESCE(p.{column}, FALSE) IS DISTINCT FROM TRUE
                  AND EXISTS (
                    SELECT 1 FROM {pieces_tbl} op
                    WHERE ST_Intersects(p.geom, op.geom)
                  )
                """
            ),
            {"jid": str(jurisdiction_id)},
        )
        await db.flush()
        return result.rowcount or 0
    finally:
        # Drop the temp table even if the UPDATE blew up, so the session's
        # connection (which goes back to the pool) doesn't carry stray state.
        try:
            await db.execute(text(f"DROP TABLE IF EXISTS {pieces_tbl}"))
        except Exception:  # noqa: BLE001 — cleanup best-effort
            pass


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

    # Run all heavy SQL on a raw asyncpg connection — DON'T use the shared
    # SQLAlchemy AsyncSession `db`. The big spatial UPDATE runs for tens of
    # seconds on large jurisdictions (Newark Essex: 175k parcels × ~10k road
    # centers); SQLAlchemy's greenlet wrapper around `db.execute()` tears
    # down its parent greenlet during long awaits and the next operation on
    # the session raises MissingGreenlet, then the pipeline's rollback
    # handler also fails on the corrupted session — and the whole job dies.
    # Raw asyncpg has no greenlet bridge to break.
    conn = await asyncpg.connect(_raw_asyncpg_url())
    try:
        # 90s ceiling — past this we drop AADT for the jurisdiction rather
        # than let it block the actor's 30-min budget and tombstone the job.
        await conn.execute("SET statement_timeout = 90000")
        # Pre-build a geography column + GiST index so ST_DWithin uses it.
        # Without an index, the join is parcels (175k) × roads (~60k) =
        # ~10 billion sequential comparisons and the UPDATE never finishes.
        await conn.execute(
            "CREATE TEMPORARY TABLE IF NOT EXISTS _aadt_roads "
            "(lng double precision, lat double precision, aadt integer, "
            "geom geography(POINT, 4326))"
        )
        await conn.execute("TRUNCATE _aadt_roads")
        await conn.copy_records_to_table(
            "_aadt_roads",
            records=road_rows,
            columns=("lng", "lat", "aadt"),
        )
        await conn.execute(
            "UPDATE _aadt_roads SET geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography "
            "WHERE geom IS NULL"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS _aadt_roads_geom_gix ON _aadt_roads USING GIST(geom)"
        )
        await conn.execute("ANALYZE _aadt_roads")
        result = await conn.execute(
            """
            WITH best AS (
                SELECT DISTINCT ON (p.id)
                    p.id AS parcel_id,
                    r.aadt
                FROM parcels p
                JOIN _aadt_roads r
                  ON ST_DWithin(
                       COALESCE(p.centroid, ST_Centroid(p.geom))::geography,
                       r.geom,
                       150
                     )
                WHERE p.jurisdiction_id = $1::uuid
                  AND (p.centroid IS NOT NULL OR p.geom IS NOT NULL)
                ORDER BY p.id, r.aadt DESC
            )
            UPDATE parcels p
            SET aadt = best.aadt
            FROM best
            WHERE p.id = best.parcel_id
            """,
            str(jurisdiction_id),
        )
    except (asyncpg.QueryCanceledError, asyncpg.exceptions.QueryCanceledError) as exc:
        # PostgreSQL timed the UPDATE out at 90s. Don't kill the pipeline —
        # AADT is non-essential enrichment, parcels and zoning are what
        # matters for ready state.
        logger.warning(
            "AADT spatial UPDATE exceeded 90s for %s — skipping: %s",
            jurisdiction_id, exc,
        )
        return 0
    finally:
        await conn.close()

    # asyncpg's `execute()` returns a status string like "UPDATE 12345"; parse
    # the row count out of it so the pipeline's progress reporting still works.
    try:
        updated = int(result.rsplit(" ", 1)[-1]) if isinstance(result, str) else 0
    except (ValueError, AttributeError):
        updated = 0
    logger.info("AADT overlay: %d parcels updated for %s", updated, jurisdiction_id)
    return updated
