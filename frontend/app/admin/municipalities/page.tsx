"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { MunicipalityBlockerList } from "@/components/admin/MunicipalityBlockerList";
import { MunicipalityHealthDot } from "@/components/admin/MunicipalityHealthDot";
import { MunicipalityTierPill } from "@/components/admin/MunicipalityTierPill";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useSourcesQueue } from "@/hooks/useSourcesQueue";
import {
  buildCrossJurisdictionMunicipalityRollup,
  deriveMunicipalityBlockers,
  deriveMunicipalityHealth,
  deriveMunicipalityTier,
  recommendMunicipalityAction,
  tierUrgency,
  type MunicipalitySnapshot,
  type MunicipalityTier,
} from "@/lib/admin/municipalityOps";

type SortMode = "readiness" | "roi" | "blocked" | "alpha";

const ALL_TIERS: MunicipalityTier[] = [
  "M0",
  "M1",
  "M2",
  "M3",
  "M4",
  "M5",
  "M6",
];

export default function MunicipalitiesPage() {
  const coverage = useAdminCoverage();
  // Pull all sources cross-jurisdiction in one call. 2000 cap matches the
  // backend hard cap; this is the lightest "all-sources" lookup we have.
  const allSources = useSourcesQueue({ limit: 2000 });

  const [sortMode, setSortMode] = useState<SortMode>("readiness");
  const [tierFilter, setTierFilter] = useState<MunicipalityTier | "">("");
  const [stateFilter, setStateFilter] = useState("");
  const [q, setQ] = useState("");
  const [hideOperational, setHideOperational] = useState(true);

  const rows = useMemo(() => {
    if (!coverage.data || !allSources.data) return [];
    return buildCrossJurisdictionMunicipalityRollup({
      jurisdictions: coverage.data.jurisdictions,
      sources: allSources.data.sources,
    });
  }, [coverage.data, allSources.data]);

  const tierCounts = useMemo(() => {
    const out: Record<MunicipalityTier, number> = {
      M0: 0,
      M1: 0,
      M2: 0,
      M3: 0,
      M4: 0,
      M5: 0,
      M6: 0,
    };
    for (const r of rows) out[deriveMunicipalityTier(r)] += 1;
    return out;
  }, [rows]);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = rows.filter((r) => {
      const tier = deriveMunicipalityTier(r);
      if (tierFilter && tier !== tierFilter) return false;
      if (hideOperational && tier === "M6" && !tierFilter) return false;
      if (stateFilter && r.state !== stateFilter) return false;
      if (needle) {
        const hay = `${r.municipality} ${r.jurisdiction_name} ${r.state ?? ""}`
          .toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    const sorted = [...filtered].sort((a, b) => {
      switch (sortMode) {
        case "readiness":
          return (
            tierUrgency(deriveMunicipalityTier(a))
              - tierUrgency(deriveMunicipalityTier(b))
            || (b.parcels - b.parcels_with_zoning)
              - (a.parcels - a.parcels_with_zoning)
            || a.municipality.localeCompare(b.municipality)
          );
        case "roi":
          return (
            (b.parcels - b.parcels_with_zoning)
              - (a.parcels - a.parcels_with_zoning)
            || a.municipality.localeCompare(b.municipality)
          );
        case "blocked":
          return (
            b.spatial_blocked_count - a.spatial_blocked_count
            || tierUrgency(deriveMunicipalityTier(a))
              - tierUrgency(deriveMunicipalityTier(b))
            || a.municipality.localeCompare(b.municipality)
          );
        case "alpha":
          return a.municipality.localeCompare(b.municipality);
      }
    });
    return sorted;
  }, [rows, sortMode, tierFilter, stateFilter, q, hideOperational]);

  const knownStates = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) {
      if (r.state) s.add(r.state);
    }
    return Array.from(s).sort();
  }, [rows]);

  const totals = useMemo(() => {
    const t = visible.reduce(
      (acc, r) => {
        acc.unzoned += r.parcels - r.parcels_with_zoning;
        acc.pending += r.source_count_pending;
        acc.verified += r.source_count_verified;
        acc.blocked += r.spatial_blocked_count;
        return acc;
      },
      { unzoned: 0, pending: 0, verified: 0, blocked: 0 },
    );
    return t;
  }, [visible]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Municipalities</h1>
        <p className="mt-1 text-sm text-slate-500">
          Cross-jurisdiction town view ranked by operator leverage. Each row
          is one town × parent jurisdiction; click for the drilldown.
        </p>
      </header>

      {/* Tier distribution as filter chips */}
      <div className="grid grid-cols-7 gap-2">
        {ALL_TIERS.map((t) => {
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

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="text-[11px] font-medium text-slate-500">Sort:</span>
          <SortButton label="Readiness" mode="readiness" active={sortMode === "readiness"} onSet={setSortMode} />
          <SortButton label="ROI" mode="roi" active={sortMode === "roi"} onSet={setSortMode} />
          <SortButton label="Most blocked" mode="blocked" active={sortMode === "blocked"} onSet={setSortMode} />
          <SortButton label="A→Z" mode="alpha" active={sortMode === "alpha"} onSet={setSortMode} />
        </div>
        <label className="flex items-center gap-1 text-[11px] text-slate-600">
          <input
            type="checkbox"
            checked={hideOperational}
            onChange={(e) => setHideOperational(e.target.checked)}
          />
          Hide M6 (operational)
        </label>
        <label className="text-[11px]">
          <span className="block font-medium uppercase tracking-wide text-slate-500">
            State
          </span>
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1"
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
          placeholder="Search town, jurisdiction"
          className="flex-1 rounded-md border border-slate-200 px-2 py-1"
        />
      </div>

      {/* Roll-up totals — non-dashboard, just an inline summary */}
      <p className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600">
        <strong className="text-slate-800">{visible.length}</strong> towns shown ·
        {" "}{totals.unzoned.toLocaleString()} unzoned parcels ·
        {" "}<span className="text-amber-700">{totals.pending}</span> pending ·
        {" "}<span className="text-emerald-700">{totals.verified}</span> verified ·
        {totals.blocked > 0 && (
          <span className="ml-1 text-rose-700">{totals.blocked} spatial-blocked sources</span>
        )}
      </p>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-6 px-2 py-2"></th>
              <th className="px-3 py-2">Municipality</th>
              <th className="px-3 py-2">Tier</th>
              <th className="px-3 py-2 text-right">Parcels</th>
              <th className="px-3 py-2 text-right">Unzoned</th>
              <th className="px-3 py-2 text-right">Pending</th>
              <th className="px-3 py-2 text-right">Verified</th>
              <th className="px-3 py-2">Blockers</th>
              <th className="px-3 py-2">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(coverage.isPending || allSources.isPending) && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
            {(coverage.isError || allSources.isError) && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs text-rose-600">
                  {(coverage.error as Error)?.message
                    ?? (allSources.error as Error)?.message
                    ?? "Failed to load."}
                </td>
              </tr>
            )}
            {!coverage.isPending
              && !allSources.isPending
              && !coverage.isError
              && !allSources.isError
              && visible.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No municipalities match.
                </td>
              </tr>
            )}
            {visible.map((m) => (
              <Row key={`${m.jurisdiction_id}::${m.municipality}`} m={m} />
            ))}
          </tbody>
        </table>
      </div>

      {allSources.data && allSources.data.total > allSources.data.count && (
        <p className="text-[11px] italic text-amber-700">
          Cross-jurisdiction source fetch is capped at {allSources.data.limit}.
          Backend reports {allSources.data.total} total — some town source
          counts may be incomplete. Drill into a town for the authoritative
          per-municipality list.
        </p>
      )}
    </div>
  );
}

function Row({ m }: { m: MunicipalitySnapshot }) {
  const tier = deriveMunicipalityTier(m);
  const blockers = deriveMunicipalityBlockers(m);
  const health = deriveMunicipalityHealth(m);
  const action = recommendMunicipalityAction(m);
  const drilldownHref = `/admin/municipalities/${m.jurisdiction_id}/${encodeURIComponent(m.municipality)}`;
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-2 py-2 text-center">
        <MunicipalityHealthDot health={health} />
      </td>
      <td className="px-3 py-2">
        <Link
          href={drilldownHref}
          className="font-medium text-slate-900 hover:underline"
        >
          {m.municipality}
        </Link>
        <div className="text-[11px] text-slate-500">
          {m.jurisdiction_name}
          {m.state && (
            <span className="ml-1 font-mono text-[10px] text-slate-400">
              {m.state}
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2">
        <MunicipalityTierPill tier={tier} />
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {m.parcels.toLocaleString()}
      </td>
      <td className="px-3 py-2 text-right font-mono text-rose-700">
        {(m.parcels - m.parcels_with_zoning).toLocaleString()}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {m.source_count_pending > 0 ? (
          <span className="text-amber-700">{m.source_count_pending}</span>
        ) : (
          <span className="text-slate-300">0</span>
        )}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {m.source_count_verified > 0 ? (
          <span className="text-emerald-700">{m.source_count_verified}</span>
        ) : (
          <span className="text-slate-300">0</span>
        )}
      </td>
      <td className="px-3 py-2">
        <MunicipalityBlockerList blockers={blockers} inline />
      </td>
      <td className="px-3 py-2">
        {action.actionable ? (
          <Link
            href={drilldownHref}
            className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-slate-800"
            title={
              action.href
                ? `Drills into the municipality workspace where the runbook executes this step. The legacy deep-link is reachable from inside the runbook.`
                : undefined
            }
          >
            {action.text} →
          </Link>
        ) : (
          <span className="text-[11px] text-slate-500">{action.text}</span>
        )}
      </td>
    </tr>
  );
}

function SortButton({
  label,
  mode,
  active,
  onSet,
}: {
  label: string;
  mode: SortMode;
  active: boolean;
  onSet: (m: SortMode) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSet(mode)}
      className={[
        "rounded px-2 py-0.5",
        active
          ? "bg-slate-900 text-white"
          : "border border-slate-200 text-slate-600 hover:bg-slate-50",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
