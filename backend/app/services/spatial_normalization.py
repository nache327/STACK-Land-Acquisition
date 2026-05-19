"""Spatial normalization helpers shared by discovery, ingest, and audit code.

Single source of truth for:
  - Esri-WKID → EPSG-code aliasing (102100 / 900913 → 3857, etc.)
  - extracting an EPSG int from an ArcGIS-shaped `spatialReference` dict
  - WGS84-bounds and corrupt-extent sanity checks

The actual coordinate transform lives in `zoning_discovery.reproject_bbox_to_wgs84`
(pyproj-backed). This module is the thin parsing layer that surrounds it so
new callers (audit script, future overlay verifier) don't reach into
zoning_discovery's internals and so the SRID-handling rules stay in one
file the next time we need to add a new alias or guard.

No DB, no network — pure functions; easy to unit-test.
"""
from __future__ import annotations

from typing import Any

# Esri-published WKIDs that are aliases for canonical EPSG codes. ArcGIS
# layers commonly publish `spatialReference: {"wkid": 102100, "latestWkid": 3857}`
# where `wkid` is Esri's private code and `latestWkid` is the EPSG. We prefer
# `latestWkid` when both are present (see `parse_arcgis_spatial_reference`).
ESRI_WKID_TO_EPSG: dict[int, int] = {
    102100: 3857,   # WebMercator (Auxiliary Sphere)
    900913: 3857,   # Google's old WebMercator code, sometimes seen on older layers
}

WGS84 = 4326
WEB_MERCATOR = 3857


def parse_arcgis_spatial_reference(sr: Any) -> int | None:
    """Return the canonical EPSG int from an ArcGIS `spatialReference` dict.

    ArcGIS publishes SR with one or both of `wkid` (Esri code) and
    `latestWkid` (EPSG). We prefer `latestWkid` when present, fall back
    to `wkid` translated through `ESRI_WKID_TO_EPSG`, and return None
    if neither yields a usable integer.
    """
    if not isinstance(sr, dict):
        return None
    latest = sr.get("latestWkid")
    if isinstance(latest, int) and latest > 0:
        return latest
    wkid = sr.get("wkid")
    if isinstance(wkid, int) and wkid > 0:
        return ESRI_WKID_TO_EPSG.get(wkid, wkid)
    return None


def bbox_looks_like_wgs84(bbox: list[float] | None) -> bool:
    """True when every coordinate falls inside the WGS84 valid range
    ([-180,180] lng, [-90,90] lat). Used to spot mis-declared SRIDs:
    a layer that says wkid=4326 but publishes state-plane northings
    (~600000) returns False here, which we treat as a data-integrity
    failure.
    """
    if not bbox or len(bbox) != 4:
        return False
    if any(v is None for v in bbox):
        return False
    xmin, ymin, xmax, ymax = bbox
    return (
        -180.0 <= xmin <= 180.0 and -180.0 <= xmax <= 180.0
        and -90.0 <= ymin <= 90.0 and -90.0 <= ymax <= 90.0
    )


def bbox_span_within_municipal_scale(bbox: list[float] | None, max_deg: float = 30.0) -> bool:
    """True when a reprojected WGS84 bbox spans less than `max_deg` degrees
    in each axis. No US municipal zoning layer covers more than that;
    a >30° span is the signature of a corrupt-extent publisher (e.g.
    South Amboy "Zoning Districts" reprojects to a hemispheric box).
    """
    if not bbox or len(bbox) != 4:
        return False
    if any(v is None for v in bbox):
        return False
    return (bbox[2] - bbox[0]) < max_deg and (bbox[3] - bbox[1]) < max_deg


def srid_is_known_geographic(srid: int | None) -> bool:
    """Quick check for SRIDs we know are already in lat/lng degrees
    (no reprojection needed). Extend the set as we onboard new sources."""
    return srid in (WGS84,)


def srid_is_known_projected(srid: int | None) -> bool:
    """Quick check for SRIDs we know are projected coordinate systems
    (require reprojection before any geometric comparison with WGS84).
    Used by the audit endpoint to distinguish 'unknown CRS' from
    'projected but unsupported' classes."""
    if srid is None or srid_is_known_geographic(srid):
        return False
    return srid == WEB_MERCATOR or 2000 <= srid <= 32766
