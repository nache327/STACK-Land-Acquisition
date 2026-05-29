"""Unit tests for the Mapbox isochrone client.

Covers the pieces we can exercise without burning real Mapbox quota:
  - Sliding-window rate limiter math.
  - Successful response → shapely geometries keyed by contour.
  - 429 retry with Retry-After honored.
  - 4xx (non-429) → MapboxIsochroneError, no retry.
  - Empty token → MapboxConfigError on init.
  - Missing contours in the response → MapboxIsochroneError.

Uses httpx.MockTransport (built-in) instead of respx so the tests don't
add a hard dependency on a mocking library that's only in dev-deps.
"""
from __future__ import annotations

import time

import httpx
import pytest
from shapely.geometry import Polygon

from app.services.mapbox_isochrone import (
    MapboxConfigError,
    MapboxIsochroneClient,
    MapboxIsochroneError,
    _SlidingWindowRateLimiter,
)


# ── Sliding-window limiter ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limiter_allows_burst_up_to_max() -> None:
    lim = _SlidingWindowRateLimiter(max_per_window=3, window_seconds=60.0)
    t0 = time.monotonic()
    for _ in range(3):
        await lim.acquire()
    assert time.monotonic() - t0 < 0.1


@pytest.mark.asyncio
async def test_limiter_blocks_when_window_full() -> None:
    """The 4th acquire in a 3/window window must wait for the oldest to age
    out. Use a 0.5s window so the test doesn't take forever."""
    lim = _SlidingWindowRateLimiter(max_per_window=3, window_seconds=0.5)
    t0 = time.monotonic()
    for _ in range(4):
        await lim.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.45, f"expected ≥0.45s, got {elapsed:.3f}s"
    assert elapsed < 1.5


# ── Client construction ─────────────────────────────────────────────────────


def test_empty_token_raises_config_error() -> None:
    with pytest.raises(MapboxConfigError, match="MAPBOX_TOKEN is empty"):
        MapboxIsochroneClient(token="")


# ── Response fixtures ───────────────────────────────────────────────────────


def _square_geojson(cx: float, cy: float, r: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [cx - r, cy - r], [cx + r, cy - r],
            [cx + r, cy + r], [cx - r, cy + r],
            [cx - r, cy - r],
        ]],
    }


def _fake_mapbox_response(contours: tuple[int, ...]) -> dict:
    """Mimics the FeatureCollection Mapbox returns. One Feature per contour
    with a `contour` minutes property and a Polygon geometry. Bigger squares
    for bigger contours so we can verify they came back in the right slots."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"contour": c, "color": "#000000"},
                "geometry": _square_geojson(0.0, 0.0, 0.001 * c),
            }
            for c in contours
        ],
    }


class _Recorder:
    """Track requests + scripted responses for a single test."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if not self.responses:
            return httpx.Response(500, text="test ran out of responses")
        return self.responses.pop(0)


def _client_with_responses(
    responses: list[httpx.Response],
    *,
    rate_limit_per_minute: int = 1000,
) -> tuple[MapboxIsochroneClient, _Recorder]:
    recorder = _Recorder(responses)
    transport = httpx.MockTransport(recorder.handler)
    http = httpx.AsyncClient(transport=transport)
    client = MapboxIsochroneClient(
        token="tok_test",
        rate_limit_per_minute=rate_limit_per_minute,
        client=http,
    )
    return client, recorder


# ── End-to-end happy path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_polygons_keyed_by_contour() -> None:
    contours = (2, 5, 10, 15)
    client, _ = _client_with_responses(
        [httpx.Response(200, json=_fake_mapbox_response(contours))]
    )
    try:
        out = await client.fetch(lng=-111.89, lat=40.76, contours=contours)
    finally:
        await client.aclose()

    assert set(out.keys()) == {2, 5, 10, 15}
    for k in contours:
        assert isinstance(out[k], Polygon)
    # Fixture builds bigger squares for bigger contours — guards against a
    # parse bug that would put the 15-min geom into the 2-min slot.
    assert out[2].area < out[5].area < out[10].area < out[15].area


@pytest.mark.asyncio
async def test_request_uses_fixed_query_params() -> None:
    client, rec = _client_with_responses(
        [httpx.Response(200, json=_fake_mapbox_response((2, 5, 10, 15)))]
    )
    try:
        await client.fetch(lng=-111.0, lat=40.0)
    finally:
        await client.aclose()

    assert len(rec.calls) == 1
    qs = dict(rec.calls[0].url.params)
    # Mirror the frontend exactly:
    assert qs["contours_minutes"] == "2,5,10,15"
    assert qs["polygons"] == "true"
    assert qs["denoise"] == "0.25"
    assert qs["generalize"] == "100"
    assert qs["access_token"] == "tok_test"
    # And the path includes the coordinate in lng,lat order.
    assert "-111.0,40.0" in str(rec.calls[0].url)


# ── Error paths ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_4xx_other_than_429_raises_no_retry() -> None:
    client, rec = _client_with_responses(
        [httpx.Response(401, text="Invalid access token")]
    )
    try:
        with pytest.raises(MapboxIsochroneError, match="401"):
            await client.fetch(lng=0.0, lat=0.0)
    finally:
        await client.aclose()
    assert len(rec.calls) == 1, "401 must not retry"


@pytest.mark.asyncio
async def test_429_retries_with_retry_after_then_succeeds() -> None:
    client, rec = _client_with_responses([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json=_fake_mapbox_response((2, 5, 10, 15))),
    ])
    try:
        out = await client.fetch(lng=0.0, lat=0.0)
    finally:
        await client.aclose()
    assert len(rec.calls) == 2
    assert set(out.keys()) == {2, 5, 10, 15}


@pytest.mark.asyncio
async def test_missing_contours_in_response_raises() -> None:
    """If we asked for 4 contours and Mapbox only returned 3, that's a bug
    worth surfacing — not silently dropping the missing drive-time."""
    client, _ = _client_with_responses(
        [httpx.Response(200, json=_fake_mapbox_response((2, 5, 10)))]
    )
    try:
        with pytest.raises(MapboxIsochroneError, match=r"missing contours \[15\]"):
            await client.fetch(lng=0.0, lat=0.0, contours=(2, 5, 10, 15))
    finally:
        await client.aclose()
