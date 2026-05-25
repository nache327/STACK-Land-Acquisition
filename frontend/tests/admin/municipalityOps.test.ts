import {
  buildCrossJurisdictionMunicipalityRollup,
  deriveMunicipalityBlockers,
  deriveMunicipalityHealth,
  deriveMunicipalityTier,
  recommendMunicipalityAction,
  type MunicipalitySnapshot,
} from "@/lib/admin/municipalityOps";
import type { CoverageJurisdiction, QueueSource } from "@/lib/schemas";

function snap(over: Partial<MunicipalitySnapshot>): MunicipalitySnapshot {
  return {
    jurisdiction_id: "11111111-1111-1111-1111-111111111111",
    jurisdiction_name: "Bergen",
    state: "NJ",
    municipality: "Paramus",
    parcels: 0,
    parcels_with_zoning: 0,
    zoning_overlays: 0,
    source_count_pending: 0,
    source_count_verified: 0,
    source_count_rejected: 0,
    source_count_needs_review: 0,
    spatial_blocked_count: 0,
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

let _idCounter = 0;
function src(over: Partial<QueueSource>): QueueSource {
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

describe("deriveMunicipalityTier", () => {
  it("M0 when no parcels", () => {
    expect(deriveMunicipalityTier(snap({}))).toBe("M0");
  });
  it("M1 when parcels exist but no sources discovered", () => {
    expect(deriveMunicipalityTier(snap({ parcels: 100 }))).toBe("M1");
  });
  it("M2 when sources exist but none verified", () => {
    expect(
      deriveMunicipalityTier(
        snap({ parcels: 100, source_count_pending: 3 }),
      ),
    ).toBe("M2");
  });
  it("M3 when verified but no overlays", () => {
    expect(
      deriveMunicipalityTier(
        snap({ parcels: 100, source_count_verified: 2 }),
      ),
    ).toBe("M3");
  });
  it("M4 when overlays exist and < 50% parcels zoned", () => {
    expect(
      deriveMunicipalityTier(
        snap({
          parcels: 100,
          parcels_with_zoning: 40,
          zoning_overlays: 12,
          source_count_verified: 2,
        }),
      ),
    ).toBe("M4");
  });
  it("M5 when 50-99% zoned", () => {
    expect(
      deriveMunicipalityTier(
        snap({
          parcels: 100,
          parcels_with_zoning: 80,
          zoning_overlays: 15,
          source_count_verified: 2,
        }),
      ),
    ).toBe("M5");
  });
  it("M6 when fully zoned", () => {
    expect(
      deriveMunicipalityTier(
        snap({
          parcels: 100,
          parcels_with_zoning: 100,
          zoning_overlays: 25,
          source_count_verified: 2,
        }),
      ),
    ).toBe("M6");
  });
});

describe("deriveMunicipalityBlockers", () => {
  it("surfaces spatial mismatch as a hard blocker", () => {
    const blockers = deriveMunicipalityBlockers(
      snap({
        parcels: 50,
        source_count_pending: 3,
        spatial_blocked_count: 2,
      }),
    );
    const keys = blockers.map((b) => b.key);
    expect(keys).toContain("spatial_blocked");
    expect(blockers.find((b) => b.key === "spatial_blocked")?.severity).toBe("block");
  });

  it("flags 'no sources discovered' when town has parcels but no sources of any kind", () => {
    const blockers = deriveMunicipalityBlockers(snap({ parcels: 50 }));
    expect(blockers.find((b) => b.key === "no_sources")?.severity).toBe("block");
  });

  it("flags coverage gap with the unzoned count baked into the label", () => {
    const blockers = deriveMunicipalityBlockers(
      snap({
        parcels: 100,
        parcels_with_zoning: 70,
        zoning_overlays: 22,
        source_count_verified: 2,
      }),
    );
    const gap = blockers.find((b) => b.key === "coverage_gap");
    expect(gap).toBeDefined();
    expect(gap!.label).toMatch(/30 parcels/);
  });

  it("returns only no_parcels for M0 towns", () => {
    const blockers = deriveMunicipalityBlockers(snap({}));
    expect(blockers).toHaveLength(1);
    expect(blockers[0].key).toBe("no_parcels");
  });
});

describe("recommendMunicipalityAction", () => {
  it("M2 → deep-link to filtered pending review", () => {
    const a = recommendMunicipalityAction(
      snap({
        jurisdiction_id: "j1",
        municipality: "Paramus",
        parcels: 100,
        source_count_pending: 5,
      }),
    );
    expect(a.tier).toBe("M2");
    expect(a.href).toBe(
      "/admin/sources/j1?status=pending&municipality=Paramus",
    );
    expect(a.actionable).toBe(true);
  });

  it("M3 → deep-link to filtered verified review", () => {
    const a = recommendMunicipalityAction(
      snap({
        jurisdiction_id: "j1",
        municipality: "Mahwah",
        parcels: 100,
        source_count_verified: 3,
      }),
    );
    expect(a.tier).toBe("M3");
    expect(a.href).toBe(
      "/admin/sources/j1?status=verified&municipality=Mahwah",
    );
  });

  it("M6 → non-actionable", () => {
    const a = recommendMunicipalityAction(
      snap({
        parcels: 100,
        parcels_with_zoning: 100,
        zoning_overlays: 25,
        source_count_verified: 2,
      }),
    );
    expect(a.actionable).toBe(false);
  });
});

describe("buildCrossJurisdictionMunicipalityRollup", () => {
  it("flattens jurisdictions × towns and joins source counts", () => {
    const j1 = jur({
      jurisdiction_id: "j1",
      jurisdiction_name: "Bergen",
      state: "NJ",
      municipality_breakdown: {
        Paramus: { parcels: 100, parcels_with_zoning: 0, zoning_overlays: 0 },
        Mahwah: { parcels: 60, parcels_with_zoning: 60, zoning_overlays: 18 },
      },
    });
    const j2 = jur({
      jurisdiction_id: "j2",
      jurisdiction_name: "Hudson",
      state: "NJ",
      municipality_breakdown: {
        Hoboken: { parcels: 50, parcels_with_zoning: 10, zoning_overlays: 3 },
      },
    });
    const sources = [
      src({
        jurisdiction_id: "j1",
        municipality_name: "Paramus",
        validation_status: "pending",
      }),
      src({
        jurisdiction_id: "j1",
        municipality_name: "Paramus",
        validation_status: "verified",
      }),
      src({
        jurisdiction_id: "j1",
        municipality_name: "Mahwah",
        validation_status: "verified",
      }),
      src({
        jurisdiction_id: "j1",
        municipality_name: "Tenafly", // not in breakdown — should still surface
        validation_status: "pending",
        confidence_breakdown: { wrong_state: -40 },
      }),
    ];
    const rows = buildCrossJurisdictionMunicipalityRollup({
      jurisdictions: [j1, j2],
      sources,
    });
    const byName = Object.fromEntries(rows.map((r) => [r.municipality, r]));

    expect(byName.Paramus.source_count_pending).toBe(1);
    expect(byName.Paramus.source_count_verified).toBe(1);
    expect(byName.Mahwah.source_count_verified).toBe(1);
    expect(byName.Hoboken.source_count_pending).toBe(0);

    // Tenafly should appear even though it has no breakdown — surfaces
    // discovered-but-unloaded towns to the operator.
    expect(byName.Tenafly).toBeDefined();
    expect(byName.Tenafly.parcels).toBe(0);
    expect(byName.Tenafly.spatial_blocked_count).toBe(1);

    // Sort: M3 (Mahwah, verified+no overlays) first by urgency rank.
    // Actually Mahwah has zoning_overlays=18 already, so its zoning ratio
    // is 60/60 = 100% → M6. The most urgent is Paramus (M3: has verified
    // sources, no overlays). Let's check ordering accurately.
    const tierByName = (n: string) =>
      deriveMunicipalityTier(byName[n]);
    expect(tierByName("Mahwah")).toBe("M6");
    expect(tierByName("Paramus")).toBe("M3");
    expect(tierByName("Hoboken")).toBe("M4"); // overlays exist, only 20% zoned
    expect(rows[0].municipality).toBe("Paramus");
  });
});

describe("deriveMunicipalityHealth", () => {
  it("unhealthy when spatial blockers present", () => {
    expect(
      deriveMunicipalityHealth(
        snap({ parcels: 50, spatial_blocked_count: 1 }),
      ),
    ).toBe("unhealthy");
  });
  it("degraded when parcels exist but no overlays", () => {
    expect(
      deriveMunicipalityHealth(
        snap({ parcels: 50, source_count_verified: 1 }),
      ),
    ).toBe("degraded");
  });
  it("healthy when fully zoned and no blockers", () => {
    expect(
      deriveMunicipalityHealth(
        snap({
          parcels: 50,
          parcels_with_zoning: 50,
          zoning_overlays: 12,
          source_count_verified: 1,
        }),
      ),
    ).toBe("healthy");
  });
});
