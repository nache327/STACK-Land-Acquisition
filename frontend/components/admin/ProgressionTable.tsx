"use client";

import type { ProgressionSnapshot } from "@/lib/schemas";

const READINESS_TONE: Record<string, string> = {
  operational: "text-emerald-700",
  partial: "text-amber-700",
  not_loaded: "text-slate-400",
};

interface Props {
  snapshots: ProgressionSnapshot[];
}

export function ProgressionTable({ snapshots }: Props) {
  if (snapshots.length === 0) {
    return (
      <p className="text-[11px] italic text-slate-400">
        No snapshots in the selected window — run a refresh to start the
        series.
      </p>
    );
  }
  // Newest first so the operator sees current state at the top, and the
  // delta direction is read top-to-bottom.
  const ordered = [...snapshots].sort((a, b) =>
    b.captured_at.localeCompare(a.captured_at),
  );
  const first = ordered[ordered.length - 1];

  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-1.5">Captured</th>
            <th className="px-3 py-1.5 text-right">Parcels</th>
            <th className="px-3 py-1.5 text-right">With zoning</th>
            <th className="px-3 py-1.5 text-right">Districts</th>
            <th className="px-3 py-1.5">Readiness</th>
            <th className="px-3 py-1.5 text-right">Δ vs first</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {ordered.map((s) => {
            const deltaParcels = s.parcel_count - first.parcel_count;
            const deltaZ = s.parcel_with_zoning_code_count
              - first.parcel_with_zoning_code_count;
            return (
              <tr key={s.captured_at}>
                <td className="px-3 py-1 font-mono text-slate-500">
                  {s.captured_at.slice(0, 16).replace("T", " ")}
                </td>
                <td className="px-3 py-1 text-right font-mono">
                  {s.parcel_count}
                </td>
                <td className="px-3 py-1 text-right font-mono">
                  {s.parcel_with_zoning_code_count}
                </td>
                <td className="px-3 py-1 text-right font-mono">
                  {s.zoning_district_count}
                </td>
                <td
                  className={[
                    "px-3 py-1 font-medium",
                    READINESS_TONE[s.operational_readiness] ?? "text-slate-600",
                  ].join(" ")}
                >
                  {s.operational_readiness}
                </td>
                <td className="px-3 py-1 text-right font-mono text-[11px]">
                  <span className={deltaParcels >= 0 ? "text-slate-400" : "text-rose-600"}>
                    parcels {deltaParcels >= 0 ? "+" : ""}
                    {deltaParcels}
                  </span>{" "}
                  <span className={deltaZ >= 0 ? "text-emerald-700" : "text-rose-600"}>
                    z {deltaZ >= 0 ? "+" : ""}
                    {deltaZ}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
