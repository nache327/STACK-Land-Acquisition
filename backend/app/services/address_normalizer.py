"""Address normalization helpers used by listings matching.

Pure functions — no I/O, no DB. The matcher (`listing_matcher.py`)
runs the listing's address through `normalize` and compares against
parcel addresses that have been put through the same pipe. ZIP+4 and
unit suffixes are stripped in Tier 2.

Kept deliberately minimal. USPS-grade normalization (CASS, ZIP4
lookup, full secondary unit detection) is a future project. For now
we cover the cases that broke our matching during dev:

  "100 N Main St"   -> "100 north main street"
  "100 N. Main St., Apt 4B"  -> "100 north main street"  (after strip_unit)
  "10 Pkwy Drive"   -> "10 parkway drive"
  "5 Hwy 24"        -> "5 route 24"           (highway/route canonicalize)
  "1150 US Hwy 22 E"-> "1150 route 22"        (state-prefix + direction strip)
"""
from __future__ import annotations

import re

# Common USPS street suffixes. Map abbreviation -> canonical word.
# Order doesn't matter; matching is whole-word.
_SUFFIX_MAP: dict[str, str] = {
    "st":     "street",
    "str":    "street",
    "rd":     "road",
    "ave":    "avenue",
    "av":     "avenue",
    "avn":    "avenue",
    "blvd":   "boulevard",
    "boul":   "boulevard",
    "dr":     "drive",
    "drv":    "drive",
    "ln":     "lane",
    "ct":     "court",
    "crt":    "court",
    "pl":     "place",
    "plz":    "plaza",
    "cir":    "circle",
    "circ":   "circle",
    "ter":    "terrace",
    "trce":   "terrace",
    "way":    "way",
    "trl":    "trail",
    "trail":  "trail",
    "pky":    "parkway",
    "pkwy":   "parkway",
    "parkwy": "parkway",
    "hwy":    "highway",
    "hiwy":   "highway",
    "expy":   "expressway",
    "fwy":    "freeway",
    "loop":   "loop",
    "row":    "row",
    "sq":     "square",
    "xing":   "crossing",
    "hts":    "heights",
    "pt":     "point",
    "rt":     "route",
    "rte":    "route",
}

_DIRECTIONALS: dict[str, str] = {
    "n":  "north",
    "s":  "south",
    "e":  "east",
    "w":  "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}

# Drop these as standalone words after normalization (noise that
# doesn't help matching).
_NOISE = {"and"}

# Apt / Unit / Suite suffix patterns. Stripped by `strip_unit`.
# Longer alternatives first so e.g. "Floor" doesn't get partially
# matched by "fl". Mandatory \s+ after the keyword prevents "Apt"
# from matching the prefix of "Apartment Building" by accident.
_UNIT_RE = re.compile(
    r"\b(?:apartment|building|apt|unit|suite|ste|bldg|floor|fl|room|rm)\.?\s+\S+",
    re.IGNORECASE,
)
# Trailing "#<token>" — addresses like "100 Main St #B"
_HASH_UNIT_RE = re.compile(r"#\s*\S+")

_PUNCT_RE = re.compile(r"[.,;:!?\"'`()\[\]{}\\/]")
_WS_RE = re.compile(r"\s+")

# ── Route / highway canonicalization ────────────────────────────────────────
#
# Background: NJ commercial listings frequently address parcels by their
# route number rather than by a named street. Brokers use many synonyms
# for the same road:
#
#   "Route 22", "Rt 22", "Hwy 22", "Highway 22"
#   "US Highway 22", "U.S. Hwy 22", "US-22"
#   "State Highway 22", "State Route 22"
#   "NJ-22", "NJ Route 22"
#   "Interstate 78", "I-78"
#
# Parcel-source tax data typically stores these inconsistently too —
# "STATE HIGHWAY 22" vs "RT 22" vs "ROUTE 22" varies by county. To make
# the address-match tier of the listing matcher work, we collapse all
# variants to one canonical form on both sides:
#
#   "<state>?\s*(highway|route)\s*N"  →  "route N"
#
# Then strip leading/trailing direction + redundant suffix words so
# "1150 Route 22 E" and "1150 State Hwy 22" both normalize identically.

# Hyphenated state-prefixed routes: "US-202", "NJ-28", "I-78".
# Matched first because they're the most specific and don't share token
# boundaries with the word-form regex.
_HYPHEN_ROUTE_RE = re.compile(r"\b(?:us|nj|i)-(\d+)\b", re.IGNORECASE)

# State-prefixed routes with word form: "US Highway 22", "State Route 22",
# "NJ Hwy 28", "Interstate 78". Optional hyphen/space between prefix and
# route word.
_PREFIXED_ROUTE_RE = re.compile(
    r"\b(?:u\.?\s*s\.?|us|state|nj|interstate|i)\s*[-]?\s*"
    r"(?:highway|hwy|route|rte|rt)\s*[-]?\s*(\d+)\b",
    re.IGNORECASE,
)

# Bare route phrases without state prefix: "Route 22", "Rt 22", "Hwy 22".
# Run last so it doesn't pre-empt the prefixed match.
_BARE_ROUTE_RE = re.compile(
    r"\b(?:highway|hwy|route|rte|rt)\s*[-]?\s*(\d+)\b", re.IGNORECASE,
)

# After canonicalization to "route N", strip leading direction tokens
# and redundant prefix words ("N Route 206", "US Highway Route 206").
# Uses + quantifier so a single substitution consumes multiple stacked
# noise tokens.
_ROUTE_LEADING_NOISE_RE = re.compile(
    r"\b(?:(?:n|s|e|w|north|south|east|west|us|state|nj|interstate|i|highway|hwy)\s+)+"
    r"(route\s+\d+)\b",
    re.IGNORECASE,
)

# Strip trailing direction tokens and redundant suffix words after
# "route N" ("Route 22 E", "Route 206 Hwy").
_ROUTE_TRAILING_NOISE_RE = re.compile(
    r"\b(route\s+\d+)(?:\s+(?:n|s|e|w|north|south|east|west|highway|hwy))+\b",
    re.IGNORECASE,
)


def _canonicalize_routes(s: str) -> str:
    """Collapse the many route/highway synonyms to ``route N`` form.

    Applied pre-tokenization so multi-word route phrases get folded
    before they fragment in the token loop.
    """
    s = _HYPHEN_ROUTE_RE.sub(r"route \1", s)
    s = _PREFIXED_ROUTE_RE.sub(r"route \1", s)
    s = _BARE_ROUTE_RE.sub(r"route \1", s)
    # Strip surrounding noise iteratively in case multiple substitutions
    # are needed (each regex has + on its noise group so single-pass
    # usually suffices, but iterating defends against odd inputs).
    for _ in range(4):
        new_s = _ROUTE_LEADING_NOISE_RE.sub(r"\1", s)
        new_s = _ROUTE_TRAILING_NOISE_RE.sub(r"\1", new_s)
        if new_s == s:
            break
        s = new_s
    return s


def normalize(addr: str | None) -> str:
    """Lowercase, strip punctuation, canonicalize routes, expand
    suffixes + directionals, collapse whitespace. Empty / None becomes
    the empty string.

    Idempotent: ``normalize(normalize(x)) == normalize(x)``.
    """
    if not addr:
        return ""
    s = addr.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""
    # Canonicalize route phrases before tokenization so multi-word
    # forms ("us highway 22", "state route 22") fold together.
    s = _canonicalize_routes(s)
    tokens = s.split(" ")
    out: list[str] = []
    for tok in tokens:
        if tok in _NOISE:
            continue
        if tok in _DIRECTIONALS:
            out.append(_DIRECTIONALS[tok])
            continue
        if tok in _SUFFIX_MAP:
            out.append(_SUFFIX_MAP[tok])
            continue
        out.append(tok)
    return " ".join(out)


def strip_unit(addr: str | None) -> str:
    """Drop apartment / unit / suite suffixes from an address.

    Returns the normalized address with units removed. Use after
    `normalize` for Tier 2 matching.

        strip_unit("100 N Main St Apt 4B")  -> "100 north main street"
        strip_unit("100 Main St #B")        -> "100 main street"
    """
    if not addr:
        return ""
    s = _UNIT_RE.sub("", addr)
    s = _HASH_UNIT_RE.sub("", s)
    return normalize(s)


def strip_zip4(zip_code: str | None) -> str:
    """ ``12345-6789 -> 12345``. Returns empty string for None / empty. """
    if not zip_code:
        return ""
    z = zip_code.strip()
    if "-" in z:
        z = z.split("-", 1)[0]
    return z.strip()


__all__ = ["normalize", "strip_unit", "strip_zip4"]
