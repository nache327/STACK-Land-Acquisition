import {
  appendDecision,
  computeStats,
  emptyStats,
  formatLatency,
} from "@/lib/admin/sessionVelocity";

describe("sessionVelocity", () => {
  it("emptyStats() reports zeros", () => {
    expect(emptyStats()).toEqual({
      total: 0,
      verified: 0,
      rejected: 0,
      needs_review: 0,
      unverified: 0,
      median_latency_ms: null,
      decisions_per_minute: null,
    });
  });

  it("appendDecision() returns a new array (no mutation)", () => {
    const a = [
      { action: "verify" as const, at_ms: 1000, latency_ms: 2000 },
    ];
    const b = appendDecision(a, {
      action: "reject",
      at_ms: 2000,
      latency_ms: 3000,
    });
    expect(b).toHaveLength(2);
    expect(a).toHaveLength(1);
  });

  it("computeStats tallies actions and median latency", () => {
    const stats = computeStats([
      { action: "verify", at_ms: 0, latency_ms: 1000 },
      { action: "verify", at_ms: 60_000, latency_ms: 2000 },
      { action: "reject", at_ms: 120_000, latency_ms: 4000 },
      { action: "needs_review", at_ms: 180_000, latency_ms: 3000 },
    ]);
    expect(stats.total).toBe(4);
    expect(stats.verified).toBe(2);
    expect(stats.rejected).toBe(1);
    expect(stats.needs_review).toBe(1);
    expect(stats.median_latency_ms).toBe(3000);
  });

  it("decisions_per_minute is null with only 1 decision", () => {
    const stats = computeStats([
      { action: "verify", at_ms: 0, latency_ms: 500 },
    ]);
    expect(stats.decisions_per_minute).toBeNull();
  });

  it("decisions_per_minute reflects elapsed wall-clock", () => {
    const stats = computeStats([
      { action: "verify", at_ms: 0, latency_ms: 500 },
      { action: "verify", at_ms: 60_000, latency_ms: 500 },
      { action: "verify", at_ms: 120_000, latency_ms: 500 },
    ]);
    // 3 decisions across 2 minutes → 1.5/min
    expect(stats.decisions_per_minute).toBeCloseTo(1.5, 2);
  });

  it("formatLatency picks the right unit", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(500)).toBe("500ms");
    expect(formatLatency(2500)).toBe("2.5s");
    expect(formatLatency(125_000)).toBe("2.1m");
  });
});
