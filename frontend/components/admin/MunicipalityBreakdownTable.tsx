"use client";

import Link from "next/link";
import {
  STATUS_LABEL,
  type MunicipalityRollup,
  type MunicipalityStatus,
} from "@/lib/admin/municipality";

const STATUS_TONE: Record<MunicipalityStatus, string> = {
  spatially_blocked: "bg-rose-50 text-rose-800 border-rose-200",
  review_backlog: "bg-amber-50 text-amber-800 border-amber-200",
  ingest_ready: "bg-sky-50 text-sky-800 border-sky-200",
  needs_discovery: "bg-slate-100 text-slate-700 border-slate-200",
  ready: "bg-emerald-50 text-emerald-800 border-emerald-200",
  no_parcels: "bg-slate-50 text-slate-500 border-slate-200",
};

interface Props {
  jurisdictionId: string;
  rows: MunicipalityRollup[];
}

export function MunicipalityBreakdownTable({ jurisdictionId, rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="text-[11px] italic text-slate-400">
        No per-municipality breakdown captured for this jurisdiction. (City
        field is null on parcels or no parcels loaded.)
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-1.5">Municipality</th>
            <th className="px-3 py-1.5">Status</th>
            <th className="px-3 py-1.5 text-right">Parcels</th>
            <th className="px-3 py-1.5 text-right">w/ zoning</th>
            <th className="px-3 py-1.5 text-right">Districts</th>
            <th className="px-3 py-1.5 text-right">Pending</th>
            <th className="px-3 py-1.5 text-right">Verified</th>
            <th className="px-3 py-1.5"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => {
            const pct = r.parcels > 0
              ? Math.round((r.parcels_with_zoning / r.parcels) * 100)
              : null;
            return (
              <tr key={r.name}>
                <td className="px-3 py-1 font-medium text-slate-800">
                  <Link
                    href={`/admin/municipalities/${jurisdictionId}/${encodeURIComponent(r.name)}`}
                    className="hover:underline"
                  >
                    {r.name}
                  </Link>
                  {r.spatial_blocked && (
                    <span
                      className="ml-1 align-middle text-[10px] font-medium text-rose-700"
                      title="At least one source flagged as wrong-state / disjoint / wrong-county by the scorer."
                    >
                      ◆ CRS
                    </span>
                  )}
                </td>
                <td className="px-3 py-1">
                  <span
                    className={[
                      "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                      STATUS_TONE[r.status],
                    ].join(" ")}
                  >
                    {STATUS_LABEL[r.status]}
                  </span>
                </td>
                <td className="px-3 py-1 text-right font-mono">{r.parcels}</td>
                <td className="px-3 py-1 text-right font-mono">
                  {r.parcels_with_zoning}
                  {pct != null && (
                    <span className="ml-1 text-[10px] text-slate-400">
                      {pct}%
                    </span>
                  )}
                </td>
                <td className="px-3 py-1 text-right font-mono">
                  {r.zoning_overlays}
                </td>
                <td className="px-3 py-1 text-right">
                  {r.source_pending > 0 ? (
                    <span className="font-mono text-amber-700">
                      {r.source_pending}
                    </span>
                  ) : (
                    <span className="font-mono text-slate-300">0</span>
                  )}
                </td>
                <td className="px-3 py-1 text-right">
                  {r.source_verified > 0 ? (
                    <span className="font-mono text-emerald-700">
                      {r.source_verified}
                    </span>
                  ) : (
                    <span className="font-mono text-slate-300">0</span>
                  )}
                </td>
                <td className="px-3 py-1 text-right">
                  {r.source_total > 0 && (
                    <Link
                      href={`/admin/sources/${jurisdictionId}?municipality=${encodeURIComponent(r.name)}`}
                      className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                    >
                      Sources →
                    </Link>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
