"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  type BuyBoxFilter,
  type SavedPreset,
  DEFAULT_FILTER,
  loadPresets,
  savePreset,
  deletePreset,
  updatePreset,
  setDefaultPreset,
} from "@/lib/buy-box-filter";
import type { PrecomputeStatus } from "@/lib/isochrone-precompute";

interface BuyBoxPanelProps {
  filter: BuyBoxFilter;
  onChange: (filter: BuyBoxFilter) => void;
  precomputeStatus: PrecomputeStatus | null;
  evaluationCounts: { match: number; borderline: number; fail: number; computing: number };
  cityDataRanges: { maxPopulation: number; maxHnwHouseholds: number } | null;
  bestActualValues?: { population: number; medianHHI: number; homeValue: number; hnwHouseholds: number } | null;
  onRecompute?: () => void;
  /** When false, the three Wealth-density sliders are greyed + non-interactive
   *  and a tooltip explains the source doesn't publish assessed values.
   *  Defaults to true (enabled) — pass false for UT/UGRC cities. */
  wealthDensityAvailable?: boolean;
}

function fmt(value: number | null | undefined, prefix = ""): string {
  // Treat undefined as null. Presets saved before the wealth-density
  // fields existed will deserialize without minHomesOverNM keys, so the
  // value coming into the slider readout is undefined for those rows.
  // Before this guard, `value.toLocaleString()` crashed the dashboard.
  if (value == null || value === 0) return "off";
  if (value >= 1_000_000) return `${prefix}${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${prefix}${Math.round(value / 1_000)}K`;
  return `${prefix}${value.toLocaleString()}`;
}

const DRIVE_TIMES: BuyBoxFilter["driveTimeMinutes"][] = [2, 5, 10, 15];

export function BuyBoxPanel({
  filter,
  onChange,
  precomputeStatus,
  evaluationCounts,
  cityDataRanges,
  bestActualValues,
  onRecompute,
  wealthDensityAvailable = true,
}: BuyBoxPanelProps) {
  const [presets, setPresets] = useState<SavedPreset[]>([]);
  const [presetsLoaded, setPresetsLoaded] = useState(false);
  const [presetError, setPresetError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [savingName, setSavingName] = useState("");
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [showManage, setShowManage] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const refreshPresets = useCallback(async () => {
    try {
      const fresh = await loadPresets();
      setPresets(fresh);
      setPresetError(null);
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    } finally {
      setPresetsLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refreshPresets();
  }, [refreshPresets]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
        setShowSaveInput(false);
        setShowManage(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [dropdownOpen]);

  function applyPreset(preset: SavedPreset) {
    // Spread DEFAULT_FILTER first so older presets — saved before fields
    // like minHomesOverNM existed — land with explicit `null` instead of
    // `undefined` for the missing keys. Downstream consumers (evaluator,
    // SliderRow readout, etc.) all handle null but several would crash
    // on undefined.
    onChange({ ...DEFAULT_FILTER, ...preset.filter });
    setDropdownOpen(false);
    setShowSaveInput(false);
    setShowManage(false);
  }

  async function handleSavePreset() {
    const name = savingName.trim();
    if (!name) return;
    try {
      await savePreset({ name, filter });
      await refreshPresets();
      setSavingName("");
      setShowSaveInput(false);
      setDropdownOpen(false);
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDeletePreset(id: string) {
    setBusyId(id);
    try {
      await deletePreset(id);
      await refreshPresets();
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleSetDefault(id: string) {
    setBusyId(id);
    try {
      await setDefaultPreset(id);
      await refreshPresets();
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleToggleEmail(p: SavedPreset, enabled: boolean) {
    setBusyId(p.id);
    try {
      await updatePreset(p.id, { dailyEmailEnabled: enabled });
      await refreshPresets();
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleEmailTopN(p: SavedPreset, topN: number) {
    if (!Number.isFinite(topN) || topN < 1 || topN > 100) return;
    setBusyId(p.id);
    try {
      await updatePreset(p.id, { dailyEmailTopN: topN });
      await refreshPresets();
    } catch (err) {
      setPresetError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  const maxPop = cityDataRanges?.maxPopulation ?? 200_000;
  const maxHnw = cityDataRanges?.maxHnwHouseholds ?? 5_000;

  const isComputing = precomputeStatus && !precomputeStatus.complete;
  const progressPct = precomputeStatus
    ? (precomputeStatus.progress / Math.max(precomputeStatus.total, 1)) * 100
    : 0;

  const hidden = evaluationCounts.fail + evaluationCounts.computing;

  return (
    <div className="border-b border-slate-800 bg-slate-950 px-3 py-3 text-slate-300">
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Buy box
        </span>
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => { setDropdownOpen((o) => !o); setShowManage(false); setShowSaveInput(false); }}
            className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            Saved Filters ▾
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded border border-slate-700 bg-slate-900 shadow-xl">
              {!showManage ? (
                <>
                  {!presetsLoaded ? (
                    <p className="px-3 py-2 text-[10px] text-slate-500">Loading…</p>
                  ) : presets.length === 0 ? (
                    <p className="px-3 py-2 text-[10px] text-slate-500">No saved filters yet.</p>
                  ) : (
                    presets.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => applyPreset(p)}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] hover:bg-slate-800"
                      >
                        {p.isDefault ? <span className="text-amber-400">★</span> : <span className="w-3" />}
                        <span className="flex-1 truncate">{p.name}</span>
                        {p.dailyEmailEnabled && <span title="Daily email on" className="text-emerald-400">✉</span>}
                        {JSON.stringify(p.filter) === JSON.stringify(filter) && (
                          <span className="text-emerald-400">✓</span>
                        )}
                      </button>
                    ))
                  )}
                  <div className="my-1 border-t border-slate-700" />
                  {showSaveInput ? (
                    <div className="flex items-center gap-1 px-3 py-1.5">
                      <input
                        autoFocus
                        value={savingName}
                        onChange={(e) => setSavingName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") void handleSavePreset(); if (e.key === "Escape") setShowSaveInput(false); }}
                        placeholder="Filter name…"
                        className="flex-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200 outline-none placeholder:text-slate-500"
                      />
                      <button onClick={() => void handleSavePreset()} className="text-[10px] text-emerald-400 hover:text-emerald-300">Save</button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setShowSaveInput(true)}
                      className="w-full px-3 py-1.5 text-left text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    >
                      + Save current as new…
                    </button>
                  )}
                  <button
                    onClick={() => setShowManage(true)}
                    className="w-full px-3 py-1.5 text-left text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                  >
                    ⚙ Manage filters…
                  </button>
                  {presetError && (
                    <p className="px-3 py-1.5 text-[10px] text-red-400">{presetError}</p>
                  )}
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2 px-3 py-1.5">
                    <button onClick={() => setShowManage(false)} className="text-[10px] text-slate-400 hover:text-slate-200">← Back</button>
                    <span className="text-[11px] font-medium text-slate-300">Manage filters</span>
                  </div>
                  <div className="my-1 border-t border-slate-700" />
                  {presets.length === 0 && (
                    <p className="px-3 py-2 text-[10px] text-slate-500">No saved filters yet.</p>
                  )}
                  {presets.map((p) => (
                    <div key={p.id} className="border-b border-slate-800 px-3 py-1.5 text-[10px] last:border-b-0">
                      <div className="flex items-center gap-1">
                        <span className="flex-1 truncate text-slate-300">{p.name}</span>
                        <button
                          onClick={() => void handleSetDefault(p.id)}
                          disabled={busyId === p.id || p.isDefault}
                          title={p.isDefault ? "Default" : "Set as default"}
                          className={p.isDefault ? "text-amber-400" : "text-slate-500 hover:text-amber-400"}
                        >
                          ★
                        </button>
                        <button
                          onClick={() => void handleDeletePreset(p.id)}
                          disabled={busyId === p.id}
                          className="text-slate-500 hover:text-red-400"
                        >
                          ✕
                        </button>
                      </div>
                      <label className="mt-1 flex items-center gap-1.5 text-slate-400">
                        <input
                          type="checkbox"
                          checked={p.dailyEmailEnabled ?? false}
                          disabled={busyId === p.id}
                          onChange={(e) => void handleToggleEmail(p, e.target.checked)}
                          className="h-3 w-3 accent-emerald-500"
                        />
                        Daily email
                      </label>
                      {p.dailyEmailEnabled && (
                        <div className="mt-1 flex items-center gap-1.5 pl-5 text-slate-400">
                          <span>Top</span>
                          <input
                            type="number"
                            min={1}
                            max={100}
                            defaultValue={p.dailyEmailTopN ?? 10}
                            disabled={busyId === p.id}
                            onBlur={(e) => void handleEmailTopN(p, parseInt(e.target.value, 10))}
                            className="w-12 rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-200 outline-none"
                          />
                          <span>parcels/day</span>
                        </div>
                      )}
                      {p.lastEmailSentAt && (
                        <p className="mt-0.5 text-[9px] text-slate-600">
                          Last sent {new Date(p.lastEmailSentAt).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {isComputing && (
        <div className="mb-2">
          <div className="mb-0.5 flex justify-between text-[9px] text-slate-500">
            <span>Computing buy-box data</span>
            <span>{precomputeStatus.progress} / {precomputeStatus.total}</span>
          </div>
          <div className="h-0.5 w-full overflow-hidden rounded bg-slate-800">
            <div
              className="h-full bg-amber-400 transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {precomputeStatus?.complete && precomputeStatus.lastComputed && (
        <p className="mb-2 text-[9px] text-slate-600">
          Last computed {new Date(precomputeStatus.lastComputed).toLocaleDateString()}
        </p>
      )}

      {/* Drive-time pills */}
      <div className="mb-3">
        <p className="mb-1 text-[9px] text-slate-500">Drive time</p>
        <div className="flex gap-1">
          {DRIVE_TIMES.map((t) => (
            <button
              key={t}
              onClick={() => onChange({ ...filter, driveTimeMinutes: t })}
              className="rounded px-2 py-0.5 text-[10px] font-medium transition-colors"
              style={
                filter.driveTimeMinutes === t
                  ? { backgroundColor: "#C9A84C", color: "#1a1a1a" }
                  : { backgroundColor: "#1e293b", color: "#94a3b8" }
              }
            >
              {t} min
            </button>
          ))}
        </div>
      </div>

      {/* Sliders */}
      <div className="mb-3 space-y-2">
        <SliderRow
          label="Population"
          value={filter.minPopulation}
          min={0}
          max={maxPop}
          step={1_000}
          readout={fmt(filter.minPopulation)}
          onChange={(v) => onChange({ ...filter, minPopulation: v })}
        />
        <SliderRow
          label="Median HHI"
          value={filter.minMedianHHI}
          min={0}
          max={500_000}
          step={5_000}
          readout={fmt(filter.minMedianHHI, "$")}
          onChange={(v) => onChange({ ...filter, minMedianHHI: v })}
        />
        <SliderRow
          label="Home value"
          value={filter.minMedianHomeValue}
          min={0}
          max={3_000_000}
          step={25_000}
          readout={fmt(filter.minMedianHomeValue, "$")}
          onChange={(v) => onChange({ ...filter, minMedianHomeValue: v })}
        />
        <SliderRow
          label="HNW households"
          value={filter.minHnwHouseholds}
          min={0}
          max={maxHnw}
          step={100}
          readout={fmt(filter.minHnwHouseholds)}
          onChange={(v) => onChange({ ...filter, minHnwHouseholds: v })}
        />
        <SliderRow
          label="Min Traffic (AADT)"
          value={filter.minAADT}
          min={0}
          max={75_000}
          step={1_000}
          readout={filter.minAADT == null ? "off" : `${(filter.minAADT / 1_000).toFixed(0)}K/day`}
          onChange={(v) => onChange({ ...filter, minAADT: v })}
        />
      </div>

      {/* Wealth density — count of residential parcels above each value
          threshold inside the drive-time ring. Source: per-state assessor
          rolls (NJ MOD-IV / FL DOR cadastral / PA OPA). Greyed when the
          jurisdiction's source publishes no assessed_value (e.g. UT UGRC),
          since dragging the slider above 0 would otherwise hide every
          parcel in that city. */}
      <div className="mb-2 mt-3 flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider text-slate-500">
          Wealth density
        </span>
        {!wealthDensityAvailable && (
          <span
            className="text-[9px] italic text-slate-500"
            title="Assessor value data not available for this city's source. Currently supported: NJ MOD-IV, PA Philly OPA, FL DOR cadastral."
          >
            unavailable for this city
          </span>
        )}
      </div>
      <div
        className={
          wealthDensityAvailable
            ? "mb-3 space-y-2"
            : "mb-3 space-y-2 pointer-events-none opacity-40"
        }
        aria-disabled={!wealthDensityAvailable}
        title={!wealthDensityAvailable ? "Assessor value data not available for this city's source." : undefined}
      >
        <SliderRow
          label="Homes ≥$1M"
          value={filter.minHomesOver1M}
          min={0}
          max={2_000}
          step={10}
          readout={fmt(filter.minHomesOver1M)}
          onChange={(v) => onChange({ ...filter, minHomesOver1M: v })}
        />
        <SliderRow
          label="Homes ≥$2M"
          value={filter.minHomesOver2M}
          min={0}
          max={500}
          step={5}
          readout={fmt(filter.minHomesOver2M)}
          onChange={(v) => onChange({ ...filter, minHomesOver2M: v })}
        />
        <SliderRow
          label="Homes ≥$5M"
          value={filter.minHomesOver5M}
          min={0}
          max={100}
          step={1}
          readout={fmt(filter.minHomesOver5M)}
          onChange={(v) => onChange({ ...filter, minHomesOver5M: v })}
        />
      </div>

      {/* Listings (Layer 4) */}
      <div className="mb-3">
        <div className="mb-1 text-[9px] uppercase tracking-wide text-slate-500">
          Listings
        </div>
        <label className="flex items-center gap-2 text-[11px] text-slate-300">
          <input
            type="checkbox"
            checked={!!filter.requireListed}
            onChange={(e) =>
              onChange({ ...filter, requireListed: e.target.checked })
            }
            className="h-3 w-3 rounded border-slate-500"
          />
          Listed for sale only
          <span className="text-[9px] text-slate-500" title="Hard filter — drops parcels with no current matched listing">
            (hard filter)
          </span>
        </label>
      </div>

      {/* Match logic */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[9px] text-slate-500">Match</span>
        {(["AND", "OR"] as const).map((logic) => (
          <button
            key={logic}
            onClick={() => onChange({ ...filter, matchLogic: logic })}
            className="rounded px-2 py-0.5 text-[10px] font-medium transition-colors"
            style={
              filter.matchLogic === logic
                ? { backgroundColor: "#C9A84C", color: "#1a1a1a" }
                : { backgroundColor: "#1e293b", color: "#94a3b8" }
            }
          >
            {logic === "AND" ? "All" : "Any"}
          </button>
        ))}
      </div>

      {/* Live counters */}
      <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          {evaluationCounts.match} match
        </span>
        <span className="text-slate-700">·</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
          {evaluationCounts.borderline} borderline
        </span>
        <span className="text-slate-700">·</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-slate-600" />
          {hidden} hidden
        </span>
      </div>

      {evaluationCounts.match === 0 && evaluationCounts.borderline === 0 && !isComputing && (
        hidden > 0 ? (
          <div className="mb-2 text-[10px] text-amber-500/80">
            <p>All parcels hidden — thresholds may be above available data.</p>
            {bestActualValues && (
              <p className="mt-1 text-slate-400">
                Best found: Pop {fmt(bestActualValues.population)} · HHI {fmt(bestActualValues.medianHHI, "$")} · Home {fmt(bestActualValues.homeValue, "$")} · HNW {fmt(bestActualValues.hnwHouseholds)}
              </p>
            )}
            <p className="mt-1">Try Recompute if data looks stale.</p>
          </div>
        ) : (
          <p className="mb-2 text-[10px] text-slate-500">
            No parcels match — try adjusting thresholds.
          </p>
        )
      )}

      {/* Footer actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange(DEFAULT_FILTER)}
          className="rounded px-2 py-1 text-[10px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          Reset
        </button>
        <button
          onClick={() => { setDropdownOpen(true); setShowSaveInput(true); }}
          className="rounded px-2 py-1 text-[10px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          Save as filter…
        </button>
        {onRecompute && precomputeStatus?.complete && (
          <button
            onClick={onRecompute}
            className="rounded px-2 py-1 text-[10px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            Recompute
          </button>
        )}
      </div>
    </div>
  );
}

// ── SliderRow subcomponent ─────────────────────────────────────────────────────

interface SliderRowProps {
  label: string;
  value: number | null;
  min: number;
  max: number;
  step: number;
  readout: string;
  onChange: (value: number | null) => void;
}

function SliderRow({ label, value, min, max, step, readout, onChange }: SliderRowProps) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-2 gap-y-0.5">
      <span className="text-[10px] text-slate-400">{label}</span>
      <span className="min-w-[40px] text-right text-[10px] text-slate-300">{readout}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value ?? 0}
        onChange={(e) => {
          const v = Number(e.target.value);
          onChange(v === 0 ? null : v);
        }}
        className="col-span-2 h-1 w-full accent-amber-500"
      />
    </div>
  );
}
