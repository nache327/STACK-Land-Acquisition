import {
  parseMunicipalityBreakdown,
  type MunicipalityBreakdownRow,
} from "./municipality";
import type { CoverageJurisdiction } from "@/lib/schemas";

export interface HighRoiRow extends MunicipalityBreakdownRow {
  /** "<Town>, <state>" — towns can collide across states so we key by both. */
  key: string;
  municipality: string;
  jurisdiction_id: string;
  jurisdiction_name: string;
  state: string | null;
  /** parcels that *aren't yet* zoned — the slice the operator can unlock by
   *  acting on this jurisdiction. */
  unzoned_parcels: number;
  /** % of parcels in the municipality that have zoning. */
  zoning_pct: number;
  /** Number of pending zoning_sources owned by this jurisdiction. We can
   *  only roll this up to jurisdiction level — the sources are tagged with
   *  municipality_name but the coverage snapshot doesn't expose that join. */
  jurisdiction_pending: number;
}

interface ComputeArgs {
  jurisdictions: CoverageJurisdiction[];
  /** Optional cap — defaults to top 30 for the queue UI. */
  limit?: number;
}

/** Compute the cross-jurisdiction high-ROI municipality queue. Pure function.
 *
 *  Strategy: for every jurisdiction that *has* a municipality_breakdown
 *  payload, project each town into a flat row carrying its parent
 *  jurisdiction's pending-source count. Rank by `unzoned_parcels` desc —
 *  acting here unlocks the most coverage per click.
 *
 *  Towns whose `parcels_with_zoning == parcels` and `parcels > 0` are
 *  already operational and dropped from the queue (no ROI left to capture).
 */
export function computeHighRoiQueue({
  jurisdictions,
  limit = 30,
}: ComputeArgs): HighRoiRow[] {
  const rows: HighRoiRow[] = [];
  for (const j of jurisdictions) {
    const breakdown = parseMunicipalityBreakdown(j.municipality_breakdown);
    for (const [name, row] of Object.entries(breakdown)) {
      if (row.parcels === 0) continue;
      const unzoned = row.parcels - row.parcels_with_zoning;
      if (unzoned <= 0) continue;
      const zoningPct = (row.parcels_with_zoning / row.parcels) * 100;
      rows.push({
        key: `${name}::${j.state ?? "?"}::${j.jurisdiction_id}`,
        municipality: name,
        jurisdiction_id: j.jurisdiction_id,
        jurisdiction_name: j.jurisdiction_name,
        state: j.state,
        parcels: row.parcels,
        parcels_with_zoning: row.parcels_with_zoning,
        zoning_overlays: row.zoning_overlays,
        unzoned_parcels: unzoned,
        zoning_pct: zoningPct,
        jurisdiction_pending: j.source_count_pending ?? 0,
      });
    }
  }
  rows.sort((a, b) => b.unzoned_parcels - a.unzoned_parcels);
  return rows.slice(0, limit);
}

/** "Ingest-ready" jurisdictions: have verified sources, but no overlays yet
 *  (zoning_district_count == 0). The single-highest-leverage queue. */
export function computeIngestReady(
  jurisdictions: CoverageJurisdiction[],
): CoverageJurisdiction[] {
  return jurisdictions
    .filter(
      (j) =>
        (j.source_count_verified ?? 0) > 0
        && (j.zoning_district_count ?? 0) === 0,
    )
    .sort((a, b) =>
      (b.source_count_verified ?? 0) - (a.source_count_verified ?? 0)
      || a.jurisdiction_name.localeCompare(b.jurisdiction_name),
    );
}
