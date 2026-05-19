"use client";

import { TrustworthinessPill } from "./TrustworthinessPill";
import type { RemediationMunicipality } from "@/lib/schemas";

interface Props {
  rows: RemediationMunicipality[];
  active: string | null;
  onPick: (municipality: string) => void;
}

const BAND_PRIORITY: Record<string, number> = {
  broken: 0,
  degraded: 1,
  partial: 2,
  empty: 3,
  operational: 4,
};

/** Side-rail of other municipalities in the same jurisdiction, ordered by
 *  worst-band-first, then most-step-rich. Click swaps the active town.
 *  Intentionally minimal — this is a picker, not a dashboard. */
export function OpsTownQueue({ rows, active, onPick }: Props) {
  const ordered = [...rows].sort((a, b) => {
    const aRank = BAND_PRIORITY[a.trustworthiness] ?? 99;
    const bRank = BAND_PRIORITY[b.trustworthiness] ?? 99;
    if (aRank !== bRank) return aRank - bRank;
    return b.remediation.steps.length - a.remediation.steps.length;
  });

  return (
    <aside className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Other towns ({rows.length})
      </div>
      <ul className="max-h-[60vh] divide-y divide-slate-100 overflow-y-auto">
        {ordered.map((m) => {
          const muni = m.municipality ?? "(no municipality)";
          const isActive = muni === active;
          const steps = m.remediation.steps.length;
          return (
            <li key={muni}>
              <button
                type="button"
                onClick={() => onPick(muni)}
                className={[
                  "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs",
                  isActive
                    ? "bg-slate-900 text-white"
                    : "text-slate-700 hover:bg-slate-50",
                ].join(" ")}
              >
                <span className="min-w-0 truncate font-medium">
                  {muni}
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  {!isActive && <TrustworthinessPill band={m.trustworthiness} />}
                  <span
                    className={[
                      "font-mono text-[10px]",
                      isActive ? "text-white/70" : "text-slate-400",
                    ].join(" ")}
                  >
                    {steps} step{steps === 1 ? "" : "s"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
