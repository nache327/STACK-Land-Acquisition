"""Tract-clustered server-side precompute for parcel_ring_metrics.

Why this exists: the frontend's per-parcel Mapbox + Census loop takes minutes
on county-sized jurisdictions (SLCo: 397k parcels). Snapping each parcel to
its census-tract centroid drops the Mapbox calls 250×; parcels in the same
tract share an isochrone close enough to the truth for filter-threshold work.

Pipeline per jurisdiction:
  1. Ensure census_tracts are loaded for the bbox.
  2. Bucket every parcel into its containing tract (ST_Within).
  3. Fetch ACS demographics for the (state, county) pairs covered.
  4. For each unique tract that has parcels:
      a. Call Mapbox once → {2,5,10,15}-min isochrone polygons.
      b. For each polygon, find intersecting tracts via PostGIS.
      c. Aggregate via `compute_ring_metrics` (same math as the frontend).
      d. Record (parcel_id, drive_time, metrics) for every parcel in the tract.
  5. Bulk-UPSERT into parcel_ring_metrics. ON CONFLICT updates only the
     demographic columns so a concurrent value-density write never gets
     clobbered (mirrors the bulk-upsert endpoint in parcels.py:594-610).

Concurrency + rate-limiting is handled by `mapbox_isochrone.MapboxIsochroneClient`.
PostGIS spatial joins use the existing ix_parcels_centroid and ix_census_tracts_geom
GiST indexes.

Math parity with the frontend lives in `ring_metrics_aggregation.py`; this
module is the orchestration only.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction
from app.services.census import ensure_census_tracts
from app.services.mapbox_isochrone import MapboxIsochroneClient, fetch_isochrone
from app.services.ring_metrics_aggregation import (
    RingMetrics,
    TractData,
    compute_ring_metrics,
)

logger = logging.getLogger(__name__)

# Mirrors the frontend's drive-time set.
DRIVE_TIMES: tuple[int, ...] = (2, 5, 10, 15)

# How many tracts we kick off in parallel. The Mapbox client also caps
# concurrency at 4 by default; this is a soft outer cap that keeps PostGIS
# polygon-intersection queries from queueing too deeply.
_TRACT_CONCURRENCY = 4

# Census "no data" sentinel — same as the frontend's parseN handling.
_NO_DATA = -666_666_666


ProgressFn = Callable[[str, int, int], Awaitable[None]]


async def precompute_ring_metrics_for_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    mapbox_client: MapboxIsochroneClient | None = None,
    on_progress: ProgressFn | None = None,
    cities: list[str] | None = None,
    bbox_override: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Pre-warm parcel_ring_metrics for every parcel in this jurisdiction.

    Idempotent: on conflict the UPSERT refreshes demographic columns only,
    so a value-density write between runs is preserved.

    Returns a summary: tracts_computed, parcels_written, mapbox_calls,
    acs_counties, elapsed_seconds.
    """
    started = time.monotonic()
    summary: dict[str, Any] = {
        "jurisdiction_id": str(jurisdiction_id),
        "tracts_computed": 0,
        "tracts_failed": 0,
        "parcels_written": 0,
        "mapbox_calls": 0,
        "acs_counties": 0,
        "elapsed_seconds": 0.0,
    }

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise ValueError(f"Jurisdiction {jurisdiction_id} not found")
    # bbox_override + cities: run a CITY-SCOPED precompute on a subset of a large
    # county jid (e.g. a few North Shore villages inside the 1.86M Cook jid) —
    # only those parcels' tracts get Mapbox isochrone calls, avoiding the gated
    # county-scale cost. bbox_override bounds the TIGER tract load; cities filters
    # the parcel→tract bucket. Both default None = original whole-jurisdiction run.
    if bbox_override is not None:
        bbox = bbox_override
    elif cities:
        # Derive the bbox from just the scoped cities' parcels so ensure_census_tracts
        # loads only the relevant tracts (not the whole county).
        ext = (await db.execute(
            text(
                "SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) "
                "FROM (SELECT ST_Extent(centroid::geometry) e FROM parcels "
                "WHERE jurisdiction_id=:jid AND city = ANY(:cities::text[]) "
                "AND centroid IS NOT NULL) s"
            ).bindparams(jid=jurisdiction_id, cities=cities)
        )).first()
        if not ext or ext[0] is None:
            raise ValueError(f"No parcels with centroids for cities={cities} in {j.name}")
        bbox = (ext[0], ext[1], ext[2], ext[3])
    else:
        if not j.bbox:
            raise ValueError(
                f"Jurisdiction {j.name} has no bbox; cannot determine census tracts. "
                "Re-ingest to populate it."
            )
        bbox = (j.bbox[0], j.bbox[1], j.bbox[2], j.bbox[3])

    # ── 1. Ensure tract geometries are loaded for the area ───────────────
    # ensure_census_tracts populates the census_tracts table with TIGER geoms
    # + B01003_001E population. We'll layer the other ACS variables on top
    # below — in memory, not in the table, since this is a one-shot job.
    await ensure_census_tracts(bbox, db)
    await db.commit()  # ensure tracts visible to subsequent queries

    if on_progress is not None:
        await on_progress("tracts_loaded", 0, 0)

    # ── 2. Bucket parcels into tracts ────────────────────────────────────
    # One row per (tract, parcel). Buffer the bbox by ~0.3° (~15-min driving
    # at highway speed) so tracts that an isochrone might reach into are
    # included even if they lie outside the parcel bbox.
    tract_parcel_rows = (await db.execute(
        text(
            """
            SELECT
              t.geoid AS geoid,
              t.state_fips AS state_fips,
              t.county_fips AS county_fips,
              ST_X(ST_Centroid(t.geom)) AS lng,
              ST_Y(ST_Centroid(t.geom)) AS lat,
              p.id AS parcel_id
            FROM parcels p
            JOIN census_tracts t ON ST_Within(p.centroid, t.geom)
            WHERE p.jurisdiction_id = :jid
              AND p.centroid IS NOT NULL
              AND (:cities::text[] IS NULL OR p.city = ANY(:cities::text[]))
            """
        ).bindparams(jid=jurisdiction_id, cities=cities)
    )).all()

    if not tract_parcel_rows:
        summary["elapsed_seconds"] = time.monotonic() - started
        logger.warning(
            "Precompute: no (parcel ∈ tract) matches for jurisdiction %s — "
            "either parcels lack centroids or census_tracts coverage is empty.",
            j.name,
        )
        return summary

    # Group parcels by tract; remember tract centroids + (state, county).
    tract_centroids: dict[str, tuple[float, float]] = {}
    tract_state_county: dict[str, tuple[str, str]] = {}
    parcels_by_tract: dict[str, list[int]] = {}
    for row in tract_parcel_rows:
        geoid = row.geoid
        tract_centroids.setdefault(geoid, (row.lng, row.lat))
        tract_state_county.setdefault(geoid, (row.state_fips, row.county_fips))
        parcels_by_tract.setdefault(geoid, []).append(row.parcel_id)

    logger.info(
        "Precompute %s: %d tracts containing %d parcels",
        j.name, len(parcels_by_tract), sum(len(v) for v in parcels_by_tract.values()),
    )

    # ── 3. Fetch ACS demographics for the covered (state, county) pairs ──
    state_county_pairs = set(tract_state_county.values())
    acs_by_geoid = await _load_acs_for_counties(state_county_pairs)
    summary["acs_counties"] = len(state_county_pairs)
    summary["acs_counties_with_data"] = len(
        {(g[:2], g[2:5]) for g in acs_by_geoid.keys()}
    )

    # ── 4. Per-tract compute (in parallel, bounded) ──────────────────────
    sem = asyncio.Semaphore(_TRACT_CONCURRENCY)
    # Result map: (parcel_id, drive_time) -> RingMetrics
    metrics_to_write: list[tuple[int, int, RingMetrics]] = []
    lock = asyncio.Lock()

    async def _process_one_tract(geoid: str) -> None:
        nonlocal metrics_to_write
        async with sem:
            try:
                cent = tract_centroids[geoid]
                client_call = (
                    mapbox_client.fetch(cent[0], cent[1], contours=DRIVE_TIMES)
                    if mapbox_client is not None
                    else fetch_isochrone(cent[0], cent[1], contours=DRIVE_TIMES)
                )
                polys = await client_call
                summary["mapbox_calls"] += 1
            except Exception as e:  # noqa: BLE001
                summary["tracts_failed"] += 1
                logger.warning(
                    "Precompute: tract %s isochrone failed (%s) — skipping",
                    geoid, e,
                )
                return

            ring_results: dict[int, RingMetrics] = {}
            for dt in DRIVE_TIMES:
                geom = polys.get(dt)
                if geom is None:
                    continue
                # Find tracts intersecting this polygon and pull their ACS.
                intersecting = await _tracts_intersecting(db, geom.wkt)
                tract_data = [
                    acs_by_geoid[g] for g in intersecting if g in acs_by_geoid
                ]
                ring_results[dt] = compute_ring_metrics(tract_data)

            pids = parcels_by_tract[geoid]
            async with lock:
                for pid in pids:
                    for dt, rm in ring_results.items():
                        metrics_to_write.append((pid, dt, rm))
            summary["tracts_computed"] += 1
            if on_progress is not None:
                await on_progress(
                    "tract_done",
                    summary["tracts_computed"],
                    len(parcels_by_tract),
                )

    # `_tracts_intersecting` reads from the SAME db session that's being
    # written through later. Running 4 tract coroutines concurrently on one
    # session works for reads, but writes need to be serialized. We're only
    # buffering Python objects above; the actual UPSERT runs single-threaded
    # after the gather.
    await asyncio.gather(
        *[_process_one_tract(g) for g in parcels_by_tract.keys()]
    )

    # ── 5. Bulk-UPSERT ──────────────────────────────────────────────────
    parcels_written = await _bulk_upsert_metrics(db, metrics_to_write)
    summary["parcels_written"] = parcels_written
    await db.commit()

    summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
    logger.info(
        "Precompute %s done in %.1fs: %d tracts, %d rows written, %d Mapbox calls",
        j.name, summary["elapsed_seconds"], summary["tracts_computed"],
        parcels_written, summary["mapbox_calls"],
    )
    return summary


# ── Internals ────────────────────────────────────────────────────────────


async def _load_acs_for_counties(
    state_county_pairs: set[tuple[str, str]],
) -> dict[str, TractData]:
    """Fetch ACS5 tract-level demographics for each (state, county) pair via
    the existing in-process census proxy logic. Returns dict[geoid -> TractData].

    Border-tract counties that the bbox query swept in may not always have
    ACS data (Census returns 404 for sparsely-populated or recently-split
    counties). One bad pair shouldn't kill an entire county precompute, so
    failures are logged and skipped — tracts under that county simply land
    with no demographics, contributing zeros to ring aggregates.
    """
    out: dict[str, TractData] = {}
    # Call the lower-level fetcher directly. Calling the route function
    # acs5_tract(...) from Python doesn't materialize FastAPI Query()
    # defaults — `vintage` arrives as a FieldInfo object, the URL ends up
    # malformed, and Census returns 404. Going one layer deeper avoids
    # the dependency-injection plumbing entirely.
    from app.api.census_proxy import _fetch_acs  # local import to avoid circular
    from fastapi import HTTPException  # noqa: E402

    variables = "B01003_001E,B19013_001E,B25077_001E,B11001_001E,B19001_017E"
    vintage = "2022"

    for state, county in sorted(state_county_pairs):
        try:
            rows = await _fetch_acs(vintage, state, county, variables)
        except HTTPException as exc:
            logger.warning(
                "Precompute: ACS fetch failed for state=%s county=%s "
                "(HTTP %s: %s) — tracts in that county will contribute zeros.",
                state, county, exc.status_code, exc.detail,
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Precompute: ACS fetch raised for state=%s county=%s: %s",
                state, county, exc,
            )
            continue
        # Census shape: row 0 is header, rows 1..N are tract records.
        if not rows or not isinstance(rows, list):
            continue
        headers = rows[0]

        def col(name: str) -> int:
            try:
                return headers.index(name)
            except ValueError:
                return -1

        i_pop  = col("B01003_001E")
        i_hhi  = col("B19013_001E")
        i_hv   = col("B25077_001E")
        i_hh   = col("B11001_001E")
        i_o200 = col("B19001_017E")
        i_st   = col("state")
        i_co   = col("county")
        i_tr   = col("tract")

        for r in rows[1:]:
            geoid = f"{r[i_st]}{r[i_co]}{r[i_tr]}"
            out[geoid] = TractData(
                population=_parse_n(r[i_pop]) if i_pop >= 0 else None,
                household_count=_parse_n(r[i_hh]) if i_hh >= 0 else None,
                median_hhi=_parse_n(r[i_hhi]) if i_hhi >= 0 else None,
                median_home_value=_parse_n(r[i_hv]) if i_hv >= 0 else None,
                households_over_200k=_parse_n(r[i_o200]) if i_o200 >= 0 else None,
            )
    return out


def _parse_n(v: Any) -> int | None:
    """Census "no data" sentinel + null + empty handled the same way as the
    frontend's parseN (isochrone.ts:186)."""
    if v is None or v == "" or v == _NO_DATA or v == str(_NO_DATA):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


async def _tracts_intersecting(db: AsyncSession, polygon_wkt: str) -> list[str]:
    """Return the geoids of census tracts whose geom intersects the polygon."""
    result = await db.execute(
        text(
            "SELECT geoid FROM census_tracts "
            "WHERE ST_Intersects(geom, ST_GeomFromText(:wkt, 4326))"
        ).bindparams(wkt=polygon_wkt)
    )
    return [r.geoid for r in result.all()]


async def _bulk_upsert_metrics(
    db: AsyncSession,
    metrics: list[tuple[int, int, RingMetrics]],
) -> int:
    """Bulk-UPSERT into parcel_ring_metrics. ON CONFLICT updates only the
    demographic columns — preserves a concurrent value-density write.

    Batched in chunks of 5000 so we stay well under asyncpg's prepared-stmt
    parameter cap (32768 / 6 columns ≈ 5461).
    """
    if not metrics:
        return 0

    sql = text(
        """
        INSERT INTO parcel_ring_metrics
          (parcel_id, drive_time_minutes, population, median_hhi,
           median_home_value, hnw_households)
        VALUES (:pid, :dt, :pop, :hhi, :hv, :hnw)
        ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE SET
          population        = EXCLUDED.population,
          median_hhi        = EXCLUDED.median_hhi,
          median_home_value = EXCLUDED.median_home_value,
          hnw_households    = EXCLUDED.hnw_households,
          computed_at       = NOW()
        """
    )

    chunk_size = 5000
    written = 0
    for i in range(0, len(metrics), chunk_size):
        chunk = metrics[i : i + chunk_size]
        payload = [
            {
                "pid": pid,
                "dt": dt,
                "pop": rm.total_population if rm.total_population else None,
                "hhi": rm.weighted_median_hhi if rm.weighted_median_hhi else None,
                "hv":  rm.weighted_median_home_value if rm.weighted_median_home_value else None,
                "hnw": rm.hnw_households if rm.hnw_households else None,
            }
            for (pid, dt, rm) in chunk
        ]
        await db.execute(sql, payload)
        written += len(chunk)
    return written
