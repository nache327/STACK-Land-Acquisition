"""Unit tests for municipality_normalize.canonical_city + alias resolution.

canonical_city is the single normalizer that decides whether two free-text
city strings (parcels.city vs a sibling jurisdiction name vs
zone_use_matrix.municipality) refer to the same place. Getting it wrong
silently drops a city's zoning coverage for a county jurisdiction, so the
contract is pinned here — especially the "Salt Lake City" guard, which must
NOT collapse to "Salt Lake" (that would alias the city onto the county).
"""
from __future__ import annotations

import pytest

from app.services.municipality_normalize import (
    canonical_city,
    resolve_with_alias_map,
)


# ── State-suffix stripping ───────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("Sandy, UT", "sandy"),
    ("Draper, UT", "draper"),
    ("Marlboro, NJ", "marlboro"),
])
def test_strips_state_suffix(raw: str, expected: str) -> None:
    assert canonical_city(raw) == expected


# ── Trailing " City" stripping (UGRC PARCEL_CITY drops "City") ───────────


@pytest.mark.parametrize("raw,expected", [
    ("Draper City", "draper"),
    ("Draper City, UT", "draper"),
    ("West Valley City", "west valley"),
])
def test_strips_trailing_city(raw: str, expected: str) -> None:
    assert canonical_city(raw) == expected


# ── The Salt Lake City guard — must stay "salt lake city" ────────────────


def test_salt_lake_city_not_collapsed() -> None:
    assert canonical_city("Salt Lake City") == "salt lake city"
    assert canonical_city("Salt Lake City, UT") == "salt lake city"
    assert canonical_city("salt lake city") == "salt lake city"


def test_salt_lake_county_distinct_from_city() -> None:
    # County jurisdictions should not normalize to the city key.
    assert canonical_city("Salt Lake County, UT") != canonical_city("Salt Lake City")


# ── Case folding + empties ───────────────────────────────────────────────


def test_case_insensitive() -> None:
    assert canonical_city("SANDY") == canonical_city("sandy") == "sandy"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_falsy_inputs_return_empty(raw) -> None:
    assert canonical_city(raw) == ""


# ── Alias resolution ─────────────────────────────────────────────────────


def test_alias_map_resolves_variant_to_canonical() -> None:
    # alias_map is keyed by canonical_city(alias) -> canonical city string.
    alias_map = {canonical_city("Salt Lake Cty"): "Salt Lake City"}
    assert resolve_with_alias_map("Salt Lake Cty", alias_map) == "salt lake city"


def test_alias_map_passthrough_when_no_match() -> None:
    assert resolve_with_alias_map("Sandy, UT", {}) == "sandy"
