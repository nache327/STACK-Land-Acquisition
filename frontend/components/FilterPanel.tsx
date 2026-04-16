"use client";

/**
 * Left-side filter panel on the dashboard — Phase 4 full implementation.
 *
 * Controls:
 *   - Zone checkboxes (with parcel counts)
 *   - Min / max acreage inputs
 *   - Toggles: Vacant Only, Exclude Flood, Exclude Steep, Exclude Wetland
 *
 * Manages its own local state; fires onChange on every change.
 */

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface FilterState {
  zones: string[];
  minAcres: number | null;
  maxAcres: number | null;
  excludeFlood: boolean;
  excludeSteep: boolean;
  excludeWetland: boolean;
  vacantOnly: boolean;
}

export const DEFAULT_FILTERS: FilterState = {
  zones: [],
  minAcres: null,
  maxAcres: null,
  excludeFlood: false,
  excludeSteep: false,
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

  // Fetch zone summary (zone codes + counts)
  const { data: zoneSummary } = useQuery({
    queryKey: ["zone-summary", jurisdictionId],
    queryFn: () => api.getZoneSummary(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
  });

  // Propagate changes upward
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

  const sortedZones = Object.entries(zoneSummary ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-5 p-4 text-sm">
      {/* ── Zones ─────────────────────────────────────────────────────── */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Zones
          </h3>
          {filters.zones.length > 0 && (
            <button
              onClick={() => update({ zones: [] })}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              Clear
            </button>
          )}
        </div>

        {sortedZones.length === 0 ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : (
          <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
            {sortedZones.map(([code, count]) => {
              const checked = filters.zones.includes(code);
              return (
                <label
                  key={code}
                  className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleZone(code)}
                    className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="flex-1 font-mono text-xs font-medium text-slate-700">
                    {code}
                  </span>
                  <span className="text-xs text-slate-400">{count.toLocaleString()}</span>
                </label>
              );
            })}
          </div>
        )}
      </section>

      <div className="border-t border-slate-100" />

      {/* ── Acreage ───────────────────────────────────────────────────── */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
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
            className="w-20 rounded border border-slate-200 px-2 py-1 text-xs placeholder-slate-400 focus:border-emerald-500 focus:outline-none"
          />
          <span className="text-xs text-slate-400">–</span>
          <input
            type="number"
            min={0}
            step={0.1}
            placeholder="Max"
            value={filters.maxAcres ?? ""}
            onChange={(e) =>
              update({ maxAcres: e.target.value ? Number(e.target.value) : null })
            }
            className="w-20 rounded border border-slate-200 px-2 py-1 text-xs placeholder-slate-400 focus:border-emerald-500 focus:outline-none"
          />
          <span className="text-xs text-slate-400">ac</span>
        </div>
      </section>

      <div className="border-t border-slate-100" />

      {/* ── Overlays / toggles ────────────────────────────────────────── */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Overlays
        </h3>
        <div className="space-y-2">
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
            label="Exclude steep slopes"
            description="Remove parcels >15% grade"
            checked={filters.excludeSteep}
            onChange={(v) => update({ excludeSteep: v })}
            accent="amber"
          />
          <Toggle
            label="Exclude wetlands"
            description="Remove USFWS NWI parcels"
            checked={filters.excludeWetland}
            onChange={(v) => update({ excludeWetland: v })}
            accent="blue"
          />
        </div>
      </section>

      <div className="border-t border-slate-100" />

      {/* ── Reset ─────────────────────────────────────────────────────── */}
      <button
        onClick={() => setFilters(DEFAULT_FILTERS)}
        className="w-full rounded-md border border-slate-200 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
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
      {/* Toggle pill */}
      <span
        className={[
          "mt-0.5 inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors",
          checked ? accentColors[accent] : "bg-slate-200",
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
        <span className="block text-xs font-medium text-slate-700">{label}</span>
        <span className="block text-xs text-slate-400">{description}</span>
      </span>
    </button>
  );
}
