import type { SourceReviewAction, ZoningSource } from "@/lib/schemas";
import { sourceIsSpatiallyBlocked } from "./municipality";

/** What the operator should default to doing on a source row, looking at
 *  *only* its persisted fields. No live probe, no rescore, no cross-row
 *  context. Pure function — testable, deterministic, free.
 *
 *  Confidence levels:
 *    - "high":   suggestion is near-certain; the primary button should
 *                read like a one-click confirm.
 *    - "medium": worth surfacing but operator should glance at breakdown.
 *    - "low":    no strong signal; row needs human read.
 */

export interface SuggestedAction {
  action: SourceReviewAction | "review";
  reason: string;
  confidence: "high" | "medium" | "low";
}

const PROPOSED_TITLE_RE = /\b(proposed|draft|preliminary|future)\b/i;
const HISTORIC_RE = /\b(historic(?:al)?|landmark|preservation)\b/i;

export function suggestActionForSource(src: ZoningSource): SuggestedAction {
  // 1. Already-decided rows. Drawer reuse may pass these in; map them to
  //    no-op suggestions so the UI doesn't double-suggest.
  if (src.validation_status === "verified") {
    return {
      action: "review",
      reason: "Already verified — no action needed.",
      confidence: "low",
    };
  }
  if (src.validation_status === "rejected") {
    return {
      action: "review",
      reason: "Already rejected.",
      confidence: "low",
    };
  }

  // 2. Spatial mismatch is the strongest reject signal we have from
  //    persisted data alone.
  if (sourceIsSpatiallyBlocked(src)) {
    return {
      action: "reject",
      reason: "Scorer flagged spatial mismatch (wrong state / county / disjoint).",
      confidence: "high",
    };
  }

  const score = src.confidence_score ?? 0;
  const breakdown = src.confidence_breakdown ?? {};

  // 3. "Proposed/Draft/Future" layer titles are reliable false positives.
  if (src.title && PROPOSED_TITLE_RE.test(src.title)) {
    return {
      action: "reject",
      reason: "Title indicates a proposed / draft / future layer.",
      confidence: "high",
    };
  }
  if (src.title && HISTORIC_RE.test(src.title)) {
    return {
      action: "reject",
      reason: "Title indicates a historic / preservation overlay, not the base zoning.",
      confidence: "medium",
    };
  }

  // 4. Junk-score rows.
  if (score > 0 && score < 30) {
    return {
      action: "reject",
      reason: `Score ${score} is below the operator triage threshold.`,
      confidence: "medium",
    };
  }
  if (src.confidence_label === "discovered_low") {
    return {
      action: "reject",
      reason: "Scorer labeled this as low-confidence discovery.",
      confidence: "medium",
    };
  }

  // 5. Very-high score + has positive geometry / name signal → verify.
  const hasStrongPositiveSignal =
    (breakdown.geometry_polygon ?? 0) > 0
    || (breakdown.bbox_overlap_strong ?? 0) > 0
    || (breakdown.name_match ?? 0) >= 20;
  if (score >= 85 && hasStrongPositiveSignal) {
    return {
      action: "verify",
      reason: `Score ${score} with strong positive signals — safe to verify.`,
      confidence: "high",
    };
  }
  if (score >= 70 && hasStrongPositiveSignal) {
    return {
      action: "verify",
      reason: `Score ${score} with positive signals — likely verify.`,
      confidence: "medium",
    };
  }

  // 6. Middle ground → no opinion.
  return {
    action: "review",
    reason: "Mixed signals — requires a human read.",
    confidence: "low",
  };
}

/** Tone hint for the suggestion pill / primary button. */
export function suggestionTone(s: SuggestedAction): "emerald" | "rose" | "indigo" | "slate" {
  switch (s.action) {
    case "verify":
      return "emerald";
    case "reject":
      return "rose";
    case "needs_review":
      return "indigo";
    default:
      return "slate";
  }
}

/** Common reject-reason presets exposed as one-click buttons in the
 *  drawer. Keep this short — too many options = decision paralysis. */
export const QUICK_REJECT_REASONS: { key: string; label: string }[] = [
  { key: "wrong_state", label: "Wrong state / jurisdiction" },
  { key: "proposed_only", label: "Proposed / draft layer" },
  { key: "historic_overlay", label: "Historic / preservation overlay" },
  { key: "duplicate", label: "Duplicate of verified source" },
  { key: "broken_endpoint", label: "Endpoint returns no features / errors" },
];
