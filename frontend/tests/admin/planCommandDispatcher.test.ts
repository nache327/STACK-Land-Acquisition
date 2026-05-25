import {
  describeDispatch,
  dispatchPlanCommand,
} from "@/lib/admin/planCommandDispatcher";

const JID = "11111111-1111-1111-1111-111111111111";
const SID = "22222222-2222-2222-2222-222222222222";

describe("dispatchPlanCommand", () => {
  it("dispatches discover-municipal-zoning to the discover kind", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_discover-municipal-zoning`,
      body: { municipality_names: ["Paramus", "Mahwah"] },
    });
    expect(d.kind).toBe("discover");
    if (d.kind === "discover") {
      expect(d.countyId).toBe(JID);
      expect(d.municipalityNames).toEqual(["Paramus", "Mahwah"]);
    }
  });

  it("rejects discover with missing municipality_names", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_discover-municipal-zoning`,
      body: {},
    });
    expect(d.kind).toBe("unsupported");
  });

  it("dispatches ingest-municipal-zoning", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_ingest-municipal-zoning`,
      body: { source_ids: [SID] },
    });
    expect(d.kind).toBe("ingest");
    if (d.kind === "ingest") expect(d.sourceIds).toEqual([SID]);
  });

  it("dispatches single-source review", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_sources/${SID}/_review`,
      body: { action: "verify" },
    });
    expect(d.kind).toBe("review");
    if (d.kind === "review") {
      expect(d.jurisdictionId).toBe(JID);
      expect(d.sourceId).toBe(SID);
      expect(d.body.action).toBe("verify");
    }
  });

  it("rejects review with unknown action", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_sources/${SID}/_review`,
      body: { action: "explode" },
    });
    expect(d.kind).toBe("unsupported");
  });

  it("dispatches bulk-review", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_sources/_bulk-review`,
      body: { action: "reject", source_ids: [SID, SID] },
    });
    expect(d.kind).toBe("bulk_review");
  });

  it("dispatches rescore with a safe dry_run default", () => {
    const d = dispatchPlanCommand({
      method: "POST",
      path: `/api/jurisdictions/${JID}/_rescore-stale-sources`,
      body: {},
    });
    expect(d.kind).toBe("rescore");
    if (d.kind === "rescore") {
      expect(d.body.dry_run).toBe(true); // safety floor
      expect(d.body.stale_only).toBe(true);
    }
  });

  it("dispatches /admin/coverage/refresh, parsing optional jurisdiction_id", () => {
    const d1 = dispatchPlanCommand({
      method: "POST",
      path: "/api/admin/coverage/refresh",
    });
    expect(d1.kind).toBe("refresh_coverage");
    if (d1.kind === "refresh_coverage") expect(d1.jurisdictionId).toBeNull();

    const d2 = dispatchPlanCommand({
      method: "POST",
      path: `/api/admin/coverage/refresh?jurisdiction_id=${JID}`,
    });
    if (d2.kind === "refresh_coverage")
      expect(d2.jurisdictionId).toBe(JID);

    const d3 = dispatchPlanCommand({
      method: "POST",
      path: "/api/admin/coverage/refresh",
      query: { jurisdiction_id: JID },
    });
    if (d3.kind === "refresh_coverage")
      expect(d3.jurisdictionId).toBe(JID);
  });

  it("rejects non-POST methods", () => {
    expect(
      dispatchPlanCommand({
        method: "GET",
        path: `/api/jurisdictions/${JID}/_discover-municipal-zoning`,
      }).kind,
    ).toBe("unsupported");
  });

  it("rejects paths outside the allow-list", () => {
    expect(
      dispatchPlanCommand({
        method: "POST",
        path: "/api/wildcards/run-arbitrary-command",
        body: { foo: "bar" },
      }).kind,
    ).toBe("unsupported");
    expect(
      dispatchPlanCommand({
        method: "POST",
        path: "/etc/passwd",
      }).kind,
    ).toBe("unsupported");
  });
});

describe("describeDispatch", () => {
  it("labels discover with the towns", () => {
    expect(
      describeDispatch({
        kind: "discover",
        countyId: JID,
        municipalityNames: ["Paramus"],
      }),
    ).toBe("Discover sources for Paramus");
  });
  it("labels ingest with the count", () => {
    expect(
      describeDispatch({
        kind: "ingest",
        countyId: JID,
        sourceIds: [SID, SID, SID],
      }),
    ).toBe("Ingest 3 verified sources");
  });
  it("falls back to CLI label for unsupported", () => {
    expect(
      describeDispatch({ kind: "unsupported", reason: "x" }),
    ).toBe("Use CLI");
  });
});
