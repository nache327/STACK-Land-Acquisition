import {
  deriveRecommendedAction,
  deriveTier,
  labelBlockingGap,
  TIERS,
} from "@/lib/admin/tier";
import type { CoverageJurisdiction } from "@/lib/schemas";

function row(over: Partial<CoverageJurisdiction>): CoverageJurisdiction {
  return {
    jurisdiction_id: "00000000-0000-0000-0000-000000000000",
    jurisdiction_name: "Test",
    state: "NJ",
    county: null,
    coverage_level: null,
    captured_at: null,
    parcel_count: 0,
    parcel_with_zoning_code_count: 0,
    zoning_district_count: 0,
    matrix_zone_count: 0,
    operational_readiness: "not_loaded",
    blocking_gaps: [],
    self_storage_classified_parcel_pct: 0,
    parcel_zoning_code_coverage_pct: 0,
    municipality_breakdown: null,
    source_count_total: 0,
    source_count_verified: 0,
    source_count_rejected: 0,
    source_count_pending: 0,
    source_confidence_distribution: {},
    ...over,
  };
}

describe("deriveTier", () => {
  it("returns T0 when no parcels are loaded", () => {
    expect(deriveTier(row({}))).toBe("T0");
  });

  it("returns T1 when parcels exist but no sources have been discovered", () => {
    expect(deriveTier(row({ parcel_count: 1000 }))).toBe("T1");
  });

  it("returns T2 when sources exist but none are verified yet", () => {
    expect(
      deriveTier(
        row({
          parcel_count: 1000,
          source_count_total: 5,
          source_count_pending: 5,
        }),
      ),
    ).toBe("T2");
  });

  it("returns T3 when sources are verified but no overlays ingested", () => {
    expect(
      deriveTier(
        row({
          parcel_count: 1000,
          source_count_total: 5,
          source_count_verified: 3,
        }),
      ),
    ).toBe("T3");
  });

  it("returns T4 when overlays exist but zoning code coverage is below 80%", () => {
    expect(
      deriveTier(
        row({
          parcel_count: 1000,
          source_count_total: 5,
          source_count_verified: 3,
          zoning_district_count: 30,
          parcel_zoning_code_coverage_pct: 42,
        }),
      ),
    ).toBe("T4");
  });

  it("returns T5 when zoning is mapped but self-storage classification is below 95%", () => {
    expect(
      deriveTier(
        row({
          parcel_count: 1000,
          source_count_total: 5,
          source_count_verified: 3,
          zoning_district_count: 30,
          parcel_zoning_code_coverage_pct: 95,
          self_storage_classified_parcel_pct: 80,
          operational_readiness: "partial",
        }),
      ),
    ).toBe("T5");
  });

  it("returns T6 only when operational_readiness === 'operational'", () => {
    expect(
      deriveTier(
        row({
          parcel_count: 1000,
          source_count_total: 5,
          source_count_verified: 3,
          zoning_district_count: 30,
          parcel_zoning_code_coverage_pct: 99,
          self_storage_classified_parcel_pct: 99,
          operational_readiness: "operational",
        }),
      ),
    ).toBe("T6");
  });
});

describe("deriveRecommendedAction", () => {
  it("links to filtered source review for review-stage jurisdictions", () => {
    const r = row({
      jurisdiction_id: "11111111-1111-1111-1111-111111111111",
      parcel_count: 1000,
      source_count_total: 7,
      source_count_pending: 7,
    });
    const action = deriveRecommendedAction(r);
    expect(action.tier).toBe("T2");
    expect(action.text).toMatch(/7 pending/);
    expect(action.href).toBe(
      "/admin/sources/11111111-1111-1111-1111-111111111111?status=pending",
    );
    expect(action.actionable).toBe(true);
  });

  it("marks T6 as non-actionable", () => {
    const r = row({
      parcel_count: 1000,
      source_count_total: 5,
      source_count_verified: 3,
      zoning_district_count: 30,
      parcel_zoning_code_coverage_pct: 99,
      self_storage_classified_parcel_pct: 99,
      operational_readiness: "operational",
    });
    expect(deriveRecommendedAction(r).actionable).toBe(false);
  });
});

describe("labelBlockingGap", () => {
  it("humanizes known gap codes", () => {
    expect(labelBlockingGap("no_parcels")).toBe("No parcels loaded");
    expect(labelBlockingGap("low_matrix_match_pct")).toMatch(/below 90%/);
  });
  it("falls back to a snake_case spread for unknown gaps", () => {
    expect(labelBlockingGap("brand_new_gap_code")).toBe("brand new gap code");
  });
});

describe("TIERS labels", () => {
  it("covers every tier with a label and stage description", () => {
    (["T0", "T1", "T2", "T3", "T4", "T5", "T6"] as const).forEach((t) => {
      expect(TIERS[t].label).toBeTruthy();
      expect(TIERS[t].stage).toBeTruthy();
    });
  });
});
