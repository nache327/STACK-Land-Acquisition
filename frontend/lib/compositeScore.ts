/**
 * Client-side composite score (0–100) for a parcel.
 *
 * PLACEHOLDER until backend `parcel_buybox_scores` ships. The values feed
 * the sortable Score column in the parcel table and the breakdown panel
 * in the parcel drawer. Once the backend lands, replace `computeScore`
 * with a row-level read of the precomputed score; the breakdown shape
 * here matches what the backend will return so the UI doesn't need to
 * change.
 *
 * The formula is intentionally transparent and tunable:
 *   base                                           50
 *   storage_permission == "permitted"             +30
 *   storage_permission == "conditional"           +15
 *   storage_permission == "unclear"                 0
 *   storage_permission == "prohibited"            -25
 *   acres bonus  (acres / 30, clamp 0..1) * 20    +0..+20
 *   aadt  bonus  ((aadt - 5K) / 45K, clamp 0..1) * 15  +0..+15
 *   in_flood_zone                                  -25
 *   in_wetland                                     -15
 *   !has_structure (vacant land)                   +5
 *
 * Final score is clamped to [0, 100].
 */
/**
 * Structural input for the score formula. Lets us call computeScore from both
 * CandidateParcelRow (table) and ParcelDetail (drawer) without a wrapper.
 * Fields the formula doesn't see are simply not factored in.
 */
export interface ScoreInput {
  storage_permission?: string | null;
  acres?: number | null;
  aadt?: number | null;
  in_flood_zone?: boolean | null;
  in_wetland?: boolean | null;
  has_structure?: boolean | null;
}

export interface ScoreFactor {
  label: string;
  delta: number;          // signed contribution to the score
  reason: string;         // short human explanation
}

export interface CompositeScore {
  score: number;          // 0..100 (rounded)
  tier: ScoreTier;
  factors: ScoreFactor[]; // ordered as applied
}

export type ScoreTier = "excellent" | "strong" | "decent" | "weak" | "avoid";

export function computeScore(parcel: ScoreInput): CompositeScore {
  const factors: ScoreFactor[] = [
    { label: "Base", delta: 50, reason: "Baseline" },
  ];

  // Storage permission — biggest single factor
  switch (parcel.storage_permission) {
    case "permitted":
      factors.push({ label: "Storage", delta: 30, reason: "Permitted by zoning" });
      break;
    case "conditional":
      factors.push({ label: "Storage", delta: 15, reason: "Conditional use" });
      break;
    case "prohibited":
      factors.push({ label: "Storage", delta: -25, reason: "Prohibited by zoning" });
      break;
    case "unclear":
      factors.push({ label: "Storage", delta: 0, reason: "Ordinance unclear — verify" });
      break;
    default:
      factors.push({ label: "Storage", delta: 0, reason: "No matrix entry yet" });
  }

  // Acreage curve — peaks in the buildable sweet spot, penalizes oversize.
  // Mirror of _acreage_delta / ACRE_* in backend/app/services/buybox_scoring.py
  // (keep byte-for-byte equivalent so the drawer matches parcel_buybox_scores).
  if (parcel.acres != null && parcel.acres > 0) {
    const delta = acreageDelta(parcel.acres);
    factors.push({
      label: "Acres",
      delta,
      reason: `${parcel.acres.toFixed(1)} ac${parcel.acres > ACRE_MAX ? " (oversize)" : ""}`,
    });
  }

  // AADT bonus — visibility (5K = 0 pts, 50K = full +15)
  if (parcel.aadt != null && parcel.aadt > 0) {
    const bonus = clamp01((parcel.aadt - 5000) / 45000) * 15;
    if (bonus > 0) {
      factors.push({
        label: "Traffic",
        delta: round1(bonus),
        reason: `${(parcel.aadt / 1000).toFixed(0)}K AADT`,
      });
    }
  }

  // Flood / wetland penalties
  if (parcel.in_flood_zone) {
    factors.push({ label: "Flood zone", delta: -25, reason: "FEMA SFHA" });
  }
  if (parcel.in_wetland) {
    factors.push({ label: "Wetland", delta: -15, reason: "USFWS NWI" });
  }

  // Vacant land bonus — small nudge
  if (parcel.has_structure === false) {
    factors.push({ label: "Vacant", delta: 5, reason: "No existing structure" });
  }

  const raw = factors.reduce((s, f) => s + f.delta, 0);
  const score = Math.max(0, Math.min(100, Math.round(raw)));
  return { score, tier: tierFor(score), factors };
}

export function tierFor(score: number): ScoreTier {
  if (score >= 80) return "excellent";
  if (score >= 60) return "strong";
  if (score >= 40) return "decent";
  if (score >= 20) return "weak";
  return "avoid";
}

export const TIER_LABELS: Record<ScoreTier, string> = {
  excellent: "Excellent",
  strong: "Strong",
  decent: "Decent",
  weak: "Weak",
  avoid: "Avoid",
};

/**
 * Tailwind background + text colors for a tier badge.
 */
export const TIER_BADGE_CLASSES: Record<ScoreTier, string> = {
  excellent: "bg-emerald-100 text-emerald-700",
  strong: "bg-blue-100 text-blue-700",
  decent: "bg-slate-100 text-slate-600",
  weak: "bg-amber-100 text-amber-700",
  avoid: "bg-red-100 text-red-700",
};

// Acreage curve constants — mirror of ACRE_* in
// backend/app/services/buybox_scoring.py. Keep in lock-step.
const ACRE_SWEET_LOW = 2.0;
const ACRE_SWEET_HIGH = 8.0;
export const ACRE_MAX = 15.0;
const ACRE_PEAK = 20.0;
const ACRE_EDGE = 5.0;
const ACRE_OVERSIZE = -15.0;

/** Signed acreage contribution — mirror of _acreage_delta in buybox_scoring.py. */
export function acreageDelta(acres: number): number {
  if (acres < ACRE_SWEET_LOW) return round1((acres / ACRE_SWEET_LOW) * ACRE_PEAK);
  if (acres <= ACRE_SWEET_HIGH) return ACRE_PEAK;
  if (acres <= ACRE_MAX) {
    const span = ACRE_MAX - ACRE_SWEET_HIGH;
    return round1(ACRE_PEAK - ((acres - ACRE_SWEET_HIGH) / span) * (ACRE_PEAK - ACRE_EDGE));
  }
  return ACRE_OVERSIZE;
}

function clamp01(x: number): number {
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function round1(x: number): number {
  return Math.round(x * 10) / 10;
}
