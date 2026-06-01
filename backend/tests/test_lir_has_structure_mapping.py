"""Unit tests for has_structure_from_prop_class.

The PROP_CLASS → has_structure mapping is the load-bearing logic that
decides whether a SLCo parcel can match Hot Deals / Worth a Look at
all. Easy to break by adding a new PROP_CLASS to one set without
remembering the other; these tests pin the current contract.
"""
from __future__ import annotations

import pytest

from app.services.lir_has_structure_backfill import has_structure_from_prop_class


# ── Vacant variants → False ──────────────────────────────────────────────


@pytest.mark.parametrize("prop_class", [
    "Vacant",
    "Vacant - Agricultural",
    "Vacant - Commercial",
    "Undeveloped",
])
def test_vacant_variants_map_to_false(prop_class: str) -> None:
    assert has_structure_from_prop_class(prop_class) is False


def test_vacant_case_insensitive() -> None:
    assert has_structure_from_prop_class("VACANT") is False
    assert has_structure_from_prop_class("vacant") is False
    assert has_structure_from_prop_class("Vacant - AGRICULTURAL") is False


# ── Developed variants → True ───────────────────────────────────────────


@pytest.mark.parametrize("prop_class", [
    "Residential",
    "Commercial",
    "Commercial - Apartment & Condo",
    "Commercial - Retail",
    "Commercial - Office Space",
    "Commercial - Industrial",
    "Industrial",
    "Mixed Use",
])
def test_built_variants_map_to_true(prop_class: str) -> None:
    assert has_structure_from_prop_class(prop_class) is True


# ── Ambiguous → None ────────────────────────────────────────────────────


@pytest.mark.parametrize("prop_class", [
    "Tax Exempt",
    "Tax Exempt - Government",
    "Tax Exempt - Charitable Organization or Religious",
    "Greenbelt",
    "Centrally Assessed",
])
def test_ambiguous_classes_map_to_none(prop_class: str) -> None:
    """Tax-exempt / greenbelt parcels can be developed (gov't buildings,
    churches) or undeveloped (parks, easements). Leave the column NULL
    rather than guess wrong and corrupt the viability check."""
    assert has_structure_from_prop_class(prop_class) is None


def test_unknown_prop_class_maps_to_none() -> None:
    """Drift defense — if AGRC adds a new PROP_CLASS we haven't seen,
    leave it NULL rather than default to True or False."""
    assert has_structure_from_prop_class("Brand New Class We Made Up") is None


# ── Null / empty inputs → None ──────────────────────────────────────────


def test_null_input_returns_none() -> None:
    assert has_structure_from_prop_class(None) is None


def test_empty_string_returns_none() -> None:
    assert has_structure_from_prop_class("") is None
    assert has_structure_from_prop_class("   ") is None


# ── Whitespace handling ─────────────────────────────────────────────────


def test_whitespace_trimmed() -> None:
    assert has_structure_from_prop_class("  Vacant  ") is False
    assert has_structure_from_prop_class("\tResidential\n") is True
