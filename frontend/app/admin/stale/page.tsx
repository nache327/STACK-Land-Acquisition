"use client";

import { useMemo, useState } from "react";
import { StaleJurisdictionSummary } from "@/components/admin/StaleJurisdictionSummary";
import { useSourcesQueue } from "@/hooks/useSourcesQueue";
import { groupStaleByJurisdiction } from "@/lib/admin/staleSummary";

export default function StaleIndexPage() {
  const [q, setQ] = useState("");
  const stale = useSourcesQueue({
    stale_only: true,
    limit: 2000,
  });

  const grouped = useMemo(() => {
    const rows = stale.data?.sources ?? [];
    const all = groupStaleByJurisdiction(rows);
    const needle = q.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((j) =>
      [j.jurisdiction_name, j.state]
        .filter(Boolean)
        .some((s) => String(s).toLowerCase().includes(needle)),
    );
  }, [stale.data, q]);

  const totals = useMemo(() => {
    return grouped.reduce(
      (acc, j) => {
        acc.jurisdictions += 1;
        acc.rows += j.total_stale;
        acc.pending += j.stale_pending;
        acc.verified += j.stale_verified;
        return acc;
      },
      { jurisdictions: 0, rows: 0, pending: 0, verified: 0 },
    );
  }, [grouped]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">
          Stale-score remediation
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Rows scored before the 2026-05-12 pyproj + bbox-overlap fix (no
          <code className="mx-1 rounded bg-slate-100 px-1 text-xs">bbox_overlap_*</code>
          component in <code className="rounded bg-slate-100 px-1 text-xs">confidence_breakdown</code>).
          Pick a jurisdiction, run a dry-run, review the diff, then apply.
          The apply step is reversible from the returned snapshot.
        </p>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Jurisdictions w/ stale" value={totals.jurisdictions} />
        <Stat label="Stale rows total" value={totals.rows} tone="rose" />
        <Stat label="Pending" value={totals.pending} tone="amber" />
        <Stat
          label="Verified at risk"
          value={totals.verified}
          tone={totals.verified > 0 ? "rose" : "muted"}
          hint="Verified rows that predate the scorer fix — never auto-mutated by rescore, but a rescore preview can flag mis-classified ones for operator action."
        />
      </section>

      <div className="flex items-end gap-3 rounded-md border border-slate-200 bg-white p-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by jurisdiction or state"
          className="flex-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={() => stale.refetch()}
          className="rounded-md border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          {stale.isFetching ? "Reloading…" : "Reload"}
        </button>
      </div>

      {stale.isPending && (
        <p className="text-[11px] italic text-slate-400">
          Loading stale rows…
        </p>
      )}
      {stale.isError && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(stale.error as Error)?.message ?? "Failed to load stale rows."}
        </p>
      )}
      {!stale.isPending && !stale.isError && (
        <StaleJurisdictionSummary rows={grouped} />
      )}

      {stale.data && stale.data.total > stale.data.count && (
        <p className="text-[11px] italic text-amber-700">
          Page returns up to {stale.data.limit} rows (server cap 2000). Backend
          reports {stale.data.total} stale rows total — drill into a jurisdiction
          to rescore in bounded batches.
        </p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "slate",
  hint,
}: {
  label: string;
  value: number | string;
  tone?: "slate" | "amber" | "emerald" | "rose" | "muted";
  hint?: string;
}) {
  const toneClass =
    tone === "rose"
      ? "text-rose-700"
      : tone === "emerald"
        ? "text-emerald-700"
        : tone === "amber"
          ? "text-amber-700"
          : tone === "muted"
            ? "text-slate-400"
            : "text-slate-900";
  return (
    <div
      title={hint}
      className="rounded-md border border-slate-200 bg-white p-3"
    >
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className={["mt-1 font-mono text-xl font-semibold", toneClass].join(" ")}>
        {value}
      </div>
    </div>
  );
}
