import {
  deriveConfidenceTier,
  isLowSignalScore,
  NOISE_THRESHOLD,
} from "@/lib/admin/confidenceTier";

describe("deriveConfidenceTier", () => {
  it("maps scores to the four operator tiers", () => {
    expect(deriveConfidenceTier(95).tier).toBe("strong");
    expect(deriveConfidenceTier(85).tier).toBe("strong");
    expect(deriveConfidenceTier(72).tier).toBe("decent");
    expect(deriveConfidenceTier(60).tier).toBe("decent");
    expect(deriveConfidenceTier(45).tier).toBe("weak");
    expect(deriveConfidenceTier(30).tier).toBe("weak");
    expect(deriveConfidenceTier(20).tier).toBe("junk");
    expect(deriveConfidenceTier(0).tier).toBe("junk");
  });

  it("returns 'unknown' for null / undefined / NaN", () => {
    expect(deriveConfidenceTier(null).tier).toBe("unknown");
    expect(deriveConfidenceTier(undefined).tier).toBe("unknown");
    expect(deriveConfidenceTier(NaN).tier).toBe("unknown");
  });
});

describe("isLowSignalScore", () => {
  it("flags below 30 as low-signal", () => {
    expect(isLowSignalScore(29)).toBe(true);
    expect(isLowSignalScore(0)).toBe(true);
    expect(isLowSignalScore(null)).toBe(true);
  });
  it("keeps 30+ as actionable", () => {
    expect(isLowSignalScore(30)).toBe(false);
    expect(isLowSignalScore(85)).toBe(false);
  });
});

it("NOISE_THRESHOLD is 30", () => {
  expect(NOISE_THRESHOLD).toBe(30);
});
