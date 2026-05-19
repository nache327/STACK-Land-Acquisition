import { suggestActionForSource } from "@/lib/admin/suggestAction";
import type { ZoningSource } from "@/lib/schemas";

let _idCounter = 0;
function src(over: Partial<ZoningSource>): ZoningSource {
  _idCounter += 1;
  const id = `00000000-0000-0000-0000-${String(_idCounter).padStart(12, "0")}`;
  return {
    id,
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
    ...over,
  };
}

describe("suggestActionForSource", () => {
  it("suggests no-op for already-verified rows", () => {
    const s = suggestActionForSource(src({ validation_status: "verified" }));
    expect(s.action).toBe("review");
    expect(s.confidence).toBe("low");
  });

  it("suggests reject (high confidence) for spatially-blocked rows", () => {
    const s = suggestActionForSource(
      src({
        confidence_score: 80,
        confidence_breakdown: { wrong_state: -40, name_match: 25 },
      }),
    );
    expect(s.action).toBe("reject");
    expect(s.confidence).toBe("high");
    expect(s.reason).toMatch(/spatial mismatch/i);
  });

  it("suggests reject for 'Proposed' titles", () => {
    const s = suggestActionForSource(
      src({
        title: "Proposed Zoning Districts 2026",
        confidence_score: 85,
      }),
    );
    expect(s.action).toBe("reject");
    expect(s.confidence).toBe("high");
  });

  it("suggests reject for low-score rows (under 30)", () => {
    const s = suggestActionForSource(src({ confidence_score: 18 }));
    expect(s.action).toBe("reject");
    expect(s.confidence).toBe("medium");
  });

  it("suggests reject when scorer labeled 'discovered_low'", () => {
    const s = suggestActionForSource(
      src({
        confidence_score: 40,
        confidence_label: "discovered_low",
      }),
    );
    expect(s.action).toBe("reject");
  });

  it("suggests verify (high) for >=85 with strong positive signals", () => {
    const s = suggestActionForSource(
      src({
        confidence_score: 92,
        confidence_breakdown: {
          geometry_polygon: 20,
          name_match: 25,
          bbox_overlap_strong: 20,
        },
      }),
    );
    expect(s.action).toBe("verify");
    expect(s.confidence).toBe("high");
  });

  it("suggests verify (medium) for 70-85 with positive signals", () => {
    const s = suggestActionForSource(
      src({
        confidence_score: 75,
        confidence_breakdown: { geometry_polygon: 20, name_match: 25 },
      }),
    );
    expect(s.action).toBe("verify");
    expect(s.confidence).toBe("medium");
  });

  it("falls back to 'review' for mid-range with no strong signal", () => {
    const s = suggestActionForSource(
      src({
        confidence_score: 55,
        confidence_breakdown: { name_match: 10 },
      }),
    );
    expect(s.action).toBe("review");
    expect(s.confidence).toBe("low");
  });
});
