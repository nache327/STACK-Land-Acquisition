import {
  deriveMunicipalityTier,
  type MunicipalitySnapshot,
} from "./municipalityOps";
import type { QueueSource } from "@/lib/schemas";

/** Operational lifecycle for a municipality, expressed as discrete
 *  executable steps. Each step is one click that hits one existing
 *  endpoint and returns inline. No multi-step orchestration here —
 *  operators chain steps by re-rendering after each commit.
 *
 *  Step kinds map 1:1 onto backend endpoints:
 *    - "discover"        → POST /_discover-municipal-zoning  (M1)
 *    - "review_pending"  → deep-link into /admin/sources     (M2)
 *    - "ingest_verified" → POST /_ingest-municipal-zoning    (M3)
 *    - "refresh_audit"   → POST /admin/coverage/refresh      (always)
 *    - "rescore_stale"   → deep-link into /admin/stale       (any tier with stale rows)
 *
 *  M0 / M4 / M5 / M6 don't currently have a town-grain executable on the
 *  backend — the only safe action is refresh_audit (always) plus the
 *  jurisdiction-grain operations linked off the parent page. We surface
 *  this honestly with `kind: "none"` placeholder steps so the operator
 *  sees the explicit "nothing to execute here" message instead of
 *  wondering whether the panel is broken.
 */

export type RunbookStepKind =
  | "discover"
  | "review_pending"
  | "ingest_verified"
  | "rescore_stale"
  | "refresh_audit"
  | "none";

export interface RunbookStep {
  key: string;
  kind: RunbookStepKind;
  title: string;
  description: string;
  /** When true, this is the next operator-leverage action for the tier.
   *  At most one primary step per panel. */
  primary: boolean;
  /** When set, the step is rendered disabled with the reason as tooltip. */
  blocked_reason?: string;
  /** Deep-link for steps where the action lives on another page (M2
   *  review still happens in the source drawer). */
  href?: string;
  /** When set, the runbook will pass these source_ids to the underlying
   *  endpoint (ingest_verified). */
  source_ids?: string[];
  /** Cosmetic — destructive steps get a rose tint to slow the operator
   *  down before they fire it. */
  danger?: boolean;
}

interface BuildArgs {
  snapshot: MunicipalitySnapshot;
  /** Sources scoped to this town. Used to compute source_ids for ingest. */
  townSources: QueueSource[];
  /** Whether *any* row in town has a stale persisted breakdown. Used to
   *  surface the rescore deep-link. */
  hasStaleRows: boolean;
}

export function deriveRunbookSteps({
  snapshot,
  townSources,
  hasStaleRows,
}: BuildArgs): RunbookStep[] {
  const tier = deriveMunicipalityTier(snapshot);
  const muni = snapshot.municipality;
  const jId = snapshot.jurisdiction_id;
  const steps: RunbookStep[] = [];

  switch (tier) {
    case "M0":
      steps.push({
        key: "m0_no_parcels",
        kind: "none",
        title: "No parcels loaded",
        description:
          "Parcel ingest is a jurisdiction-level pipeline job — not executable per-town. Trigger it for the parent jurisdiction first.",
        primary: false,
        blocked_reason: "Parcels must be loaded at jurisdiction grain.",
      });
      break;

    case "M1": {
      steps.push({
        key: "discover",
        kind: "discover",
        title: `Discover zoning sources for ${muni}`,
        description:
          "Runs zoning_discovery against the parent county scoped to this town. Persists candidate rows into zoning_sources for operator review.",
        primary: true,
      });
      break;
    }

    case "M2": {
      const pending = snapshot.source_count_pending;
      steps.push({
        key: "review_pending",
        kind: "review_pending",
        title: `Review ${pending} pending source${pending === 1 ? "" : "s"}`,
        description:
          "Opens the source-review screen filtered to this town. Use V/R/N shortcuts in the drawer.",
        primary: true,
        href: `/admin/sources/${jId}?status=pending&municipality=${encodeURIComponent(muni)}`,
      });
      break;
    }

    case "M3": {
      const verifiedIds = townSources
        .filter((s) => s.validation_status === "verified")
        .map((s) => s.id);
      steps.push({
        key: "ingest_verified",
        kind: "ingest_verified",
        title: `Ingest ${verifiedIds.length} verified source${verifiedIds.length === 1 ? "" : "s"}`,
        description:
          "Downloads each verified source, ingests into zoning_districts, and runs the parcel spatial-join. Idempotent (ON CONFLICT on overlay rows).",
        primary: true,
        source_ids: verifiedIds,
        blocked_reason:
          verifiedIds.length === 0
            ? "No verified sources to ingest — verify some first."
            : undefined,
      });
      break;
    }

    case "M4":
    case "M5": {
      steps.push({
        key: "rerun_jurisdiction_action",
        kind: "none",
        title: "Closing the coverage gap is a jurisdiction-grain operation",
        description:
          "Re-ingestion / backfill runs at the parent-jurisdiction level. Use the coverage drilldown for refresh; use the queue's Ingest-ready tab if a verified source for this town can fill the gap.",
        primary: false,
        href: `/admin/coverage/${jId}`,
      });
      break;
    }

    case "M6":
      steps.push({
        key: "operational",
        kind: "none",
        title: "Operational",
        description: "Nothing to execute. Monitor via the coverage dashboard.",
        primary: false,
      });
      break;
  }

  if (hasStaleRows) {
    steps.push({
      key: "rescore_stale",
      kind: "rescore_stale",
      title: "Rescore stale rows in parent jurisdiction",
      description:
        "Stale rows (missing bbox_overlap_*) live at the jurisdiction grain. Opens the rescore workspace — operator must trigger from there.",
      primary: false,
      href: `/admin/stale/${jId}`,
    });
  }

  // Universal step — always available, always last in the list.
  steps.push({
    key: "refresh_audit",
    kind: "refresh_audit",
    title: "Refresh coverage audit for parent jurisdiction",
    description:
      "Re-runs the coverage audit so the town's parcels_with_zoning and overlay counts reflect the latest state. ~3s.",
    primary: false,
  });

  return steps;
}

/** Tiny summary of "what executable level is this town at?". Useful for
 *  the index page's inline runbook badge — at-a-glance status without
 *  rendering the whole panel. */
export function runbookExecutability(steps: RunbookStep[]): {
  has_primary: boolean;
  primary_kind: RunbookStepKind | null;
  blocked_count: number;
} {
  let has_primary = false;
  let primary_kind: RunbookStepKind | null = null;
  let blocked_count = 0;
  for (const s of steps) {
    if (s.blocked_reason) blocked_count += 1;
    if (s.primary && !has_primary) {
      has_primary = true;
      primary_kind = s.kind;
    }
  }
  return { has_primary, primary_kind, blocked_count };
}
