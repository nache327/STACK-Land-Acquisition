import type { PrecomputedParcelData } from "@/lib/isochrone-precompute";

// ── Types ──────────────────────────────────────────────────────────────────────

export type DriveTime = 2 | 5 | 10 | 15;

export interface BuyBoxFilter {
  driveTimeMinutes: DriveTime;
  minPopulation: number | null;
  minMedianHHI: number | null;
  minMedianHomeValue: number | null;
  minHnwHouseholds: number | null;
  minAADT: number | null;
  // "Wealth density" sliders — count of residential parcels with total
  // assessed value above the threshold inside the drive-time ring. Sourced
  // from per-state assessor data via POST /api/parcels/value-density and
  // cached on the backend, so a filter being null means the user hasn't
  // enabled this dimension (zero backend cost).
  minHomesOver1M: number | null;
  minHomesOver2M: number | null;
  minHomesOver5M: number | null;
  matchLogic: "AND" | "OR";
  // Layer 4: For-Sale Listings. Both optional — null/undefined means
  // the listings dimension is inactive for this filter.
  requireListed?: boolean;
  listingScoreBoost?: number;
}

export type EvaluationStatus = "match" | "borderline" | "fail" | "computing";

export interface EvaluationResult {
  status: EvaluationStatus;
  failedConditions: string[];
  borderlineConditions: string[];
}

export interface SavedPreset {
  id: string;
  name: string;
  filter: BuyBoxFilter;
  isDefault?: boolean;
  dailyEmailEnabled?: boolean;
  dailyEmailTopN?: number;
  lastEmailSentAt?: string | null;
}

// ── Defaults ───────────────────────────────────────────────────────────────────

export const DEFAULT_FILTER: BuyBoxFilter = {
  driveTimeMinutes: 10,
  minPopulation: null,
  minMedianHHI: null,
  minMedianHomeValue: null,
  minHnwHouseholds: null,
  minAADT: null,
  minHomesOver1M: null,
  minHomesOver2M: null,
  minHomesOver5M: null,
  matchLogic: "AND",
  requireListed: false,
  listingScoreBoost: 0,
};

// Legacy localStorage key — kept solely for the one-shot migration helper.
export const LEGACY_PRESET_STORAGE_KEY = "parcellogic_presets_v1";
const MIGRATION_FLAG_KEY = "parcellogic_presets_migrated_v1";

// ── Pure evaluation ────────────────────────────────────────────────────────────

export function isFilterActive(filter: BuyBoxFilter): boolean {
  return (
    filter.minPopulation != null ||
    filter.minMedianHHI != null ||
    filter.minMedianHomeValue != null ||
    filter.minHnwHouseholds != null ||
    filter.minAADT != null ||
    filter.minHomesOver1M != null ||
    filter.minHomesOver2M != null ||
    filter.minHomesOver5M != null
  );
}

/** True when ANY of the three wealth-density sliders is set. Drives the
 * lazy backend fetch — precompute only hits /api/parcels/value-density
 * when this returns true. */
export function isHomeDensityActive(filter: BuyBoxFilter): boolean {
  return (
    filter.minHomesOver1M != null ||
    filter.minHomesOver2M != null ||
    filter.minHomesOver5M != null
  );
}

export interface EvaluateOptions {
  /** When false, the three wealth-density sliders are bypassed in
   * evaluation regardless of their filter values. Set from the
   * dashboard's per-jurisdiction feature-flags fetch so cities whose
   * source publishes no assessed_value (UT UGRC) don't filter to "all
   * hidden" the moment a user drags Homes ≥$1M off 0. Defaults to true
   * (gate enabled) when omitted. */
  wealthDensityAvailable?: boolean;
}

export function evaluateParcel(
  parcelId: string,
  precomputedData: Map<string, PrecomputedParcelData>,
  filter: BuyBoxFilter,
  options?: EvaluateOptions,
): EvaluationResult {
  const data = precomputedData.get(parcelId);
  if (!data) return { status: "computing", failedConditions: [], borderlineConditions: [] };

  const metrics = data.rings[filter.driveTimeMinutes];

  type Condition = { label: string; actual: number; threshold: number };
  const active: Condition[] = [];

  if (filter.minPopulation != null)
    active.push({ label: "population", actual: metrics.totalPopulation, threshold: filter.minPopulation });
  if (filter.minMedianHHI != null)
    active.push({ label: "medianHHI", actual: metrics.weightedMedianHHI, threshold: filter.minMedianHHI });
  if (filter.minMedianHomeValue != null)
    active.push({ label: "homeValue", actual: metrics.weightedMedianHomeValue, threshold: filter.minMedianHomeValue });
  if (filter.minHnwHouseholds != null)
    active.push({ label: "hnwHouseholds", actual: metrics.hnwHouseholds, threshold: filter.minHnwHouseholds });
  // Wealth-density: each contributes only when its slider is enabled AND
  // the jurisdiction's source actually publishes assessed-value data.
  // Without the wealthDensityAvailable gate, a UT/UGRC city (assessed_value
  // null on every parcel) would treat the actual as 0, and any slider
  // above 0 would hide every parcel. The dashboard sets the flag from the
  // backend's GET /api/jurisdictions/{id}/feature-flags.
  const wealthGate = options?.wealthDensityAvailable !== false;
  if (wealthGate && filter.minHomesOver1M != null)
    active.push({ label: "homesOver1M", actual: metrics.homesOver1M ?? 0, threshold: filter.minHomesOver1M });
  if (wealthGate && filter.minHomesOver2M != null)
    active.push({ label: "homesOver2M", actual: metrics.homesOver2M ?? 0, threshold: filter.minHomesOver2M });
  if (wealthGate && filter.minHomesOver5M != null)
    active.push({ label: "homesOver5M", actual: metrics.homesOver5M ?? 0, threshold: filter.minHomesOver5M });

  if (active.length === 0) return { status: "match", failedConditions: [], borderlineConditions: [] };

  const failing = active.filter((c) => c.actual < c.threshold);
  const passing = active.filter((c) => c.actual >= c.threshold);

  if (filter.matchLogic === "OR") {
    return {
      status: passing.length > 0 ? "match" : "fail",
      failedConditions: failing.map((c) => c.label),
      borderlineConditions: [],
    };
  }

  if (failing.length === 0) {
    return { status: "match", failedConditions: [], borderlineConditions: [] };
  }

  const borderlineConditions = failing.filter((c) => c.actual >= c.threshold * 0.9);
  const hardFails = failing.filter((c) => c.actual < c.threshold * 0.9);

  return {
    status: hardFails.length === 0 ? "borderline" : "fail",
    failedConditions: failing.map((c) => c.label),
    borderlineConditions: borderlineConditions.map((c) => c.label),
  };
}

export function evaluateAll(
  parcelIds: string[],
  precomputedData: Map<string, PrecomputedParcelData>,
  filter: BuyBoxFilter,
  options?: EvaluateOptions,
): Map<string, EvaluationResult> {
  const out = new Map<string, EvaluationResult>();
  for (const id of parcelIds) {
    out.set(id, evaluateParcel(id, precomputedData, filter, options));
  }
  return out;
}

// ── Server-backed preset CRUD ──────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ServerFilterRow {
  id: string;
  organization_id: string;
  use_case_id: string;
  name: string;
  filter_json: BuyBoxFilter;
  is_default: boolean;
  daily_email_enabled: boolean;
  daily_email_top_n: number;
  last_email_sent_at: string | null;
  created_at: string;
  updated_at: string;
}

function rowToPreset(r: ServerFilterRow): SavedPreset {
  return {
    id: r.id,
    name: r.name,
    filter: r.filter_json,
    isDefault: r.is_default,
    dailyEmailEnabled: r.daily_email_enabled,
    dailyEmailTopN: r.daily_email_top_n,
    lastEmailSentAt: r.last_email_sent_at,
  };
}

async function apiJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function loadPresets(): Promise<SavedPreset[]> {
  const rows = await apiJSON<ServerFilterRow[]>("/api/buybox-filters");
  if (rows.length === 0) {
    await migrateLegacyPresets();
    const after = await apiJSON<ServerFilterRow[]>("/api/buybox-filters");
    return after.map(rowToPreset);
  }
  return rows.map(rowToPreset);
}

export async function savePreset(input: {
  name: string;
  filter: BuyBoxFilter;
  isDefault?: boolean;
  dailyEmailEnabled?: boolean;
  dailyEmailTopN?: number;
}): Promise<SavedPreset> {
  const row = await apiJSON<ServerFilterRow>("/api/buybox-filters", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      filter_json: input.filter,
      is_default: input.isDefault ?? false,
      daily_email_enabled: input.dailyEmailEnabled ?? false,
      daily_email_top_n: input.dailyEmailTopN ?? 10,
    }),
  });
  return rowToPreset(row);
}

export async function updatePreset(
  id: string,
  patch: Partial<{
    name: string;
    filter: BuyBoxFilter;
    isDefault: boolean;
    dailyEmailEnabled: boolean;
    dailyEmailTopN: number;
  }>,
): Promise<SavedPreset> {
  const body: Record<string, unknown> = {};
  if (patch.name !== undefined) body.name = patch.name;
  if (patch.filter !== undefined) body.filter_json = patch.filter;
  if (patch.isDefault !== undefined) body.is_default = patch.isDefault;
  if (patch.dailyEmailEnabled !== undefined) body.daily_email_enabled = patch.dailyEmailEnabled;
  if (patch.dailyEmailTopN !== undefined) body.daily_email_top_n = patch.dailyEmailTopN;

  const row = await apiJSON<ServerFilterRow>(`/api/buybox-filters/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return rowToPreset(row);
}

export async function deletePreset(id: string): Promise<void> {
  await apiJSON<void>(`/api/buybox-filters/${id}`, { method: "DELETE" });
}

export async function setDefaultPreset(id: string): Promise<SavedPreset> {
  return updatePreset(id, { isDefault: true });
}

export async function getDefaultPreset(): Promise<SavedPreset | null> {
  const all = await loadPresets();
  return all.find((p) => p.isDefault) ?? null;
}

// One-shot localStorage → server migration. Idempotent: skipped after the
// first successful run via MIGRATION_FLAG_KEY. Best-effort — failures are
// swallowed so a transient API outage doesn't strand the user.
async function migrateLegacyPresets(): Promise<void> {
  if (typeof window === "undefined") return;
  if (localStorage.getItem(MIGRATION_FLAG_KEY) === "1") return;

  try {
    const raw = localStorage.getItem(LEGACY_PRESET_STORAGE_KEY);
    if (!raw) {
      localStorage.setItem(MIGRATION_FLAG_KEY, "1");
      return;
    }
    const legacy = JSON.parse(raw) as Array<{
      name: string;
      filter: BuyBoxFilter;
      isDefault?: boolean;
    }>;
    for (const p of legacy) {
      try {
        await savePreset({
          name: p.name,
          filter: p.filter,
          isDefault: p.isDefault ?? false,
        });
      } catch {
        // duplicate name (409) etc — keep going
      }
    }
    localStorage.setItem(MIGRATION_FLAG_KEY, "1");
  } catch {
    // ignore
  }
}
