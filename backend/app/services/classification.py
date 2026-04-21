"""
Heuristic zone-code classifier.

Given a zone code (and optionally a zone name or source-provided class field),
returns a canonical `ZoneClass` value. Used when a zoning layer does not carry
an authoritative class attribute — e.g., NYC MapPLUTO ships only ZONEDIST codes,
Philadelphia OPA ships only `zoning` codes.

Ordering matters: the first matching rule wins. Long-prefix tests come before
short ones (e.g., "CMX-2" → mixed_use before "C" → commercial).
"""
from __future__ import annotations

import re
from typing import Iterable

from app.models.zoning_district import ZoneClass

# ── Literal keyword matches (tested against both code and name, case-insensitive)

_KEYWORD_RULES: list[tuple[ZoneClass, tuple[str, ...]]] = [
    (ZoneClass.mixed_use, (
        "mixed use", "mixed-use", "cmx", "mu-", "mu ", "tod", "transit oriented",
    )),
    (ZoneClass.overlay, (
        "overlay", "special purpose", "historic", "flood overlay",
    )),
    (ZoneClass.open_space, (
        "open space", "parks", "park", "recreation", "conservation", "forest",
        "greenway",
    )),
    (ZoneClass.agricultural, (
        "agricultur", "farm", "rural residential", "rr-",
    )),
    (ZoneClass.industrial, (
        "industrial", "manufactur", "warehouse", "logistics",
    )),
    (ZoneClass.commercial, (
        "commercial", "business", "office", "retail", "shopping",
    )),
    (ZoneClass.residential, (
        "residential", "dwelling", "single family", "multifamily", "multi-family",
        "multi family", "townhouse",
    )),
    (ZoneClass.special, (
        "special district", "pud", "planned unit development", "pdd",
        "planned development",
    )),
]

# ── Regex rules on zone code only (whole-code match, case-insensitive)

_CODE_PATTERNS: list[tuple[ZoneClass, re.Pattern[str]]] = [
    # Mixed-use (test before commercial/residential since codes overlap).
    # The trailing `[-\s0-9a-z]*` covers NYC-style suffixes ("R6A"), Philly
    # ("CMX-3"), and multi-part numeric codes ("C4-6A", "M1-1").
    (ZoneClass.mixed_use, re.compile(r"^(cmx|mu|mx|tod|muo|mrd)[-\s0-9a-z]*$", re.I)),
    # Industrial: I-1/I-2, M-1/M-2 (incl. NYC M1-1, M2-3), LI, HI, IH, IL, IP, IND, IR, ICM
    (ZoneClass.industrial, re.compile(r"^(m|i|li|hi|ih|il|ip|ind|ir|icm|lm|gm|hm)[-\s0-9a-z]*$", re.I)),
    # Commercial: C-\d (incl. NYC C1-2 / C4-6A), CB, CC, CG, CN, CO, CS, CBD, NC, GC, HC, LC, SC, B-\d
    (ZoneClass.commercial, re.compile(
        r"^(cbd|cb|cc|cg|cn|co|cs|c|nc|gc|hc|lc|sc|tc|rc|of|bp|pbd|oc|ob|b)[-\s0-9a-z]*$", re.I
    )),
    # Agricultural: A-\d, AG
    (ZoneClass.agricultural, re.compile(r"^(ag|a)[-\s0-9a-z]*$", re.I)),
    # Open space / public facilities: OS, PF, PR, PL
    (ZoneClass.open_space, re.compile(r"^(os|pf|pr|pl)[-\s0-9a-z]*$", re.I)),
    # Residential: R-\d, RM, RR, RS, RH, RA, R1-1, R6A, R8X, etc.
    (ZoneClass.residential, re.compile(r"^r[-\s0-9a-z]*$", re.I)),
]


def classify_zone_code(
    code: str | None,
    zone_name: str | None = None,
    source_class: str | None = None,
) -> ZoneClass:
    """
    Classify a zoning code into a canonical ZoneClass.

    Args:
        code:         The zone code string (e.g., "R6A", "M1-4", "CMX-2").
        zone_name:    Optional human-readable name ("Light Manufacturing").
        source_class: Optional verbatim class string from the source layer.

    Returns:
        A ZoneClass value. Defaults to `unknown` if nothing matches.
    """
    # Source-provided class wins when it's one of our canonical values
    if source_class:
        normalized = _normalize(source_class)
        for zc in ZoneClass:
            if zc.value == normalized:
                return zc

    haystacks = [s for s in (code, zone_name, source_class) if s]
    if not haystacks:
        return ZoneClass.unknown

    # Keyword scan across code + name (most ordinances describe the zone in the name)
    joined = " ".join(haystacks).lower()
    for zc, keywords in _KEYWORD_RULES:
        if any(kw in joined for kw in keywords):
            return zc

    # Regex-match on the code itself
    if code:
        stripped = code.strip()
        for zc, pattern in _CODE_PATTERNS:
            if pattern.match(stripped):
                return zc

    return ZoneClass.unknown


def classify_many(
    codes: Iterable[str],
) -> dict[str, ZoneClass]:
    """Batch helper — returns {code: zone_class}."""
    return {c: classify_zone_code(c) for c in codes}


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z_]+", "_", s.strip().lower()).strip("_")
