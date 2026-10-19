"""Keep-market lane rules for the garage-condo (LGC) lane — the single source.

WHY THIS EXISTS
---------------
The 2026-10 keep-market calibration (``outputs/KEEP_MARKET_CALIBRATION_2026-10.md``;
methods in ``outputs/keep_calibration/calibration_part1.md``) priced 26 garage-condo
campuses off county deed records and found that price — expressed as a RATIO of the
campus's $/SF to the county's typical home $/SF in the sale year — tracks WEALTH DEPTH
near the site, not the ring MEDIAN home value the LGC lane used to borrow from storage:

  * share of owner-occupied homes worth $1M+ within a 20-minute drive (ACS B25075)
    — rank correlation +0.56 with the ratio, the strongest signal;
  * drive time to the nearest wealthy ($700K+ median; was $1M+ in the calibration) neighbourhood cluster — −0.45, and the only signal
    that also separated SPEED (the Texas Garages-of-America test: the campus 64 min
    from its wealth center was the one still 57/99 unsold after ~3 years);
  * today's median-home-value gate — +0.28, weak, and it FAILED campuses that sold out.

So the LGC lane classifies every candidate parcel into one of three lanes and attaches a
supported price band. Storage scoring/needles never read anything in this module.

THE RULES (pre-registered from the calibration — do not tune without a new study)
--------------------------------------------------------------------------------
  edge_of_wealth   owner_1m_share_20 >= 3%  AND wealth_center_drive_min <= 40
                   → price ratio band 1.2–1.8 (Toy Barn Scottsdale / Dove Valley / Big Door tier)
  core             (owner_1m_share_20 >= 1.5% OR wealth_center_drive_min <= 40), not edge
                   → band 0.9–1.3 (Toy Barn Chandler N, Luxe Dream, Henderson tier)
  growth_corridor  otherwise
                   → band 0.7–1.1 (LuxeLocker-style; win on land cost and speed)
  velocity_flag    'far_from_wealth' when wealth_center_drive_min > 55 (Woodlands territory)

  price_band_low/high = round(ratio × county_home_ppsf), where
  county_home_ppsf = county typical home value (Zillow ZHVI, latest full calendar year
  mean) ÷ 1,800 SF — the same normalisation the calibration used to strip out timing.

IMPORTANT — PRODUCT ASSUMPTION: the bands assume a FINISHED CLUBHOUSE product (Toy Barn /
Motocave tier: finished units, clubhouse, amenity). A bare-shell LuxeLocker-style
product sold 0.46–0.99× in the same study, i.e. roughly one lane lower. Treat bands as
±15% (26 campuses across 4 operator families — direction, not precision).

NULL POLICY: never guess. Any NULL input that a rule needs → the lane (and therefore
the band) is NULL; a NULL drive time → no velocity flag; a NULL county $/SF → no band.
Downstream (scoring, needles) treats a NULL lane as "not measured" and falls back to
the previous gate rather than reading it as a failure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

# ── Lane names (persisted in parcel_keep_metrics.keep_lane; pushed to the board) ──
LANE_EDGE = "edge_of_wealth"
LANE_CORE = "core"
LANE_GROWTH = "growth_corridor"
LANES: tuple[str, ...] = (LANE_EDGE, LANE_CORE, LANE_GROWTH)

# Lanes that qualify a parcel as an LGC NEEDLE (precompute_needles / verify_batch).
NEEDLE_LANES: tuple[str, ...] = (LANE_EDGE, LANE_CORE)

VELOCITY_FAR_FROM_WEALTH = "far_from_wealth"

# ── Thresholds (from the calibration memo) ────────────────────────────────────
EDGE_OWNER_1M_SHARE_MIN = 0.03     # 3% of owner homes $1M+ within 20 min
CORE_OWNER_1M_SHARE_MIN = 0.015    # 1.5%
WEALTH_CENTER_DRIVE_MAX_MIN = 40.0  # minutes to the nearest $700K+ cluster
FAR_FROM_WEALTH_MIN = 55.0          # velocity warning beyond this drive time

# Supported $/SF ÷ county typical home $/SF, per lane.
PRICE_RATIO_BANDS: dict[str, tuple[float, float]] = {
    LANE_EDGE: (1.2, 1.8),
    LANE_CORE: (0.9, 1.3),
    LANE_GROWTH: (0.7, 1.1),
}

# National typical-home size used to turn a ZHVI home value into a home $/SF.
HOME_SF = 1800.0

# ── Scoring constants (consumed by buybox_scoring for the LGC lane only) ──────
WEALTH_DEPTH_FLOOR = 0.01   # share at which the bonus starts (+0)
WEALTH_DEPTH_FULL = 0.10    # share for the full bonus
WEALTH_DEPTH_MAX_BONUS = 15.0
FAR_FROM_WEALTH_PENALTY = -10.0


def classify_lane(
    owner_1m_share_20: float | None,
    wealth_center_drive_min: float | None,
    center_is_cluster: bool = True,
) -> str | None:
    """Return the keep lane, or None when either input is unmeasured (never guess).

    ``center_is_cluster=False`` means the nearest "wealth center" is the calibration's
    FALLBACK (a single $600K+ tract, used where no cluster of >= 3 contiguous $700K+ tracts
    lies within 60 km). The calibration treated those rows as not comparable, and in the
    mountain West the fallback made every Lehi UT parcel read edge-of-wealth (2026-10-15).
    So a fallback-measured site can be at most CORE — edge requires a real wealth cluster.
    """
    if owner_1m_share_20 is None or wealth_center_drive_min is None:
        return None
    near = wealth_center_drive_min <= WEALTH_CENTER_DRIVE_MAX_MIN
    if owner_1m_share_20 >= EDGE_OWNER_1M_SHARE_MIN and near and center_is_cluster:
        return LANE_EDGE
    if owner_1m_share_20 >= CORE_OWNER_1M_SHARE_MIN or near:
        return LANE_CORE
    return LANE_GROWTH


def velocity_flag(wealth_center_drive_min: float | None) -> str | None:
    """'far_from_wealth' beyond FAR_FROM_WEALTH_MIN minutes; None otherwise / unmeasured."""
    if wealth_center_drive_min is None:
        return None
    return VELOCITY_FAR_FROM_WEALTH if wealth_center_drive_min > FAR_FROM_WEALTH_MIN else None


def county_home_ppsf(county_typical_home_value: float | None) -> float | None:
    """County typical home value (ZHVI) → home $/SF on the 1,800 SF basis."""
    if county_typical_home_value is None or county_typical_home_value <= 0:
        return None
    return county_typical_home_value / HOME_SF


# Observed-range caps (Nache 2026-10-19). The ratio bands were calibrated mostly where homes
# run $200–260/SF (AZ/FL); applied to ~$450/SF counties (Middlesex/Norfolk MA) they produced
# $507–805/SF — above any developer sale we recorded (max ~$463, Jupiter). So the top of a band
# never exceeds PRICE_BAND_CEILING, and its bottom never exceeds PRICE_BAND_LOW_CAP (about the
# lowest price any high-wealth campus sold at: Scottsdale Airpark $298, Luxe Dream $307).
PRICE_BAND_CEILING = 450
PRICE_BAND_LOW_CAP = 300


def price_band(lane: str | None, home_ppsf: float | None) -> tuple[int | None, int | None]:
    """Supported garage-condo $/SF band for a lane: round(ratio × county home $/SF), capped to
    the observed range (see PRICE_BAND_CEILING / PRICE_BAND_LOW_CAP)."""
    if lane is None or home_ppsf is None or home_ppsf <= 0 or lane not in PRICE_RATIO_BANDS:
        return None, None
    lo, hi = PRICE_RATIO_BANDS[lane]
    return (min(int(round(lo * home_ppsf)), PRICE_BAND_LOW_CAP),
            min(int(round(hi * home_ppsf)), PRICE_BAND_CEILING))


@dataclass(frozen=True)
class KeepAssessment:
    keep_lane: str | None
    price_band_low: int | None
    price_band_high: int | None
    velocity_flag: str | None


def assess(
    owner_1m_share_20: float | None,
    wealth_center_drive_min: float | None,
    home_ppsf: float | None,
    center_is_cluster: bool = True,
) -> KeepAssessment:
    """Lane + band + velocity flag in one call (what the precompute persists)."""
    lane = classify_lane(owner_1m_share_20, wealth_center_drive_min, center_is_cluster)
    lo, hi = price_band(lane, home_ppsf)
    return KeepAssessment(lane, lo, hi, velocity_flag(wealth_center_drive_min))


def wealth_depth_delta(owner_1m_share_20: float | None) -> float | None:
    """LGC 'Wealth depth' score delta: clamp((share − 1%) / (10% − 1%), 0, 1) × 15.

    None when unmeasured (caller falls back to the legacy HNW-depth factor)."""
    if owner_1m_share_20 is None:
        return None
    frac = (owner_1m_share_20 - WEALTH_DEPTH_FLOOR) / (WEALTH_DEPTH_FULL - WEALTH_DEPTH_FLOOR)
    return round(max(0.0, min(1.0, frac)) * WEALTH_DEPTH_MAX_BONUS, 1)


def far_from_wealth_delta(wealth_center_drive_min: float | None) -> float:
    """−10 when the nearest wealthy ($700K+) area is more than 55 min away; else 0."""
    if wealth_center_drive_min is not None and wealth_center_drive_min > FAR_FROM_WEALTH_MIN:
        return FAR_FROM_WEALTH_PENALTY
    return 0.0


# ═════════════════════════════════════════════════════════════════════════════
# CARD STRATEGY — price tier / unit mix / margin (owner decision 2026-10-19)
# ═════════════════════════════════════════════════════════════════════════════
# The Keep is a MIXED collector + business-owner garage-condo community priced
# $270–350/SF. Every garage-condo (LGC) board card shows a price TIER, the suggested
# unit MIX (Premium / Standard / Signature %) for that tier, the competitor units
# within ~30 min (information only — never a gate), and the margin on STACK's real
# costs. The tier is derived from the keep lane above plus wealth depth:
#
#   edge_of_wealth                            → tier_325_350
#   core AND owner_1m_share_20 >= 1.5%        → tier_295_325
#   core otherwise                            → tier_270_295
#   growth_corridor                           → 'pass' (below the $270 floor)
#   lane unmeasured (None)                    → None (never guess)
#
# Cost model = STACK's actual inputs, reconciled in
# ``outputs/keep_research/00_model_reconcile.md`` (2026-10-19): per ~90,000 SF campus
# (sellable = building) hard $127.50/SF (Build Co, 0% fee) + land $3.0M + soft $1.0M +
# financing ~$1.1M ⇒ TDC $16.575M = $184.17/SF. Selling cost = 0.75% marketing + the
# state's seller transfer tax (no brokers). Margin is on COST at the tier midpoint.
# No acreage or flood filter lives here on purpose — the owner wants to see more parcels.

TIER_325_350 = "tier_325_350"
TIER_295_325 = "tier_295_325"
TIER_270_295 = "tier_270_295"
TIER_PASS = "pass"
TIERS: tuple[str, ...] = (TIER_325_350, TIER_295_325, TIER_270_295)

# Supported $/SF per tier (low, high).
TIER_PRICE: dict[str, tuple[int, int]] = {
    TIER_325_350: (325, 350),
    TIER_295_325: (295, 325),
    TIER_270_295: (270, 295),
}

# Suggested unit mix per tier: (Premium %, Standard %, Signature %).
TIER_MIX: dict[str, tuple[int, int, int]] = {
    TIER_325_350: (50, 30, 20),
    TIER_295_325: (30, 40, 30),
    TIER_270_295: (15, 40, 45),
}

# Core sites at/above this wealth depth earn the upper core tier.
TIER_CORE_UPPER_SHARE_MIN = CORE_OWNER_1M_SHARE_MIN  # 1.5%

# ── STACK cost model (owner inputs, per 90,000 SF campus) ─────────────────────
# The original flat model priced land at a fixed $3.0M per 90K SF ($33.33/SF), giving
# one all-in $184.17/SF for every card. Land is what varies most between tiers, so the
# card margin now uses each parcel's ACTUAL listing price (owner decision 2026-10-19):
#
#   land_psf   = sale_price / (acres × sf_per_acre)
#   all_in_psf = (HARD_BASE_PSF × state factor × (1 + CONTINGENCY_PCT)
#                 + SOFT_PSF + FIN_PSF + land_psf) × (1 + DEV_FEE_PCT)
#   margin     = (tier_mid × (1 − selling_cost_pct) − all_in_psf) / all_in_psf
CAMPUS_SF = 90_000.0
COST_LAND = 3_000_000.0
COST_SOFT = 1_000_000.0
COST_HARD_PSF = 127.50
COST_FINANCING = 1_100_000.0
# Legacy flat all-in (fixed $3M land, no dev fee) — kept for margin_pct_flat and the
# before/after comparison; the card margin no longer uses it.
ALL_IN_COST_PSF = round(
    COST_HARD_PSF + (COST_LAND + COST_SOFT + COST_FINANCING) / CAMPUS_SF, 2
)  # 184.17

# Buildable SF per usable acre (Grayslake ~16K, Spring Hill ~9K). The dashboard lets
# the user override it per card (keep_sf_per_ac — never pushed from here).
DEFAULT_SF_PER_ACRE = 15_000.0
DEFAULT_LAND_PSF = COST_LAND / CAMPUS_SF  # 33.33 — the old fixed land assumption

HARD_BASE_PSF = COST_HARD_PSF  # 127.50
# Hard-cost regional factor by state. MA / IL / CO / UT are pending Build Co pricing
# and use the default 1.00 until then.
STATE_HARD_FACTOR: dict[str, float] = {
    "FL": 0.95,
    "NJ": 1.00,
    "PA": 1.00,
    "AZ": 1.05,
}
DEFAULT_HARD_FACTOR = 1.00
SOFT_PSF = COST_SOFT / CAMPUS_SF  # ≈ 11.11
FIN_PSF = COST_FINANCING / CAMPUS_SF  # ≈ 12.22
CONTINGENCY_PCT = 0.0  # owner decision 2026-10-19: 0 for now
DEV_FEE_PCT = 0.05  # development fee = 5% of total project cost

MARKETING_PCT = 0.0075
# Seller transfer tax (typical, state level) keyed by 2-letter state.
SELLER_TRANSFER_TAX: dict[str, float] = {
    "NJ": 0.0084,
    "FL": 0.0070,
    "IL": 0.0015,
    "PA": 0.0100,
    "MA": 0.0046,
}
DEFAULT_SELLER_TRANSFER_TAX = 0.0100
# Municipal override hook, keyed (STATE, CITY upper-cased) — replaces the state rate.
# Philadelphia's combined realty transfer tax is 4.278% (city + state); customarily
# split between buyer and seller, so the seller's share is 2.139%.
SELLER_TRANSFER_TAX_CITY: dict[tuple[str, str], float] = {
    ("PA", "PHILADELPHIA"): 0.02139,
}


def keep_tier(lane: str | None, owner_1m_share_20: float | None) -> str | None:
    """Price tier for a garage-condo card from its keep lane (+ wealth depth for core).

    Returns 'tier_325_350' | 'tier_295_325' | 'tier_270_295' | 'pass' | None. A core
    site with an unmeasured share falls to the lower core tier (never promoted on a
    guess); an unmeasured / unknown lane is None."""
    if lane == LANE_EDGE:
        return TIER_325_350
    if lane == LANE_CORE:
        if owner_1m_share_20 is not None and owner_1m_share_20 >= TIER_CORE_UPPER_SHARE_MIN:
            return TIER_295_325
        return TIER_270_295
    if lane == LANE_GROWTH:
        return TIER_PASS
    return None


def mix_label(tier: str | None) -> str | None:
    """'50/30/20' style Premium/Standard/Signature mix; None for 'pass'/None."""
    mix = TIER_MIX.get(tier) if tier else None
    return "/".join(str(p) for p in mix) if mix else None


def selling_cost_pct(state: str | None, city: str | None = None) -> float:
    """0.75% marketing + the seller transfer tax: the (state, city) override when one
    exists, else the state's rate (default 1.0%)."""
    st = (state or "").strip().upper()
    ct = (city or "").strip().upper()
    tax = SELLER_TRANSFER_TAX_CITY.get((st, ct)) if ct else None
    if tax is None:
        tax = SELLER_TRANSFER_TAX.get(st, DEFAULT_SELLER_TRANSFER_TAX)
    return MARKETING_PCT + tax


def hard_factor(state: str | None) -> float:
    return STATE_HARD_FACTOR.get((state or "").strip().upper(), DEFAULT_HARD_FACTOR)


def hard_psf(state: str | None) -> float:
    """Hard cost $/SF for the state: base × regional factor × (1 + contingency)."""
    return HARD_BASE_PSF * hard_factor(state) * (1.0 + CONTINGENCY_PCT)


def soft_fin_psf() -> float:
    """Soft + financing $/SF (fixed per-campus dollars spread over 90K SF)."""
    return SOFT_PSF + FIN_PSF


def land_psf(
    sale_price: float | None,
    acres: float | None,
    sf_per_acre: float = DEFAULT_SF_PER_ACRE,
) -> float | None:
    """Land $/buildable SF = sale_price / (acres × sf_per_acre). None when the price or
    acreage is missing / ≤ 0 (never a guessed land cost)."""
    try:
        price = float(sale_price) if sale_price is not None else None
        ac = float(acres) if acres is not None else None
        spa = float(sf_per_acre) if sf_per_acre is not None else None
    except (TypeError, ValueError):
        return None
    if not price or price <= 0 or not ac or ac <= 0 or not spa or spa <= 0:
        return None
    return price / (ac * spa)


def all_in_psf(land_psf: float, state: str | None) -> float:
    """All-in development cost $/SF including land and the development fee."""
    return (hard_psf(state) + soft_fin_psf() + land_psf) * (1.0 + DEV_FEE_PCT)


def _tier_mid(tier: str | None) -> float | None:
    band = TIER_PRICE.get(tier) if tier else None
    return None if band is None else (band[0] + band[1]) / 2.0


def margin_pct(
    tier: str | None,
    state: str | None,
    land_psf: float | None,
    city: str | None = None,
) -> float | None:
    """Land-aware margin on cost at the tier midpoint, net of selling costs:

        (mid × (1 − selling) − all_in_psf(land_psf)) / all_in_psf(land_psf)

    None for 'pass' / None (no supported price) or when land_psf is unknown."""
    mid = _tier_mid(tier)
    if mid is None or land_psf is None:
        return None
    cost = all_in_psf(land_psf, state)
    net = mid * (1.0 - selling_cost_pct(state, city))
    return (net - cost) / cost


def margin_pct_default_land(
    tier: str | None, state: str | None, city: str | None = None
) -> float | None:
    """margin_pct at the old fixed land assumption ($3M / 90K SF), new cost stack."""
    return margin_pct(tier, state, DEFAULT_LAND_PSF, city)


def margin_pct_flat(tier: str | None, state: str | None) -> float | None:
    """LEGACY flat-cost margin (fixed $184.17/SF, no dev fee) — the pre-2026-10-19
    card number, kept only for before/after comparisons."""
    mid = _tier_mid(tier)
    if mid is None:
        return None
    net = mid * (1.0 - selling_cost_pct(state))
    return (net - ALL_IN_COST_PSF) / ALL_IN_COST_PSF


# ── Competitor supply within ~30 min (information only — never a gate) ────────
# Source: backend/data/keep_supply_campuses.csv, a column subset of the national
# garage-condo supply layer (outputs/keep_national/supply_campuses.csv, method in
# outputs/keep_national/supply_method.md; the known M1 Concourse duplicate dropped).
#
# PROXY: 30 km straight-line from the parcel's census-tract point stands in for a
# 30-minute drive (no per-parcel Mapbox call). Units per campus = the LARGER of
# units_built and units_planned (blank = 0): in that file units_planned is the
# campus's total planned count — ~300 rows carry built == planned — so summing the two
# would double-count (supply_method.md: "Units are the larger of built and planned").
# OGC anonymous points are geolocated to ~5–10 km and include some boat/RV condos, and
# a few Florida points are very large; treat the count as direction, not precision.
SUPPLY_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "keep_supply_campuses.csv"
COMPETITOR_RADIUS_KM = 30.0
_EARTH_KM = 6371.0088


@dataclass(frozen=True)
class SupplyCampus:
    name: str
    lat: float
    lng: float
    units: int


def _units(v: str | None) -> int:
    try:
        return max(0, int(round(float(v)))) if v not in (None, "") else 0
    except ValueError:
        return 0


def load_supply_campuses(path=None) -> list[SupplyCampus]:
    """Campuses with coordinates from the supply CSV (rows without lat/lng skipped)."""
    import csv

    out: list[SupplyCampus] = []
    with Path(path or SUPPLY_CSV_PATH).open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                lat, lng = float(r["lat"]), float(r["lng"])
            except (TypeError, ValueError):
                continue
            units = max(_units(r.get("units_built")), _units(r.get("units_planned")))
            out.append(SupplyCampus(r.get("name") or "", lat, lng, units))
    return out


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def competitor_units(
    lat: float | None,
    lng: float | None,
    campuses: list[SupplyCampus],
    radius_km: float = COMPETITOR_RADIUS_KM,
) -> int | None:
    """Garage-condo units (built or planned) within ``radius_km`` straight-line of a
    point. None when the point is unknown; 0 is a real measured zero."""
    if lat is None or lng is None:
        return None
    dlat = radius_km / 111.0 + 0.01  # cheap latitude-band prefilter
    total = 0
    for c in campuses:
        if abs(c.lat - lat) > dlat:
            continue
        if haversine_km(lat, lng, c.lat, c.lng) <= radius_km:
            total += c.units
    return total
