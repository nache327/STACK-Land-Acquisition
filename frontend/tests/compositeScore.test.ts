/**
 * Composite-score mirror guard.
 *
 * `frontend/lib/compositeScore.ts` is a placeholder mirror of
 * `backend/app/services/buybox_scoring.score_for_parcel`. Both files carry
 * "keep byte-for-byte equivalent" comments but nothing enforced it, and the
 * acreage curve has already been changed twice.
 *
 * The vectors live in backend/tests/fixtures/score_golden_vectors.json and are
 * asserted by BOTH suites (pytest: test_acreage_curve.py::
 * test_golden_vectors_match_backend). If the formulas drift, one side fails.
 *
 * NOTE the fixture intentionally only uses inputs the placeholder implements.
 * The backend has additional factor families (3-mi population floor, wealth
 * density, LGC HNW depth, saturation, $/acre, listing boost, SS overlay) that
 * the placeholder does not — which is exactly why the placeholder must never be
 * used for ranking. See the batch scores endpoint.
 */
import { readFileSync } from "fs";
import { join } from "path";

import { acreageDelta, computeScore, tierFor, OVERSIZE_SCORE_CAP, ACRE_MAX } from "@/lib/compositeScore";

interface Vector {
  name: string;
  input: {
    storage_permission?: string | null;
    acres?: number;
    aadt?: number;
    in_flood_zone?: boolean;
    in_wetland?: boolean;
    has_structure?: boolean;
  };
  score: number;
  tier: string;
}

const fixturePath = join(
  __dirname,
  "..",
  "..",
  "backend",
  "tests",
  "fixtures",
  "score_golden_vectors.json"
);
const vectors: Vector[] = JSON.parse(readFileSync(fixturePath, "utf8")).vectors;

describe("composite score mirrors the backend (shared golden vectors)", () => {
  it("has vectors to check", () => {
    expect(vectors.length).toBeGreaterThan(10);
  });

  it.each(vectors.map((v) => [v.name, v] as const))("%s", (_name, v) => {
    const result = computeScore({
      storage_permission: v.input.storage_permission ?? null,
      acres: v.input.acres ?? null,
      aadt: v.input.aadt ?? null,
      in_flood_zone: v.input.in_flood_zone ?? false,
      in_wetland: v.input.in_wetland ?? false,
      has_structure: v.input.has_structure ?? null,
    });
    expect(result.score).toBe(v.score);
    expect(result.tier).toBe(v.tier);
  });
});

describe("acreage curve", () => {
  it.each([
    [0.5, 5.0],
    [2.0, 20.0],
    [8.0, 20.0],
    [15.0, 5.0],
    [16.0, 4.4],
    [33.0, -5.8],
    [100.0, -46.0],
    [160.0, -60.0],
    [259.0, -60.0],
  ])("delta(%sac) = %s", (acres, expected) => {
    expect(acreageDelta(acres as number)).toBe(expected);
  });

  it("is graduated, not a cliff", () => {
    expect(acreageDelta(16)).toBeGreaterThan(acreageDelta(33));
    expect(acreageDelta(33)).toBeGreaterThan(acreageDelta(100));
  });

  it("floors the penalty", () => {
    expect(acreageDelta(10_000)).toBe(-60.0);
  });
});

describe("oversize card cap", () => {
  it.each([15.01, 16, 28, 33, 100, 160, 259])(
    "%sac can never read deal-grade (>=70)",
    (acres) => {
      const r = computeScore({
        storage_permission: "permitted",
        acres: acres as number,
        aadt: 50_000,
        in_flood_zone: false,
        in_wetland: false,
        has_structure: false,
      });
      expect(r.score).toBeLessThanOrEqual(OVERSIZE_SCORE_CAP);
      expect(r.score).toBeLessThan(70);
    }
  );

  it("leaves in-band parcels alone", () => {
    const r = computeScore({
      storage_permission: "permitted",
      acres: 4,
      aadt: 50_000,
      in_flood_zone: false,
      in_wetland: false,
      has_structure: false,
    });
    expect(r.score).toBeGreaterThan(OVERSIZE_SCORE_CAP);
    expect(ACRE_MAX).toBe(15);
  });
});

describe("tier boundaries match the backend", () => {
  it.each([
    [80, "excellent"],
    [79, "strong"],
    [60, "strong"],
    [59, "decent"],
    [40, "decent"],
    [39, "weak"],
    [20, "weak"],
    [19, "avoid"],
    [0, "avoid"],
  ])("tierFor(%s) = %s", (score, tier) => {
    expect(tierFor(score as number)).toBe(tier);
  });
});
