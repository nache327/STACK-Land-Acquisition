"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CoverageTierPill } from "@/components/admin/CoverageTierPill";
import { RecommendedAction } from "@/components/admin/RecommendedAction";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useRefreshCoverage } from "@/hooks/useRefreshCoverage";
import {
  deriveRecommendedAction,
  deriveTier,
  TIERS,
  type CoverageTier,
} from "@/lib/admin/tier";

const TIER_ORDER: CoverageTier[] = ["T0", "T1", "T2", "T3", "T4", "T5", "T6"];

/** Operator-urgency rank used to sort the table. Highest-leverage first. */
const URGENCY_RANK: Record<CoverageTier, number> = {
  T3: 0, // verified sources waiting to be ingested = one click to value
  T2: 1, // pending review backlog
  T4: 2, // overlays exist, zoning codes incomplete
  T5: 3, // matrix incomplete
  T1: 4, // need discovery
  T0: 5, // empty
  T6: 6, // operational — bottom
};

type ScopeFilter = "all" | "action" | "operational";

export default function CoverageDashboardPage() {
  const coverage = useAdminCoverage();
  const refresh = useRefreshCoverage();

  const [scope, setScope] = useState<ScopeFilter>("action");
  const [tierFilter, setTierFilter] = useState<CoverageTier | "">("");
  const [stateFilter, setStateFilter] = useState("");
  const [q, setQ] = useState("");

  const rowsWithTier = useMemo(() => {
    const list = coverage.data?.jurisdictions ?? [];
    return list.map((r) => ({
      row: r,
      tier: deriveTier(r),
    }));
  }, [coverage.data]);

  const tierCounts = useMemo(() => {
    const out: Record<CoverageTier, number> = {
      T0: 0,
      T1: 0,
      T2: 0,
      T3: 0,
      T4: 0,
      T5: 0,
      T6: 0,
    };
    for (const r of rowsWithTier) out[r.tier]++;
    return out;
  }, [rowsWithTier]);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rowsWithTier
      .filter((r) => {
        if (tierFilter && r.tier !== tierFilter) return false;
        if (scope === "action" && r.tier === "T6") return false;
        if (scope === "operational" && r.tier !== "T6") return false;
        if (stateFilter && r.row.state !== stateFilter) return false;
        if (needle) {
          const hay = [
            r.row.jurisdiction_name,
            r.row.county,
            r.row.state,
          ]
            .filter(Boolean)
            .map((s) => String(s).toLowerCase())
            .join(" ");
          if (!hay.includes(needle)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const r = URGENCY_RANK[a.tier] - URGENCY_RANK[b.tier];
        if (r !== 0) return r;
        const aPend = a.row.source_count_pending ?? 0;
        const bPend = b.row.source_count_pending ?? 0;
        if (aPend !== bPend) return bPend - aPend;
        return a.row.jurisdiction_name.localeCompare(b.row.jurisdiction_name);
      });
  }, [rowsWithTier, scope, tierFilter, stateFilter, q]);

  const knownStates = useMemo(() => {
    const set = new Set<string>();
    for (const r of rowsWithTier) {
      if (r.row.state) set.add(r.row.state);
    }
    return Array.from(set).sort();
  }, [rowsWithTier]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">
            Coverage dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Pipeline state across all jurisdictions. Sorted by operator
            leverage — ingest-ready first, operational last.
          </p>
        </div>
        <button
          type="button"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate(null)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          title="Re-run the coverage audit for every jurisdiction (~2-3 min for a full sweep)"
        >
          {refresh.isPending ? "Refreshing all…" : "Refresh all"}
        </button>
      </header>

      {refresh.isError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(refresh.error as Error)?.message ?? "Refresh failed."}
        </div>
      )}
      {refresh.isSuccess && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          Audit complete · {refresh.data?.snapshots_written ?? "?"} snapshots
          written.
        </div>
      )}

      {/* Tier distribution */}
      <div className="grid grid-cols-7 gap-2">
        {TIER_ORDER.map((t) => {
          const active = tierFilter === t;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTierFilter(active ? "" : t)}
              className={[
                "rounded-md border px-2 py-1.5 text-left transition-colors",
                active
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white hover:bg-slate-50",
              ].join(" ")}
            >
              <div className="font-mono text-[11px] opacity-70">{t}</div>
              <div
                className={[
                  "truncate text-xs font-semibold",
                  active ? "text-white" : "text-slate-800",
                ].join(" ")}
              >
                {TIERS[t].label}
              </div>
              <div
                className={[
                  "mt-0.5 font-mono text-lg",
                  active ? "text-white" : "text-slate-900",
                ].join(" ")}
              >
                {tierCounts[t]}
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-3">
        <div className="flex gap-1 rounded-md border border-slate-200 p-0.5 text-xs">
          {(["action", "all", "operational"] as ScopeFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={[
                "rounded px-2 py-1 capitalize",
                scope === s
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-50",
              ].join(" ")}
            >
              {s === "action" ? "Action needed" : s}
            </button>
          ))}
        </div>
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            State
          </span>
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
          >
            <option value="">all</option>
            {knownStates.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search jurisdiction, county"
          className="flex-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={() => coverage.refetch()}
          className="rounded-md border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          {coverage.isFetching ? "Loading…" : "Reload"}
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Jurisdiction</th>
              <th className="px-3 py-2">Tier</th>
              <th className="px-3 py-2 text-right">Parcels</th>
              <th className="px-3 py-2 text-right">Z code %</th>
              <th className="px-3 py-2 text-right">SS %</th>
              <th className="px-3 py-2 text-right">Pending</th>
              <th className="px-3 py-2 text-right">Verified</th>
              <th className="px-3 py-2">Last audit</th>
              <th className="px-3 py-2">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {coverage.isPending && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
            {coverage.isError && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs text-rose-600">
                  {(coverage.error as Error)?.message ?? "Failed to load."}
                </td>
              </tr>
            )}
            {!coverage.isPending && !coverage.isError && visible.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No jurisdictions match these filters.
                </td>
              </tr>
            )}
            {visible.map(({ row, tier }) => {
              const action = deriveRecommendedAction(row);
              const zPct = row.parcel_zoning_code_coverage_pct;
              const ssPct = row.self_storage_classified_parcel_pct;
              return (
                <tr key={row.jurisdiction_id} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Link
                      href={`/admin/coverage/${row.jurisdiction_id}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {row.jurisdiction_name}
                    </Link>
                    {row.county && (
                      <span className="ml-1 text-xs text-slate-500">
                        · {row.county}
                      </span>
                    )}
                    {row.state && (
                      <span className="ml-1 font-mono text-xs text-slate-400">
                        {row.state}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <CoverageTierPill tier={tier} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {row.parcel_count ?? 0}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {zPct != null ? `${Math.round(zPct)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {ssPct != null ? `${Math.round(ssPct)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {(row.source_count_pending ?? 0) > 0 ? (
                      <span className="font-mono text-amber-700">
                        {row.source_count_pending}
                      </span>
                    ) : (
                      <span className="font-mono text-slate-300">0</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-600">
                    {row.source_count_verified ?? 0}
                  </td>
                  <td className="px-3 py-2 text-[11px] font-mono text-slate-500">
                    {row.captured_at ? row.captured_at.slice(0, 10) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <RecommendedAction action={action} />
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
