"""
ArcGIS layer discovery service — Phase 5 implementation.

Discovery strategies (tried in order):
  1. Direct FeatureServer URL  — user pasted a known endpoint directly
  2. ArcGIS Web Map URL        — parse the item's operationalLayers via REST
  3. ArcGIS Hub search         — geocode the city name, bbox-search Hub for datasets

Regrid fallback is handled in pipeline.py (requires REGRID_API_KEY env var).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

_FEATURE_SERVER_RE = re.compile(
    r"https?://\S+/arcgis/rest/services/[^/?#\s]+/FeatureServer(?:/\d+)?",
    re.IGNORECASE,
)
_WEBMAP_ITEM_RE = re.compile(
    r"[?&/](?:webmap|id)[=/]([a-f0-9]{32})", re.IGNORECASE
)

_PARCEL_KEYWORDS = [
    "parcel", "parcels", "cadastral", "ownership", "tax lot", "pluto", "mappluto",
    "opa_properties", "opa properties", "property_public",
]
_ZONING_KEYWORDS = [
    "zoning", "zone district", "land use", "landuse", "general plan",
    "zoning district", "zoning districts", "zone base", "zoning base",
    "base district", "zoning_base", "zoning overlay", "zoning_districts",
]

# Layers whose titles contain these strings are almost never the city-wide parcel layer
_PARCEL_EXCLUDE = [
    "row", "right of way", "right-of-way",
    "centerline", "address", "building", "utility",
    "pipeline", "easement", "trail", "sidewalk",
    "highway", "road", "street", "subdivision",
    "project", "corridor", "boundary", "permit",
]

_GEOCODER_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer"
    "/findAddressCandidates"
)
_HUB_DATASETS_URL = "https://hub.arcgis.com/api/v3/datasets"


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class GeocodedPlace:
    city: str
    state: str          # 2-letter abbreviation, e.g. "UT"
    county: str         # e.g. "Salt Lake County"
    lat: float
    lon: float
    bbox: list[float]   # [minx, miny, maxx, maxy] in WGS-84


@dataclass
class LayerEndpoints:
    parcel_url: str
    zoning_url: str | None
    source: str             # "direct" | "webmap" | "hub" | "regrid"
    geocoded: GeocodedPlace | None = None


# ─── Public entry point ───────────────────────────────────────────────────────

async def discover_layers(map_url_or_name: str) -> LayerEndpoints:
    """
    Given a city/county name or ArcGIS URL, return parcel + zoning FeatureServer URLs.

    Raises:
        RuntimeError: If no parcel layer can be discovered and Regrid is not available.
    """
    s = map_url_or_name.strip()

    # Strategy 1: direct FeatureServer URL
    if _FEATURE_SERVER_RE.match(s):
        logger.info("Direct FeatureServer URL: %s", s)
        return LayerEndpoints(parcel_url=s.rstrip("/"), zoning_url=None, source="direct")

    # Strategy 2: ArcGIS Web Map / Experience URL
    if "arcgis.com" in s.lower():
        result = await _from_webmap(s)
        if result:
            return result
        # Fall through to Hub search in case the URL is just an arcgis.com page

    # Strategy 3: ArcGIS Hub search (geocode + bbox)
    result = await _from_hub(s)
    if result:
        return result

    raise RuntimeError(
        f"Could not discover ArcGIS parcel layers for '{s}'. "
        "Paste a direct FeatureServer URL, or set REGRID_API_KEY to enable the Regrid fallback."
    )


# ─── Strategy 2: Web Map ──────────────────────────────────────────────────────

async def _from_webmap(url: str) -> LayerEndpoints | None:
    match = _WEBMAP_ITEM_RE.search(url)
    if not match:
        return None

    item_id = match.group(1)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data",
                params={"f": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Web map item %s fetch failed: %s", item_id, exc)
        return None

    layers = data.get("operationalLayers", [])
    parcel_url = _pick_layer(layers, _PARCEL_KEYWORDS)
    zoning_url = _pick_layer(layers, _ZONING_KEYWORDS)

    if not parcel_url:
        logger.info("Web map %s: no parcel layer found in operationalLayers", item_id)
        return None

    logger.info("Web map %s → parcel=%s  zoning=%s", item_id, parcel_url, zoning_url)
    return LayerEndpoints(parcel_url=parcel_url, zoning_url=zoning_url, source="webmap")


def _pick_layer(layers: list[dict], keywords: list[str]) -> str | None:
    """Return the FeatureServer URL of the first layer whose title matches a keyword."""
    for layer in layers:
        title = (layer.get("title") or layer.get("name") or "").lower()
        url = layer.get("url") or ""
        if "FeatureServer" in url and any(kw in title for kw in keywords):
            return url.rstrip("/")
    return None


# ─── Strategy 3: ArcGIS Hub search ────────────────────────────────────────────

async def _from_hub(name: str) -> LayerEndpoints | None:
    try:
        geo = await geocode_jurisdiction(name)
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", name, exc)
        return None

    bbox_str = "{:.6f},{:.6f},{:.6f},{:.6f}".format(*geo.bbox)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        parcel_url = await _hub_search(client, "parcels", bbox_str, _PARCEL_KEYWORDS)
        if not parcel_url:
            logger.info("Hub found no parcel layer for %r", name)
            return None

        zoning_url = await _hub_search(client, "zoning", bbox_str, _ZONING_KEYWORDS)

    logger.info("Hub → parcel=%s  zoning=%s", parcel_url, zoning_url)
    return LayerEndpoints(
        parcel_url=parcel_url,
        zoning_url=zoning_url,
        source="hub",
        geocoded=geo,
    )


async def _hub_search(
    client: httpx.AsyncClient,
    query: str,
    bbox_str: str,
    keywords: list[str],
) -> str | None:
    try:
        resp = await client.get(
            _HUB_DATASETS_URL,
            params={
                "q": query,
                "bbox": bbox_str,
                "filter[type]": "Feature Service",
                "page[size]": "20",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Hub search q=%r failed: %s", query, exc)
        return None

    candidates: list[tuple[int, str]] = []
    for ds in data.get("data", []):
        attrs = ds.get("attributes", {})
        title = (attrs.get("name") or attrs.get("title") or "").lower()
        url = attrs.get("url") or ""
        layer_id = attrs.get("layerId")

        if not any(kw in title for kw in keywords):
            continue
        if "FeatureServer" not in url:
            continue
        if any(ex in title for ex in _PARCEL_EXCLUDE):
            logger.debug("Hub: skipping excluded layer %r", title)
            continue

        full_url = url.rstrip("/")
        if layer_id is not None:
            full_url = f"{full_url}/{layer_id}"
        # Score: shorter title = more likely to be the city-wide layer
        candidates.append((len(title), full_url))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ─── Geocoding ────────────────────────────────────────────────────────────────

async def geocode_jurisdiction(name: str) -> GeocodedPlace:
    """
    Geocode a jurisdiction name using the ArcGIS World Geocoder (no key required).
    Raises RuntimeError if no result is found.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _GEOCODER_URL,
            params={
                "SingleLine": name,
                "outFields": "Region,Subregion,City",
                "maxLocations": "1",
                "f": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Geocoder returned no results for {name!r}")

    best = candidates[0]
    loc = best["location"]
    attrs = best.get("attributes", {})
    extent = best.get("extent")

    if extent:
        bbox = [extent["xmin"], extent["ymin"], extent["xmax"], extent["ymax"]]
    else:
        d = 0.4  # ~44 km buffer at mid-latitudes
        bbox = [loc["x"] - d, loc["y"] - d, loc["x"] + d, loc["y"] + d]

    # Region is sometimes a full state name — try to pull 2-letter code from address
    state = attrs.get("Region", "")
    if len(state) > 2:
        address = best.get("address", "")
        m = re.search(r",\s*([A-Z]{2})\b", address.upper())
        if m:
            state = m.group(1)
        else:
            state = state[:2].upper()

    return GeocodedPlace(
        city=attrs.get("City", "") or name,
        state=state.upper() if state else "",
        county=attrs.get("Subregion", ""),
        lat=loc["y"],
        lon=loc["x"],
        bbox=bbox,
    )
