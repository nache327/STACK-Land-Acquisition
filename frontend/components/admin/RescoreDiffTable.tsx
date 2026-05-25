"use client";

import { useMemo, useState } from "react";
import { ThresholdCrossPill } from "./ThresholdCrossPill";
import { ValidationStatusPill, VerdictPill } from "./StatusPill";
import { suggestPostRescoreAction } from "@/lib/admin/staleSummary";
import type { RescoreChange, SpatialCheckVerdict } from "@/lib/schemas";

type DiffFilter =
  | "all"
  | "score_down"
  | "score_up"
  | "crossed_down"
  | "newly_disjoint"
  | "verified_at_risk";

interface Props {
  changes: RescoreChange[];
  selected: Set<string>;
  onToggle: (sourceId: string) => void;
  onToggleAll: () => void;
}

const FILTER_OPTIONS: { value: DiffFilter; label: string }[] = [
  { value: "all", label: "All changes" },
  { value: "score_down", label: "Score ↓" },
  { value: "score_up", label: "Score ↑" },
  { value: "crossed_down", label: "Crossed under 70" },
  { value: "newly_disjoint", label: "Newly disjoint" },
  { value: "verified_at_risk", label: "Verified at risk" },
];

export function RescoreDiffTable({
  changes,
  selected,
  onToggle,
  onToggleAll,
}: Props) {
  const [filter, setFilter] = useState<DiffFilter>("all");

  const filtered = useMemo(() => {
    return changes.filter((c) => {
      switch (filter) {
        case "score_down":
          return c.delta < 0;
        case "score_up":
          return c.delta > 0;
        case "crossed_down":
          return c.crosses_threshold_70 === "down";
        case "newly_disjoint":
          return c.live_verdict === "disjoint";
        case "verified_at_risk":
          return (
            c.validation_status === "verified"
            && (c.live_verdict === "disjoint" || c.live_verdict === "tiny")
          );
        default:
          return true;
      }
    });
  }, [changes, filter]);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        {FILTER_OPTIONS.map((o) => {
          const isActive = filter === o.value;
          const count = countFiltered(changes, o.value);
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => setFilter(o.value)}
              className={[
                "rounded px-2 py-1",
                isActive
                  ? "bg-slate-900 text-white"
                  : "border border-slate-200 text-slate-600 hover:bg-slate-50",
              ].join(" ")}
            >
              {o.label}
              <span
                className={[
                  "ml-1 font-mono",
                  isActive ? "opacity-80" : "text-slate-400",
                ].join(" ")}
              >
                {count}
              </span>
            </button>
          );
        })}
        <span className="ml-auto text-slate-500">
          Showing {filtered.length} of {changes.length}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-50 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-8 px-2 py-2">
                <input
                  type="checkbox"
                  aria-label="Select all visible"
                  checked={
                    filtered.length > 0
                    && filtered.every((c) => selected.has(c.source_id))
                  }
                  onChange={onToggleAll}
                />
              </th>
              <th className="px-2 py-2">Municipality</th>
              <th className="px-2 py-2">Layer</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2 text-right">Before</th>
              <th className="px-2 py-2 text-right">After</th>
              <th className="px-2 py-2 text-right">Δ</th>
              <th className="px-2 py-2">Cross 70</th>
              <th className="px-2 py-2">Live</th>
              <th className="px-2 py-2">Suggested</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No rows match this filter.
                </td>
              </tr>
            )}
            {filtered.map((c) => {
              const suggestion = suggestPostRescoreAction(c);
              const isChecked = selected.has(c.source_id);
              const before = c.before.confidence_score ?? 0;
              const after = c.after.confidence_score ?? 0;
              return (
                <tr
                  key={c.source_id}
                  className={[
                    isChecked
                      ? "bg-sky-50"
                      : c.live_verdict === "disjoint"
                        ? "bg-rose-50/40"
                        : "hover:bg-slate-50",
                  ].join(" ")}
                >
                  <td className="px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => onToggle(c.source_id)}
                    />
                  </td>
                  <td className="px-2 py-1.5 font-medium text-slate-800">
                    {c.municipality_name ?? "—"}
                  </td>
                  <td className="px-2 py-1.5 text-slate-600">
                    <span
                      className="block max-w-[260px] truncate"
                      title={c.title ?? undefined}
                    >
                      {c.title ?? c.zoning_endpoint ?? "—"}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <ValidationStatusPill status={c.validation_status} />
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {before}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {after}
                  </td>
                  <td
                    className={[
                      "px-2 py-1.5 text-right font-mono font-semibold",
                      c.delta < 0
                        ? "text-rose-700"
                        : c.delta > 0
                          ? "text-emerald-700"
                          : "text-slate-400",
                    ].join(" ")}
                  >
                    {c.delta >= 0 ? "+" : ""}
                    {c.delta}
                  </td>
                  <td className="px-2 py-1.5">
                    <ThresholdCrossPill direction={c.crosses_threshold_70} />
                  </td>
                  <td className="px-2 py-1.5">
                    {c.live_verdict ? (
                      <VerdictPill verdict={c.live_verdict as SpatialCheckVerdict} />
                    ) : (
                      <span className="text-[10px] text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <SuggestionPill suggestion={suggestion} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function countFiltered(changes: RescoreChange[], f: DiffFilter): number {
  return changes.filter((c) => {
    switch (f) {
      case "score_down":
        return c.delta < 0;
      case "score_up":
        return c.delta > 0;
      case "crossed_down":
        return c.crosses_threshold_70 === "down";
      case "newly_disjoint":
        return c.live_verdict === "disjoint";
      case "verified_at_risk":
        return (
          c.validation_status === "verified"
          && (c.live_verdict === "disjoint" || c.live_verdict === "tiny")
        );
      default:
        return true;
    }
  }).length;
}

function SuggestionPill({
  suggestion,
}: {
  suggestion: ReturnType<typeof suggestPostRescoreAction>;
}) {
  if (suggestion === "none") {
    return <span className="text-[10px] text-slate-300">—</span>;
  }
  const colour =
    suggestion === "reject"
      ? "bg-rose-50 text-rose-800 border-rose-200"
      : suggestion === "needs_review"
        ? "bg-indigo-50 text-indigo-800 border-indigo-200"
        : "bg-emerald-50 text-emerald-800 border-emerald-200";
  const label =
    suggestion === "verify_candidate"
      ? "verify?"
      : suggestion.replace("_", " ");
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        colour,
      ].join(" ")}
    >
      {label}
    </span>
  );
}
