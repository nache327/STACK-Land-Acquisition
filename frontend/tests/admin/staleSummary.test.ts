import {
  computeQueueDelta,
  groupStaleByJurisdiction,
  isStaleBreakdown,
  suggestPostRescoreAction,
} from "@/lib/admin/staleSummary";
import type { QueueSource, RescoreChange } from "@/lib/schemas";

let _idCounter = 0;
function qs(over: Partial<QueueSource>): QueueSource {
  _idCounter += 1;
  const id = `00000000-0000-0000-0000-${String(_idCounter).padStart(12, "0")}`;
  return {
    id,
    jurisdiction_id: "11111111-1111-1111-1111-111111111111",
    jurisdiction_name: "Bergen",
    state: "NJ",
    county: null,
    municipality_name: null,
    zoning_endpoint: null,
    title: null,
    source_type: null,
    feature_count: null,
    geometry_type: null,
    confidence_score: null,
    confidence_label: null,
    confidence_breakdown: null,
    validation_status: "pending",
    discovered_by: null,
    reasons: null,
    last_verified_at: null,
    rejected_reason: null,
    notes: null,
    updated_at: null,
    ...over,
  };
}

describe("isStaleBreakdown", () => {
  it("treats null and {} as stale", () => {
    expect(isStaleBreakdown(null)).toBe(true);
    expect(isStaleBreakdown(undefined)).toBe(true);
    expect(isStaleBreakdown({})).toBe(true);
  });

  it("treats any bbox_overlap_* key as fresh", () => {
    expect(isStaleBreakdown({ bbox_overlap_strong: 20 })).toBe(false);
    expect(isStaleBreakdown({ bbox_overlap_tiny: 0 })).toBe(false);
    expect(isStaleBreakdown({ bbox_overlap_disjoint: -60 })).toBe(false);
  });

  it("treats other keys as stale even with content", () => {
    expect(isStaleBreakdown({ name_match: 25, wrong_state: -40 })).toBe(true);
  });
});

describe("groupStaleByJurisdiction", () => {
  it("aggregates per-status counts and ranks by total stale desc", () => {
    const rows = [
      qs({
        jurisdiction_id: "j1",
        jurisdiction_name: "Bergen",
        validation_status: "pending",
        confidence_score: 72,
        updated_at: "2026-05-01T00:00:00Z",
      }),
      qs({
        jurisdiction_id: "j1",
        jurisdiction_name: "Bergen",
        validation_status: "verified",
        confidence_score: 85,
        updated_at: "2026-05-10T00:00:00Z",
      }),
      qs({
        jurisdiction_id: "j1",
        jurisdiction_name: "Bergen",
        validation_status: "pending",
        confidence_score: 60,
        updated_at: "2026-05-05T00:00:00Z",
      }),
      qs({
        jurisdiction_id: "j2",
        jurisdiction_name: "Hudson",
        validation_status: "pending",
        confidence_score: 50,
        updated_at: "2026-05-08T00:00:00Z",
      }),
    ];
    const grouped = groupStaleByJurisdiction(rows);
    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({
      jurisdiction_id: "j1",
      total_stale: 3,
      stale_pending: 2,
      stale_verified: 1,
      max_confidence_score: 85,
      latest_stale_updated_at: "2026-05-10T00:00:00Z",
    });
    expect(grouped[1].jurisdiction_id).toBe("j2");
    expect(grouped[1].total_stale).toBe(1);
  });

  it("returns an empty array for no rows", () => {
    expect(groupStaleByJurisdiction([])).toEqual([]);
  });
});

function change(over: Partial<RescoreChange>): RescoreChange {
  return {
    source_id: "00000000-0000-0000-0000-000000000000",
    municipality_name: null,
    title: null,
    zoning_endpoint: null,
    validation_status: "pending",
    before: {
      source_id: "00000000-0000-0000-0000-000000000000",
      confidence_score: 75,
      confidence_label: "discovered",
      confidence_breakdown: { name_match: 25 },
      reasons: [],
    },
    after: {
      confidence_score: 15,
      confidence_label: "discovered_low",
      confidence_breakdown: { name_match: 25, bbox_overlap_disjoint: -60 },
      reasons: [],
    },
    delta: -60,
    crosses_threshold_70: "down",
    live_verdict: "disjoint",
    live_overlap_ratio: 0,
    applied: false,
    ...over,
  };
}

describe("computeQueueDelta", () => {
  it("compresses backend summary into operator deltas", () => {
    const out = computeQueueDelta([change({}), change({})], {
      newly_above_threshold_70: 1,
      newly_below_threshold_70: 5,
      live_verdict_disjoint: 4,
      applied: 0,
      skipped_immutable: 0,
      score_decreased: 6,
      score_increased: 1,
    });
    expect(out.total_changed).toBe(2);
    expect(out.queue_70_net_delta).toBe(-4);
    expect(out.newly_disjoint).toBe(4);
  });
});

describe("suggestPostRescoreAction", () => {
  it("flags verified+disjoint for reject", () => {
    expect(
      suggestPostRescoreAction(
        change({ validation_status: "verified", live_verdict: "disjoint" }),
      ),
    ).toBe("reject");
  });
  it("flags verified+tiny for needs_review", () => {
    expect(
      suggestPostRescoreAction(
        change({ validation_status: "verified", live_verdict: "tiny" }),
      ),
    ).toBe("needs_review");
  });
  it("flags pending rows that fall under 30 for reject", () => {
    expect(
      suggestPostRescoreAction(
        change({
          validation_status: "pending",
          after: {
            confidence_score: 12,
            confidence_label: "discovered_low",
            confidence_breakdown: null,
            reasons: [],
          },
        }),
      ),
    ).toBe("reject");
  });
  it("flags pending rows crossing up over 70 as verify-candidates", () => {
    expect(
      suggestPostRescoreAction(
        change({
          validation_status: "pending",
          crosses_threshold_70: "up",
          after: {
            confidence_score: 88,
            confidence_label: "discovered",
            confidence_breakdown: null,
            reasons: [],
          },
        }),
      ),
    ).toBe("verify_candidate");
  });
  it("returns none for unremarkable rescores", () => {
    expect(
      suggestPostRescoreAction(
        change({
          validation_status: "pending",
          crosses_threshold_70: null,
          live_verdict: "good",
          after: {
            confidence_score: 55,
            confidence_label: "discovered",
            confidence_breakdown: null,
            reasons: [],
          },
        }),
      ),
    ).toBe("none");
  });
});
