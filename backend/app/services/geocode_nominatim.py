"""OpenStreetMap Nominatim geocoder — free fallback for addresses
that Census can't resolve (e.g. Utah grid-style "1170 E 3200 N").

The public Nominatim instance has a usage policy of <=1 req/s + a
descriptive User-Agent header identifying the app. We enforce both.

In practice the matcher chains Census first (faster, U.S.-focused),
falls back to Nominatim only when Census returns no match. The chain
runs serially behind the same asyncio.Semaphore(1) used by Census,
so the combined rate is still 1 req/s — total cost for a 50-listing
upload is at most ~50 seconds of wall time.

Public endpoint is fine for our volume (a handful of uploads per
day). If we ever exceed their fair-use policy we self-host via
Docker — same interface.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Final

import httpx

from app.services.address_normalizer import normalize

logger = logging.getLogger(__name__)

_NOMINATIM_BASE: Final[str] = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a meaningful UA. Don't impersonate
# a browser — they explicitly ask for an app-identifying string.
_USER_AGENT: Final[str] = "ParcelLogic/1.0 (https://zoning-finder.vercel.app)"
_RATE_LIMIT_INTERVAL_SEC: Final[float] = 1.0
_HTTP_TIMEOUT_SEC: Final[float] = 20.0

_lock = asyncio.Semaphore(1)
_cache: dict[str, "NominatimResult | None"] = {}


@dataclass(frozen=True)
class NominatimResult:
    lat: float
    lon: float
    display_name: str
    # OSM importance score (0..1) — higher = more likely correct
    importance: float


def _cache_key(address: str, city: str | None, state: str | None) -> str:
    return f"{normalize(address)}|{(city or '').lower().strip()}|{(state or '').lower().strip()}"


async def geocode_address(
    address: str,
    city: str | None = None,
    state: str | None = None,
) -> NominatimResult | None:
    """Free OSM-backed geocode. Returns None on no match or network
    error. Handles formats Census can't (Utah grid, NYC borough
    aliases, etc.)."""
    if not address:
        return None
    key = _cache_key(address, city, state)
    if key in _cache:
        return _cache[key]

    # Nominatim works best with structured params rather than a single
    # oneline string. Hand it street + city + state separately when we
    # have them.
    params: dict = {"format": "jsonv2", "limit": 1, "countrycodes": "us"}
    parts = [address.strip()]
    if city:
        parts.append(city.strip())
    if state:
        parts.append(state.strip())
    params["q"] = ", ".join(p for p in parts if p)

    async with _lock:
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT_SEC,
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US"},
            ) as client:
                resp = await client.get(_NOMINATIM_BASE, params=params)
        except Exception as exc:
            logger.warning("nominatim error for %r: %s", params["q"], exc)
            _cache[key] = None
            await asyncio.sleep(_RATE_LIMIT_INTERVAL_SEC)
            return None

        await asyncio.sleep(_RATE_LIMIT_INTERVAL_SEC)

        if resp.status_code != 200:
            logger.warning("nominatim %s for %r", resp.status_code, params["q"])
            _cache[key] = None
            return None

        try:
            data = resp.json()
        except Exception:
            _cache[key] = None
            return None

        if not isinstance(data, list) or not data:
            _cache[key] = None
            return None

        m = data[0]
        try:
            lat = float(m["lat"])
            lon = float(m["lon"])
            importance = float(m.get("importance", 0.0))
        except (KeyError, TypeError, ValueError):
            _cache[key] = None
            return None

        result = NominatimResult(
            lat=lat,
            lon=lon,
            display_name=m.get("display_name") or params["q"],
            importance=importance,
        )
        _cache[key] = result
        return result


def _reset_cache_for_tests() -> None:
    _cache.clear()


__all__ = ["NominatimResult", "geocode_address"]
