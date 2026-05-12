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
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["census-proxy"])

_ACS_BASE = "https://api.census.gov/data"

# Cache keyed by (vintage, state, county, variables). The frontend always
# requests the same five variables for tracts in one county, so the cache
# has at most ~200 entries (one per US county the dashboards touch).
_cache: dict[tuple[str, str, str, str], list] = {}


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

    url = f"{_ACS_BASE}/{vintage}/acs/acs5"
    params = {
        "get": variables,
        "for": "tract:*",
        "in": [f"state:{state}", f"county:{county}"],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
    except Exception as exc:
        logger.warning("census proxy upstream error %s/%s: %s", state, county, exc)
        raise HTTPException(502, f"Census upstream error: {exc}")

    if resp.status_code != 200:
        logger.warning(
            "census proxy non-200 for %s/%s: %s",
            state, county, resp.status_code,
        )
        raise HTTPException(502, f"Census returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(502, f"Census payload not JSON: {exc}")

    if not isinstance(data, list) or not data:
        raise HTTPException(502, "Census returned empty payload")

    _cache[cache_key] = data
    return data
