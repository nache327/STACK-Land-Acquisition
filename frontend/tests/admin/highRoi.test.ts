import {
  computeHighRoiQueue,
  computeIngestReady,
} from "@/lib/admin/highRoi";
import type { CoverageJurisdiction } from "@/lib/schemas";

function jur(over: Partial<CoverageJurisdiction>): CoverageJurisdiction {
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

describe("computeHighRoiQueue", () => {
  it("ranks municipalities by unzoned-parcel count desc, dropping operational towns", () => {
    const a = jur({
      jurisdiction_id: "11111111-1111-1111-1111-111111111111",
      jurisdiction_name: "Bergen County",
      state: "NJ",
      source_count_pending: 12,
      municipality_breakdown: {
        Paramus: { parcels: 100, parcels_with_zoning: 0, zoning_overlays: 0 },
        Mahwah: { parcels: 60, parcels_with_zoning: 60, zoning_overlays: 18 }, // done — should drop
        Tenafly: { parcels: 40, parcels_with_zoning: 10, zoning_overlays: 3 },
      },
    });
    const b = jur({
      jurisdiction_id: "22222222-2222-2222-2222-222222222222",
      jurisdiction_name: "Philadelphia",
      state: "PA",
      source_count_pending: 0,
      municipality_breakdown: {
        Philadelphia: {
          parcels: 200,
          parcels_with_zoning: 50,
          zoning_overlays: 22,
        },
      },
    });

    const ranked = computeHighRoiQueue({ jurisdictions: [a, b] });
    expect(ranked).toHaveLength(3); // Mahwah dropped
    expect(ranked[0].municipality).toBe("Philadelphia"); // 150 unzoned
    expect(ranked[1].municipality).toBe("Paramus"); // 100 unzoned
    expect(ranked[2].municipality).toBe("Tenafly"); // 30 unzoned

    // jurisdiction_pending propagates from parent jurisdiction
    expect(ranked[1].jurisdiction_pending).toBe(12);
    expect(ranked[0].jurisdiction_pending).toBe(0);

    expect(ranked[0].unzoned_parcels).toBe(150);
    expect(ranked[0].zoning_pct).toBeCloseTo(25, 1);
  });

  it("returns an empty array when no jurisdiction has a breakdown", () => {
    const out = computeHighRoiQueue({
      jurisdictions: [jur({ municipality_breakdown: null })],
    });
    expect(out).toEqual([]);
  });

  it("respects the limit parameter", () => {
    const breakdown: Record<string, { parcels: number; parcels_with_zoning: number; zoning_overlays: number }> = {};
    for (let i = 0; i < 50; i++) {
      breakdown[`Town${i}`] = {
        parcels: 10 + i,
        parcels_with_zoning: 0,
        zoning_overlays: 0,
      };
    }
    const ranked = computeHighRoiQueue({
      jurisdictions: [jur({ municipality_breakdown: breakdown })],
      limit: 5,
    });
    expect(ranked).toHaveLength(5);
    // Largest unzoned counts win — Town49 has 59 parcels
    expect(ranked[0].municipality).toBe("Town49");
  });
});

describe("computeIngestReady", () => {
  it("surfaces jurisdictions with verified sources and zero overlays, sorted by verified desc", () => {
    const ready = computeIngestReady([
      jur({
        jurisdiction_name: "A",
        source_count_verified: 3,
        zoning_district_count: 0,
      }),
      jur({
        jurisdiction_name: "B",
        source_count_verified: 7,
        zoning_district_count: 0,
      }),
      jur({
        jurisdiction_name: "C",
        source_count_verified: 5,
        zoning_district_count: 12, // already ingested → skip
      }),
      jur({
        jurisdiction_name: "D",
        source_count_verified: 0,
        zoning_district_count: 0, // no verified → skip
      }),
    ]);
    expect(ready.map((j) => j.jurisdiction_name)).toEqual(["B", "A"]);
  });
});
