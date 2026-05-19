import {
  buildMunicipalityRollup,
  parseMunicipalityBreakdown,
  sourceIsSpatiallyBlocked,
} from "@/lib/admin/municipality";
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

describe("parseMunicipalityBreakdown", () => {
  it("returns an empty dict for null/undefined/non-object input", () => {
    expect(parseMunicipalityBreakdown(null)).toEqual({});
    expect(parseMunicipalityBreakdown(undefined)).toEqual({});
    expect(parseMunicipalityBreakdown("nope")).toEqual({});
  });

  it("coerces numeric fields, defaulting missing ones to 0", () => {
    const out = parseMunicipalityBreakdown({
      Paramus: { parcels: 12, parcels_with_zoning: 10 },
      Mahwah: { parcels: 5, parcels_with_zoning: 5, zoning_overlays: 3 },
    });
    expect(out.Paramus).toEqual({
      parcels: 12,
      parcels_with_zoning: 10,
      zoning_overlays: 0,
    });
    expect(out.Mahwah.zoning_overlays).toBe(3);
  });
});

describe("sourceIsSpatiallyBlocked", () => {
  it("detects wrong_state / wrong_county / bbox_overlap_disjoint as blockers", () => {
    expect(
      sourceIsSpatiallyBlocked(
        src({ confidence_breakdown: { wrong_state: -40, name_match: 10 } }),
      ),
    ).toBe(true);
    expect(
      sourceIsSpatiallyBlocked(
        src({ confidence_breakdown: { bbox_overlap_disjoint: -60 } }),
      ),
    ).toBe(true);
  });

  it("ignores positive deltas (key present but score is positive)", () => {
    expect(
      sourceIsSpatiallyBlocked(
        src({ confidence_breakdown: { wrong_state: 0, name_match: 10 } }),
      ),
    ).toBe(false);
  });

  it("returns false when no spatial keys are present", () => {
    expect(
      sourceIsSpatiallyBlocked(
        src({ confidence_breakdown: { name_match: 25, geometry_polygon: 20 } }),
      ),
    ).toBe(false);
  });
});

describe("buildMunicipalityRollup", () => {
  it("classifies a typical Bergen-style row set across statuses", () => {
    const sources = [
      // Paramus: 2 pending, 1 verified, 0 spatial → review_backlog (because zoning_overlays = 0)
      src({ municipality_name: "Paramus", validation_status: "pending" }),
      src({ municipality_name: "Paramus", validation_status: "pending" }),
      src({ municipality_name: "Paramus", validation_status: "verified" }),
      // Mahwah: 1 verified, no overlays yet → ingest_ready
      src({ municipality_name: "Mahwah", validation_status: "verified" }),
      // Tenafly: 1 source with wrong_state → spatially_blocked
      src({
        municipality_name: "Tenafly",
        validation_status: "pending",
        confidence_breakdown: { wrong_state: -40 },
      }),
      // Englewood: source with positive scoring + town has parcels & overlays → ready
      src({ municipality_name: "Englewood", validation_status: "verified" }),
    ];
    const breakdown = parseMunicipalityBreakdown({
      Paramus: { parcels: 100, parcels_with_zoning: 0, zoning_overlays: 0 },
      Mahwah: { parcels: 50, parcels_with_zoning: 0, zoning_overlays: 0 },
      Tenafly: { parcels: 30, parcels_with_zoning: 0, zoning_overlays: 0 },
      Englewood: { parcels: 80, parcels_with_zoning: 75, zoning_overlays: 25 },
    });
    const rows = buildMunicipalityRollup({ breakdown, sources });
    const byName = Object.fromEntries(rows.map((r) => [r.name, r]));

    // The expected ordering puts urgent statuses first.
    expect(rows[0].name).toBe("Tenafly");
    expect(byName.Tenafly.status).toBe("spatially_blocked");
    expect(byName.Tenafly.spatial_blocked).toBe(true);

    // Paramus has 1 verified + 2 pending + 0 overlays, so the rollup
    // surfaces it as ingest-ready (any verified source is a one-click win
    // for the operator and outranks the pending backlog).
    expect(byName.Paramus.status).toBe("ingest_ready");
    expect(byName.Mahwah.status).toBe("ingest_ready");
    expect(byName.Englewood.status).toBe("ready");
  });

  it("ingest_ready beats review_backlog when there are any verified sources and no overlays", () => {
    const sources = [
      src({ municipality_name: "Mahwah", validation_status: "verified" }),
      src({ municipality_name: "Mahwah", validation_status: "pending" }),
    ];
    const rows = buildMunicipalityRollup({
      breakdown: parseMunicipalityBreakdown({
        Mahwah: { parcels: 50, parcels_with_zoning: 0, zoning_overlays: 0 },
      }),
      sources,
    });
    expect(rows[0].status).toBe("ingest_ready");
  });
});
