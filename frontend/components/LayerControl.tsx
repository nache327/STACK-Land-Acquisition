"use client";

/**
 * Top-right overlay on the map: grouped layer toggles with opacity sliders
 * and a dynamic legend. Driven by LAYER_REGISTRY — adding a layer there
 * automatically shows up here.
 */
import { useState } from "react";
import { LAYER_REGISTRY, type LayerCategory, type LayerDef } from "@/lib/layers";

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
}

const CATEGORY_LABELS: Record<LayerCategory, string> = {
  base: "Base",
  data: "Data",
  overlay: "Overlays",
};

export function LayerControl({ visibility, onChange }: LayerControlProps) {
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
        </div>
      )}
    </div>
  );
}
