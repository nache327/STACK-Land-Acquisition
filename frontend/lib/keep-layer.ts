/**
 * The Keep — luxury garage condo scoring.
 *
 * Derives a 0-100 score from the parcel's garage_permission value
 * so the LayerControl min-score slider can filter the map layer.
 *
 * Score bands map to the A/B/C legend colours:
 *   A  85-100  gold    #C9A84C  permitted by right
 *   B  70-84   blue    #5B8DB8  conditional use permit required
 *   C  55-69   slate   #8B9BA8  unclear / not explicitly mentioned
 *
 * When isochroneWealth is available the base score is multiplied by a
 * wealth factor derived from the weighted-mean HHI of the drive-time ring:
 *   $100k HHI → multiplier 1.0 (no change)
 *   $150k HHI → ~1.25 (max boost)
 *   $60k  HHI → ~0.75 (max penalty)
 */

import type { TractData } from "@/lib/isochrone";

export type KeepGrade = "A" | "B" | "C";

export const KEEP_COLORS: Record<KeepGrade, string> = {
  A: "#C9A84C",
  B: "#5B8DB8",
  C: "#8B9BA8",
};

export function garagePermToScore(permission: string | null | undefined): number | null {
  switch (permission) {
    case "permitted":    return 90;
    case "conditional":  return 72;
    case "unclear":      return 57;
    default:             return null;   // prohibited / unclassified → hide
  }
}

export function scoreToGrade(score: number): KeepGrade {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  return "C";
}

export function scoreToColor(score: number): string {
  return KEEP_COLORS[scoreToGrade(score)];
}

/** Returns true when the parcel should be visible given the current min-score slider. */
export function isKeepVisible(
  permission: string | null | undefined,
  minScore: number,
): boolean {
  const score = garagePermToScore(permission);
  return score !== null && score >= minScore;
}

/**
 * Weighted-mean HHI across tracts (weighted by household_count).
 * Normalised to a multiplier centred on $100k: [0.75, 1.25].
 */
export function computeWealthMultiplier(tracts: TractData[]): number {
  const valid = tracts.filter(
    (t) => t.median_hhi != null && t.household_count != null && t.household_count > 0,
  );
  if (!valid.length) return 1.0;
  const totalHH = valid.reduce((s, t) => s + t.household_count!, 0);
  const weightedHHI =
    valid.reduce((s, t) => s + t.median_hhi! * t.household_count!, 0) / totalHH;
  const raw = weightedHHI / 100_000;
  return Math.min(1.25, Math.max(0.75, raw));
}

/**
 * Wealth-adjusted Keep score (0-100).
 * Returns null for prohibited / unclassified — those parcels are hidden on the map.
 */
export function computeKeepScore(
  permission: string | null | undefined,
  tracts: TractData[] | null | undefined,
): number | null {
  const base = garagePermToScore(permission);
  if (base === null) return null;
  const multiplier = tracts?.length ? computeWealthMultiplier(tracts) : 1.0;
  return Math.round(Math.min(100, Math.max(0, base * multiplier)));
}
