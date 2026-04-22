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
        "transit-oriented", "downtown mixed",
    )),
    (ZoneClass.overlay, (
        "overlay", "special purpose", "historic", "flood overlay",
    )),
    (ZoneClass.open_space, (
        "open space", "parks", "park", "recreation", "conservation", "forest",
        "greenway", "civic", "institutional", "public facility", "public facilities",
        "fire station", "pond", "water",
    )),
    (ZoneClass.agricultural, (
        "agricultur", "farm", "rural residential", "rr-",
    )),
    (ZoneClass.industrial, (
        "industrial", "manufactur", "warehouse", "logistics",
        "sand & gravel", "sand and gravel", "gravel", "mining",
    )),
    (ZoneClass.commercial, (
        "commercial", "business", "office", "retail", "shopping",
        "professional office", "gateway commercial", "neighborhood commercial",
        "general commercial", "highway commercial", "town center",
    )),
    (ZoneClass.residential, (
        "residential", "dwelling", "single family", "multifamily", "multi-family",
        "multi family", "townhouse", "townhome", "townhomes",
        "low density", "high density", "medium density",
        "senior housing", "village", "estates",
    )),
    (ZoneClass.special, (
        "special district", "pud", "planned unit development", "pdd",
        "planned development", "specific plan", "flex use",
        "redevelopment", "subarea", "under review",
    )),
]

# ── Regex rules on zone code only (whole-code match, case-insensitive)

_CODE_PATTERNS: list[tuple[ZoneClass, re.Pattern[str]]] = [
    # Mixed-use (test before commercial/residential since codes overlap).
    # Covers: MU, MX, TOD, CMX, T-M (Transit/Mixed), TMX, MXD, DT (Downtown SLC/Provo)
    (ZoneClass.mixed_use, re.compile(r"^(cmx|mu|mx|tod|muo|mrd|tmx|mxd|t[-/]m|dt|d)[-\s0-9a-z]*$", re.I)),
    # Industrial: I-1/I-2, M-1/M-2, LI, HI, H/I (slash variant), IH, IL, IP, IND, IR, ICM
    (ZoneClass.industrial, re.compile(r"^(m|i|li|hi|h[/]i|ih|il|ip|ind|ir|icm|lm|gm|hm)[-\s0-9a-z/]*$", re.I)),
    # Open space / civic / public facilities — must come BEFORE commercial (CI starts with C)
    # NOS = Natural Open Space; O-S = Open Space (Murray); EUO = Environmental/Open
    (ZoneClass.open_space, re.compile(r"^(os|nos|o-s|pf|pr|pl|ci|pz|ps|euo)[-\s0-9a-z]*$", re.I)),
    # Special districts — must come BEFORE commercial
    (ZoneClass.special, re.compile(r"^(pc|pud|pd|pdz|spa|pdd|cpd|ssd)[-\s0-9a-z]*$", re.I)),
    # Commercial: C-\d, CB, CC, CG, CN, CO, CS, CBD, NC, GC, HC, LC, SC, B-\d, BP
    # P-O / PO = Professional Office; HBD = Highway Business District
    (ZoneClass.commercial, re.compile(
        r"^(cbd|cb|cc|cg|cn|co|cs|c|nc|gc|hc|lc|sc|tc|rc|of|bp|pbd|oc|ob|b|p-?o|hbd)[-\s0-9a-z]*$", re.I
    )),
    # Agricultural: A-\d, AG
    (ZoneClass.agricultural, re.compile(r"^(ag|a)[-\s0-9a-z]*$", re.I)),
    # Residential: R-\d, RA, RM, RR, RS, RH, R1-1, R6A, TH, SF, MF, FR (Foothill Res.),
    # HDR/LDR/MDR (High/Low/Medium Density Residential), MR (Multi-Res),
    # SR (Standard Residential — SLC/North Salt Lake), F- (Foothill — Cottonwood Heights)
    # Allows decimal in code (R-2.5, FR-2.5) via `[-\s.0-9a-z]*`
    (ZoneClass.residential, re.compile(
        r"^(fr|hdr|ldr|mdr|mr|sr|f|r|th|sf|mf|rm|rr|rs|rh)[-\s.0-9a-z]*$", re.I
    )),
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

    # Some counties store multiple zone codes separated by commas or semicolons,
    # e.g. "NC, GC" or "A5; CC; RM2". Classify the first segment that resolves.
    if code:
        for sep in (",", ";"):
            if sep in code:
                for segment in code.split(sep):
                    seg = segment.strip()
                    if seg:
                        result = classify_zone_code(seg, zone_name, source_class)
                        if result != ZoneClass.unknown:
                            return result
                break  # tried splitting; fall through to keyword/regex on full code

    # Strip parenthetical suffixes common in Utah: "C-G(ZC)", "R-1-8(INF)", "RM(10)"
    # Keep the base code for regex matching but pass full code through keywords first.
    if code and re.search(r"\(", code):
        base = re.sub(r"\s*\(.*\)\s*$", "", code).strip()
        if base and base != code:
            result = classify_zone_code(base, zone_name, source_class)
            if result != ZoneClass.unknown:
                return result

    # Strip "/zc" or "/ZC" suffix used by Millcreek overlay variants: "C-2/zc" → "C-2"
    if code and re.search(r"/zc\s*$", code, re.I):
        base = re.sub(r"/zc\s*$", "", code, flags=re.I).strip()
        if base:
            result = classify_zone_code(base, zone_name, source_class)
            if result != ZoneClass.unknown:
                return result

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
