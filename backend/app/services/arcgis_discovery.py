"""
ArcGIS layer discovery service — Phase 5 implementation.

Discovery strategies (tried in order):
  1. Direct FeatureServer URL  — user pasted a known endpoint directly
  2. ArcGIS Web Map URL        — parse the item's operationalLayers via REST
  3. ArcGIS Hub search         — geocode the city name, bbox-search Hub for datasets

If no public layer is found, pipeline.py falls back to state-level open data
(e.g. UGRC for UT). Token-protected layers are skipped during Hub search.
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
        "Paste a direct FeatureServer URL, or rely on the state-level "
        "fallback in pipeline.py."
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
    tokens = _name_tokens(name, geo)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        parcel_url = await _hub_search(
            client, "parcels", bbox_str, _PARCEL_KEYWORDS, geo=geo, name_tokens=tokens
        )
        if not parcel_url:
            logger.info("Hub found no parcel layer for %r", name)
            return None

        zoning_url = await _hub_search(
            client, "zoning", bbox_str, _ZONING_KEYWORDS, geo=geo, name_tokens=tokens
        )

    logger.info("Hub → parcel=%s  zoning=%s", parcel_url, zoning_url)
    return LayerEndpoints(
        parcel_url=parcel_url,
        zoning_url=zoning_url,
        source="hub",
        geocoded=geo,
    )


# Generic locality words carry no identity — "mercer" distinguishes a layer,
# "county" does not.
_NAME_STOPWORDS = frozenset({
    "county", "city", "town", "township", "borough", "village",
    "parish", "state", "the", "of", "and",
})


def _name_tokens(name: str, geo: GeocodedPlace | None) -> frozenset[str]:
    """Identity-bearing words from the requested jurisdiction, for ranking."""
    words: set[str] = set()
    for source in (name, geo.county if geo else "", geo.city if geo else ""):
        for w in re.findall(r"[a-z]+", (source or "").lower()):
            if len(w) >= 4 and w not in _NAME_STOPWORDS:
                words.add(w)
    return frozenset(words)


async def _hub_search(
    client: httpx.AsyncClient,
    query: str,
    bbox_str: str,
    keywords: list[str],
    geo: GeocodedPlace | None = None,
    name_tokens: frozenset[str] = frozenset(),
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

    candidates: list[tuple[tuple[int, int], str]] = []
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
        # Rank: a title naming the requested jurisdiction beats everything, THEN
        # shorter titles win within each group. Pure len(title) was the defect that
        # sent "Mercer County, NJ" to a neighboring county's layer titled just
        # "Parcels" — the shortest possible match is also the least identifying,
        # and the Hub bbox filter is only an *intersects* test on a geocoded
        # envelope, so neighbors are routinely in the candidate pool.
        named = 0 if any(t in title for t in name_tokens) else 1
        candidates.append(((named, len(title)), full_url))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    for _, url in candidates:
        meta = await _probe_layer(client, url)
        if meta is None:
            logger.info("Hub: skipping token-protected layer %s", url)
            continue
        if geo is not None and not _extent_contains_point(meta, geo.lon, geo.lat):
            logger.warning(
                "Hub: REJECTING %s — its extent does not contain the geocoded "
                "point (%.4f, %.4f) for the requested jurisdiction. This is the "
                "wrong-county signature (Mercer→Ocean, Burlington→Ocean).",
                url, geo.lon, geo.lat,
            )
            continue
        return url
    return None


async def _probe_layer(client: httpx.AsyncClient, url: str) -> dict | None:
    """Fetch a FeatureServer/Layer's f=json metadata; ``None`` if token-protected.

    One request serves two purposes: the token probe (the old
    ``_is_publicly_queryable``) and the extent for the wrong-county gate — the
    metadata was already being fetched and thrown away.
    """
    try:
        resp = await client.get(url, params={"f": "json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as exc:
        logger.warning("Probe failed for %s: %s", url, exc)
        return None
    if not isinstance(data, dict):
        return None
    if data.get("error"):
        # 499 = Token Required, 498 = Invalid Token, 403 = Forbidden
        logger.info("Layer %s reported error: %s", url, data["error"])
        return None
    return data


# Tolerance around the layer extent, in degrees (~5.5 km). Generous on purpose:
# this gate exists to reject a DIFFERENT county's layer (tens of km off), not to
# litigate a jurisdiction whose geocoded point sits on its own boundary.
_EXTENT_TOLERANCE_DEG = 0.05


def _extent_contains_point(meta: dict, lon: float, lat: float) -> bool:
    """Does the layer's advertised extent contain the geocoded point?

    Decisive for the observed failure: Ocean County's extent (lng −74.55..−74.03)
    does not contain Trenton (−74.76), so the mis-resolved layer is rejected
    outright — no reference geometry needed beyond the layer's own metadata.

    FAIL-OPEN on anything indeterminate (missing extent, unknown projection,
    corrupt values): a healthy discovery must not break because a publisher left
    metadata out. Only a decisively disjoint extent rejects.
    """
    extent = meta.get("extent") or meta.get("fullExtent")
    if not isinstance(extent, dict):
        return True
    try:
        xmin, ymin = float(extent["xmin"]), float(extent["ymin"])
        xmax, ymax = float(extent["xmax"]), float(extent["ymax"])
    except (KeyError, TypeError, ValueError):
        return True
    if not (xmin < xmax and ymin < ymax):
        return True

    sr = extent.get("spatialReference") or {}
    wkid = sr.get("latestWkid") or sr.get("wkid")
    if wkid not in (4326, 4269, None):
        # Any projected CRS (Web-Mercator, state plane, ...) → WGS-84 via the
        # shared helper: pyproj for the general case, hand-rolled Web-Mercator
        # fallback, and the >30° corrupt-extent guard from the South Amboy
        # incident. None (unreprojectable) is indeterminate → fail open.
        from app.services.zoning_discovery import reproject_bbox_to_wgs84

        bbox = reproject_bbox_to_wgs84([xmin, ymin, xmax, ymax], wkid)
        if bbox is None:
            return True
        xmin, ymin, xmax, ymax = bbox
    # WGS-84 plausibility: values outside lat/lng ranges mean the WKID lied.
    if not (-180 <= xmin <= 180 and -90 <= ymin <= 90):
        return True

    t = _EXTENT_TOLERANCE_DEG
    return (xmin - t) <= lon <= (xmax + t) and (ymin - t) <= lat <= (ymax + t)


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

    state = _state_from_geocoder(attrs.get("Region", ""), best.get("address", ""))

    return GeocodedPlace(
        city=attrs.get("City", "") or name,
        state=state,
        county=attrs.get("Subregion", ""),
        lat=loc["y"],
        lon=loc["x"],
        bbox=bbox,
    )


def _state_from_geocoder(region: str, address: str) -> str:
    """Resolve the geocoder's Region/address to a 2-letter state code — or ``""``.

    Region often arrives as a FULL state name ("New Jersey"). The old fallback
    truncated it — ``"New Jersey"[:2].upper()`` — which stamped **NE** on every
    New-Jersey/New-York/New-Mexico/New-Hampshire jurisdiction whose address didn't
    happen to carry a 2-letter code. That single line mislabelled Mercer, Morris,
    Paterson, Elizabeth and New Brunswick rows as state='NE' in prod, twice
    seeding wrong-county ingests. Resolution order:

      1. Region IS a 2-letter code → use it.
      2. Region is a full state name → the _US_STATES map (shared with
         zoning_discovery, which never had this bug).
      3. A ", XX" code inside the address string.
      4. Give up with "" — an EMPTY state is visible and correctable downstream;
         a truncated one looks valid and poisons the jurisdictions row forever.
    """
    # Local import: zoning_discovery imports nothing from this module, so no cycle.
    from app.services.zoning_discovery import _US_STATES

    region = (region or "").strip()
    if len(region) == 2 and region.isalpha():
        return region.upper()
    if region:
        mapped = _US_STATES.get(region.lower())
        if mapped:
            return mapped
    m = re.search(r",\s*([A-Z]{2})\b", (address or "").upper())
    if m and m.group(1) not in ("US",):
        return m.group(1)
    return ""
