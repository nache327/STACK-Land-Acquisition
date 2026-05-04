"use client";

/**
 * Top-right overlay on the map: grouped layer toggles with opacity sliders
 * and a dynamic legend. Driven by LAYER_REGISTRY — adding a layer there
 * automatically shows up here.
 */
import { useState } from "react";
import { LAYER_REGISTRY, type LayerCategory, type LayerDef } from "@/lib/layers";
import type { DriveTimeMode } from "@/components/Map";

export type LayerVisibility = Record<string, { visible: boolean; opacity: number }>;

export function initialLayerVisibility(): LayerVisibility {
  const state: LayerVisibility = {};
  for (const layer of LAYER_REGISTRY) {
    state[layer.id] = {
      visible: layer.defaultVisible,
      opacity: layer.defaultOpacity,
    };
  }
  return state;
}

interface LayerControlProps {
  visibility: LayerVisibility;
  onChange: (next: LayerVisibility) => void;
  driveTimeMode?: DriveTimeMode;
  onDriveTimeModeChange?: (mode: DriveTimeMode) => void;
  keepActive?: boolean;
  keepMinScore?: number;
  onKeepChange?: (active: boolean, minScore: number) => void;
  keepEffectiveScores?: {
    permitted: number | null;
    conditional: number | null;
    unclear: number | null;
  };
}

const CATEGORY_LABELS: Record<LayerCategory, string> = {
  base: "Base",
  data: "Data",
  overlay: "Overlays",
};

export function LayerControl({
  visibility,
  onChange,
  driveTimeMode = "off",
  onDriveTimeModeChange,
  keepActive = false,
  keepMinScore = 55,
  onKeepChange,
  keepEffectiveScores,
}: LayerControlProps) {
  const [collapsed, setCollapsed] = useState(false);

  function setLayer(id: string, patch: Partial<LayerVisibility[string]>) {
    onChange({ ...visibility, [id]: { ...visibility[id], ...patch } });
  }

  const groups: Record<LayerCategory, LayerDef[]> = {
    base: [],
    data: [],
    overlay: [],
  };
  for (const layer of LAYER_REGISTRY) {
    groups[layer.category].push(layer);
  }

  return (
    <div className="absolute right-3 top-3 z-10 w-64 rounded-lg border border-slate-200 bg-white/95 shadow-lg backdrop-blur-sm">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-700 hover:bg-slate-50"
      >
        <span>Layers</span>
        <span className="text-slate-400">{collapsed ? "▸" : "▾"}</span>
      </button>

      {!collapsed && (
        <div className="max-h-[70vh] overflow-y-auto px-3 pb-3">
          {(Object.keys(groups) as LayerCategory[]).map((cat) => {
            const layers = groups[cat];
            if (layers.length === 0) return null;
            return (
              <div key={cat} className="mb-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  {CATEGORY_LABELS[cat]}
                </p>
                <div className="space-y-1.5">
                  {layers.map((layer) => {
                    const v = visibility[layer.id];
                    if (!v) return null;
                    return (
                      <div
                        key={layer.id}
                        className="rounded border border-slate-100 bg-slate-50/50 p-1.5"
                      >
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={v.visible}
                            onChange={(e) =>
                              setLayer(layer.id, { visible: e.target.checked })
                            }
                            className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                          />
                          <span className="flex-1 text-xs font-medium text-slate-700">
                            {layer.title}
                          </span>
                        </label>

                        {v.visible && (
                          <>
                            <input
                              type="range"
                              min={0}
                              max={1}
                              step={0.05}
                              value={v.opacity}
                              onChange={(e) =>
                                setLayer(layer.id, {
                                  opacity: Number(e.target.value),
                                })
                              }
                              className="mt-1.5 h-1 w-full"
                            />
                            {layer.legend && layer.legend.length > 0 && (
                              <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1">
                                {layer.legend.map((sw) => (
                                  <div
                                    key={sw.label}
                                    className="flex items-center gap-1 text-[10px] text-slate-600"
                                  >
                                    <span
                                      className="inline-block h-2 w-2 rounded-sm"
                                      style={{ backgroundColor: sw.color }}
                                    />
                                    {sw.label}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {/* ── Analysis tools ── */}
          <div className="mb-2">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Analysis
            </p>
            <div className="space-y-1.5">

              {/* Drive-time rings */}
              <div className="rounded border border-slate-100 bg-slate-50/50 p-1.5">
                <button
                  onClick={() => {
                    if (!onDriveTimeModeChange) return;
                    const next: DriveTimeMode =
                      driveTimeMode === "off" ? "on"
                      : driveTimeMode === "on"  ? "pinned"
                      : "off";
                    onDriveTimeModeChange(next);
                  }}
                  className="flex w-full items-center justify-between text-xs font-medium text-slate-700"
                >
                  <span className="flex items-center gap-1.5">
                    {/* Ring icon */}
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1" fill="none" opacity="0.4"/>
                      <circle cx="6" cy="6" r="3.2" stroke="currentColor" strokeWidth="1" fill="none" opacity="0.6"/>
                      <circle cx="6" cy="6" r="1.4" stroke="currentColor" strokeWidth="1" fill="none" opacity="0.9"/>
                    </svg>
                    Drive-time rings
                  </span>
                  <span
                    className={[
                      "rounded-full px-1.5 py-0.5 text-[9px] font-semibold",
                      driveTimeMode === "off"    ? "bg-slate-200 text-slate-500"
                      : driveTimeMode === "on"   ? "bg-blue-100 text-blue-700"
                      : "bg-orange-100 text-orange-700",
                    ].join(" ")}
                  >
                    {driveTimeMode === "off" ? "OFF" : driveTimeMode === "on" ? "ON" : "PINNED"}
                  </span>
                </button>
                {driveTimeMode !== "off" && (
                  <p className="mt-1 text-[9px] text-slate-400">
                    {driveTimeMode === "on"
                      ? "Click a parcel to draw 2/5/10-min rings"
                      : "Rings locked — click another parcel to compare"}
                  </p>
                )}
              </div>

              {/* The Keep scoring layer */}
              <div className="rounded border border-slate-100 bg-slate-50/50 p-1.5">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={keepActive}
                    onChange={(e) => onKeepChange?.(e.target.checked, keepMinScore)}
                    className="h-3.5 w-3.5 rounded border-slate-300 text-amber-500 focus:ring-amber-400"
                  />
                  <span className="flex items-center gap-1.5 flex-1 text-xs font-medium text-slate-700">
                    {/* Key icon */}
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <circle cx="4.5" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.2" fill="none"/>
                      <path d="M6.5 5h4M9 5v1.5M10.5 5v2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                    </svg>
                    The Keep
                  </span>
                </label>

                {keepActive && (
                  <>
                    <div className="mt-1.5">
                      <label className="text-[9px] text-slate-500 flex justify-between mb-0.5">
                        <span>Min score</span>
                        <span className="text-amber-600 font-semibold">{keepMinScore}</span>
                      </label>
                      <input
                        type="range"
                        min={40}
                        max={100}
                        step={5}
                        value={keepMinScore}
                        onChange={(e) => onKeepChange?.(true, Number(e.target.value))}
                        className="h-1 w-full accent-amber-500"
                      />
                    </div>
                    {keepEffectiveScores ? (
                      <div className="mt-1.5">
                        <div className="flex flex-wrap gap-x-2 gap-y-1">
                          {[
                            { color: "#C9A84C", key: "permitted"   as const, grade: "A" },
                            { color: "#5B8DB8", key: "conditional" as const, grade: "B" },
                            { color: "#8B9BA8", key: "unclear"     as const, grade: "C" },
                          ].map((sw) => {
                            const score = keepEffectiveScores[sw.key];
                            return (
                              <div key={sw.grade} className="flex items-center gap-1 text-[9px] text-slate-600">
                                <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: sw.color }} />
                                {score != null ? `${sw.grade} · ${score}` : sw.grade}
                              </div>
                            );
                          })}
                        </div>
                        <p className="mt-0.5 text-[9px] text-amber-600">Wealth-adjusted</p>
                      </div>
                    ) : (
                      <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1">
                        {[
                          { color: "#C9A84C", label: "A  85–100" },
                          { color: "#5B8DB8", label: "B  70–84" },
                          { color: "#8B9BA8", label: "C  55–69" },
                        ].map((sw) => (
                          <div key={sw.label} className="flex items-center gap-1 text-[9px] text-slate-600">
                            <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: sw.color }} />
                            {sw.label}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

            </div>
          </div>
        </div>
      )}
    </div>
  );
}
