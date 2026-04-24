"use client";

/**
 * Zone → use matrix with traffic-light cells.
 *
 * - Citation popover on hover (appears below cell)
 * - Human-reviewed badge on rows that have been manually corrected
 * - onCellClick fires with (zone, useKey) so the caller can open the override drawer
 *
 * Phase 6: fully implemented.
 */

import type { ZoneRow } from "@/lib/schemas";
import type { UseKey } from "./ZoneOverrideDrawer";

const USES: { key: UseKey; label: string }[] = [
  { key: "self_storage", label: "Self-Storage" },
  { key: "mini_warehouse", label: "Mini-Warehouse" },
  { key: "light_industrial", label: "Light Industrial" },
  { key: "luxury_garage_condo", label: "Garage Condo" },
];

type Permission = "permitted" | "conditional" | "prohibited" | "unclear";

const PERMISSION_COLORS: Record<Permission, string> = {
  permitted: "bg-emerald-100 text-emerald-800 border-emerald-300",
  conditional: "bg-amber-100 text-amber-800 border-amber-300",
  prohibited: "bg-red-100 text-red-800 border-red-300",
  unclear: "bg-violet-100 text-violet-700 border-violet-300",
};

const PERMISSION_LABELS: Record<Permission, string> = {
  permitted: "P",
  conditional: "C",
  prohibited: "X",
  unclear: "?",
};

interface ZoneMatrixProps {
  zones: ZoneRow[];
  onCellClick?: (zone: ZoneRow, useKey: UseKey) => void;
}

export function ZoneMatrix({ zones, onCellClick }: ZoneMatrixProps) {
  if (zones.length === 0) {
    return (
      <p className="text-sm text-slate-400">
        No zone data available. Run the ordinance parser first.
      </p>
    );
  }

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">
              Zone
            </th>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">
              Name
            </th>
            {USES.map((use) => (
              <th
                key={use.key}
                className="px-3 py-2 text-center text-xs font-medium text-slate-500"
              >
                {use.label}
              </th>
            ))}
            <th className="px-3 py-2 text-center text-xs font-medium text-slate-500">
              Conf.
            </th>
          </tr>
        </thead>
        <tbody>
          {zones.map((zone) => (
            <tr
              key={zone.zone_code}
              className={[
                "border-t border-slate-100 transition-colors hover:bg-slate-50/60",
                zone.human_reviewed ? "bg-emerald-50/30" : "",
              ].join(" ")}
            >
              {/* Zone code */}
              <td className="px-3 py-2">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-xs font-semibold text-slate-900">
                    {zone.zone_code}
                  </span>
                  {zone.human_reviewed && (
                    <span
                      title="Manually reviewed"
                      className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700"
                    >
                      ✓
                    </span>
                  )}
                  {!zone.human_reviewed && zone.classification_source === "llm_low_confidence" && (
                    <span
                      title="Low-confidence LLM result (< 70%) — verify against ordinance"
                      className="rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] font-medium text-orange-700"
                    >
                      ~verify
                    </span>
                  )}
                  {!zone.human_reviewed && zone.classification_source === "llm_rule" && (
                    <span
                      title="LLM parsed; unclear slots filled by rule classifier"
                      className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-600"
                    >
                      ~partial
                    </span>
                  )}
                  {!zone.human_reviewed && zone.classification_source === "rule" && (
                    <span
                      title="Rule-based classification — not yet verified against ordinance text"
                      className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700"
                    >
                      ⚠
                    </span>
                  )}
                </div>
              </td>

              {/* Zone name */}
              <td className="px-3 py-2 text-xs text-slate-500">
                {zone.zone_name ?? "—"}
              </td>

              {/* Permission cells */}
              {USES.map((use) => {
                const perm = (zone[use.key] as Permission) ?? "unclear";
                const hasCitations =
                  zone.citations && zone.citations.length > 0;

                return (
                  <td key={use.key} className="px-3 py-2 text-center">
                    <div className="relative inline-block group">
                      <button
                        onClick={() => onCellClick?.(zone, use.key)}
                        className={[
                          "inline-flex h-7 w-7 items-center justify-center rounded border text-xs font-bold transition-all",
                          "hover:scale-110 hover:shadow-sm",
                          PERMISSION_COLORS[perm] ?? PERMISSION_COLORS.unclear,
                          // Slightly thicker border for human-reviewed cells
                          zone.human_reviewed
                            ? "border-2 ring-1 ring-offset-1 ring-emerald-300"
                            : "",
                        ].join(" ")}
                        title={`${zone.zone_code} — ${use.label}: ${perm}. Click to override.`}
                      >
                        {PERMISSION_LABELS[perm] ?? "?"}
                      </button>

                      {/* Citation popover — appears on hover when citations exist */}
                      {hasCitations && (
                        <div
                          className={[
                            "pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2",
                            "rounded-lg border border-slate-200 bg-white p-3 shadow-lg",
                            "opacity-0 group-hover:opacity-100 transition-opacity duration-150",
                          ].join(" ")}
                        >
                          <p className="mb-1.5 text-xs font-semibold text-slate-700">
                            Parser citations for {zone.zone_code}
                          </p>
                          <div className="space-y-1.5">
                            {zone.citations!.slice(0, 3).map((c, i) => (
                              <div key={i}>
                                <p className="text-[10px] font-medium text-slate-500">
                                  {c.section}
                                </p>
                                <p className="text-[10px] italic text-slate-400 line-clamp-2">
                                  &ldquo;{c.quote}&rdquo;
                                </p>
                              </div>
                            ))}
                          </div>
                          {/* Caret */}
                          <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 h-3 w-3 rotate-45 border-b border-r border-slate-200 bg-white" />
                        </div>
                      )}
                    </div>
                  </td>
                );
              })}

              {/* Confidence */}
              <td className="px-3 py-2 text-center text-xs text-slate-400">
                {zone.confidence != null
                  ? `${(zone.confidence * 100).toFixed(0)}%`
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <span>
          <span className="font-semibold text-emerald-700">P</span> Permitted
        </span>
        <span>
          <span className="font-semibold text-amber-700">C</span> Conditional
        </span>
        <span>
          <span className="font-semibold text-red-700">X</span> Prohibited
        </span>
        <span>
          <span className="font-semibold text-violet-600">?</span> Unclear
        </span>
        <span className="text-slate-300">·</span>
        <span>Click any cell to override</span>
        {zones.some((z) => z.citations && z.citations.length > 0) && (
          <>
            <span className="text-slate-300">·</span>
            <span>Hover for parser citations</span>
          </>
        )}
      </div>
    </div>
  );
}
