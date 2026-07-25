/**
 * Zoning Verification engine — the contracts that keep the panel honest.
 *
 * These lock in the 2026-07-25 audit fixes. Before them the engine had no test
 * coverage at all, and three defects shipped:
 *   1. isGrounded required confidence>=0.5 while the backend's
 *      verdict_gate.is_grounded ignores confidence — so a grounded verdict with
 *      NULL confidence (common for op5_factory / llm_rule) scored 35*0.25=9 and
 *      the panel read "44/100 Needs Verification" on parcels we HAD grounded.
 *   2. Layer 2 compared the queried zone code against itself, so it always
 *      returned "exact" (+35) — even on the no-coverage path, where a parcel we
 *      know nothing about collected points for a comparison never made.
 *   3. A grounded CONDITIONAL verdict was floored to 85 and then only its label
 *      demoted, rendering the self-contradictory "85/100 · Likely Viable".
 */
import {
  computeComposite,
  computeLayer2,
  isGrounded,
  scoreLayer1DB,
  type Layer1Result,
  type Layer3Result,
  type UseStatus,
} from "@/lib/verification";

const L3_NOT_RUN: Layer3Result = {
  status: "not-run",
  ordinanceUrl: null,
  ordinanceSource: null,
  selfStorageStatus: null,
  keepStatus: null,
  evidence: null,
  aiConfidence: null,
  notes: null,
  classificationSource: null,
  score: 0,
};

/** Mirrors useVerification.buildState so tests exercise the real wiring. */
function evaluate(opts: {
  source: string;
  confidence: number | null;
  humanReviewed: boolean;
  status: UseStatus;
  layer1Status?: Layer1Result["status"];
}) {
  const l1Status = opts.layer1Status ?? "complete";
  const scored = scoreLayer1DB({
    selfStorageStatus: opts.status,
    classificationSource: opts.source,
    confidence: opts.confidence,
    humanReviewed: opts.humanReviewed,
  });
  const layer1: Layer1Result = {
    status: l1Status,
    zoneCode: "LI",
    zoneName: "Light Industrial",
    selfStorageStatus: opts.status,
    miniWarehouseStatus: "unclear",
    lightIndustrialStatus: "unclear",
    luxuryGarageStatus: "unclear",
    classificationSource: opts.source,
    confidence: opts.confidence,
    humanReviewed: opts.humanReviewed,
    grounded: scored.grounded,
    notes: null,
    permitType: scored.permitType,
    score: scored.score,
    fetchedAt: Date.now(),
  };
  // buildState passes null unless Layer 1 resolved.
  const layer2 = computeLayer2("LI", l1Status === "complete" ? layer1.zoneCode : null);
  return { layer1, layer2, ...computeComposite(layer1, layer2, L3_NOT_RUN) };
}

describe("isGrounded — lock-step with verdict_gate.is_grounded", () => {
  it("is grounded on a grounded source regardless of confidence (the 44/100 fix)", () => {
    for (const source of ["human", "llm", "llm_rule", "op5_factory"]) {
      expect(isGrounded({ classificationSource: source, confidence: null, humanReviewed: false })).toBe(true);
      expect(isGrounded({ classificationSource: source, confidence: 0.1, humanReviewed: false })).toBe(true);
    }
  });

  it("is grounded whenever a human reviewed it, whatever the source", () => {
    expect(isGrounded({ classificationSource: "crosswalk", confidence: null, humanReviewed: true })).toBe(true);
  });

  it("is NOT grounded for heuristic sources", () => {
    for (const source of ["rule", "unclear", "crosswalk", "inherited_pending"]) {
      expect(isGrounded({ classificationSource: source, confidence: 0.99, humanReviewed: false })).toBe(false);
    }
  });
});

describe("grounded verdicts reach VERIFIED without a manual Layer-3 pass", () => {
  it.each(["op5_factory", "llm_rule", "human", "llm"])(
    "%s + permitted + NULL confidence => VERIFIED (was 44/100)",
    (source) => {
      const r = evaluate({ source, confidence: null, humanReviewed: false, status: "permitted" });
      expect(r.compositeScore).toBeGreaterThanOrEqual(85);
      expect(r.overallStatus).toBe("VERIFIED");
    }
  );

  it("human-reviewed row with an unlisted source still verifies", () => {
    const r = evaluate({ source: "crosswalk", confidence: null, humanReviewed: true, status: "permitted" });
    expect(r.overallStatus).toBe("VERIFIED");
  });
});

describe("conditional (CUP) verdicts never read as fully permitted", () => {
  it("caps the SCORE below the VERIFIED band, not just the label", () => {
    const r = evaluate({ source: "op5_factory", confidence: null, humanReviewed: true, status: "conditional" });
    expect(r.compositeScore).toBeLessThanOrEqual(84);
    expect(r.overallStatus).not.toBe("VERIFIED");
    // The old bug: score 85 with a PROBABLE label ("85/100 · Likely Viable").
    expect(r.compositeScore === 85 && r.overallStatus === "PROBABLE").toBe(false);
  });
});

describe("hard overrides still win over the grounded floor", () => {
  it("grounded + prohibited => PROHIBITED 0, never VERIFIED", () => {
    const r = evaluate({ source: "human", confidence: 0.95, humanReviewed: true, status: "prohibited" });
    expect(r.compositeScore).toBe(0);
    expect(r.overallStatus).toBe("PROHIBITED");
  });
});

describe("Layer 2 only scores when Layer 1 actually resolved", () => {
  it("no-coverage parcel gets no points and reads UNVERIFIED", () => {
    const r = evaluate({
      source: "unclear",
      confidence: null,
      humanReviewed: false,
      status: "unclear",
      layer1Status: "no-coverage",
    });
    expect(r.layer2.score).toBe(0);
    expect(r.layer2.matchType).toBe("unavailable");
    expect(r.compositeScore).toBe(0);
    expect(r.overallStatus).toBe("UNVERIFIED");
  });

  it("a missing db zone code is unavailable, not a match", () => {
    expect(computeLayer2("LI", null).matchType).toBe("unavailable");
    expect(computeLayer2("LI", null).score).toBe(0);
    expect(computeLayer2(null, "LI").score).toBe(0);
  });

  it("a genuine code mismatch is a CONFLICT that zeroes the composite", () => {
    const layer2 = computeLayer2("LI", "R-1");
    expect(layer2.matchType).toBe("conflict");
    const layer1: Layer1Result = {
      status: "complete", zoneCode: "R-1", zoneName: "", selfStorageStatus: "permitted",
      miniWarehouseStatus: "unclear", lightIndustrialStatus: "unclear", luxuryGarageStatus: "unclear",
      classificationSource: "human", confidence: 0.9, humanReviewed: true, grounded: true,
      notes: null, permitType: "permitted-by-right", score: 35, fetchedAt: 0,
    };
    const c = computeComposite(layer1, layer2, L3_NOT_RUN);
    expect(c.compositeScore).toBe(0);
    expect(c.overallStatus).toBe("CONFLICT");
  });
});

describe("single-source verdicts are capped (the <2-layers safety net)", () => {
  it("caps at 65 when only one layer resolved", () => {
    // Layer 1 resolved but ungrounded, Layer 2 unavailable, Layer 3 not run.
    const layer1: Layer1Result = {
      status: "complete", zoneCode: "LI", zoneName: "", selfStorageStatus: "permitted",
      miniWarehouseStatus: "unclear", lightIndustrialStatus: "unclear", luxuryGarageStatus: "unclear",
      classificationSource: "rule", confidence: 0.8, humanReviewed: false, grounded: false,
      notes: null, permitType: "permitted-by-right", score: 100, fetchedAt: 0,
    };
    const c = computeComposite(layer1, computeLayer2("LI", null), L3_NOT_RUN);
    expect(c.compositeScore).toBeLessThanOrEqual(65);
  });
});
