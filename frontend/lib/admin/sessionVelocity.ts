import type { SourceReviewAction } from "@/lib/schemas";

/** Per-session decision tally + median seconds-per-decision. Lives in
 *  memory (lost on full page reload), which matches the "burndown for
 *  this sitting" mental model the operator has. */

export interface SessionDecision {
  action: SourceReviewAction;
  /** ms epoch when the action mutation settled. */
  at_ms: number;
  /** ms between opening the row and committing the action. */
  latency_ms: number;
}

export interface SessionStats {
  total: number;
  verified: number;
  rejected: number;
  needs_review: number;
  unverified: number;
  median_latency_ms: number | null;
  /** Decisions per minute, averaged over the elapsed wall-clock window
   *  since the first decision in the session. Null until 2+ decisions. */
  decisions_per_minute: number | null;
}

export function emptyStats(): SessionStats {
  return {
    total: 0,
    verified: 0,
    rejected: 0,
    needs_review: 0,
    unverified: 0,
    median_latency_ms: null,
    decisions_per_minute: null,
  };
}

export function appendDecision(
  decisions: SessionDecision[],
  decision: SessionDecision,
): SessionDecision[] {
  return [...decisions, decision];
}

export function computeStats(decisions: SessionDecision[]): SessionStats {
  if (decisions.length === 0) return emptyStats();

  const counts = decisions.reduce(
    (acc, d) => {
      acc[d.action] = (acc[d.action] ?? 0) + 1;
      return acc;
    },
    {} as Record<SourceReviewAction, number>,
  );

  const sortedLatencies = decisions
    .map((d) => d.latency_ms)
    .filter((ms) => Number.isFinite(ms) && ms > 0)
    .sort((a, b) => a - b);
  const median =
    sortedLatencies.length === 0
      ? null
      : sortedLatencies[Math.floor(sortedLatencies.length / 2)];

  let perMin: number | null = null;
  if (decisions.length >= 2) {
    const first = Math.min(...decisions.map((d) => d.at_ms));
    const last = Math.max(...decisions.map((d) => d.at_ms));
    const minutes = Math.max((last - first) / 60_000, 1 / 60);
    perMin = decisions.length / minutes;
  }

  return {
    total: decisions.length,
    verified: counts.verify ?? 0,
    rejected: counts.reject ?? 0,
    needs_review: counts.needs_review ?? 0,
    unverified: counts.unverify ?? 0,
    median_latency_ms: median,
    decisions_per_minute: perMin,
  };
}

export function formatLatency(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}
