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
 */

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
