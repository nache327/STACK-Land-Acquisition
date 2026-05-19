"use client";

import Link from "next/link";
import type { StaleJurisdictionRow } from "@/lib/admin/staleSummary";

interface Props {
  rows: StaleJurisdictionRow[];
}

export function StaleJurisdictionSummary({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-4 text-center text-xs text-emerald-800">
        No stale rows detected — every source has bbox_overlap_* signals.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Jurisdiction</th>
            <th className="px-3 py-2 text-right">Stale</th>
            <th className="px-3 py-2 text-right">Pending</th>
            <th className="px-3 py-2 text-right">Verified</th>
            <th className="px-3 py-2 text-right">Rejected</th>
            <th className="px-3 py-2 text-right">Top score</th>
            <th className="px-3 py-2 text-right">Latest stale</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.jurisdiction_id} className="hover:bg-slate-50">
              <td className="px-3 py-2">
                <Link
                  href={`/admin/stale/${r.jurisdiction_id}`}
                  className="font-medium text-slate-900 hover:underline"
                >
                  {r.jurisdiction_name}
                </Link>
                {r.state && (
                  <span className="ml-1 font-mono text-[10px] text-slate-400">
                    {r.state}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono text-rose-700">
                {r.total_stale}
              </td>
              <td className="px-3 py-2 text-right font-mono text-amber-700">
                {r.stale_pending}
              </td>
              <td className="px-3 py-2 text-right font-mono text-emerald-700">
                {r.stale_verified}
              </td>
              <td className="px-3 py-2 text-right font-mono text-slate-400">
                {r.stale_rejected}
              </td>
              <td className="px-3 py-2 text-right font-mono">
                {r.max_confidence_score ?? "—"}
              </td>
              <td className="px-3 py-2 text-right font-mono text-[11px] text-slate-500">
                {r.latest_stale_updated_at
                  ? r.latest_stale_updated_at.slice(0, 10)
                  : "—"}
              </td>
              <td className="px-3 py-2 text-right">
                <Link
                  href={`/admin/stale/${r.jurisdiction_id}`}
                  className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-slate-800"
                >
                  Rescore →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
