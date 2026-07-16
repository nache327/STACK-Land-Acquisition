"""Shared types + helpers for listing parsers.

``ListingRow`` mirrors the canonical columns of ``forsale_listings``.
Every provider parser produces ``ListingRow`` objects so the upload
endpoint can UPSERT them generically.

``load_dataframe`` handles both .xlsx (via openpyxl) and .csv. We keep
pandas as an optional dep — only used here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)


class ParserError(Exception):
    pass


@dataclass
class ListingRow:
    address: str
    sale_status: str

    # Canonical optional fields
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    sale_category: str | None = None
    property_type: str | None = None
    secondary_type: str | None = None
    rating: int | None = None
    size_sf: Decimal | None = None
    sale_price: Decimal | None = None
    price_per_sf: Decimal | None = None
    cap_rate: Decimal | None = None
    days_on_market: int | None = None
    sale_type: str | None = None
    property_name: str | None = None
    land_area_ac: Decimal | None = None
    land_area_sf: Decimal | None = None
    price_per_ac: Decimal | None = None
    price_per_land_sf: Decimal | None = None
    num_units: int | None = None
    price_per_unit: Decimal | None = None
    listing_broker_company: str | None = None
    listing_broker_contact: str | None = None
    listing_broker_phone: str | None = None
    listing_broker_email: str | None = None
    # Owner contact (from the CoStar report — distinct from the assessor
    # owner on parcels.owner_name). Surfaced in-app for Stage-4 outreach.
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_contact: str | None = None
    owner_address: str | None = None
    recorded_owner_name: str | None = None
    recorded_owner_phone: str | None = None
    # Prior-sale history (distinct from the for-sale asking price in sale_price).
    last_sale_price: Decimal | None = None
    last_sale_date: str | None = None
    building_class: str | None = None
    zoning_listed: str | None = None
    market: str | None = None
    submarket: str | None = None
    county: str | None = None
    raw_row: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    rows: list[ListingRow]
    detected_source: str
    warnings: list[str] = field(default_factory=list)


def load_dataframe(file_bytes: bytes, filename: str):
    """Lazy-import pandas, parse xlsx or csv into a DataFrame.

    Raises ParserError on unsupported extension or unreadable file.
    """
    try:
        import pandas as pd  # noqa: WPS433 — optional dep
    except ImportError as exc:  # pragma: no cover
        raise ParserError(
            "pandas is required for listings parsing — pip install pandas openpyxl"
        ) from exc

    name = (filename or "").lower()
    bio = BytesIO(file_bytes)
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(bio, dtype=object)
        elif name.endswith(".csv"):
            df = pd.read_csv(bio, dtype=object)
        else:
            raise ParserError(f"Unsupported file extension: {filename!r}")
    except ParserError:
        raise
    except Exception as exc:
        raise ParserError(f"Failed to read {filename}: {exc}") from exc
    return df


# ── Coercion helpers ──────────────────────────────────────────────────────────

def to_str(v: Any) -> str | None:
    if v is None:
        return None
    try:
        import math  # local — only when needed
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    s = str(v).strip()
    return s or None


def to_decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    # pandas reads blank Excel cells as float('nan'); guard before Decimal()
    # since Decimal("nan") succeeds and produces Decimal('NaN'), which
    # breaks Postgres numeric inserts downstream.
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    if isinstance(v, Decimal):
        if v.is_nan():
            return None
        return v
    try:
        s = str(v).strip()
        if s.lower() in {"", "-", "n/a", "na", "--", "nan", "none"}:
            return None
        # Strip $ , % for currency / rate columns
        s = s.replace("$", "").replace(",", "").replace("%", "").strip()
        d = Decimal(s)
        return None if d.is_nan() else d
    except (InvalidOperation, ValueError):
        return None


def to_int(v: Any) -> int | None:
    d = to_decimal(v)
    if d is None:
        return None
    try:
        return int(d)
    except (ValueError, OverflowError):
        return None


def pick_column(columns: list[str], *candidates: str) -> str | None:
    """Return the first column in ``columns`` matching any candidate
    (case-insensitive, exact match after strip). Useful for parsers
    where the same field has a few spelling variants across exports.
    """
    lower_map = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        col = lower_map.get(cand.lower().strip())
        if col is not None:
            return col
    return None


__all__ = [
    "ListingRow",
    "ParseResult",
    "ParserError",
    "load_dataframe",
    "to_str",
    "to_decimal",
    "to_int",
    "pick_column",
]
