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
  matchLogic: "AND" | "OR";
}

export type EvaluationStatus = "match" | "borderline" | "fail" | "computing";

export interface EvaluationResult {
  status: EvaluationStatus;
  failedConditions: string[];
  borderlineConditions: string[];
}

export interface SavedPreset {
  name: string;
  filter: BuyBoxFilter;
  isDefault?: boolean;
}

// ── Defaults ───────────────────────────────────────────────────────────────────

export const DEFAULT_FILTER: BuyBoxFilter = {
  driveTimeMinutes: 10,
  minPopulation: 30_000,
  minMedianHHI: 150_000,
  minMedianHomeValue: null,
  minHnwHouseholds: null,
  minAADT: null,
  matchLogic: "AND",
};

export const PRESET_STORAGE_KEY = "parcellogic_presets_v1";

const DEFAULT_PRESETS: SavedPreset[] = [
  {
    name: "Keep — Tier A",
    filter: {
      driveTimeMinutes: 10,
      minPopulation: 30_000,
      minMedianHHI: 200_000,
      minMedianHomeValue: 1_000_000,
      minHnwHouseholds: 2_500,
      minAADT: null,
      matchLogic: "AND",
    },
    isDefault: true,
  },
  {
    name: "Keep — Tier B",
    filter: {
      driveTimeMinutes: 15,
      minPopulation: 25_000,
      minMedianHHI: 150_000,
      minMedianHomeValue: null,
      minHnwHouseholds: null,
      minAADT: null,
      matchLogic: "AND",
    },
  },
  {
    name: "Storage — Trade Area",
    filter: {
      driveTimeMinutes: 10,
      minPopulation: 10_000,
      minMedianHHI: null,
      minMedianHomeValue: null,
      minHnwHouseholds: null,
      minAADT: null,
      matchLogic: "AND",
    },
  },
];

// ── Pure evaluation ────────────────────────────────────────────────────────────

export function isFilterActive(filter: BuyBoxFilter): boolean {
  return (
    filter.minPopulation != null ||
    filter.minMedianHHI != null ||
    filter.minMedianHomeValue != null ||
    filter.minHnwHouseholds != null ||
    filter.minAADT != null
  );
}

export function evaluateParcel(
  parcelId: string,
  precomputedData: Map<string, PrecomputedParcelData>,
  filter: BuyBoxFilter,
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

  // AND mode
  if (failing.length === 0) {
    return { status: "match", failedConditions: [], borderlineConditions: [] };
  }

  // Borderline: ALL failed conditions are within 10% of threshold
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
): Map<string, EvaluationResult> {
  const out = new Map<string, EvaluationResult>();
  for (const id of parcelIds) {
    out.set(id, evaluateParcel(id, precomputedData, filter));
  }
  return out;
}

// ── Preset CRUD ────────────────────────────────────────────────────────────────

export function loadPresets(): SavedPreset[] {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(PRESET_STORAGE_KEY) : null;
    if (raw) return JSON.parse(raw) as SavedPreset[];
  } catch {
    // fall through to seed defaults
  }
  if (typeof window !== "undefined") {
    try { localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(DEFAULT_PRESETS)); } catch { /* quota */ }
  }
  return DEFAULT_PRESETS;
}

export function savePreset(preset: SavedPreset): void {
  const existing = loadPresets().filter((p) => p.name !== preset.name);
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify([...existing, preset]));
  } catch { /* quota */ }
}

export function deletePreset(name: string): void {
  const filtered = loadPresets().filter((p) => p.name !== name);
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(filtered));
  } catch { /* quota */ }
}

export function setDefaultPreset(name: string): void {
  const presets = loadPresets().map((p) => ({ ...p, isDefault: p.name === name }));
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets));
  } catch { /* quota */ }
}

export function getDefaultPreset(): SavedPreset | null {
  return loadPresets().find((p) => p.isDefault) ?? null;
}
