import {
  deriveRunbookSteps,
  runbookExecutability,
} from "@/lib/admin/municipalityRunbook";
import type { MunicipalitySnapshot } from "@/lib/admin/municipalityOps";
import type { QueueSource } from "@/lib/schemas";

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

let _idCounter = 0;
function src(over: Partial<QueueSource>): QueueSource {
  _idCounter += 1;
  return {
    id: `00000000-0000-0000-0000-${String(_idCounter).padStart(12, "0")}`,
    jurisdiction_id: "11111111-1111-1111-1111-111111111111",
    jurisdiction_name: "Bergen",
    state: "NJ",
    county: null,
    municipality_name: "Paramus",
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

describe("deriveRunbookSteps", () => {
  it("M0 — no executable, surfaces honest 'parcel ingest is jurisdiction-grain' message", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({}),
      townSources: [],
      hasStaleRows: false,
    });
    expect(steps[0].kind).toBe("none");
    expect(steps[0].blocked_reason).toMatch(/jurisdiction/i);
    expect(steps.find((s) => s.kind === "refresh_audit")).toBeDefined();
  });

  it("M1 — surfaces a primary 'discover' step", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({ parcels: 50 }),
      townSources: [],
      hasStaleRows: false,
    });
    const discover = steps.find((s) => s.kind === "discover")!;
    expect(discover).toBeDefined();
    expect(discover.primary).toBe(true);
    expect(discover.title).toMatch(/Paramus/);
  });

  it("M2 — surfaces a primary 'review_pending' step with deep-link", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({
        jurisdiction_id: "j1",
        municipality: "Paramus",
        parcels: 50,
        source_count_pending: 7,
      }),
      townSources: [
        src({ jurisdiction_id: "j1", validation_status: "pending" }),
      ],
      hasStaleRows: false,
    });
    const review = steps.find((s) => s.kind === "review_pending")!;
    expect(review.primary).toBe(true);
    expect(review.href).toBe(
      "/admin/sources/j1?status=pending&municipality=Paramus",
    );
    expect(review.title).toMatch(/7 pending/);
  });

  it("M3 — surfaces a primary 'ingest_verified' step carrying source_ids of verified rows", () => {
    const v1 = src({
      jurisdiction_id: "j1",
      validation_status: "verified",
    });
    const v2 = src({
      jurisdiction_id: "j1",
      validation_status: "verified",
    });
    const p = src({
      jurisdiction_id: "j1",
      validation_status: "pending",
    });
    const steps = deriveRunbookSteps({
      snapshot: snap({
        jurisdiction_id: "j1",
        parcels: 50,
        source_count_verified: 2,
      }),
      townSources: [v1, v2, p],
      hasStaleRows: false,
    });
    const ingest = steps.find((s) => s.kind === "ingest_verified")!;
    expect(ingest.primary).toBe(true);
    expect(ingest.source_ids).toEqual([v1.id, v2.id]); // pending excluded
  });

  it("M3 with no verified sources — ingest step is blocked", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({
        parcels: 50,
        source_count_verified: 1, // tier says M3...
      }),
      townSources: [], // ...but no verified rows in our list
      hasStaleRows: false,
    });
    const ingest = steps.find((s) => s.kind === "ingest_verified")!;
    expect(ingest.blocked_reason).toMatch(/no verified sources/i);
    expect(ingest.source_ids).toEqual([]);
  });

  it("M4/M5 — points operator to the parent-jurisdiction page", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({
        jurisdiction_id: "j1",
        parcels: 100,
        parcels_with_zoning: 60,
        zoning_overlays: 15,
        source_count_verified: 2,
      }),
      townSources: [],
      hasStaleRows: false,
    });
    const point = steps.find(
      (s) => s.key === "rerun_jurisdiction_action",
    )!;
    expect(point.href).toBe("/admin/coverage/j1");
  });

  it("M6 — surfaces 'operational, nothing to execute'", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({
        parcels: 100,
        parcels_with_zoning: 100,
        zoning_overlays: 25,
        source_count_verified: 2,
      }),
      townSources: [],
      hasStaleRows: false,
    });
    expect(steps[0].kind).toBe("none");
    expect(steps[0].title).toMatch(/Operational/);
  });

  it("hasStaleRows surfaces a rescore deep-link regardless of tier", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({ parcels: 50, source_count_pending: 2 }),
      townSources: [],
      hasStaleRows: true,
    });
    const rescore = steps.find((s) => s.kind === "rescore_stale");
    expect(rescore).toBeDefined();
    expect(rescore!.primary).toBe(false);
  });

  it("refresh_audit is always present and never primary", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({}),
      townSources: [],
      hasStaleRows: false,
    });
    const refresh = steps.find((s) => s.kind === "refresh_audit")!;
    expect(refresh).toBeDefined();
    expect(refresh.primary).toBe(false);
  });
});

describe("runbookExecutability", () => {
  it("reports the primary kind when one exists", () => {
    const steps = deriveRunbookSteps({
      snapshot: snap({ parcels: 50 }),
      townSources: [],
      hasStaleRows: false,
    });
    const ex = runbookExecutability(steps);
    expect(ex.has_primary).toBe(true);
    expect(ex.primary_kind).toBe("discover");
  });

  it("reports no primary for M6 / M0", () => {
    const m6 = runbookExecutability(
      deriveRunbookSteps({
        snapshot: snap({
          parcels: 100,
          parcels_with_zoning: 100,
          zoning_overlays: 25,
          source_count_verified: 2,
        }),
        townSources: [],
        hasStaleRows: false,
      }),
    );
    expect(m6.has_primary).toBe(false);
    expect(m6.primary_kind).toBeNull();
  });

  it("counts blocked steps", () => {
    const blockedM0 = runbookExecutability(
      deriveRunbookSteps({
        snapshot: snap({}),
        townSources: [],
        hasStaleRows: false,
      }),
    );
    expect(blockedM0.blocked_count).toBeGreaterThanOrEqual(1);
  });
});
