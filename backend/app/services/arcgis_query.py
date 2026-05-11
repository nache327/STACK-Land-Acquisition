"""
ArcGIS FeatureServer query client.

Pulls parcel and zoning polygon features from ArcGIS REST FeatureServers in
pages (default 1 000 features per request) and converts them to GeoDataFrames.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import geopandas as gpd
import httpx

logger = logging.getLogger(__name__)

# Default page size for ArcGIS /query requests.
# Most FeatureServers cap at 1 000 or 2 000 per request.
_PAGE_SIZE = 1_000
_MAX_CONCURRENT_PAGES = 4

# Transient gateway errors (504/503/502) hit AGOL-hosted endpoints regularly
# under bursty parallel pagination — Phase 3 saw Fairfax's
# services1.arcgis.com node return 504 within 60 s of starting a 392K download
# while Loudoun + Mont PA + MD ran in parallel. Retry with exponential backoff
# instead of failing the whole job.
_RETRY_STATUSES = {502, 503, 504}
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 1.5


async def _send_with_retry(
    client: httpx.AsyncClient | None,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    timeout: float = 120.0,
) -> httpx.Response:
    """HTTP request with exponential-backoff retry on 502/503/504 + transport
    errors. Honours the caller's `client` if provided (so connection pools and
    timeouts are reused across the page batch); otherwise opens a one-shot
    AsyncClient.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            if client is None:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as local_client:
                    resp = await local_client.request(method, url, params=params, data=data)
            else:
                resp = await client.request(method, url, params=params, data=data)
            if resp.status_code in _RETRY_STATUSES:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}",
                    request=resp.request,
                    response=resp,
                )
                if attempt == _MAX_RETRIES - 1:
                    resp.raise_for_status()
                wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "ArcGIS %s %s → %d, retrying in %.1fs (attempt %d/%d)",
                    method, url, resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning(
                "ArcGIS %s %s transport error %r, retrying in %.1fs (attempt %d/%d)",
                method, url, exc, wait, attempt + 1, _MAX_RETRIES,
            )
            await asyncio.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry loop exited without response")  # unreachable


async def query_feature_layer(
    endpoint_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    result_offset: int = 0,
    result_record_count: int = _PAGE_SIZE,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    Single paged /query call to an ArcGIS FeatureServer layer.
    Returns the raw GeoJSON response dict.
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "outSR": out_sr,
        "f": "geojson",
        "resultOffset": result_offset,
        "resultRecordCount": result_record_count,
        "returnGeometry": "true",
    }
    url = endpoint_url.rstrip("/") + "/query"
    resp = await _send_with_retry(client, "GET", url, params=params, timeout=120.0)
    return resp.json()


async def get_layer_count(
    endpoint_url: str,
    where: str = "1=1",
    client: httpx.AsyncClient | None = None,
) -> int:
    """Return total feature count for a layer (used to drive pagination)."""
    params: dict[str, str | int] = {
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }
    url = endpoint_url.rstrip("/") + "/query"
    resp = await _send_with_retry(client, "GET", url, params=params, timeout=30.0)
    data = resp.json()
    return int(data.get("count", 0))


async def get_layer_metadata(
    endpoint_url: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    Fetch the layer metadata JSON (fields, geometry type, name, etc.)
    Used by arcgis_discovery to identify layer purposes.
    """
    url = endpoint_url.rstrip("/")
    resp = await _send_with_retry(client, "GET", url, params={"f": "json"}, timeout=30.0)
    return resp.json()


async def _get_all_object_ids(
    endpoint_url: str,
    where: str = "1=1",
    client: httpx.AsyncClient | None = None,
) -> list[int] | None:
    """
    Fetch all ObjectIDs for a layer. Returns None if the service doesn't
    support returnIdsOnly (falls back to offset pagination).
    """
    params: dict[str, str] = {
        "where": where,
        "returnIdsOnly": "true",
        "f": "json",
    }
    url = endpoint_url.rstrip("/") + "/query"
    try:
        resp = await _send_with_retry(client, "GET", url, params=params, timeout=60.0)
        data = resp.json()
        oids = data.get("objectIds")
        if isinstance(oids, list):
            return sorted(oids)
    except Exception as exc:
        logger.debug("returnIdsOnly not supported or failed: %s", exc)
    return None


async def _fetch_by_object_ids(
    endpoint_url: str,
    oid_chunk: list[int],
    out_fields: str = "*",
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Fetch a batch of features by explicit ObjectID list via POST (avoids URL length limits)."""
    data = {
        "objectIds": ",".join(str(o) for o in oid_chunk),
        "outFields": out_fields,
        "outSR": "4326",
        "f": "geojson",
        "returnGeometry": "true",
    }
    url = endpoint_url.rstrip("/") + "/query"
    resp = await _send_with_retry(client, "POST", url, data=data, timeout=120.0)
    return resp.json().get("features", [])


async def download_all_features(
    endpoint_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = _PAGE_SIZE,
    max_concurrency: int = _MAX_CONCURRENT_PAGES,
    progress_callback: Any = None,
) -> gpd.GeoDataFrame:
    """
    Download ALL features from an ArcGIS FeatureServer layer.

    Tries ObjectID-based pagination first (works for large services that cap
    offset-based pagination, e.g. Philadelphia OPA at 89K). Falls back to
    offset pagination for services that don't support returnIdsOnly.

    Returns a GeoDataFrame in EPSG:4326.
    """
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        logger.info("Getting feature count from %s", endpoint_url)
        total = await get_layer_count(endpoint_url, where, client=client)
        logger.info("Total features to download: %d", total)

        if total == 0:
            return gpd.GeoDataFrame()

        # Try ObjectID pagination — required for services that 400 on large offsets
        oids = await _get_all_object_ids(endpoint_url, where, client=client)

        features: list[dict] = []
        downloaded = 0

        if oids is not None:
            logger.info("Using ObjectID pagination (%d OIDs)", len(oids))
            total = len(oids)  # use actual OID count as authoritative total
            oid_chunks = [oids[i : i + page_size] for i in range(0, len(oids), page_size)]

            for chunk_start in range(0, len(oid_chunks), max_concurrency):
                batch = oid_chunks[chunk_start : chunk_start + max_concurrency]
                responses = await asyncio.gather(
                    *[
                        _fetch_by_object_ids(endpoint_url, chunk, out_fields=out_fields, client=client)
                        for chunk in batch
                    ]
                )
                for page_features in responses:
                    features.extend(page_features)
                    downloaded += len(page_features)
                if progress_callback is not None:
                    await progress_callback(downloaded, total)

        else:
            # Offset pagination fallback
            logger.info("Using offset pagination")
            first_page = await query_feature_layer(
                endpoint_url,
                where=where,
                out_fields=out_fields,
                result_offset=0,
                result_record_count=page_size,
                client=client,
            )
            features = list(first_page.get("features", []))
            downloaded = len(features)

            if progress_callback is not None:
                await progress_callback(downloaded, total)

            offsets = list(range(page_size, total, page_size))
            chunk_size = max(1, min(max_concurrency, len(offsets) or 1))

            for chunk_start in range(0, len(offsets), chunk_size):
                chunk = offsets[chunk_start : chunk_start + chunk_size]
                responses = await asyncio.gather(
                    *[
                        query_feature_layer(
                            endpoint_url,
                            where=where,
                            out_fields=out_fields,
                            result_offset=offset,
                            result_record_count=page_size,
                            client=client,
                        )
                        for offset in chunk
                    ]
                )
                for offset, data in zip(chunk, responses):
                    page_features = data.get("features", [])
                    if not page_features:
                        logger.warning("Empty page at offset %d — skipping", offset)
                        continue
                    features.extend(page_features)
                    downloaded += len(page_features)
                if progress_callback is not None:
                    await progress_callback(downloaded, total)

    if not features:
        return gpd.GeoDataFrame()

    combined = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    logger.info("Downloaded %d total features from %s", len(combined), endpoint_url)
    return combined
