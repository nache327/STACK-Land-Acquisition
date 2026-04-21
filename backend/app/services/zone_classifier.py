"""
Universal zone character classifier and shared classification utilities.

Provides:
  - PerUseClassification: dataclass returned by all classify_* functions
  - classify_by_zone_character(): universal fallback for any US city zone code
  - apply_luxury_garage_inference(): shared inference rule (extracted from
    ordinance_parser.py so scripts and the LLM pipeline use identical logic)

Design principles:
  - Conservative by default: unknown zones → prohibited (not conditional)
  - Per-use granularity: each of the 4 target uses is classified independently
  - No per-city keyword hacks: naming conventions cover ~95% of US zones
  - Classification source is always written to the DB (rule / llm / human)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PerUseClassification:
    """Per-use classification result returned by all classify_* functions."""
    self_storage: str         # permitted | conditional | prohibited | unclear
    mini_warehouse: str
    light_industrial: str
    luxury_garage_condo: str
    confidence: float
    notes: str


# ─── Shared inference rule ────────────────────────────────────────────────────

def apply_luxury_garage_inference(cls: PerUseClassification) -> PerUseClassification:
    """
    Infer luxury_garage_condo when the ordinance is silent.

    Rule (applied in order):
      1. mini_warehouse or self_storage == permitted  → permitted
      2. mini_warehouse or self_storage == conditional → conditional
      3. light_industrial == permitted or conditional  → conditional
      4. none of the above                             → prohibited

    Only overrides when luxury_garage_condo is 'unclear'.
    """
    if cls.luxury_garage_condo != "unclear":
        return cls

    ss, mw, li = cls.self_storage, cls.mini_warehouse, cls.light_industrial

    if mw == "permitted" or ss == "permitted":
        lgc = "permitted"
    elif mw == "conditional" or ss == "conditional":
        lgc = "conditional"
    elif li in ("permitted", "conditional"):
        lgc = "conditional"
    else:
        lgc = "prohibited"

    return PerUseClassification(
        self_storage=cls.self_storage,
        mini_warehouse=cls.mini_warehouse,
        light_industrial=cls.light_industrial,
        luxury_garage_condo=lgc,
        confidence=cls.confidence,
        notes=cls.notes,
    )


# ─── Zone character patterns ──────────────────────────────────────────────────
# Each tuple: (compiled regex, storage_class, li_class, confidence, label)
# storage_class applies to both self_storage and mini_warehouse.
# Evaluated in order; first match wins.

_ZONE_RULES: list[tuple[re.Pattern, str, str, float, str]] = [
    # ── Industrial / Manufacturing → permitted ────────────────────────────────
    (re.compile(
        r'^(I|M|LI|LM|HI|HM|ML|IND|MFG|MAN|INDUS|MANUFACTUR)'
        r'([\s\-_/]|$)',
        re.IGNORECASE),
        "permitted", "permitted", 0.72, "industrial prefix"),

    (re.compile(
        r'^(I|M)-?\d',
        re.IGNORECASE),
        "permitted", "permitted", 0.75, "industrial numbered"),

    (re.compile(
        r'\b(LIGHT\s+INDUSTR|HEAVY\s+INDUSTR|LIGHT\s+MANUFACTUR|HEAVY\s+MANUFACTUR'
        r'|LIGHT\s+INDUSTRIAL|HEAVY\s+COMMERCIAL\s+INDUSTRIAL'
        r'|BUSINESS\s+PARK|AIRPARK|RESEARCH\s+PARK|FLEX\s+INDUSTRIAL'
        r'|COMMERCIAL.+STORAGE|SAND\s+.?\s+GRAVEL|DESTINATION\s+RETAIL)',
        re.IGNORECASE),
        "permitted", "permitted", 0.78, "industrial descriptor"),

    (re.compile(r'^BP$', re.IGNORECASE),
        "permitted", "permitted", 0.72, "business park"),

    # Commercial/Industrial hybrids
    (re.compile(r'(I|M|IND)\s*/\s*(C|COM)', re.IGNORECASE),
        "permitted", "permitted", 0.70, "industrial-commercial hybrid"),

    # Mixed Use — commercial-leaning → conditional
    (re.compile(
        r'(MU-C|MXD-C|CX\b|TOD\b|TRANSIT[\s-]+ORIENTED|MU.+COMMERCIAL)',
        re.IGNORECASE),
        "conditional", "conditional", 0.65, "commercial MU"),

    # ── Commercial / Business → conditional ──────────────────────────────────
    (re.compile(
        r'^(C|B|GC|CC|HC|NC|SC|DC|TC|CG|CB|CS|CN|CU|CRD|CRZ|CA|CH|CR|CL|CI)\b'
        r'(?!VIC|IVIC)',   # exclude Civic
        re.IGNORECASE),
        "conditional", "conditional", 0.70, "commercial prefix"),

    (re.compile(
        r'\b(GENERAL\s+COMMERCIAL|HIGHWAY\s+COMMERCIAL|REGIONAL\s+COMMERCIAL'
        r'|NEIGHBORHOOD\s+COMMERCIAL|COMMERCIAL\s+CORRIDOR'
        r'|COMMUNITY\s+COMMERCIAL|DOWNTOWN\s+COMMERCIAL|TOWN\s+CENTER'
        r'|VILLAGE\s+CORE|INFILL\s+(OVERLAY|COMMERCIAL)'
        r'|MIXED\s+USE\s+COMMERCIAL)',
        re.IGNORECASE),
        "conditional", "conditional", 0.70, "commercial descriptor"),

    # Infill Overlay (treated as commercial transition zone)
    (re.compile(r'INFILL\s+OVERLAY', re.IGNORECASE),
        "conditional", "conditional", 0.60, "infill overlay"),

    # ── Mixed Use — residential-leaning → PROHIBITED ─────────────────────────
    # Must come AFTER commercial-leaning MU patterns above
    (re.compile(
        r'\b(MIXED[\s-]+USE|MU\b|RMU\b|MXD\b|MIXED[\s-]+USE[\s-]+RESIDENTIAL'
        r'|RESIDENTIAL[\s/]+COMMERCIAL)',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.60, "residential MU"),

    # ── Residential → prohibited ──────────────────────────────────────────────
    (re.compile(
        r'^(R|RA|FR|SR|RE|RL|RM|RR|RH|RT|RS|RMF|SF|MH|MDR|HDR|RMF|R-MF|RPD'
        r'|RURAL|TRADITIONAL\s+RESIDENTIAL|ESTATE\s+RESIDENTIAL)\b',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.75, "residential prefix"),

    (re.compile(
        r'\b(SINGLE[\s-]+FAMILY|MULTI[\s-]+FAMILY|MULTIFAMILY|RESIDENTIAL'
        r'|APARTMENT|TOWNHOME|TOWNHOUSE|MOBILE\s+HOME|MANUFACTURED\s+HOME)',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.72, "residential descriptor"),

    # ── Agricultural → prohibited ─────────────────────────────────────────────
    (re.compile(
        r'^(A|AG|FA|EFU|OSR|RA|EA|AA)\b',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.72, "agricultural prefix"),

    (re.compile(r'\bAGRICULTUR', re.IGNORECASE),
        "prohibited", "prohibited", 0.70, "agricultural descriptor"),

    # ── Open Space / Civic / Institutional / Public → prohibited ─────────────
    (re.compile(
        r'^(OS|POS|PL|PI|PF|UI|EI|IN|GI|NOS|PR|PARK|OPEN)\b',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.75, "open space prefix"),

    (re.compile(
        r'\b(CIVIC|INSTITUTIONAL|OPEN\s+SPACE|PUBLIC\s+FACILITY'
        r'|PUBLIC\s+LAND|UNDESIGNATED|AIRPORT)',
        re.IGNORECASE),
        "prohibited", "prohibited", 0.72, "civic descriptor"),
]


def storage_cls(
    perm: str,
    confidence: float,
    notes: str,
    light_industrial: str | None = None,
) -> PerUseClassification:
    """
    Convenience constructor for classify_* functions.

    Creates a PerUseClassification where self_storage and mini_warehouse share
    the same permission, light_industrial defaults to the same value (or explicit),
    and luxury_garage_condo is inferred via the inference rule.
    """
    li = light_industrial if light_industrial is not None else perm
    cls = PerUseClassification(
        self_storage=perm,
        mini_warehouse=perm,
        light_industrial=li,
        luxury_garage_condo="unclear",
        confidence=confidence,
        notes=notes,
    )
    return apply_luxury_garage_inference(cls)


def classify_by_zone_character(code: str) -> PerUseClassification:
    """
    Classify a zone code using standard North American zone naming conventions.

    Covers ~95% of US zone codes without city-specific knowledge.
    Unknown codes default to 'prohibited' (conservative fail-safe).

    Args:
        code: Raw zone code or name (e.g., "I-1", "M-2", "R-1-8", "Mixed Use")

    Returns:
        PerUseClassification with all 4 uses independently classified.
    """
    u = (code or "").strip()

    for pattern, storage_class, li_class, conf, label in _ZONE_RULES:
        if pattern.search(u):
            cls = PerUseClassification(
                self_storage=storage_class,
                mini_warehouse=storage_class,
                light_industrial=li_class,
                luxury_garage_condo="unclear",
                confidence=conf,
                notes=f"Universal zone character classifier: {label} pattern",
            )
            return apply_luxury_garage_inference(cls)

    # Conservative default — unknown zone → prohibited
    return PerUseClassification(
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.45,
        notes=f"Universal classifier: no pattern matched '{u}' — prohibited (conservative default)",
    )
