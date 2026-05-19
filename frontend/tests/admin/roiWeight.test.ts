import {
  buildMunicipalityIndex,
  roiTagFor,
  roiWeight,
  sortQueueByMode,
} from "@/lib/admin/roiWeight";
import type { CoverageJurisdiction, QueueSource } from "@/lib/schemas";

let _idCounter = 0;
function qs(over: Partial<QueueSource>): QueueSource {
  _idCounter += 1;
  return {
    id: `00000000-0000-0000-0000-${String(_idCounter).padStart(12, "0")}`,
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

function jur(over: Partial<CoverageJurisdiction>): CoverageJurisdiction {
  return {
    jurisdiction_id: "11111111-1111-1111-1111-111111111111",
    jurisdiction_name: "Bergen",
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

describe("roiWeight", () => {
  const idx = buildMunicipalityIndex([
    jur({
      jurisdiction_id: "j1",
      municipality_breakdown: {
        Paramus: { parcels: 100, parcels_with_zoning: 0, zoning_overlays: 0 },
        Mahwah: { parcels: 5, parcels_with_zoning: 5, zoning_overlays: 2 },
        Tenafly: { parcels: 50, parcels_with_zoning: 10, zoning_overlays: 3 },
      },
    }),
  ]);

  it("returns 0 when the municipality isn't in the breakdown", () => {
    expect(
      roiWeight(qs({ jurisdiction_id: "j1", municipality_name: "Nowhere" }), idx),
    ).toBe(0);
  });

  it("returns 0 when there are no unzoned parcels", () => {
    expect(
      roiWeight(qs({ jurisdiction_id: "j1", municipality_name: "Mahwah" }), idx),
    ).toBe(0);
  });

  it("scales positive for unzoned parcels and stays within [0, 1]", () => {
    const wParamus = roiWeight(
      qs({ jurisdiction_id: "j1", municipality_name: "Paramus" }),
      idx,
    );
    const wTenafly = roiWeight(
      qs({ jurisdiction_id: "j1", municipality_name: "Tenafly" }),
      idx,
    );
    expect(wParamus).toBeGreaterThan(0);
    expect(wParamus).toBeLessThanOrEqual(1);
    // 100 unzoned > 40 unzoned, so Paramus weight should be higher.
    expect(wParamus).toBeGreaterThan(wTenafly);
  });
});

describe("sortQueueByMode", () => {
  const idx = buildMunicipalityIndex([
    jur({
      jurisdiction_id: "j1",
      municipality_breakdown: {
        Big: { parcels: 5000, parcels_with_zoning: 0, zoning_overlays: 0 },
        Small: { parcels: 20, parcels_with_zoning: 0, zoning_overlays: 0 },
      },
    }),
  ]);

  const high = qs({
    jurisdiction_id: "j1",
    municipality_name: "Small",
    confidence_score: 90,
  });
  const lowBig = qs({
    jurisdiction_id: "j1",
    municipality_name: "Big",
    confidence_score: 45,
  });
  const mid = qs({
    jurisdiction_id: "j1",
    municipality_name: "Big",
    confidence_score: 70,
  });

  it("'confidence' preserves backend order", () => {
    const out = sortQueueByMode([high, lowBig, mid], "confidence", idx);
    expect(out).toEqual([high, lowBig, mid]);
  });

  it("'roi' surfaces high-unzoned rows first regardless of confidence", () => {
    const out = sortQueueByMode([high, lowBig, mid], "roi", idx);
    // Both Big rows beat Small on ROI weight; tie-break is confidence desc.
    expect(out[0].municipality_name).toBe("Big");
    expect(out[2]).toBe(high);
  });

  it("'confidence_x_roi' blends — high score wins when ROI difference is small", () => {
    // Same ROI bucket (both 'Big') → confidence wins.
    const out = sortQueueByMode([lowBig, mid], "confidence_x_roi", idx);
    expect(out[0]).toBe(mid);
  });
});

describe("roiTagFor", () => {
  const idx = buildMunicipalityIndex([
    jur({
      jurisdiction_id: "j1",
      municipality_breakdown: {
        Paramus: { parcels: 100, parcels_with_zoning: 25, zoning_overlays: 10 },
      },
    }),
  ]);

  it("returns a tag for rows in a populated municipality", () => {
    const tag = roiTagFor(
      qs({ jurisdiction_id: "j1", municipality_name: "Paramus" }),
      idx,
    );
    expect(tag).not.toBeNull();
    expect(tag!.unzoned_parcels).toBe(75);
  });

  it("returns null when the municipality isn't in the index", () => {
    expect(
      roiTagFor(qs({ jurisdiction_id: "j1", municipality_name: "X" }), idx),
    ).toBeNull();
  });
});
