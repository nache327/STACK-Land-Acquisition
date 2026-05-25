import {
  parseMunicipalityBreakdown,
  sourceIsSpatiallyBlocked,
} from "./municipality";
import type { CoverageJurisdiction, QueueSource } from "@/lib/schemas";

/** Municipality-grain readiness tier. Mirrors the jurisdiction T0-T6 model
 *  from PR2 but operates on a single town inside a parent jurisdiction.
 *
 *    M0  No parcels in this town yet
 *    M1  Parcels loaded, no sources discovered for this town
 *    M2  Sources discovered, none verified — review backlog
 *    M3  Verified sources, but no overlays ingested (one click from value)
 *    M4  Overlays exist, but coverage is low (< 50% parcels zoned)
 *    M5  Mostly zoned (50-99%) — small gap remaining
 *    M6  Fully zoned — operational at this granularity
 */
export type MunicipalityTier =
  | "M0"
  | "M1"
  | "M2"
  | "M3"
  | "M4"
  | "M5"
  | "M6";

const FULL_THRESHOLD = 0.99;
const MOSTLY_THRESHOLD = 0.5;

export interface MunicipalitySnapshot {
  jurisdiction_id: string;
  jurisdiction_name: string;
  state: string | null;
  municipality: string;
  parcels: number;
  parcels_with_zoning: number;
  zoning_overlays: number;
  source_count_pending: number;
  source_count_verified: number;
  source_count_rejected: number;
  source_count_needs_review: number;
  spatial_blocked_count: number;
}

export function deriveMunicipalityTier(m: MunicipalitySnapshot): MunicipalityTier {
  if (m.parcels === 0) return "M0";

  // If overlays exist, the town is past the discovery/ingest stages even
  // when no source row exists (e.g. bulk-imported via regrid). Coverage
  // ratio determines the M4/M5/M6 bucket.
  if (m.zoning_overlays > 0) {
    const zoningRatio = m.parcels_with_zoning / m.parcels;
    if (zoningRatio >= FULL_THRESHOLD) return "M6";
    if (zoningRatio >= MOSTLY_THRESHOLD) return "M5";
    return "M4";
  }

  // No overlays yet — read the source state.
  const totalSources =
    m.source_count_pending
    + m.source_count_verified
    + m.source_count_rejected
    + m.source_count_needs_review;
  if (totalSources === 0) return "M1";
  if (m.source_count_verified === 0) return "M2";
  return "M3";
}

export const MUNICIPALITY_TIERS: Record<
  MunicipalityTier,
  { label: string; stage: string }
> = {
  M0: { label: "Empty", stage: "No parcels in this town" },
  M1: { label: "Discovery", stage: "Parcels loaded · no sources yet" },
  M2: { label: "Review", stage: "Sources discovered · awaiting verify" },
  M3: { label: "Ingest", stage: "Verified · awaiting overlay ingest" },
  M4: { label: "Gap", stage: "Overlays loaded · most parcels still unzoned" },
  M5: { label: "Closing", stage: "Mostly zoned · small gap remaining" },
  M6: { label: "Operational", stage: "Fully zoned at this granularity" },
};

const URGENCY_RANK: Record<MunicipalityTier, number> = {
  M3: 0, // one-click win
  M2: 1, // review backlog
  M4: 2, // ingest broke or wrong layer
  M5: 3, // tiny gap
  M1: 4, // need discovery
  M0: 5, // no parcels
  M6: 6, // done
};

export function tierUrgency(t: MunicipalityTier): number {
  return URGENCY_RANK[t];
}

/** Operator-facing tone for the pill. Matches the Iter3 ConfidenceTierPill
 *  palette so the surface stays visually consistent. */
export function tierTone(
  t: MunicipalityTier,
): "rose" | "amber" | "sky" | "indigo" | "emerald" | "slate" {
  switch (t) {
    case "M0":
      return "slate";
    case "M1":
      return "rose";
    case "M2":
      return "amber";
    case "M3":
      return "sky";
    case "M4":
      return "indigo";
    case "M5":
      return "indigo";
    case "M6":
      return "emerald";
  }
}

// ───────── Blockers ─────────────────────────────────────────────────────

export interface MunicipalityBlocker {
  key: string;
  label: string;
  severity: "info" | "warn" | "block";
  detail?: string;
}

export function deriveMunicipalityBlockers(
  m: MunicipalitySnapshot,
): MunicipalityBlocker[] {
  const out: MunicipalityBlocker[] = [];
  if (m.parcels === 0) {
    out.push({
      key: "no_parcels",
      label: "No parcels loaded",
      severity: "info",
    });
    return out;
  }
  if (
    m.source_count_pending === 0
    && m.source_count_verified === 0
    && m.source_count_rejected === 0
    && m.source_count_needs_review === 0
  ) {
    out.push({
      key: "no_sources",
      label: "No zoning sources discovered",
      severity: "block",
    });
  }
  if (m.spatial_blocked_count > 0) {
    out.push({
      key: "spatial_blocked",
      label: `${m.spatial_blocked_count} source${m.spatial_blocked_count === 1 ? "" : "s"} flagged spatial mismatch`,
      severity: "block",
    });
  }
  if (m.source_count_pending > 0 && m.source_count_verified === 0) {
    out.push({
      key: "pending_review",
      label: `${m.source_count_pending} pending review`,
      severity: "warn",
    });
  }
  if (m.source_count_verified > 0 && m.zoning_overlays === 0) {
    out.push({
      key: "ingest_pending",
      label: `${m.source_count_verified} verified · not ingested`,
      severity: "warn",
    });
  }
  if (m.zoning_overlays > 0 && m.parcels > 0) {
    const ratio = m.parcels_with_zoning / m.parcels;
    if (ratio < FULL_THRESHOLD) {
      const unzoned = m.parcels - m.parcels_with_zoning;
      out.push({
        key: "coverage_gap",
        label: `${unzoned.toLocaleString()} parcels still unzoned (${Math.round(ratio * 100)}% coverage)`,
        severity: ratio < MOSTLY_THRESHOLD ? "warn" : "info",
      });
    }
  }
  return out;
}

// ───────── Next action ─────────────────────────────────────────────────

export interface MunicipalityNextAction {
  tier: MunicipalityTier;
  text: string;
  /** Deep link the operator should follow. Always opens an existing
   *  surface — no new pages are introduced here. */
  href?: string;
  actionable: boolean;
}

export function recommendMunicipalityAction(
  m: MunicipalitySnapshot,
): MunicipalityNextAction {
  const tier = deriveMunicipalityTier(m);
  const jId = m.jurisdiction_id;
  const muni = m.municipality;
  switch (tier) {
    case "M0":
      return { tier, text: "Run parcel ingest", actionable: true };
    case "M1":
      return {
        tier,
        text: "Run zoning discovery for this town",
        actionable: true,
      };
    case "M2": {
      const count = m.source_count_pending;
      return {
        tier,
        text: `Review ${count} pending source${count === 1 ? "" : "s"}`,
        href: `/admin/sources/${jId}?status=pending&municipality=${encodeURIComponent(muni)}`,
        actionable: count > 0,
      };
    }
    case "M3": {
      const count = m.source_count_verified;
      return {
        tier,
        text: `Ingest ${count} verified source${count === 1 ? "" : "s"}`,
        href: `/admin/sources/${jId}?status=verified&municipality=${encodeURIComponent(muni)}`,
        actionable: count > 0,
      };
    }
    case "M4": {
      const pct = Math.round((m.parcels_with_zoning / m.parcels) * 100);
      return {
        tier,
        text: `Backfill zoning codes (${pct}% covered)`,
        href: `/admin/coverage/${jId}`,
        actionable: true,
      };
    }
    case "M5": {
      const unzoned = m.parcels - m.parcels_with_zoning;
      return {
        tier,
        text: `Close ${unzoned.toLocaleString()}-parcel gap`,
        href: `/admin/coverage/${jId}`,
        actionable: true,
      };
    }
    case "M6":
      return {
        tier,
        text: "Operational — monitor only",
        actionable: false,
      };
  }
}

// ───────── Cross-jurisdiction rollup ───────────────────────────────────

interface BuildArgs {
  jurisdictions: CoverageJurisdiction[];
  sources: QueueSource[];
}

/** Flatten every jurisdiction × municipality combo into MunicipalitySnapshot
 *  rows. Sources are grouped by `(jurisdiction_id, municipality_name)`. */
export function buildCrossJurisdictionMunicipalityRollup({
  jurisdictions,
  sources,
}: BuildArgs): MunicipalitySnapshot[] {
  // Group sources by composite key for O(1) lookup per (jur, town).
  const srcByKey = new Map<string, QueueSource[]>();
  for (const s of sources) {
    const muni = s.municipality_name;
    if (!muni) continue;
    const key = `${s.jurisdiction_id}::${muni}`;
    const list = srcByKey.get(key) ?? [];
    list.push(s);
    srcByKey.set(key, list);
  }

  const out: MunicipalitySnapshot[] = [];
  const seenKeys = new Set<string>();

  // First pass: every town in any jurisdiction's coverage breakdown.
  for (const j of jurisdictions) {
    const breakdown = parseMunicipalityBreakdown(j.municipality_breakdown);
    for (const [name, row] of Object.entries(breakdown)) {
      const key = `${j.jurisdiction_id}::${name}`;
      seenKeys.add(key);
      const list = srcByKey.get(key) ?? [];
      out.push(snapshotFor(j, name, row, list));
    }
  }

  // Second pass: sources whose municipality_name isn't in any breakdown.
  // These still belong on the operator's radar — typically a discovery
  // ran for a town that has no parcels loaded yet, or for a spelling
  // variant. Surface them as M1 with parcels=0 so the operator can act.
  srcByKey.forEach((list, key) => {
    if (seenKeys.has(key)) return;
    const [jurId, name] = key.split("::");
    const j = jurisdictions.find((x) => x.jurisdiction_id === jurId);
    if (!j) return;
    out.push(
      snapshotFor(
        j,
        name,
        { parcels: 0, parcels_with_zoning: 0, zoning_overlays: 0 },
        list,
      ),
    );
  });

  out.sort(
    (a, b) =>
      tierUrgency(deriveMunicipalityTier(a))
        - tierUrgency(deriveMunicipalityTier(b))
      || (b.parcels - b.parcels_with_zoning)
        - (a.parcels - a.parcels_with_zoning)
      || a.municipality.localeCompare(b.municipality),
  );
  return out;
}

function snapshotFor(
  j: CoverageJurisdiction,
  municipality: string,
  row: { parcels: number; parcels_with_zoning: number; zoning_overlays: number },
  sources: QueueSource[],
): MunicipalitySnapshot {
  let pending = 0;
  let verified = 0;
  let rejected = 0;
  let needsReview = 0;
  let spatialBlocked = 0;
  for (const s of sources) {
    switch (s.validation_status) {
      case "pending":
        pending += 1;
        break;
      case "verified":
        verified += 1;
        break;
      case "rejected":
        rejected += 1;
        break;
      case "needs_review":
        needsReview += 1;
        break;
    }
    if (sourceIsSpatiallyBlocked(s)) spatialBlocked += 1;
  }
  return {
    jurisdiction_id: j.jurisdiction_id,
    jurisdiction_name: j.jurisdiction_name,
    state: j.state,
    municipality,
    parcels: row.parcels,
    parcels_with_zoning: row.parcels_with_zoning,
    zoning_overlays: row.zoning_overlays,
    source_count_pending: pending,
    source_count_verified: verified,
    source_count_rejected: rejected,
    source_count_needs_review: needsReview,
    spatial_blocked_count: spatialBlocked,
  };
}

// ───────── Health signal ───────────────────────────────────────────────

export type MunicipalityHealth = "healthy" | "degraded" | "unhealthy";

export function deriveMunicipalityHealth(
  m: MunicipalitySnapshot,
): MunicipalityHealth {
  if (m.spatial_blocked_count > 0) return "unhealthy";
  if (m.source_count_pending > 0 && m.source_count_verified === 0) {
    return "degraded";
  }
  if (m.source_count_rejected > 0 && m.source_count_verified === 0) {
    return "degraded";
  }
  if (m.parcels > 0 && m.zoning_overlays === 0) return "degraded";
  return "healthy";
}
