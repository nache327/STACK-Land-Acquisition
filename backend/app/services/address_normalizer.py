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
  "5 Hwy 24"        -> "5 highway 24"
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


def normalize(addr: str | None) -> str:
    """Lowercase, strip punctuation, expand suffixes + directionals,
    collapse whitespace. Empty / None becomes the empty string.

    Idempotent: ``normalize(normalize(x)) == normalize(x)``.
    """
    if not addr:
        return ""
    s = addr.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""
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
