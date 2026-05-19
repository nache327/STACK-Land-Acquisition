/** One-glance bucketing of `confidence_score`. The thresholds are pinned to
 *  the discovery scorer's mental model: 70 is the operator triage cutoff,
 *  85 is "almost certainly the right layer", 30 is "probably junk". */

export type ConfidenceTier = "strong" | "decent" | "weak" | "junk" | "unknown";

const TIER_THRESHOLDS = [
  { tier: "strong" as const, min: 85, label: "Strong", short: "S" },
  { tier: "decent" as const, min: 60, label: "Decent", short: "D" },
  { tier: "weak" as const, min: 30, label: "Weak", short: "W" },
  { tier: "junk" as const, min: 0, label: "Junk", short: "J" },
];

export interface ConfidenceTierMeta {
  tier: ConfidenceTier;
  label: string;
  short: string;
  score: number | null;
}

export function deriveConfidenceTier(
  score: number | null | undefined,
): ConfidenceTierMeta {
  if (score == null || !Number.isFinite(score)) {
    return { tier: "unknown", label: "?", short: "?", score: null };
  }
  for (const t of TIER_THRESHOLDS) {
    if (score >= t.min) {
      return { tier: t.tier, label: t.label, short: t.short, score };
    }
  }
  return { tier: "junk", label: "Junk", short: "J", score };
}

/** Hide-by-default threshold for noise suppression. Rows below this score
 *  with no positive spatial signal aren't worth an operator click. */
export const NOISE_THRESHOLD = 30;

/** Should this score be auto-hidden from the queue by default? */
export function isLowSignalScore(score: number | null | undefined): boolean {
  return (score ?? 0) < NOISE_THRESHOLD;
}
