"""Census ACS proxy — server-side fetch + in-memory cache.

The frontend's isochrone-based ring metrics needed direct browser access
to api.census.gov. As of today that endpoint started returning a 302
without a CORS header, which the browser blocks. Every dashboard load
that touched the wealth-density / HHI / home-value / population sliders
ended in a cascade of "Failed to fetch" + an eventual top-level React
crash ("Application error: a client-side exception has occurred").

Workaround: have the FastAPI backend make the Census call (no CORS
involved) and serve the raw JSON to the frontend through our normal
/api/* prefix. Frontend just swaps the URL.

The endpoint is read-only and ACS 5-year data is updated yearly, so the
in-memory cache key is (vintage, state, county) with no TTL. Worst case
on a process restart we re-fetch.

In-flight deduplication: when 100+ parcels fire simultaneous ring
precompute calls for the same county, we don't want 100 parallel Census
requests — Census rate-limits and we get 502s. We hold one
``asyncio.Future`` per cache key; the first caller starts the upstream
fetch, every subsequent caller awaits the same future.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["census-proxy"])

_ACS_BASE = "https://api.census.gov/data"

# Cache keyed by (vintage, state, county, variables). The frontend always
# requests the same five variables for tracts in one county, so the cache
# has at most ~200 entries (one per US county the dashboards touch).
_cache: dict[tuple[str, str, str, str], list] = {}
# In-flight requests so concurrent callers for the same key share one
# upstream fetch instead of stampeding Census.
_inflight: dict[tuple[str, str, str, str], "asyncio.Future[list]"] = {}


@router.get("/census/acs5/tract")
async def acs5_tract(
    state: str = Query(..., min_length=2, max_length=2),
    county: str = Query(..., min_length=3, max_length=3),
    variables: str = Query(
        default="B01003_001E,B19013_001E,B25077_001E,B11001_001E,B19001_017E",
        description="Comma-separated ACS variable IDs",
    ),
    vintage: str = Query(default="2022"),
) -> list:
    """Proxy api.census.gov ACS 5-year tract-level data.

    Same shape as Census returns: a JSON array where row 0 is the header
    and rows 1..N are tract records. Cached per (vintage, state, county,
    variables) in memory.

    Errors are surfaced as 502 so the frontend can fall back gracefully.
    """
    if not (state.isdigit() and county.isdigit()):
        raise HTTPException(422, "state and county must be FIPS digits")

    cache_key = (vintage, state, county, variables)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # Coalesce concurrent callers onto a single upstream request. The
    # first caller wins the right to fetch from Census; everyone else
    # awaits the same future. Eliminates the ~564-parallel-request burst
    # that drove Census to 502 every dashboard load.
    existing = _inflight.get(cache_key)
    if existing is not None:
        return await existing

    loop = asyncio.get_running_loop()
    future: asyncio.Future[list] = loop.create_future()
    _inflight[cache_key] = future

    try:
        data = await _fetch_acs(vintage, state, county, variables)
        _cache[cache_key] = data
        if not future.done():
            future.set_result(data)
        return data
    except HTTPException as exc:
        if not future.done():
            future.set_exception(exc)
        raise
    except Exception as exc:
        if not future.done():
            future.set_exception(exc)
        raise HTTPException(502, f"Census upstream error: {exc}")
    finally:
        _inflight.pop(cache_key, None)


async def _fetch_acs(
    vintage: str, state: str, county: str, variables: str
) -> list:
    """Single upstream call to Census. Caller handles caching + dedup."""
    url = f"{_ACS_BASE}/{vintage}/acs/acs5"
    params: dict = {
        "get": variables,
        "for": "tract:*",
        "in": [f"state:{state}", f"county:{county}"],
    }
    if settings.census_api_key:
        params["key"] = settings.census_api_key

    # Single retry on 5xx — Census hiccups under burst load.
    last_status: int | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                resp = await client.get(url, params=params)
        except Exception as exc:
            logger.warning(
                "census upstream error %s/%s attempt=%d: %s",
                state, county, attempt, exc,
            )
            if attempt == 1:
                raise HTTPException(502, f"Census upstream error: {exc}")
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as exc:
                raise HTTPException(502, f"Census payload not JSON: {exc}")
            if not isinstance(data, list) or not data:
                raise HTTPException(502, "Census returned empty payload")
            return data

        last_status = resp.status_code
        logger.warning(
            "census non-200 for %s/%s attempt=%d: %s",
            state, county, attempt, resp.status_code,
        )
        if resp.status_code in (401, 403, 404):
            break

    raise HTTPException(502, f"Census returned HTTP {last_status}")
