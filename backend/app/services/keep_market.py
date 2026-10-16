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

from dataclasses import dataclass

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


def price_band(lane: str | None, home_ppsf: float | None) -> tuple[int | None, int | None]:
    """Supported garage-condo $/SF band for a lane: round(ratio × county home $/SF)."""
    if lane is None or home_ppsf is None or home_ppsf <= 0 or lane not in PRICE_RATIO_BANDS:
        return None, None
    lo, hi = PRICE_RATIO_BANDS[lane]
    return int(round(lo * home_ppsf)), int(round(hi * home_ppsf))


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
