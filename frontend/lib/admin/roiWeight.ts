import {
  parseMunicipalityBreakdown,
  type MunicipalityBreakdownDict,
} from "./municipality";
import type { CoverageJurisdiction, QueueSource } from "@/lib/schemas";

/** Per-municipality parcel weight cap. A 100k-parcel city shouldn't
 *  dwarf a 5k-parcel city by 20×; the log compression already does the
 *  heavy lifting, this is belt-and-braces. */
const ROI_CAP_LOG = 12;

/** Map a row -> a numeric ROI weight in [0, 1].
 *
 *  ROI is "how many unzoned parcels does verifying / ingesting this row
 *  unlock". We can compute this purely from coverage data:
 *    weight = log(unzoned_parcels) / cap, clamped to [0, 1].
 *
 *  Rows whose municipality isn't in the breakdown (or has 0 parcels)
 *  return 0. Operator sorting with `score * (1 + 0.5 * roi_weight)`
 *  will lift big-town rows but not eclipse confidence ranking.
 */
export function roiWeight(
  source: QueueSource,
  byJurisdiction: Map<string, MunicipalityBreakdownDict>,
): number {
  const breakdown = byJurisdiction.get(source.jurisdiction_id);
  if (!breakdown) return 0;
  const muni = source.municipality_name;
  if (!muni) return 0;
  const row = breakdown[muni];
  if (!row || row.parcels <= 0) return 0;
  const unzoned = Math.max(0, row.parcels - row.parcels_with_zoning);
  if (unzoned === 0) return 0;
  const w = Math.log(unzoned + 1) / ROI_CAP_LOG;
  return Math.min(1, Math.max(0, w));
}

/** Cache-friendly index of `municipality_breakdown` JSONBs keyed by
 *  jurisdiction id. Build this once per render from the coverage payload
 *  and pass it to every `roiWeight()` call. */
export function buildMunicipalityIndex(
  jurisdictions: CoverageJurisdiction[],
): Map<string, MunicipalityBreakdownDict> {
  const m = new Map<string, MunicipalityBreakdownDict>();
  for (const j of jurisdictions) {
    m.set(j.jurisdiction_id, parseMunicipalityBreakdown(j.municipality_breakdown));
  }
  return m;
}

export type QueueSortMode = "confidence" | "roi" | "confidence_x_roi";

/** Operator-facing sort. Stable for equal keys (preserves backend order). */
export function sortQueueByMode(
  rows: QueueSource[],
  mode: QueueSortMode,
  index: Map<string, MunicipalityBreakdownDict>,
): QueueSource[] {
  if (mode === "confidence") {
    // Backend already returns confidence-sorted — no work.
    return rows;
  }
  const withWeight = rows.map((r, i) => ({
    r,
    i,
    w: roiWeight(r, index),
    s: r.confidence_score ?? 0,
  }));
  if (mode === "roi") {
    withWeight.sort((a, b) => b.w - a.w || b.s - a.s || a.i - b.i);
  } else {
    // confidence_x_roi — multiplicative; weight=0 still leaves score in play
    withWeight.sort((a, b) => {
      const aKey = a.s * (1 + 0.5 * a.w);
      const bKey = b.s * (1 + 0.5 * b.w);
      return bKey - aKey || a.i - b.i;
    });
  }
  return withWeight.map((x) => x.r);
}

export interface RoiTag {
  unzoned_parcels: number;
  weight: number;
}

/** Public lookup for showing a "5,200 unzoned" badge next to a row. */
export function roiTagFor(
  source: QueueSource,
  byJurisdiction: Map<string, MunicipalityBreakdownDict>,
): RoiTag | null {
  const breakdown = byJurisdiction.get(source.jurisdiction_id);
  if (!breakdown) return null;
  const muni = source.municipality_name;
  if (!muni) return null;
  const row = breakdown[muni];
  if (!row || row.parcels <= 0) return null;
  const unzoned = Math.max(0, row.parcels - row.parcels_with_zoning);
  if (unzoned === 0) return null;
  return { unzoned_parcels: unzoned, weight: roiWeight(source, byJurisdiction) };
}
