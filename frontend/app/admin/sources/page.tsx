"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";

export default function SourcesPickerPage() {
  const [q, setQ] = useState("");
  const { data, isPending, isError, error } = useAdminCoverage();

  const rows = useMemo(() => {
    const list = data?.jurisdictions ?? [];
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? list.filter((j) =>
          [j.jurisdiction_name, j.county, j.state]
            .filter(Boolean)
            .some((s) => String(s).toLowerCase().includes(needle)),
        )
      : list;
    // Surface the jurisdictions where operator attention matters most:
    // anything with pending sources first, then by total source volume.
    return [...filtered].sort((a, b) => {
      const aPending = a.source_count_pending ?? 0;
      const bPending = b.source_count_pending ?? 0;
      if (aPending !== bPending) return bPending - aPending;
      return (
        (b.source_count_total ?? 0) - (a.source_count_total ?? 0) ||
        a.jurisdiction_name.localeCompare(b.jurisdiction_name)
      );
    });
  }, [data, q]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">
          Source review — pick a jurisdiction
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Jurisdictions with pending zoning sources are surfaced first. Click a
          row to triage.
        </p>
      </header>

      <input
        type="search"
        placeholder="Search by name, county, or state"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
      />

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Jurisdiction</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2 text-right">Pending</th>
              <th className="px-3 py-2 text-right">Verified</th>
              <th className="px-3 py-2 text-right">Rejected</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isPending && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  Loading coverage…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-rose-600">
                  {(error as Error)?.message ?? "Coverage load failed."}
                </td>
              </tr>
            )}
            {!isPending && !isError && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No jurisdictions match.
                </td>
              </tr>
            )}
            {rows.map((j) => {
              const pending = j.source_count_pending ?? 0;
              const verified = j.source_count_verified ?? 0;
              const rejected = j.source_count_rejected ?? 0;
              const total = j.source_count_total ?? 0;
              return (
                <tr key={j.jurisdiction_id} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Link
                      href={`/admin/sources/${j.jurisdiction_id}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {j.jurisdiction_name}
                    </Link>
                    {j.county && (
                      <span className="ml-1 text-xs text-slate-500">
                        · {j.county}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">
                    {j.state ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {pending > 0 ? (
                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800">
                        {pending}
                      </span>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-600">
                    {verified}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-400">
                    {rejected}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-700">
                    {total}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      href={`/admin/sources/${j.jurisdiction_id}?status=pending`}
                      className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                    >
                      Review →
                    </Link>
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
