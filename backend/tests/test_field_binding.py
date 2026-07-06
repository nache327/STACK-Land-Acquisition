"""
Unit tests for the shared field-binding layer (Tier 1 hardening):
  - value-shape validator (catch #33 numeric-city, #34 URL/over-long/constant)
  - Option-B per-jurisdiction field-override precedence
  - the end-to-end effect in both _map_rows: a URL bound as a code is dropped,
    and an override pins the real code ahead of a colliding global candidate.

Pure/in-memory — no DB or network.
"""
from __future__ import annotations

import uuid

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from app.services import field_binding as fb
from app.services.ingestion import _map_row as parcel_map_row
from app.services.zoning_ingestion import (
    _ZONE_CODE_FIELDS,
    _ZONE_NAME_FIELDS,
    _map_row as zoning_map_row,
)

_JID = uuid.uuid4()
_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _row(**attrs):
    """Build a single GeoDataFrame row (pandas Series) with the given attrs."""
    gdf = gpd.GeoDataFrame(
        {k: [v] for k, v in attrs.items()},
        geometry=[_SQUARE],
        crs="EPSG:4326",
    )
    return next(gdf.iterrows())[1]


# ── validator ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "https://ecode360.com/30218069",
    "HTTP://example.com/x",
    "R-3 - Residence District (long label)",  # > 20 chars
])
def test_bad_code_reason_flags(value):
    assert fb.bad_code_reason(value)


@pytest.mark.parametrize("value", ["R-3", "LI", "PIP", "C-1", "R-100", None, ""])
def test_bad_code_reason_allows(value):
    assert fb.bad_code_reason(value) is None


def test_numeric_city():
    assert fb.is_numeric_city("43") is True
    assert fb.is_numeric_city("Darby Borough") is False
    assert fb.is_numeric_city(None) is False


def test_constant_code_detector():
    assert fb.constant_code_reason(["District"] * 12)  # 100% one value
    assert fb.constant_code_reason(["R-1", "R-2", "LI", "C-1", "O", "I", "R-3"]) is None
    assert fb.constant_code_reason(["District"] * 3) is None  # below min_rows floor


def test_matched_field_reports_source():
    row = {"LABEL": "R-3", "Zoning_Code": "https://ecode360.com/x"}
    assert fb.matched_field(row, ["LABEL", "ZONING_CODE"]) == "LABEL"


# ── zoning _map_row: catch #34 (Delaware County PA shape) ─────────────────────

def _delco_zoning_row():
    return _row(
        LABEL="R-3",
        Zoning_Code="https://ecode360.com/30218069",   # the URL landmine
        Legend_Info="R-3 - Residence District",
    )


def test_zoning_without_override_drops_url_code():
    """Global lists pick `Zoning_Code` (matches ZONING_CODE) = a URL → the
    value-shape validator drops the row rather than binding a URL as the code."""
    row = _delco_zoning_row()
    # global-list code binding would be the URL — confirm the collision exists…
    assert fb.first_match(row, _ZONE_CODE_FIELDS) == "https://ecode360.com/30218069"
    # …and that _map_row rejects it.
    assert zoning_map_row(row, _JID) is None


def test_zoning_with_override_binds_real_code():
    """Option-B override pins LABEL ahead of the global list → binds R-3."""
    row = _delco_zoning_row()
    code_fields = ["LABEL"] + [f for f in _ZONE_CODE_FIELDS if f != "LABEL"]
    name_fields = ["Legend_Info"] + [f for f in _ZONE_NAME_FIELDS if f != "Legend_Info"]
    mapped = zoning_map_row(row, _JID, code_fields=code_fields, name_fields=name_fields)
    assert mapped is not None
    assert mapped["zone_code"] == "R-3"
    assert mapped["zone_name"] == "R-3 - Residence District"


# ── parcel _map_row: catch #33 numeric city + #34 URL zone code ───────────────

def test_parcel_drops_numeric_city():
    row = _row(PIN="12-345", CITY="43")
    mapped = parcel_map_row(row, _JID)
    assert mapped is not None
    assert mapped["city"] is None  # numeric muni code dropped, not persisted


def test_parcel_drops_url_zoning_code():
    row = _row(PIN="12-345", ZONING_CODE="https://ecode360.com/30218069")
    mapped = parcel_map_row(row, _JID)
    assert mapped is not None
    assert mapped["zoning_code"] is None  # URL dropped → NULL for spatial backfill


def test_parcel_zone_field_override():
    row = _row(PIN="12-345", ZONING="C-1", MYZONE="LI")
    mapped = parcel_map_row(row, _JID, parcel_zone_field="MYZONE")
    assert mapped["zoning_code"] == "LI"  # override beats the global ZONING field
