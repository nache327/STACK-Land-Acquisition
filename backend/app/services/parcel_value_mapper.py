"""Per-state mapping of source assessor fields → (assessed_value, is_residential).

Every state has its own cadastral schema. NJ MOD-IV publishes NET_VALUE +
PROP_CLASS; FL DOR publishes JV + DOR_UC; UT UGRC has TOTAL_MKT_VALUE +
PROP_CLASS; PA Philadelphia OPA has market_value + category_code.

This module is the **single place** state-specific logic lives. The
ingest service and the backfill script both call ``map_value_and_residential``;
nothing downstream needs to know which state a parcel came from to derive
its wealth flags.

When a state has no mapper yet, returns ``(None, None)`` and the parcel just
won't contribute to the "Wealth density" counts. Adding a new state is a
matter of writing one helper and registering it in ``_STATE_MAPPERS``.
"""
from __future__ import annotations

from typing import Callable, Iterable


# ─── Helpers ────────────────────────────────────────────────────────────

def _first_value(raw: dict, keys: Iterable[str]) -> str | int | float | None:
    """Return the value of the first key that exists and is non-empty.

    Case-insensitive — county feeds publish in mixed casing.
    """
    lookup = {k.lower(): v for k, v in raw.items()}
    for k in keys:
        v = lookup.get(k.lower())
        if v not in (None, "", " "):
            return v
    return None


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return f if f > 0 else None


def _to_str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ─── Per-state mappers ──────────────────────────────────────────────────
#
# Each returns (assessed_value, is_residential). Either field can be None
# when the source row doesn't carry it; the buy-box density counts ignore
# rows where either is None.

# NJ MOD-IV (statewide Parcels_Composite_NJ_WM, plus per-county services).
# PROP_CLASS = '2' is the canonical residential code; '4A'/'4B'/'4C' are
# commercial/industrial/apartment. NET_VALUE is the total assessment.
# Fallback: LAND_VAL + IMPRVT_VAL summed for counties that don't publish
# NET_VALUE directly.
_NJ_VALUE_FIELDS = ["NET_VALUE", "net_value", "TOT_ASSMNT"]
_NJ_LAND_FIELDS = ["LAND_VAL", "land_val", "LAND_VALUE"]
_NJ_IMPR_FIELDS = ["IMPRVT_VAL", "imprvt_val", "IMPRVT_VALUE", "IMPR_VALUE"]
_NJ_CLASS_FIELDS = ["PROP_CLASS", "prop_class", "PROPCLASS", "property_class"]


def _map_nj(raw: dict) -> tuple[float | None, bool | None]:
    val = _to_float(_first_value(raw, _NJ_VALUE_FIELDS))
    if val is None:
        land = _to_float(_first_value(raw, _NJ_LAND_FIELDS)) or 0.0
        impr = _to_float(_first_value(raw, _NJ_IMPR_FIELDS)) or 0.0
        sum_ = land + impr
        val = sum_ if sum_ > 0 else None

    cls = _to_str(_first_value(raw, _NJ_CLASS_FIELDS))
    is_res = cls == "2" if cls is not None else None
    return val, is_res


# UT UGRC parcel services (services1.arcgis.com/99lidPhWCzftIe9K).
# Each county exposes a TOTAL_MKT_VALUE (current market) and per-component
# LAND_MKT_VALUE + BLDG_MKT_VALUE. PROP_CLASS varies by county — Salt Lake
# uses 'Residential', Utah County uses 'R', so we accept either.
_UT_VALUE_FIELDS = [
    "TOTAL_MKT_VALUE", "total_mkt_value",
    "TOTAL_VAL", "TOT_VALUE", "MARKET_VAL",
]
_UT_LAND_FIELDS = ["LAND_MKT_VALUE", "land_mkt_value", "LAND_VALUE"]
_UT_BLDG_FIELDS = ["BLDG_MKT_VALUE", "bldg_mkt_value", "BLDG_VALUE", "BUILDING_VALUE"]
_UT_CLASS_FIELDS = ["PROP_CLASS", "prop_class", "CLASS", "PROPERTY_CLASS"]
_UT_LANDUSE_FIELDS = ["LAND_USE_CD", "land_use_cd", "LAND_USE", "LANDUSE"]


def _map_ut(raw: dict) -> tuple[float | None, bool | None]:
    val = _to_float(_first_value(raw, _UT_VALUE_FIELDS))
    if val is None:
        land = _to_float(_first_value(raw, _UT_LAND_FIELDS)) or 0.0
        bldg = _to_float(_first_value(raw, _UT_BLDG_FIELDS)) or 0.0
        sum_ = land + bldg
        val = sum_ if sum_ > 0 else None

    cls = _to_str(_first_value(raw, _UT_CLASS_FIELDS))
    landuse = _to_str(_first_value(raw, _UT_LANDUSE_FIELDS))
    is_res: bool | None
    if cls is not None:
        upper = cls.upper()
        is_res = upper.startswith("R") or upper.startswith("RES")
    elif landuse is not None:
        # UGRC LAND_USE_CD: '1xx' = residential.
        is_res = landuse.startswith("1")
    else:
        is_res = None
    return val, is_res


# Philadelphia OPA — market_value is current full market value (annual
# reassessment); category_code starts with '1' for residential per OPA
# spec. Other PA counties (Allentown City_Landuse, Montgomery) vary —
# we cover the common patterns.
_PA_VALUE_FIELDS = ["market_value", "MARKET_VAL", "MKT_VAL", "TOT_VAL"]
_PA_CLASS_FIELDS = ["category_code", "CATEGORY_CODE", "PROPCAT", "LAND_USE_CODE"]


def _map_pa(raw: dict) -> tuple[float | None, bool | None]:
    val = _to_float(_first_value(raw, _PA_VALUE_FIELDS))
    cls = _to_str(_first_value(raw, _PA_CLASS_FIELDS))
    is_res = cls.startswith("1") if cls else None
    return val, is_res


# FL statewide cadastral (services9.arcgis.com/Gh9awoU677aKree0) — JV is
# Just Value, the assessor's full market value. DOR_UC starts with '01'
# for single-family residential, '02' for mobile homes, '04' for condos.
# We treat '01' / '02' / '04' / '08' (multi-family) as residential.
_FL_VALUE_FIELDS = ["JV", "jv", "JUST_VALUE", "TOTAL_JV"]
_FL_CLASS_FIELDS = ["DOR_UC", "dor_uc", "PA_UC", "USE_CODE"]
_FL_RESIDENTIAL_PREFIXES = ("01", "02", "04", "08")


def _map_fl(raw: dict) -> tuple[float | None, bool | None]:
    val = _to_float(_first_value(raw, _FL_VALUE_FIELDS))
    cls = _to_str(_first_value(raw, _FL_CLASS_FIELDS))
    is_res = cls.startswith(_FL_RESIDENTIAL_PREFIXES) if cls else None
    return val, is_res


_STATE_MAPPERS: dict[str, Callable[[dict], tuple[float | None, bool | None]]] = {
    "NJ": _map_nj,
    "UT": _map_ut,
    "PA": _map_pa,
    "FL": _map_fl,
}


# ─── Public entry point ─────────────────────────────────────────────────

def map_value_and_residential(
    state: str | None, raw: dict | None
) -> tuple[float | None, bool | None]:
    """Return ``(assessed_value, is_residential)`` for one parcel's source row.

    Either or both can be None — caller decides how to handle missing data.
    The buy-box density counts ignore parcels with either field NULL.
    """
    if not state or not raw:
        return None, None
    mapper = _STATE_MAPPERS.get(state.upper())
    if mapper is None:
        return None, None
    try:
        return mapper(raw)
    except Exception:
        # Never let one malformed row break a whole ingest / backfill batch.
        return None, None
