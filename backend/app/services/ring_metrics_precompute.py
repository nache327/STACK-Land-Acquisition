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

# ACS target, module-level so an auditor can align to it by IMPORT rather than by
# copying the strings. A checker that hardcodes its own year can report "wealth
# exists, recompute read none" purely from a vintage mismatch — a false verdict on
# the exact question the epoch sentinel exists to answer. Independent in FETCH,
# aligned in TARGET.
#   B01003_001E population · B19013_001E median HHI · B25077_001E median home value
#   B11001_001E households (the aggregation WEIGHT) · B19001_017E households >$200k
_ACS_VINTAGE = "2022"
_ACS_VARIABLES = "B01003_001E,B19013_001E,B25077_001E,B11001_001E,B19001_017E"


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
                # CAST(:p AS t), never :p::t -- SQLAlchemy's bind regex silently
                # TRUNCATES a name followed by a colon (":cities::text[]" parses as
                # "citie"), so .bindparams(cities=...) raises "doesn't define a bound
                # parameter named 'cities'". See the same fix at the bucket query below.
                "SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) "
                "FROM (SELECT ST_Extent(centroid::geometry) e FROM parcels "
                "WHERE jurisdiction_id=:jid AND city = ANY(CAST(:cities AS text[])) "
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
    #
    # BUFFER the bbox first. An isochrone anchored near the jurisdiction edge
    # reaches WELL outside the parcel bbox — up to ~15 minutes of driving — and
    # step 2 below already buffers by 0.3° when bucketing parcels into tracts.
    # This call did not, so those outer tracts were never LOADED: the rings
    # aggregated only the tracts inside the raw bbox and systematically
    # UNDER-measured population/HV/HHI for every edge parcel. That bias runs
    # against the product (it pushes edge wealth pockets below the needle's
    # wealth gate) and is a prime suspect for the dt=10-vs-3mi discrepancies.
    xmin, ymin, xmax, ymax = bbox
    _BBOX_PAD_DEG = 0.3  # ~15-min drive at highway speed; matches step 2
    await ensure_census_tracts(
        (xmin - _BBOX_PAD_DEG, ymin - _BBOX_PAD_DEG,
         xmax + _BBOX_PAD_DEG, ymax + _BBOX_PAD_DEG),
        db,
    )
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
              -- Cast with CAST(x AS text[]), never the double-colon form.
              -- SQLAlchemy's bind regex truncates a parameter name followed by a
              -- colon, so the double-colon spelling parsed as a phantom "citie" and
              -- every call to this function raised ArgumentError before reaching the
              -- DB. This query is unconditional, so the whole entrypoint was dead on
              -- arrival. NOTE: no colon-prefixed token may appear even in a comment --
              -- text() parses comments too, which is how this trap recurs.
              AND (CAST(:cities AS text[]) IS NULL
                   OR p.city = ANY(CAST(:cities AS text[])))
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

    # Make an ACS shortfall LOUD. _load_acs_for_counties logs each failed county
    # and continues, and these two counters were computed and then read by
    # nobody — so an ACS outage during a precompute quietly produced rings with
    # NULL wealth for a whole county. Every parcel there then fails the needle's
    # wealth gate (NULL is not >= 475000), i.e. the county's needle count drops
    # to ~0 and looks like a *finding* rather than an outage. Surface it as an
    # error + a summary flag the caller/job-state can act on.
    summary["acs_counties_missing"] = (
        summary["acs_counties"] - summary["acs_counties_with_data"]
    )
    if summary["acs_counties_missing"]:
        summary["acs_incomplete"] = True
        logger.error(
            "ring precompute: ACS data missing for %d of %d counties — the rings "
            "written by this run will have NULL wealth for the affected tracts, "
            "which reads downstream as 'fails the wealth gate'. Re-run this "
            "jurisdiction once the Census API recovers.",
            summary["acs_counties_missing"], summary["acs_counties"],
        )

    # ── 4. Per-tract compute (in parallel, bounded) ──────────────────────
    sem = asyncio.Semaphore(_TRACT_CONCURRENCY)
    # Result map: (parcel_id, drive_time) -> RingMetrics
    metrics_to_write: list[tuple[int, int, RingMetrics]] = []
    lock = asyncio.Lock()
    # SEPARATE lock guarding the shared AsyncSession. An AsyncSession is NOT safe for
    # concurrent use -- overlapping execute() calls raise "This session is provisioning
    # a new connection; concurrent operations are not permitted" -- and the tract tasks
    # below run _TRACT_CONCURRENCY-wide against this one `db`. That never surfaced only
    # because the entrypoint was dead (phantom bindparam) and the DB call sits after
    # the isochrone fetch, so it was never reached.
    #
    # Serialising the DB call, rather than giving each task its own session, is also
    # what keeps this run off the live app's back: the pooler caps SESSION mode at 15
    # clients and the live board shares that pool, so a per-task session would put a
    # 139-jurisdiction run in direct competition with the dashboard. One session,
    # serialised, means the repair holds exactly ONE connection however wide the
    # isochrone fan-out gets. The slow part (Mapbox) stays concurrent.
    db_lock = asyncio.Lock()

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
                # db_lock: the session is shared across concurrent tract tasks and
                # cannot take overlapping queries (see the lock's definition).
                async with db_lock:
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

    variables = _ACS_VARIABLES
    vintage = _ACS_VINTAGE

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
    """Parse a Census value, mapping EVERY no-data annotation to None.

    Census uses a whole family of "jam values", not just -666666666: -111111111,
    -222222222, -333333333, -444444444, -555555555, -777777777, -888888888,
    -999999999 all encode distinct no-data reasons (too few samples, not
    applicable, median in the lowest/highest interval, controlled value, ...).

    Only special-casing -666666666 is the dangerous failure: a tract annotated with
    a different sentinel parses as a real value, flows into a ring that DOES
    aggregate, and yields a confidently wrong wealth number carrying a FRESH
    computed_at. That is worse than epoch -- it is neither an honest NULL nor
    visible to the epoch audit, and a single tract's garbage need not move needles
    far enough to trip the movement backstop.

    So the rule is structural rather than an enumeration: every variable fetched
    here (population, household count, median HHI, median home value, households
    over 200k) is a count or a dollar median, and NONE can validly be negative.
    Any negative is therefore a sentinel -- including jam values Census adds later.
    """
    if v is None or v == "":
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return None if n < 0 else n


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
           median_home_value, hnw_households, computed_at)
        VALUES (:pid, :dt, :pop, :hhi, :hv, :hnw,
          -- computed_at must be stated EXPLICITLY on insert. Omitting it took the
          -- column's server_default of now(), which stamped a brand-new PARTIAL row
          -- as freshly computed and bypassed the DO UPDATE guard below entirely.
          --
          -- EPOCH SENTINEL: to_timestamp(0) (1970-01-01T00:00:00Z) means "NEVER
          -- VALIDLY COMPUTED". It is not a real measurement time. Chosen over NULL
          -- deliberately: computed_at is NOT NULL (so NULL needs a migration), and
          -- more importantly a NULL row goes INVISIBLE to
          -- detect_stale_ring_metrics — its predicate is
          --   (ratio test) OR prm.computed_at < NOW() - INTERVAL '180 days'
          -- and for a partial row BOTH branches evaluate to NULL (population is
          -- NULL too), so nothing would ever flag it. That is the very bug this
          -- guard exists to prevent, reintroduced. The epoch instead makes
          -- `computed_at < NOW() - 180d` TRUE, so the detector DOES surface the row,
          -- while the cutoff predicate in api/parcels.py stays FALSE, so it is still
          -- excluded from the "current" view. Conservative in both readers.
          --
          -- NB: NEVER write a colon-prefixed token in these comments. SQLAlchemy
          -- text() scans for bind parameters LEXICALLY and does not skip "--"
          -- comments, so naming the reader's cutoff parameter in prose invented a
          -- phantom required parameter and broke this UPSERT for EVERY caller
          -- ("A value is required for bind parameter 'cutoff'"). The first attempt
          -- to warn about it reintroduced it twice, in the warning itself. Same
          -- class as the brace-placeholder-inside-a-comment that broke the LGC
          -- lane's SELECT. Describe parameters in words, never in token form.
          --
          -- TZ: to_timestamp(double precision) returns TIMESTAMPTZ, and this column
          -- is DateTime(timezone=True) => timestamptz. Same basis, so the boundary
          -- comparisons above are exact. (A naive-vs-aware mismatch is what made a
          -- cutoff six hours wrong elsewhere in this codebase.)
          -- CASTs are REQUIRED, not stylistic. Each of these parameters also
          -- appears in the VALUES list above, where its type is inferred from the
          -- target column; here it appears only inside `IS NOT NULL`, which conveys
          -- no type. asyncpg then cannot resolve the parameter and the whole
          -- statement fails with
          --   AmbiguousParameterError: could not determine data type of parameter $3
          -- Types match the columns exactly: population integer, median_home_value
          -- and median_hhi numeric.
          CASE
              WHEN CAST(:pop AS INTEGER) IS NOT NULL
               AND CAST(:hv  AS NUMERIC) IS NOT NULL
               AND CAST(:hhi AS NUMERIC) IS NOT NULL
              THEN NOW()
              ELSE to_timestamp(0)
          END)
        ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE SET
          -- NEVER REGRESS. These were assigned straight from EXCLUDED, so a
          -- recompute whose ACS lookup failed overwrote previously-MEASURED wealth
          -- with NULL — and because the computed_at CASE below then falls to ELSE
          -- (keeping the row's existing, recent stamp), the result was a NULL-wealth
          -- row reading as freshly computed. That is the trust trap, and on this
          -- path it also destroys good data: 6.6M rows already have a dt=10 row, so
          -- a Census hiccup on the day of a full run could silently degrade them.
          --
          -- COALESCE makes a failed recompute a NO-OP instead of a degradation, and
          -- the ELSE-keeps-old-stamp is then honest: the row still holds its old
          -- VALUES, so the old timestamp still describes them.
          --
          -- Why NULL must not be allowed to clear wealth: compute_ring_metrics
          -- returns 0 for every field both when a ring genuinely has no households
          -- AND when the ACS fetch failed, and the payload collapses falsy -> None.
          -- Those two cases are indistinguishable here, so treating NULL as "clear
          -- it" would erase real data on a transient outage. (Fixing that
          -- conflation at the source in compute_ring_metrics is the true class fix
          -- and changes what every caller receives — backlogged, not done here.)
          population        = COALESCE(EXCLUDED.population,        parcel_ring_metrics.population),
          median_hhi        = COALESCE(EXCLUDED.median_hhi,        parcel_ring_metrics.median_hhi),
          median_home_value = COALESCE(EXCLUDED.median_home_value, parcel_ring_metrics.median_home_value),
          hnw_households    = COALESCE(EXCLUDED.hnw_households,    parcel_ring_metrics.hnw_households),
          -- computed_at advances ONLY when the three gate-bearing metrics all
          -- actually landed. It used to be an unconditional NOW(), which meant a
          -- row could be stamped "fresh" while carrying NULL wealth from an ACS
          -- outage — and a fresh stamp is exactly what silences the staleness
          -- detectors (ring API 90d filter, the drawer's 180d banner,
          -- detect_stale_ring_metrics). That is the audit's trust trap: the data
          -- looks repaired while the wealth gate still fails on NULL.
          --
          -- hnw_households is deliberately NOT in the condition: it comes from
          -- B19001_017E, which is legitimately absent for some tracts, and it
          -- feeds a scoring BONUS rather than the needle gate. Requiring it would
          -- withhold honest stamps from otherwise-complete rows.
          -- THREE cases on the update path, in order. The invariant they enforce:
          -- after this statement no row is ever NULL-wealth with a non-epoch stamp.
          -- Every row is either (complete wealth, real stamp) or (NULL wealth, epoch).
          computed_at       = CASE
              -- 1. A fresh measurement landed for all three gate-bearing metrics
              --    => advance the stamp; it now describes new data.
              WHEN EXCLUDED.population        IS NOT NULL
               AND EXCLUDED.median_home_value IS NOT NULL
               AND EXCLUDED.median_hhi        IS NOT NULL
              THEN NOW()
              -- 2. The recompute came back partial, but COALESCE above preserved
              --    complete PREVIOUSLY-MEASURED wealth => keep the row's existing
              --    real stamp. Advancing would claim a measurement that did not
              --    happen; epoching would slander data that is still valid. Tested
              --    on the COALESCED values, not on EXCLUDED, precisely so this case
              --    is distinguishable from case 3.
              WHEN COALESCE(EXCLUDED.population,        parcel_ring_metrics.population)        IS NOT NULL
               AND COALESCE(EXCLUDED.median_home_value, parcel_ring_metrics.median_home_value) IS NOT NULL
               AND COALESCE(EXCLUDED.median_hhi,        parcel_ring_metrics.median_hhi)        IS NOT NULL
              THEN parcel_ring_metrics.computed_at
              -- 3. Resulting wealth is STILL NULL — a pre-existing NULL row whose
              --    recompute failed again (Utah County: 487/487 rows NULL, a
              --    systemic ACS gap). Keeping its old stamp would leave a
              --    NULL-wealth row reading as freshly computed: the trust trap that
              --    COALESCE alone does not close. Epoch it, so the staleness
              --    detector surfaces it and the current view excludes it.
              ELSE to_timestamp(0)
          END
        """
    )

    chunk_size = 5000
    written = 0
    for i in range(0, len(metrics), chunk_size):
        chunk = metrics[i : i + chunk_size]
        # falsy -> NULL is DELIBERATE, do not "fix" it to write 0 as 0.
        # compute_ring_metrics sums only tracts with household_count > 0, so when
        # ACS data is absent (fetch failed / county 404) `valid` is empty and
        # every aggregate comes back 0. That 0 means "we have no demographics
        # here", NOT "zero people live here" — persisting it as a measured 0
        # would be a false measurement, exactly the poison that made unmeasured
        # 3-mi populations read as "too rural" and unmeasured saturation read as
        # "underserved". NULL is the honest encoding; the ACS shortfall is
        # surfaced separately (summary["acs_incomplete"] + an error log) so the
        # gap is visible instead of silent.
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
