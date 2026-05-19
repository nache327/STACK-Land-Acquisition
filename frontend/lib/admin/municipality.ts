import type { ZoningSource } from "@/lib/schemas";

export interface MunicipalityBreakdownRow {
  parcels: number;
  parcels_with_zoning: number;
  zoning_overlays: number;
}

export type MunicipalityBreakdownDict = Record<string, MunicipalityBreakdownRow>;

const SPATIAL_BAD_KEYS = new Set([
  "wrong_state",
  "wrong_county",
  "bbox_overlap_disjoint",
  "out_of_state",
]);

/** Parse the snapshot's municipality_breakdown JSONB into a typed dict.
 *  The backend stores `null` or `{}` when no per-town breakdown is available;
 *  return an empty dict in that case so callers can just iterate. */
export function parseMunicipalityBreakdown(
  raw: unknown,
): MunicipalityBreakdownDict {
  if (!raw || typeof raw !== "object") return {};
  const out: MunicipalityBreakdownDict = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!v || typeof v !== "object") continue;
    const row = v as Record<string, unknown>;
    out[k] = {
      parcels: Number(row.parcels ?? 0) || 0,
      parcels_with_zoning: Number(row.parcels_with_zoning ?? 0) || 0,
      zoning_overlays: Number(row.zoning_overlays ?? 0) || 0,
    };
  }
  return out;
}

/** Did the discovery scorer flag this source for a spatial/CRS mismatch?
 *  Reads only the persisted `confidence_breakdown` JSONB — no live probe. */
export function sourceIsSpatiallyBlocked(src: ZoningSource): boolean {
  const b = src.confidence_breakdown;
  if (!b) return false;
  for (const k of Object.keys(b)) {
    if (SPATIAL_BAD_KEYS.has(k) && b[k] < 0) return true;
  }
  return false;
}

export interface MunicipalityRollup {
  name: string;
  /** Coverage from the snapshot's municipality_breakdown. May be all-zero if
   *  the town has sources but no parcels in this jurisdiction yet. */
  parcels: number;
  parcels_with_zoning: number;
  zoning_overlays: number;
  source_total: number;
  source_pending: number;
  source_verified: number;
  source_rejected: number;
  spatial_blocked: boolean;
  status: MunicipalityStatus;
}

export type MunicipalityStatus =
  | "ready"
  | "ingest_ready"
  | "review_backlog"
  | "spatially_blocked"
  | "needs_discovery"
  | "no_parcels";

export interface MunicipalityRollupArgs {
  breakdown: MunicipalityBreakdownDict;
  sources: ZoningSource[];
}

export function buildMunicipalityRollup({
  breakdown,
  sources,
}: MunicipalityRollupArgs): MunicipalityRollup[] {
  const grouped = new Map<string, ZoningSource[]>();
  for (const s of sources) {
    const key = s.municipality_name ?? "(unknown)";
    const list = grouped.get(key) ?? [];
    list.push(s);
    grouped.set(key, list);
  }

  const allNames = new Set<string>(Object.keys(breakdown));
  grouped.forEach((_value, key) => allNames.add(key));

  const rows: MunicipalityRollup[] = [];
  Array.from(allNames).forEach((name) => {
    const cov = breakdown[name] ?? {
      parcels: 0,
      parcels_with_zoning: 0,
      zoning_overlays: 0,
    };
    const list = grouped.get(name) ?? [];
    const verified = list.filter((s) => s.validation_status === "verified");
    const pending = list.filter(
      (s) =>
        s.validation_status === "pending" ||
        s.validation_status === "needs_review",
    );
    const rejected = list.filter((s) => s.validation_status === "rejected");
    const blockedSources = list.filter(sourceIsSpatiallyBlocked);

    rows.push({
      name,
      parcels: cov.parcels,
      parcels_with_zoning: cov.parcels_with_zoning,
      zoning_overlays: cov.zoning_overlays,
      source_total: list.length,
      source_pending: pending.length,
      source_verified: verified.length,
      source_rejected: rejected.length,
      spatial_blocked: blockedSources.length > 0,
      status: classifyMunicipality({
        parcels: cov.parcels,
        parcels_with_zoning: cov.parcels_with_zoning,
        zoning_overlays: cov.zoning_overlays,
        pending: pending.length,
        verified: verified.length,
        spatial_blocked: blockedSources.length > 0,
      }),
    });
  });

  rows.sort((a, b) => statusPriority(a.status) - statusPriority(b.status)
    || b.parcels - a.parcels
    || a.name.localeCompare(b.name),
  );
  return rows;
}

interface ClassifyArgs {
  parcels: number;
  parcels_with_zoning: number;
  zoning_overlays: number;
  pending: number;
  verified: number;
  spatial_blocked: boolean;
}

function classifyMunicipality(a: ClassifyArgs): MunicipalityStatus {
  if (a.parcels > 0 && a.zoning_overlays > 0 && a.parcels_with_zoning > 0) {
    return "ready";
  }
  if (a.verified > 0 && a.zoning_overlays === 0) return "ingest_ready";
  if (a.spatial_blocked && a.zoning_overlays === 0) return "spatially_blocked";
  if (a.pending > 0) return "review_backlog";
  if (a.parcels === 0 && a.verified === 0 && a.pending === 0) {
    return "no_parcels";
  }
  return "needs_discovery";
}

/** Lower number = higher operator priority (sorted first). */
function statusPriority(s: MunicipalityStatus): number {
  switch (s) {
    case "spatially_blocked":
      return 0; // operator must act — broken ingest
    case "review_backlog":
      return 1; // queue waiting
    case "ingest_ready":
      return 2; // one-click win
    case "needs_discovery":
      return 3;
    case "ready":
      return 4;
    case "no_parcels":
      return 5;
  }
}

export const STATUS_LABEL: Record<MunicipalityStatus, string> = {
  ready: "Ready",
  ingest_ready: "Ingest-ready",
  review_backlog: "Review backlog",
  spatially_blocked: "Spatially blocked",
  needs_discovery: "Needs discovery",
  no_parcels: "No parcels",
};
