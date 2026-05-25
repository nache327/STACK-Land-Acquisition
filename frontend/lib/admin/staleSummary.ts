import type { QueueSource, RescoreChange } from "@/lib/schemas";

const BBOX_OVERLAP_KEYS = [
  "bbox_overlap_strong",
  "bbox_overlap_tiny",
  "bbox_overlap_disjoint",
] as const;

/** Mirror of backend `_has_bbox_overlap_component` in
 *  `stale_score_remediation.py`. A row is "stale" when its persisted
 *  confidence_breakdown carries none of the bbox_overlap_* components. */
export function isStaleBreakdown(
  breakdown: Record<string, number> | null | undefined,
): boolean {
  if (!breakdown) return true;
  return !BBOX_OVERLAP_KEYS.some((k) => k in breakdown);
}

export interface StaleJurisdictionRow {
  jurisdiction_id: string;
  jurisdiction_name: string;
  state: string | null;
  total_stale: number;
  stale_pending: number;
  stale_verified: number;
  stale_rejected: number;
  stale_needs_review: number;
  max_confidence_score: number | null;
  /** Best-effort proxy for "how recently was scoring last touched here" —
   *  the freshest `updated_at` across the stale rows. Helps the operator
   *  spot jurisdictions whose stale rows are very old. */
  latest_stale_updated_at: string | null;
}

/** Group a flat stale-row list into a per-jurisdiction summary, ranked by
 *  total stale count desc. Pure function — no I/O. */
export function groupStaleByJurisdiction(
  rows: QueueSource[],
): StaleJurisdictionRow[] {
  const m = new Map<string, StaleJurisdictionRow>();
  for (const r of rows) {
    const existing = m.get(r.jurisdiction_id) ?? {
      jurisdiction_id: r.jurisdiction_id,
      jurisdiction_name: r.jurisdiction_name,
      state: r.state,
      total_stale: 0,
      stale_pending: 0,
      stale_verified: 0,
      stale_rejected: 0,
      stale_needs_review: 0,
      max_confidence_score: null,
      latest_stale_updated_at: null,
    };
    existing.total_stale += 1;
    if (r.validation_status === "pending") existing.stale_pending += 1;
    else if (r.validation_status === "verified") existing.stale_verified += 1;
    else if (r.validation_status === "rejected") existing.stale_rejected += 1;
    else if (r.validation_status === "needs_review")
      existing.stale_needs_review += 1;

    if (r.confidence_score != null) {
      existing.max_confidence_score = Math.max(
        existing.max_confidence_score ?? 0,
        r.confidence_score,
      );
    }
    if (
      r.updated_at
      && (existing.latest_stale_updated_at == null
        || r.updated_at > existing.latest_stale_updated_at)
    ) {
      existing.latest_stale_updated_at = r.updated_at;
    }
    m.set(r.jurisdiction_id, existing);
  }
  return Array.from(m.values()).sort(
    (a, b) =>
      b.total_stale - a.total_stale
      || a.jurisdiction_name.localeCompare(b.jurisdiction_name),
  );
}

export interface QueueDeltaSummary {
  total_changed: number;
  /** Net change in the >=70 "high-confidence queue" — negative = queue shrinks
   *  (rows dropped below 70), positive = queue grows. */
  queue_70_net_delta: number;
  newly_disjoint: number;
  applied: number;
  skipped_immutable: number;
  total_score_decreases: number;
  total_score_increases: number;
}

/** Compress a RescoreResponse.summary into operator-facing deltas. */
export function computeQueueDelta(
  changes: RescoreChange[],
  summary: {
    newly_above_threshold_70: number;
    newly_below_threshold_70: number;
    live_verdict_disjoint: number;
    applied: number;
    skipped_immutable: number;
    score_decreased: number;
    score_increased: number;
  },
): QueueDeltaSummary {
  return {
    total_changed: changes.length,
    queue_70_net_delta:
      summary.newly_above_threshold_70 - summary.newly_below_threshold_70,
    newly_disjoint: summary.live_verdict_disjoint,
    applied: summary.applied,
    skipped_immutable: summary.skipped_immutable,
    total_score_decreases: summary.score_decreased,
    total_score_increases: summary.score_increased,
  };
}

/** Pick a default action the operator should take on each diff row after
 *  reviewing the dry-run. Pure — no I/O.
 *
 *  Decision table:
 *    - status==verified && live_verdict==disjoint → REJECT (ingest would break)
 *    - status==verified && live_verdict==tiny     → NEEDS_REVIEW (suspect)
 *    - status==pending  && after.score < 30       → REJECT (now low-confidence noise)
 *    - status==pending  && crosses_threshold_70==up → VERIFY-candidate
 *    - default                                    → none — apply rescore only
 */
export type StaleAfterAction =
  | "reject"
  | "needs_review"
  | "verify_candidate"
  | "none";

export function suggestPostRescoreAction(c: RescoreChange): StaleAfterAction {
  const status = c.validation_status;
  const liveVerdict = c.live_verdict;
  const afterScore = c.after.confidence_score ?? 0;

  if (status === "verified" && liveVerdict === "disjoint") return "reject";
  if (status === "verified" && liveVerdict === "tiny") return "needs_review";
  if (status === "pending" && afterScore < 30) return "reject";
  if (status === "pending" && c.crosses_threshold_70 === "up") {
    return "verify_candidate";
  }
  return "none";
}
