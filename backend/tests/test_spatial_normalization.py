"""Unit tests for spatial_normalization helpers — pure functions, no I/O."""
from __future__ import annotations

from app.services.spatial_normalization import (
    ESRI_WKID_TO_EPSG,
    bbox_looks_like_wgs84,
    bbox_span_within_municipal_scale,
    parse_arcgis_spatial_reference,
    srid_is_known_geographic,
    srid_is_known_projected,
)


# ─── parse_arcgis_spatial_reference ──────────────────────────────────────────

def test_parse_sr_prefers_latest_wkid():
    """When both fields are populated, latestWkid (true EPSG) wins."""
    sr = {"wkid": 102100, "latestWkid": 3857}
    assert parse_arcgis_spatial_reference(sr) == 3857


def test_parse_sr_falls_back_to_wkid_through_alias_map():
    """Old MapServers only publish `wkid`; we translate via the alias map."""
    sr = {"wkid": 102100}
    assert parse_arcgis_spatial_reference(sr) == 3857


def test_parse_sr_returns_wkid_unchanged_when_not_an_alias():
    """An EPSG-shaped wkid (e.g. 3424) without latestWkid passes through."""
    sr = {"wkid": 3424}
    assert parse_arcgis_spatial_reference(sr) == 3424


def test_parse_sr_returns_none_for_missing_or_zero():
    """Missing dict, empty dict, or wkid=0 all yield None — never silently
    coerce to a default EPSG."""
    assert parse_arcgis_spatial_reference(None) is None
    assert parse_arcgis_spatial_reference({}) is None
    assert parse_arcgis_spatial_reference({"wkid": 0}) is None
    assert parse_arcgis_spatial_reference("not a dict") is None


def test_parse_sr_900913_alias():
    """900913 is Google's old WebMercator code — still seen on some MapServers."""
    assert parse_arcgis_spatial_reference({"wkid": 900913}) == 3857
    assert ESRI_WKID_TO_EPSG[900913] == 3857


# ─── bbox_looks_like_wgs84 ────────────────────────────────────────────────────

def test_bbox_looks_like_wgs84_yes_for_lng_lat_values():
    assert bbox_looks_like_wgs84([-74.0, 40.9, -73.9, 41.1]) is True


def test_bbox_looks_like_wgs84_no_for_state_plane_values():
    """NJ State Plane northings are ~600000 ft — way out of lat/lng range."""
    assert bbox_looks_like_wgs84([602253.34, 756172.03, 619511.88, 782410.35]) is False


def test_bbox_looks_like_wgs84_no_for_mercator_values():
    assert bbox_looks_like_wgs84([-8245000.0, 4970000.0, -8230000.0, 4985000.0]) is False


def test_bbox_looks_like_wgs84_no_for_malformed_input():
    assert bbox_looks_like_wgs84(None) is False
    assert bbox_looks_like_wgs84([]) is False
    assert bbox_looks_like_wgs84([1.0, 2.0]) is False
    assert bbox_looks_like_wgs84([1.0, None, 2.0, 3.0]) is False


# ─── bbox_span_within_municipal_scale ────────────────────────────────────────

def test_municipal_span_yes_for_county_bbox():
    """Bergen County is well under 30° in any axis."""
    assert bbox_span_within_municipal_scale([-74.27, 40.76, -73.90, 41.13]) is True


def test_municipal_span_no_for_hemispheric_bbox():
    """South-Amboy's corrupt extent reprojects to a hemispheric span and
    must be rejected — this is the case that motivated the guard."""
    assert bbox_span_within_municipal_scale([-164.0, -45.0, 15.0, 45.0]) is False


# ─── srid_is_known_* ─────────────────────────────────────────────────────────

def test_srid_is_known_geographic():
    assert srid_is_known_geographic(4326) is True
    assert srid_is_known_geographic(3857) is False
    assert srid_is_known_geographic(None) is False


def test_srid_is_known_projected_covers_state_plane_range():
    """State-plane SRIDs land in the 2000-32766 range. We accept the
    coarse range to keep the check cheap — pyproj is the authoritative
    transformer downstream."""
    assert srid_is_known_projected(3857) is True
    assert srid_is_known_projected(3424) is True   # NJ State Plane
    assert srid_is_known_projected(3435) is True   # IL State Plane East
    assert srid_is_known_projected(2234) is True   # CT State Plane
    assert srid_is_known_projected(4326) is False  # geographic, not projected
    assert srid_is_known_projected(None) is False
