"""Admin one-shot backfills.

POST /api/admin/_backfill-nj-parcel-city
    Populate ``parcels.city`` with the NJ township/borough name for every
    parcel whose centroid falls inside an NJ Minor Civil Division (MCD).

Why this exists:
    Ingest pipelines for NJ counties left ``parcels.city`` NULL across
    all ~1.7M parcels. The dashboard's "search a township" UX expects
    city to be populated; without it, a search like "Bridgewater"
    returns nothing even though Somerset County's parcels include
    Bridgewater. Backfilling also unblocks a future
    ``zone_use_matrix.municipality`` schema dimension so per-township
    zoning rules can replace the current county-level
    "all of Somerset gets Somerville's rules" half-truth.

How it works:
    1. Fetch NJ county subdivisions from Census TIGER as GeoJSON.
       ~565 polygons covering every inch of NJ uniquely; no overlaps.
    2. Load polygons into a temp table, build a spatial index.
    3. UPDATE parcels SET city = township_name FROM the temp table
       WHERE ST_Within(centroid, township_polygon) AND parcels are
       in NJ jurisdictions. Batched at 50K rows per transaction so
       Supabase's 60s statement timeout doesn't cancel mid-flight.
    4. Drop the temp table.

Idempotent: running again UPDATE-overwrites with the same values.
Safe to re-fire after a partial failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import asyncpg
import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import settings
from app.db import get_db
from app.services.job_state_store import set_job_state, get_job_state

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])


_TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/1/query"
)

# NJ FIPS state code. Hardcoded — the endpoint is NJ-specific by design.
# Other states get their own endpoints when they need it; sharing one
# polymorphic endpoint adds parameters and validation we don't need yet.
_NJ_STATE_FIPS = "34"


def _raw_dsn() -> str:
    """Convert SQLAlchemy URL to raw asyncpg URL — same trick the
    existing buybox scorer uses to escape the SQLAlchemy timeout."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _fetch_nj_subdivisions() -> list[dict[str, Any]]:
    """Pull every NJ MCD from TIGER as GeoJSON features.

    TIGER caps result counts; iterate using resultOffset until the
    response stops returning features.
    """
    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000  # TIGER's max
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            resp = await client.get(_TIGER_URL, params={
                "where": f"STATE='{_NJ_STATE_FIPS}'",
                "outFields": "NAME,STATE,COUNTY,GEOID",
                "f": "geojson",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            })
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                break
            out.extend(features)
            if len(features) < page_size:
                break
            offset += page_size
    return out


_BATCH_SIZE = 50_000


async def _run_backfill(job_id: str) -> None:
    """Worker body. Updates the job state in Redis as it progresses."""
    state: dict[str, Any] = {
        "job_id": job_id,
        "status": "fetching",
        "subdivisions_fetched": 0,
        "subdivisions_loaded": 0,
        "parcels_updated": 0,
        "started_at": _now(),
        "finished_at": None,
        "errors": [],
    }
    await set_job_state(job_id, state)

    try:
        # ── 1. Fetch from TIGER ──────────────────────────────────────────
        features = await _fetch_nj_subdivisions()
        state["subdivisions_fetched"] = len(features)
        state["status"] = "loading_polygons"
        await set_job_state(job_id, state)
        logger.info(
            "backfill-nj-parcel-city job=%s: fetched %d NJ MCDs",
            job_id, len(features),
        )

        # ── 2. Load into a temp table + spatial index ────────────────────
        conn = await asyncpg.connect(_raw_dsn())
        try:
            await conn.execute("SET statement_timeout = 0")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _nj_mcd_backfill (
                    geoid TEXT PRIMARY KEY,
                    name  TEXT NOT NULL,
                    geom  GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
                )
            """)
            await conn.execute("TRUNCATE _nj_mcd_backfill")

            insert_sql = """
                INSERT INTO _nj_mcd_backfill (geoid, name, geom)
                VALUES (
                    $1, $2,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($3), 4326))
                )
                ON CONFLICT (geoid) DO UPDATE
                  SET name = EXCLUDED.name, geom = EXCLUDED.geom
            """
            for feat in features:
                props = feat.get("properties") or {}
                geoid = props.get("GEOID")
                name = props.get("NAME")
                geom = feat.get("geometry")
                if not (geoid and name and geom):
                    continue
                await conn.execute(insert_sql, geoid, name, json.dumps(geom))
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_nj_mcd_geom "
                "ON _nj_mcd_backfill USING GIST (geom)"
            )
            await conn.execute("ANALYZE _nj_mcd_backfill")
            state["subdivisions_loaded"] = len(features)
            state["status"] = "updating_parcels"
            await set_job_state(job_id, state)
            logger.info(
                "backfill-nj-parcel-city job=%s: loaded %d polygons + GIST index",
                job_id, len(features),
            )

            # ── 3. Batched UPDATE parcels.city ───────────────────────────
            # FOR UPDATE OF p SKIP LOCKED so concurrent writers (e.g. the
            # ingest pipeline) keep working while we drain. Loop until a
            # batch returns 0 rows.
            update_sql = """
                WITH batch AS (
                    SELECT p.id, m.name AS mcd_name
                      FROM parcels p
                      JOIN jurisdictions j ON j.id = p.jurisdiction_id
                      JOIN _nj_mcd_backfill m
                        ON ST_Within(p.centroid, m.geom)
                     WHERE j.state = 'NJ'
                       AND p.centroid IS NOT NULL
                       AND (p.city IS NULL OR p.city <> m.name)
                     LIMIT $1
                     FOR UPDATE OF p SKIP LOCKED
                )
                UPDATE parcels p
                   SET city = b.mcd_name
                  FROM batch b
                 WHERE p.id = b.id
                RETURNING 1
            """
            while True:
                rows = await conn.fetch(update_sql, _BATCH_SIZE)
                n = len(rows)
                if n == 0:
                    break
                state["parcels_updated"] += n
                await set_job_state(job_id, state)
                logger.info(
                    "backfill-nj-parcel-city job=%s: +%d (total %d)",
                    job_id, n, state["parcels_updated"],
                )

            # ── 4. Drop the temp table ───────────────────────────────────
            await conn.execute("DROP TABLE IF EXISTS _nj_mcd_backfill")
        finally:
            await conn.close()

        state["status"] = "completed"
        logger.info(
            "backfill-nj-parcel-city job=%s complete: subdivisions=%d parcels=%d",
            job_id, state["subdivisions_loaded"], state["parcels_updated"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("backfill-nj-parcel-city job=%s failed: %s", job_id, exc)
        state["status"] = "failed"
        state["errors"].append(str(exc))
    finally:
        state["finished_at"] = _now()
        await set_job_state(job_id, state)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@router.post("/admin/_backfill-nj-parcel-city", status_code=202)
async def backfill_nj_parcel_city(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),  # unused but keeps the auth wiring consistent
) -> dict[str, Any]:
    """Kick off the NJ parcels.city backfill. Returns ``{job_id}``
    immediately; poll
    ``GET /api/admin/_backfill-nj-parcel-city-status/{job_id}``
    for progress.

    The work is idempotent and SKIP-LOCKED so it doesn't block ingest
    writers. ~1.7M parcels across 21 NJ counties typically completes
    in 5-15 minutes depending on Supabase load.
    """
    import uuid as _uuid
    job_id = str(_uuid.uuid4())
    background_tasks.add_task(_run_backfill, job_id)
    return {"job_id": job_id, "status": "started"}


@router.get("/admin/_backfill-nj-parcel-city-status/{job_id}")
async def backfill_status(job_id: str) -> dict[str, Any]:
    state = await get_job_state(job_id)
    if state is None:
        raise HTTPException(404, "backfill job not found (may have expired)")
    return state
