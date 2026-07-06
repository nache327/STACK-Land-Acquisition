"""
Shared field-binding helpers for the parcel + zoning-district ingest paths.

Both ``ingestion.py`` (parcels) and ``zoning_ingestion.py`` (zoning districts)
map raw ArcGIS / GeoJSON rows onto DB columns by trying a list of candidate
source-field names, first non-null match wins. This module is the SINGLE
implementation of that lookup (previously copy-pasted as ``_first`` in both
files) plus a value-shape validator that rejects the known bad-binding
signatures — the "catch #3x" family — before they poison ``zone_code`` /
``city``:

  - #34 : a field literally named ``ZONING_CODE`` holding an eCode360 **URL**
          (Delaware County PA) — every parcel would bind its code to a URL.
  - #34 : a constant field (Montgomery PA ``Type="District"``) covering every
          row — every parcel binds to the same bogus code.
  - #33 : a raw integer muni code surfacing as ``city="43"`` (Chester PA).

Overrides (``JurisdictionConfig.zone_code_field`` etc.) pin the correct field
for a source we've reconned; this validator is the generic backstop for
live-discovered sources we haven't written config for.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# ── Case-insensitive candidate-field lookup ─────────────────────────────────

def _row_lookup(row: Any) -> dict:
    """Build a lowercase-keyed accessor from a dict / namedtuple / pandas row."""
    if isinstance(row, dict):
        return {k.lower(): v for k, v in row.items()}
    if hasattr(row, "_asdict"):
        return {k.lower(): v for k, v in row._asdict().items()}
    if hasattr(row, "to_dict"):
        return {k.lower(): v for k, v in row.to_dict().items()}
    return {}


def _is_present(v: Any) -> bool:
    return v is not None and str(v).strip() not in ("", "nan", "None")


def matched_field(row: Any, fields: list[str]) -> str | None:
    """Return the *source field name* that ``first_match`` would bind from, or
    None. Used for binding-provenance logging (which field fed which column)."""
    lookup = _row_lookup(row)
    for f in fields:
        if _is_present(lookup.get(f.lower())):
            return f
        for key, candidate in lookup.items():
            if key.rsplit(".", 1)[-1] == f.lower() and _is_present(candidate):
                return key
    return None


def first_match(row: Any, fields: list[str]) -> Any:
    """Case-insensitive first-match lookup over candidate field names.

    Source layers publish field names in mixed / lower / upper case (MapPLUTO
    mixed, Philly OPA lower, UGRC upper) and occasionally dotted
    ("GIS.landbase1_Zoning.ZONINGCODE"); we match the last dotted segment too.
    Returns the first candidate whose value is non-null and non-blank.
    """
    lookup = _row_lookup(row)
    for f in fields:
        v = lookup.get(f.lower())
        if _is_present(v):
            return v
        for key, candidate in lookup.items():
            if key.rsplit(".", 1)[-1] == f.lower() and _is_present(candidate):
                return candidate
    return None


# ── Value-shape validator (catch #33 / #34 backstop) ─────────────────────────

# zone_use_matrix.zone_code is String(50) and ZoningDistrict.zone_code is a
# short code; anything longer than this is a description or a URL, never a code.
MAX_CODE_LEN = 20
_URL_RE = re.compile(r"^\s*https?://", re.IGNORECASE)


def bad_code_reason(value: Any) -> str | None:
    """Return a human-readable reason if ``value`` has the shape of a mis-bound
    zone/district **code** (catch #34), else None. Per-row check.

    Signatures:
      - a URL (eCode360 / municode legend links bound as the code), or
      - longer than ``MAX_CODE_LEN`` chars (a description, not a code).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if _URL_RE.match(s):
        return f"URL-shaped value bound as zone code: {s[:60]!r}"
    if len(s) > MAX_CODE_LEN:
        return f"value too long ({len(s)} > {MAX_CODE_LEN} chars) to be a zone code: {s[:60]!r}"
    return None


def is_numeric_city(value: Any) -> bool:
    """catch #33: a purely-numeric municipality (``city='43'``) is a raw MUNI
    code that was never resolved to a name."""
    if value is None:
        return False
    s = str(value).strip()
    return bool(s) and s.isdigit()


def constant_code_reason(
    codes: list[str],
    *,
    min_rows: int = 6,
    threshold: float = 0.90,
) -> str | None:
    """Dataset-level signature (catch #34, Montgomery ``Type="District"``): one
    ``zone_code`` value covering more than ``threshold`` of ``codes`` across
    more than ``min_rows`` rows means the bound field is a constant, not the
    real district code. Returns the offending value + share if detected.

    Conservative by design — only fires above ``min_rows`` so a genuinely
    single-district small pull isn't flagged.
    """
    if len(codes) <= min_rows:
        return None
    counts = Counter(codes)
    top_val, top_n = counts.most_common(1)[0]
    share = top_n / len(codes)
    if share > threshold:
        return (
            f"single zone_code {top_val!r} covers {share:.0%} of {len(codes)} rows "
            f"— bound field looks constant, not a real district code"
        )
    return None
