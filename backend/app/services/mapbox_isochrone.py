"""Server-side Mapbox Isochrone client.

Used by the ring-metrics precompute to fetch drive-time polygons for each
census-tract centroid. Mirrors the frontend's call exactly (same path, same
query params, same denoise + generalize values) so server and client agree
on the geometry of the resulting isochrones — any drift here would cause
the parity tests in `test_ring_metrics_aggregation.py` to pass while
production parcels still flip their verdicts depending on which side
computed them.

Mapbox quotas
-------------
The Isochrone API allows 300 requests per minute on the free tier. We enforce
this client-side via a sliding-window rate limiter so that running multiple
county precomputes concurrently still stays under the global cap. The window
is keyed on the singleton client, so a process that imports this module gets
one shared budget regardless of how many call sites schedule fetches.

The semaphore is independent of the rate limit: it caps the number of
in-flight requests so a burst doesn't open 50 sockets at once. The rate
limit caps the number of NEW requests over a 60-second window.

Failures
--------
- 429 Too Many Requests: respects the `Retry-After` header when present,
  otherwise exponential backoff. Up to 3 retries before giving up.
- 5xx: same retry pattern (Mapbox occasionally returns 502 under load).
- 4xx (other than 429): no retry — likely a bad token or malformed
  coordinate, which retrying can't fix.

The default singleton is lazy: the client is only constructed on first use,
so module import never touches the network or requires `MAPBOX_TOKEN` to be
set. Callers that want to inject a test double can use
`MapboxIsochroneClient` directly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.config import settings

logger = logging.getLogger(__name__)

# Mirrors the frontend isochrone call at
# frontend/lib/isochrone.ts:109-112 — DO NOT diverge without bumping the
# parcellogic_precompute_v* cache key in lock-step.
_MAPBOX_URL = "https://api.mapbox.com/isochrone/v1/mapbox/driving"
_DEFAULT_CONTOURS: tuple[int, ...] = (2, 5, 10, 15)
_FIXED_QUERY = {
    "polygons": "true",
    "denoise": "0.25",
    "generalize": "100",
}

_MAX_RETRIES = 3
_REQUEST_TIMEOUT_S = 30.0


class MapboxConfigError(RuntimeError):
    """Raised when MAPBOX_TOKEN isn't set and a real request is attempted."""


class MapboxIsochroneError(RuntimeError):
    """Raised when Mapbox returns an unrecoverable error or the response
    shape doesn't match what we expect."""


class _SlidingWindowRateLimiter:
    """Allow up to `max_per_window` events per `window_seconds`.

    Sliding window, not fixed bucket — so 300/min means "no 60-second
    interval ever contains >300 requests," not "300 in :00-:59 then 300
    more at :00-:59 of the next minute." Matches how Mapbox actually
    accounts. Acquire blocks (asyncio sleep) until the oldest event in
    the window is old enough to drop off.
    """

    def __init__(self, max_per_window: int, window_seconds: float = 60.0) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                # Drop events that have aged out of the window.
                while self._events and now - self._events[0] >= self._window:
                    self._events.popleft()
                if len(self._events) < self._max:
                    self._events.append(now)
                    return
                # Wait until the oldest event ages out.
                sleep_for = self._window - (now - self._events[0])
                # Tiny pad so we don't loop on borderline timing.
                await asyncio.sleep(sleep_for + 0.01)


class MapboxIsochroneClient:
    """Thin wrapper around Mapbox's Isochrone API with per-process
    rate-limiting + concurrency capping + retries.

    Instances own a single httpx.AsyncClient for connection reuse. Call
    `.aclose()` to clean up; or use `async with`. The module-level
    `fetch_isochrone()` convenience uses a lazy singleton — only build
    your own instance when you need to inject a fake (tests) or run with
    non-default rate limits.
    """

    def __init__(
        self,
        token: str,
        *,
        max_concurrency: int = 4,
        rate_limit_per_minute: int = 300,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise MapboxConfigError(
                "MAPBOX_TOKEN is empty — server-side isochrones are disabled. "
                "Set it in .env or the Railway env."
            )
        self._token = token
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._limiter = _SlidingWindowRateLimiter(rate_limit_per_minute)
        self._client = client or httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT_S,
            follow_redirects=True,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "MapboxIsochroneClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def fetch(
        self,
        lng: float,
        lat: float,
        contours: tuple[int, ...] = _DEFAULT_CONTOURS,
    ) -> dict[int, BaseGeometry]:
        """Return one shapely Polygon (or MultiPolygon) per requested
        drive-time minute. The dict is keyed by the contour minute, e.g.
        `{2: Polygon(...), 5: Polygon(...), 10: ..., 15: ...}`.

        Raises:
            MapboxIsochroneError: if the API returns a non-recoverable
                error or its response shape doesn't match what we expect.
        """
        if not contours:
            return {}

        path = f"{_MAPBOX_URL}/{lng},{lat}"
        params = {
            "contours_minutes": ",".join(str(c) for c in contours),
            **_FIXED_QUERY,
            "access_token": self._token,
        }

        async with self._semaphore:
            data = await self._fetch_with_retry(path, params)

        return self._parse_response(data, contours)

    async def _fetch_with_retry(self, path: str, params: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            await self._limiter.acquire()
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Mapbox isochrone transport error (attempt %d/%d): %s — retrying in %.2fs",
                        attempt + 1, _MAX_RETRIES + 1, e, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                break

            if resp.status_code == 200:
                return resp.json()

            # Retry on 429 + 5xx; raise on anything else.
            should_retry = resp.status_code == 429 or 500 <= resp.status_code < 600
            if not should_retry or attempt >= _MAX_RETRIES:
                raise MapboxIsochroneError(
                    f"Mapbox isochrone failed {resp.status_code}: {resp.text[:200]}"
                )
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait_s = float(retry_after)
            else:
                wait_s = 0.5 * (2 ** attempt)
            logger.warning(
                "Mapbox isochrone %d (attempt %d/%d) — retrying in %.2fs",
                resp.status_code, attempt + 1, _MAX_RETRIES + 1, wait_s,
            )
            await asyncio.sleep(wait_s)

        # Exhausted retries with transport errors.
        raise MapboxIsochroneError(
            f"Mapbox isochrone exhausted retries: {last_exc}"
        ) from last_exc

    @staticmethod
    def _parse_response(data: dict, contours: tuple[int, ...]) -> dict[int, BaseGeometry]:
        features = data.get("features") or []
        if not isinstance(features, list):
            raise MapboxIsochroneError(f"Mapbox response missing features list: {data!r}")
        by_contour: dict[int, BaseGeometry] = {}
        for feat in features:
            props = (feat or {}).get("properties") or {}
            contour = props.get("contour")
            geom = (feat or {}).get("geometry")
            if contour is None or geom is None:
                continue
            try:
                by_contour[int(contour)] = shape(geom)
            except Exception as e:  # noqa: BLE001
                logger.warning("Mapbox isochrone: bad geometry for contour=%s: %s", contour, e)
        missing = [c for c in contours if c not in by_contour]
        if missing:
            raise MapboxIsochroneError(
                f"Mapbox isochrone response missing contours {missing}; got {sorted(by_contour)}"
            )
        return by_contour


# ── Module-level singleton + convenience ─────────────────────────────────────

_default_client: MapboxIsochroneClient | None = None
_default_client_lock = asyncio.Lock()


async def _get_default_client() -> MapboxIsochroneClient:
    global _default_client
    if _default_client is not None:
        return _default_client
    async with _default_client_lock:
        if _default_client is None:
            _default_client = MapboxIsochroneClient(
                token=settings.mapbox_token,
                rate_limit_per_minute=settings.mapbox_isochrone_rpm,
            )
    return _default_client


async def fetch_isochrone(
    lng: float,
    lat: float,
    contours: tuple[int, ...] = _DEFAULT_CONTOURS,
) -> dict[int, BaseGeometry]:
    """Convenience wrapper using a lazily-instantiated singleton client.

    For tests, instantiate MapboxIsochroneClient directly with a stubbed
    httpx.AsyncClient (or use respx) — don't reach for the singleton.
    """
    client = await _get_default_client()
    return await client.fetch(lng, lat, contours=contours)
