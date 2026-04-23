"""
Unit tests for the heuristic zone-code classifier.

Covers the NY/PA common code families plus the Utah/Draper legacy codes to
guard against regressions during the Storage → Zoning Intelligence pivot.
"""
from __future__ import annotations

import pytest

from app.models.zoning_district import ZoneClass
from app.services.classification import classify_zone_code


# fmt: off
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        # ── Residential ──
        ("R1",          ZoneClass.residential),
        ("R-2",         ZoneClass.residential),
        ("R6A",         ZoneClass.residential),       # NYC
        ("R10",         ZoneClass.residential),
        ("RSF-1",       ZoneClass.residential),
        ("RA-1",        ZoneClass.residential),
        # ── Commercial ──
        ("C-1",         ZoneClass.commercial),
        ("C2-4",        ZoneClass.commercial),        # NYC
        ("CBD",         ZoneClass.commercial),
        ("NC",          ZoneClass.commercial),
        ("B-2",         ZoneClass.commercial),
        # ── Industrial ──
        ("M1-1",        ZoneClass.industrial),        # NYC light manufacturing
        ("M2-3",        ZoneClass.industrial),
        ("M3-2",        ZoneClass.industrial),        # NYC heavy manufacturing
        ("LI",          ZoneClass.industrial),
        ("HI",          ZoneClass.industrial),
        ("I-1",         ZoneClass.industrial),
        ("I-2",         ZoneClass.industrial),
        # ── Mixed use ──
        ("MU-1",        ZoneClass.mixed_use),
        ("CMX-2",       ZoneClass.mixed_use),         # Philadelphia
        ("CMX-5",       ZoneClass.mixed_use),
        ("TOD-1",       ZoneClass.mixed_use),
        # ── Open space / parks ──
        ("OS",          ZoneClass.open_space),
        ("NOS",         ZoneClass.open_space),   # Natural Open Space
        ("PF",          ZoneClass.open_space),
        # ── Planned Residential (Utah PR codes are residential, not open space) ──
        ("PR-1",        ZoneClass.residential),
        ("PR-2.0",      ZoneClass.residential),  # American Fork
        # ── Agricultural ──
        ("A-1",         ZoneClass.agricultural),
        ("AG",          ZoneClass.agricultural),
        # ── Unknown fallback ──
        ("XYZ-123",     ZoneClass.unknown),
        ("",            ZoneClass.unknown),
    ],
)
# fmt: on
def test_classify_zone_code(code: str, expected: ZoneClass) -> None:
    assert classify_zone_code(code) == expected


def test_source_class_overrides_code_pattern() -> None:
    # If the source layer gives us an explicit class, we trust it.
    result = classify_zone_code(
        "R1", zone_name=None, source_class="industrial"
    )
    assert result == ZoneClass.industrial


def test_zone_name_keyword_overrides_ambiguous_code() -> None:
    # Code "A" alone is agricultural-ish, but when the name says otherwise,
    # keyword scan wins for multi-signal classification.
    result = classify_zone_code(
        "A", zone_name="A Light Manufacturing District"
    )
    assert result == ZoneClass.industrial


def test_none_returns_unknown() -> None:
    assert classify_zone_code(None) == ZoneClass.unknown


def test_philadelphia_mixed_use_variants() -> None:
    # Philly uses CMX (Commercial Mixed-Use) with numeric suffixes.
    for code in ("CMX-1", "CMX-2", "CMX-3", "CMX-4", "CMX-5"):
        assert classify_zone_code(code) == ZoneClass.mixed_use, f"failed for {code}"


def test_nyc_residential_contextual_codes() -> None:
    # NYC uses suffixes heavily: R6A, R6B, R7D, R8X, R10A, etc.
    for code in ("R1-1", "R6", "R6A", "R7-3", "R8X", "R10A"):
        assert classify_zone_code(code) == ZoneClass.residential, f"failed for {code}"
