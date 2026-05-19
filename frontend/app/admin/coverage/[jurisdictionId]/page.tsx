"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { BlockingGapsPanel } from "@/components/admin/BlockingGapsPanel";
import { CoverageTierPill } from "@/components/admin/CoverageTierPill";
import { MunicipalityBreakdownTable } from "@/components/admin/MunicipalityBreakdownTable";
import { ProgressionTable } from "@/components/admin/ProgressionTable";
import { RecommendedAction } from "@/components/admin/RecommendedAction";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useAdminSources } from "@/hooks/useAdminSources";
import { useCoverageProgression } from "@/hooks/useCoverageProgression";
import { useRefreshCoverage } from "@/hooks/useRefreshCoverage";
import {
  buildMunicipalityRollup,
  parseMunicipalityBreakdown,
} from "@/lib/admin/municipality";
import {
  deriveRecommendedAction,
  deriveTier,
  TIERS,
} from "@/lib/admin/tier";

export default function CoverageDrilldownPage() {
  const params = useParams<{ jurisdictionId: string }>();
  const jurisdictionId = params.jurisdictionId;
  const [days, setDays] = useState(30);

  const coverage = useAdminCoverage();
  const refresh = useRefreshCoverage();
  const progression = useCoverageProgression(jurisdictionId, days);
  const sources = useAdminSources(jurisdictionId, { limit: 500 });

  const row = useMemo(
    () =>
      coverage.data?.jurisdictions.find(
        (j) => j.jurisdiction_id === jurisdictionId,
      ),
    [coverage.data, jurisdictionId],
  );

  const tier = row ? deriveTier(row) : null;
  const action = row ? deriveRecommendedAction(row) : null;

  const rollup = useMemo(() => {
    if (!row) return [];
    return buildMunicipalityRollup({
      breakdown: parseMunicipalityBreakdown(row.municipality_breakdown),
      sources: sources.data?.sources ?? [],
    });
  }, [row, sources.data]);

  const blockedCount = rollup.filter((r) => r.spatial_blocked).length;
  const ingestReadyCount = rollup.filter((r) => r.status === "ingest_ready").length;
  const reviewBacklog = rollup.filter((r) => r.status === "review_backlog").length;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            <Link href="/admin/coverage" className="hover:underline">
              Coverage
            </Link>{" "}
            ·{" "}
            <span className="font-mono text-slate-400">
              {jurisdictionId.slice(0, 8)}
            </span>
          </p>
          <h1 className="truncate text-lg font-semibold text-slate-900">
            {row?.jurisdiction_name ?? "Jurisdiction"}
          </h1>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            {row?.county && <span>{row.county}</span>}
            {row?.state && <span className="font-mono">{row.state}</span>}
            <span>·</span>
            <span>
              snapshot{" "}
              {row?.captured_at ? row.captured_at.slice(0, 16).replace("T", " ") : "—"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {tier && <CoverageTierPill tier={tier} size="md" />}
          <button
            type="button"
            onClick={() => refresh.mutate(jurisdictionId)}
            disabled={refresh.isPending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {refresh.isPending ? "Refreshing…" : "Refresh this jurisdiction"}
          </button>
        </div>
      </header>

      {action && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Next action ({TIERS[action.tier].label})
          </div>
          <div className="mt-1 flex items-center gap-2">
            <RecommendedAction action={action} />
            <span className="text-xs text-slate-500">
              {TIERS[action.tier].stage}
            </span>
          </div>
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Parcels"
          value={(row?.parcel_count ?? 0).toLocaleString()}
        />
        <Stat
          label="Zoning code coverage"
          value={
            row?.parcel_zoning_code_coverage_pct != null
              ? `${Math.round(row.parcel_zoning_code_coverage_pct)}%`
              : "—"
          }
        />
        <Stat
          label="Self-storage classified"
          value={
            row?.self_storage_classified_parcel_pct != null
              ? `${Math.round(row.self_storage_classified_parcel_pct)}%`
              : "—"
          }
        />
        <Stat
          label="Districts"
          value={(row?.zoning_district_count ?? 0).toLocaleString()}
        />
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Sources pending"
          value={String(row?.source_count_pending ?? 0)}
          tone={row && (row.source_count_pending ?? 0) > 0 ? "amber" : "slate"}
        />
        <Stat
          label="Sources verified"
          value={String(row?.source_count_verified ?? 0)}
          tone={row && (row.source_count_verified ?? 0) > 0 ? "emerald" : "slate"}
        />
        <Stat
          label="Spatially-blocked towns"
          value={String(blockedCount)}
          tone={blockedCount > 0 ? "rose" : "slate"}
        />
        <Stat
          label="Ingest-ready towns"
          value={String(ingestReadyCount)}
          tone={ingestReadyCount > 0 ? "sky" : "slate"}
        />
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Blocking gaps
        </h2>
        <div className="mt-2">
          <BlockingGapsPanel gaps={row?.blocking_gaps} />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Progression
          </h2>
          <div className="flex gap-1 text-[11px]">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDays(d)}
                className={[
                  "rounded px-2 py-0.5",
                  days === d
                    ? "bg-slate-900 text-white"
                    : "border border-slate-200 text-slate-600 hover:bg-slate-50",
                ].join(" ")}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        {progression.isPending && (
          <p className="text-[11px] italic text-slate-400">
            Loading progression…
          </p>
        )}
        {progression.isError && (
          <p className="text-[11px] text-rose-600">
            {(progression.error as Error)?.message ?? "Progression load failed."}
          </p>
        )}
        {progression.data && (
          <ProgressionTable snapshots={progression.data.snapshots} />
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Municipalities · {rollup.length}
          </h2>
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            {reviewBacklog > 0 && (
              <span>{reviewBacklog} with review backlog</span>
            )}
            {sources.isFetching && <span>(refreshing sources…)</span>}
          </div>
        </div>
        {sources.isPending && (
          <p className="text-[11px] italic text-slate-400">Loading sources…</p>
        )}
        {sources.isError && (
          <p className="text-[11px] text-rose-600">
            {(sources.error as Error)?.message ?? "Sources load failed."}
          </p>
        )}
        {!sources.isPending && (
          <MunicipalityBreakdownTable
            jurisdictionId={jurisdictionId}
            rows={rollup}
          />
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "slate" | "amber" | "emerald" | "sky" | "rose";
}) {
  const toneClass =
    tone === "amber"
      ? "text-amber-800"
      : tone === "emerald"
        ? "text-emerald-800"
        : tone === "sky"
          ? "text-sky-800"
          : tone === "rose"
            ? "text-rose-800"
            : "text-slate-900";
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className={["mt-1 font-mono text-xl font-semibold", toneClass].join(" ")}>
        {value}
      </div>
    </div>
  );
}
