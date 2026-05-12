"""Census Geocoding Service wrapper — Tier 3 of listing matching.

Public endpoint at geocoding.geo.census.gov. No API key, but their
TOS asks for ~1 req/s. We enforce that with an asyncio.Semaphore(1)
plus a sleep — sequential calls only, regardless of how many
listings the matcher feeds in.

Results are cached in-process on the normalized address key. A pod
restart drops the cache; for v1 that's fine since Tier 1/2 normally
cover ≥80% of listings and the long-tail Tier 3 fallback is bounded
by Census rate limits anyway.

If geocoding becomes a real bottleneck (5000+ row upload), we'll
swap to a paid parallel geocoder (Mapbox / Google). The interface
in this file is the seam for that.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Final

import httpx

from app.services.address_normalizer import normalize

logger = logging.getLogger(__name__)

_CENSUS_BASE: Final[str] = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
_BENCHMARK: Final[str] = "Public_AR_Current"
_RATE_LIMIT_INTERVAL_SEC: Final[float] = 1.0
_HTTP_TIMEOUT_SEC: Final[float] = 20.0

_lock = asyncio.Semaphore(1)
_cache: dict[str, "GeocodeResult | None"] = {}


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    matched_address: str
    match_type: str  # "Exact" | "Non_Exact" per Census


def _cache_key(address: str, city: str | None, state: str | None) -> str:
    return f"{normalize(address)}|{(city or '').lower().strip()}|{(state or '').lower().strip()}"


async def geocode_address(
    address: str,
    city: str | None = None,
    state: str | None = None,
) -> GeocodeResult | None:
    """Geocode a single street address via the public Census endpoint.

    Returns None on no match, network error, or empty response. Caller
    decides what to do (Tier 3 matcher flags unmatched).

    Sequential by design — Census asks for 1 req/s, so 100 listings
    take ~100s of geocoding wall time. Tier 1/2 should keep this rare.
    """
    if not address:
        return None
    key = _cache_key(address, city, state)
    if key in _cache:
        return _cache[key]

    parts = [address.strip()]
    if city:
        parts.append(city.strip())
    if state:
        parts.append(state.strip())
    oneline = ", ".join(p for p in parts if p)

    async with _lock:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
                resp = await client.get(
                    _CENSUS_BASE,
                    params={
                        "address": oneline,
                        "benchmark": _BENCHMARK,
                        "format": "json",
                    },
                )
        except Exception as exc:
            logger.warning("census geocoder error for %r: %s", oneline, exc)
            _cache[key] = None
            await asyncio.sleep(_RATE_LIMIT_INTERVAL_SEC)
            return None

        await asyncio.sleep(_RATE_LIMIT_INTERVAL_SEC)

        if resp.status_code != 200:
            logger.warning("census geocoder %s for %r", resp.status_code, oneline)
            _cache[key] = None
            return None

        try:
            data = resp.json()
        except Exception:
            _cache[key] = None
            return None

        matches = (data.get("result") or {}).get("addressMatches") or []
        if not matches:
            _cache[key] = None
            return None

        m = matches[0]
        coords = m.get("coordinates") or {}
        try:
            lon = float(coords["x"])
            lat = float(coords["y"])
        except (KeyError, TypeError, ValueError):
            _cache[key] = None
            return None

        result = GeocodeResult(
            lat=lat,
            lon=lon,
            matched_address=m.get("matchedAddress") or oneline,
            match_type=m.get("tigerLine", {}).get("side") or "Exact",
        )
        _cache[key] = result
        return result


def _reset_cache_for_tests() -> None:
    """Test helper — drops the in-process cache so each test starts
    from a clean slate. Don't use from app code."""
    _cache.clear()


__all__ = ["GeocodeResult", "geocode_address"]
