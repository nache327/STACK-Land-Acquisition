import type { CoverageJurisdiction } from "@/lib/schemas";

export type CoverageTier = "T0" | "T1" | "T2" | "T3" | "T4" | "T5" | "T6";

export interface TierMeta {
  tier: CoverageTier;
  label: string;
  /** Operator-facing short description of where this jurisdiction is in the
   *  discovery → verified → ingested → overlays → operational pipeline. */
  stage: string;
}

export const TIERS: Record<CoverageTier, { label: string; stage: string }> = {
  T0: { label: "Empty", stage: "No parcels loaded" },
  T1: { label: "Discovery", stage: "Parcels loaded · no sources yet" },
  T2: { label: "Review", stage: "Sources discovered · awaiting verify" },
  T3: { label: "Ingest", stage: "Sources verified · awaiting overlay ingest" },
  T4: { label: "Overlay gap", stage: "Overlays ingested · zoning codes incomplete" },
  T5: { label: "Matrix gap", stage: "Codes mapped · matrix/classification incomplete" },
  T6: { label: "Operational", stage: "All systems green" },
};

const ZONING_COVERAGE_OK = 80;
const SELF_STORAGE_OK = 95;

/** Derive an operator-facing tier from a coverage snapshot row.
 *  Pure function — no I/O, no side effects. */
export function deriveTier(row: CoverageJurisdiction): CoverageTier {
  if (row.operational_readiness === "operational") return "T6";

  const parcels = row.parcel_count ?? 0;
  if (parcels === 0) return "T0";

  const total = row.source_count_total ?? 0;
  if (total === 0) return "T1";

  const verified = row.source_count_verified ?? 0;
  if (verified === 0) return "T2";

  const districts = row.zoning_district_count ?? 0;
  if (districts === 0) return "T3";

  const zoningPct = row.parcel_zoning_code_coverage_pct ?? 0;
  if (zoningPct < ZONING_COVERAGE_OK) return "T4";

  const ssPct = row.self_storage_classified_parcel_pct ?? 0;
  if (ssPct < SELF_STORAGE_OK) return "T5";

  return "T5";
}

export function tierLabel(tier: CoverageTier): string {
  return `${tier} ${TIERS[tier].label}`;
}

export interface RecommendedAction {
  tier: CoverageTier;
  text: string;
  /** Where the operator should click. May be a /admin/sources/{id}?... URL. */
  href?: string;
  /** Whether the operator should act now (true) vs. monitor (false). */
  actionable: boolean;
}

export function deriveRecommendedAction(
  row: CoverageJurisdiction,
): RecommendedAction {
  const tier = deriveTier(row);
  const id = row.jurisdiction_id;
  const pending = row.source_count_pending ?? 0;
  const verified = row.source_count_verified ?? 0;
  const zoningPct = row.parcel_zoning_code_coverage_pct ?? 0;
  const ssPct = row.self_storage_classified_parcel_pct ?? 0;

  switch (tier) {
    case "T0":
      return {
        tier,
        text: "Run parcel ingest",
        actionable: true,
      };
    case "T1":
      return {
        tier,
        text: "Run zoning discovery",
        actionable: true,
      };
    case "T2":
      return {
        tier,
        text: `Review ${pending} pending source${pending === 1 ? "" : "s"}`,
        href: `/admin/sources/${id}?status=pending`,
        actionable: pending > 0,
      };
    case "T3":
      return {
        tier,
        text: `Ingest ${verified} verified source${verified === 1 ? "" : "s"}`,
        href: `/admin/sources/${id}?status=verified`,
        actionable: verified > 0,
      };
    case "T4":
      return {
        tier,
        text: `Backfill zoning codes (${Math.round(zoningPct)}% covered)`,
        actionable: true,
      };
    case "T5":
      return {
        tier,
        text: `Complete zone-use matrix (${Math.round(ssPct)}% classified)`,
        actionable: true,
      };
    case "T6":
      return { tier, text: "Operational — monitor only", actionable: false };
  }
}

const GAP_LABELS: Record<string, string> = {
  no_parcels: "No parcels loaded",
  no_parcel_geometry: "Parcels missing geometry",
  no_parcel_zoning_codes: "Parcels missing zoning_code",
  no_zone_use_matrix: "Zone-use matrix empty",
  no_matrix_matches_for_parcel_zones: "Matrix doesn't match parcel zones",
  low_matrix_match_pct: "Matrix match rate below 90%",
  high_unclear_self_storage_share: "Self-storage classification < 95%",
  missing_parcel_zone_class_column: "Schema: parcels.zone_class column missing",
  missing_zoning_districts_table: "Schema: zoning_districts table missing",
  no_zoning_polygons: "No zoning polygons ingested",
  missing_jurisdiction_bbox_column: "Schema: jurisdictions.bbox column missing",
  missing_bbox: "Jurisdiction bbox not set",
  missing_overlays_table: "Schema: zoning_overlays table missing",
  coverage_level_overstates_readiness: "coverage_level says 'full' but gaps remain",
};

export function labelBlockingGap(gap: string): string {
  return GAP_LABELS[gap] ?? gap.replace(/_/g, " ");
}

export function tierTone(
  tier: CoverageTier,
): "rose" | "amber" | "sky" | "indigo" | "emerald" | "slate" {
  switch (tier) {
    case "T0":
      return "slate";
    case "T1":
      return "rose";
    case "T2":
      return "amber";
    case "T3":
      return "sky";
    case "T4":
      return "indigo";
    case "T5":
      return "indigo";
    case "T6":
      return "emerald";
  }
}
