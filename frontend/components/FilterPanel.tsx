"use client";

/**
 * Left-side filter panel on the dashboard — Phase 4 full implementation.
 *
 * Controls:
 *   - Search by APN/address
 *   - Storage permission checkboxes
 *   - Zone checkboxes with parcel counts
 *   - Min / max acreage inputs
 *   - Toggles: Vacant Only, Exclude Flood, Exclude Wetland
 *
 * Manages its own local state; fires onChange on every change.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ZONE_CLASS_COLORS, ZONE_CLASS_LABELS } from "@/lib/layers";
import type { ZoneClass } from "@/lib/schemas";

// ─── Types ────────────────────────────────────────────────────────────────────

export type StoragePermission =
  | "permitted"
  | "conditional"
  | "unclear"
  | "prohibited"
  | "unclassified";

export interface FilterState {
  search: string;
  storagePermissions: StoragePermission[];
  zones: string[];
  zoneClasses: ZoneClass[];
  cities: string[];
  minAcres: number | null;
  maxAcres: number | null;
  excludeFlood: boolean;
  excludeWetland: boolean;
  vacantOnly: boolean;
}

export const DEFAULT_FILTERS: FilterState = {
  search: "",
  storagePermissions: [],
  zones: [],
  zoneClasses: [],
  cities: [],
  minAcres: 1.5,
  maxAcres: 15,
  excludeFlood: false,
  excludeWetland: false,
  vacantOnly: false,
};

interface FilterPanelProps {
  jurisdictionId: string | null;
  onChange: (filters: FilterState) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function FilterPanel({ jurisdictionId, onChange }: FilterPanelProps) {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);

  useEffect(() => {
    setFilters(DEFAULT_FILTERS);
  }, [jurisdictionId]);

  const { data: zoneSummary, isLoading: summaryLoading } = useQuery({
    queryKey: ["zone-summary", jurisdictionId],
    queryFn: () => api.getZoneSummary(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
  });

  const { data: classSummary } = useQuery({
    queryKey: ["zone-class-summary", jurisdictionId],
    queryFn: () => api.getZoneClassSummary(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
  });

  const { data: zoneMatrix, isLoading: matrixLoading } = useQuery({
    queryKey: ["zone-matrix", jurisdictionId],
    queryFn: () => api.getZoneMatrix(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
  });

  // Cities within this jurisdiction (for county-as-jurisdiction drill-down).
  // Single-city jurisdictions return 0–1 rows → the City section hides itself.
  const { data: cityCounts } = useQuery({
    queryKey: ["jurisdiction-cities", jurisdictionId],
    queryFn: () => api.getJurisdictionCities(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    onChange(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  function update(patch: Partial<FilterState>) {
    setFilters((prev) => ({ ...prev, ...patch }));
  }

  function toggleZone(code: string) {
    setFilters((prev) => ({
      ...prev,
      zones: prev.zones.includes(code)
        ? prev.zones.filter((z) => z !== code)
        : [...prev.zones, code],
    }));
  }

  function toggleZoneClass(klass: ZoneClass) {
    setFilters((prev) => ({
      ...prev,
      zoneClasses: prev.zoneClasses.includes(klass)
        ? prev.zoneClasses.filter((c) => c !== klass)
        : [...prev.zoneClasses, klass],
    }));
  }

  function toggleCity(city: string) {
    setFilters((prev) => ({
      ...prev,
      cities: prev.cities.includes(city)
        ? prev.cities.filter((c) => c !== city)
        : [...prev.cities, city],
    }));
  }

  function toggleStoragePermission(perm: StoragePermission) {
    setFilters((prev) => ({
      ...prev,
      storagePermissions: prev.storagePermissions.includes(perm)
        ? prev.storagePermissions.filter((p) => p !== perm)
        : [...prev.storagePermissions, perm],
    }));
  }

  const sortedZones = Object.entries(zoneSummary ?? {}).sort((a, b) => b[1] - a[1]);

  const matrixZones =
    sortedZones.length === 0
      ? (zoneMatrix?.zones ?? []).map((z) => ({
          code: z.zone_code,
          name: z.zone_name,
          storage: z.self_storage,
        }))
      : [];

  const classEntries = classSummary
    ? (Object.entries(classSummary) as [ZoneClass, number][])
        .filter(([c]) => c in ZONE_CLASS_LABELS)
        .sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div className="space-y-5 p-4 text-sm">
      {/* ── Search ─────────────────────────────────────────────────────── */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Search
        </h3>
        <input
          type="text"
          value={filters.search}
          onChange={(e) => update({ search: e.target.value })}
          placeholder="APN or address"
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
        />
      </section>

      <div className="border-t border-slate-800" />

      {/* ── City (county drill-down) ──────────────────────────────────── */}
      {(cityCounts?.length ?? 0) > 1 && (
        <>
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                City
              </h3>
              {filters.cities.length > 0 && (
                <button
                  onClick={() => update({ cities: [] })}
                  className="text-[10px] text-slate-600 transition hover:text-slate-400"
                >
                  Clear
                </button>
              )}
            </div>
            <div className="max-h-44 space-y-0.5 overflow-y-auto pr-1">
              {(cityCounts ?? []).map(({ city, parcel_count }) => {
                const checked = filters.cities.includes(city);
                return (
                  <label
                    key={city}
                    className={[
                      "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition",
                      checked ? "bg-slate-800" : "hover:bg-slate-800/50",
                    ].join(" ")}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleCity(city)}
                      className="h-3 w-3 rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                    />
                    <span className="flex-1 truncate text-xs font-medium text-slate-300">
                      {city}
                    </span>
                    <span className="text-[10px] tabular-nums text-slate-600">
                      {parcel_count.toLocaleString()}
                    </span>
                  </label>
                );
              })}
            </div>
          </section>

          <div className="border-t border-slate-800" />
        </>
      )}

      {/* ── DATA section header ───────────────────────────────────────── */}
      <div className="pt-1">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
          Data
        </p>
      </div>

      {/* ── Storage Use ───────────────────────────────────────────────── */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Storage Use
          </h3>
          {filters.storagePermissions.length > 0 && (
            <button
              onClick={() => update({ storagePermissions: [] })}
              className="text-[10px] text-slate-600 transition hover:text-slate-400"
            >
              Clear
            </button>
          )}
        </div>
        <div className="space-y-0.5">
          {(
            [
              { value: "permitted", label: "Permitted", dot: "bg-emerald-500" },
              { value: "conditional", label: "Conditional", dot: "bg-amber-400" },
              { value: "unclear", label: "Unclear", dot: "bg-violet-400" },
              { value: "prohibited", label: "Prohibited", dot: "bg-slate-400" },
            ] as { value: StoragePermission; label: string; dot: string }[]
          ).map(({ value, label, dot }) => {
            const checked = filters.storagePermissions.includes(value);
            return (
              <label
                key={value}
                className={[
                  "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition",
                  checked ? "bg-slate-800" : "hover:bg-slate-800/50",
                ].join(" ")}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleStoragePermission(value)}
                  className="h-3 w-3 rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                />
                <span className={`inline-block h-2 w-2 flex-shrink-0 rounded-full ${dot}`} />
                <span className="flex-1 text-xs font-medium text-slate-300">
                  {label}
                </span>
              </label>
            );
          })}
        </div>
      </section>

      <div className="border-t border-slate-800" />

      {/* Zone Class + Zones sections intentionally removed —
          the parcel-detail drawer + the buy-box flow cover this. */}

      {/* ── Acreage ───────────────────────────────────────────────────── */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Acreage
        </h3>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            step={0.1}
            placeholder="Min"
            value={filters.minAcres ?? ""}
            onChange={(e) =>
              update({ minAcres: e.target.value ? Number(e.target.value) : null })
            }
            className="w-20 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
          />
          <span className="text-xs text-slate-600">–</span>
          <input
            type="number"
            min={0}
            step={0.1}
            placeholder="Max"
            value={filters.maxAcres ?? ""}
            onChange={(e) =>
              update({ maxAcres: e.target.value ? Number(e.target.value) : null })
            }
            className="w-20 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
          />
          <span className="text-xs text-slate-600">ac</span>
        </div>
      </section>

      <div className="border-t border-slate-800" />

      {/* ── Overlays section header ───────────────────────────────────── */}
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
        Overlays
      </p>

      {/* ── Toggles ───────────────────────────────────────────────────── */}
      <section className="space-y-1">
        <Toggle
          label="Vacant only"
          description="Parcels with no known structure"
          checked={filters.vacantOnly}
          onChange={(v) => update({ vacantOnly: v })}
          accent="emerald"
        />
        <Toggle
          label="Exclude flood zone"
          description="Remove FEMA SFHA parcels"
          checked={filters.excludeFlood}
          onChange={(v) => update({ excludeFlood: v })}
          accent="red"
        />
        <Toggle
          label="Exclude wetlands"
          description="Remove USFWS NWI parcels"
          checked={filters.excludeWetland}
          onChange={(v) => update({ excludeWetland: v })}
          accent="blue"
        />
      </section>

      <div className="border-t border-slate-800" />

      {/* ── Reset ─────────────────────────────────────────────────────── */}
      <button
        onClick={() => setFilters(DEFAULT_FILTERS)}
        className="w-full rounded-lg border border-slate-800 py-2 text-xs text-slate-500 transition hover:border-slate-700 hover:text-slate-300"
      >
        Reset all filters
      </button>
    </div>
  );
}

// ─── Toggle sub-component ────────────────────────────────────────────────────

function Toggle({
  label,
  description,
  checked,
  onChange,
  accent,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  accent: "emerald" | "red" | "amber" | "blue";
}) {
  const accentColors = {
    emerald: "bg-emerald-600",
    red: "bg-red-500",
    amber: "bg-amber-500",
    blue: "bg-blue-500",
  };

  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-start gap-3 text-left"
    >
      <span
        className={[
          "mt-0.5 inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors",
          checked ? accentColors[accent] : "bg-slate-700",
        ].join(" ")}
      >
        <span
          className={[
            "h-3 w-3 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-3.5" : "translate-x-0.5",
          ].join(" ")}
        />
      </span>
      <span>
        <span className="block text-xs font-medium text-slate-300">{label}</span>
        <span className="block text-xs text-slate-500">{description}</span>
      </span>
    </button>
  );
}