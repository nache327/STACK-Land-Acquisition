"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CrossJurisdictionSourceTable } from "@/components/admin/CrossJurisdictionSourceTable";
import { MunicipalityBlockerList } from "@/components/admin/MunicipalityBlockerList";
import { MunicipalityHealthDot } from "@/components/admin/MunicipalityHealthDot";
import { MunicipalityRunbookPanel } from "@/components/admin/MunicipalityRunbookPanel";
import {
  MunicipalityProgressionBar,
  MunicipalityTierPill,
} from "@/components/admin/MunicipalityTierPill";
import { SourceDetailDrawer } from "@/components/admin/SourceDetailDrawer";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useSourcesQueue } from "@/hooks/useSourcesQueue";
import {
  parseMunicipalityBreakdown,
  sourceIsSpatiallyBlocked,
} from "@/lib/admin/municipality";
import {
  buildCrossJurisdictionMunicipalityRollup,
  deriveMunicipalityBlockers,
  deriveMunicipalityHealth,
  deriveMunicipalityTier,
  MUNICIPALITY_TIERS,
} from "@/lib/admin/municipalityOps";
import { deriveRunbookSteps } from "@/lib/admin/municipalityRunbook";
import { isStaleBreakdown } from "@/lib/admin/staleSummary";
import type { QueueSource } from "@/lib/schemas";

export default function MunicipalityDrilldownPage() {
  const params = useParams<{ jurisdictionId: string; municipality: string }>();
  const jurisdictionId = params.jurisdictionId;
  const municipality = decodeURIComponent(params.municipality);

  const coverage = useAdminCoverage();
  const sources = useSourcesQueue({ municipality, limit: 500 });

  const [drawer, setDrawer] = useState<QueueSource | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const parent = useMemo(
    () =>
      coverage.data?.jurisdictions.find(
        (j) => j.jurisdiction_id === jurisdictionId,
      ),
    [coverage.data, jurisdictionId],
  );

  const muniRow = useMemo(() => {
    if (!parent) return null;
    const breakdown = parseMunicipalityBreakdown(parent.municipality_breakdown);
    const allSources = (sources.data?.sources ?? []).filter(
      (s) =>
        s.jurisdiction_id === jurisdictionId
        && s.municipality_name === municipality,
    );
    const [row] = buildCrossJurisdictionMunicipalityRollup({
      jurisdictions: [{ ...parent, municipality_breakdown: breakdown[municipality]
        ? { [municipality]: breakdown[municipality] }
        : {} }],
      sources: allSources,
    });
    return row ?? null;
  }, [parent, sources.data, jurisdictionId, municipality]);

  const sourcesForTown = useMemo(
    () =>
      (sources.data?.sources ?? []).filter(
        (s) =>
          s.jurisdiction_id === jurisdictionId
          && s.municipality_name === municipality,
      ),
    [sources.data, jurisdictionId, municipality],
  );

  const blockedSources = useMemo(
    () => sourcesForTown.filter(sourceIsSpatiallyBlocked),
    [sourcesForTown],
  );

  const tier = muniRow ? deriveMunicipalityTier(muniRow) : null;
  const blockers = muniRow ? deriveMunicipalityBlockers(muniRow) : [];
  const health = muniRow ? deriveMunicipalityHealth(muniRow) : null;
  const hasStaleRows = useMemo(
    () =>
      sourcesForTown.some((s) => isStaleBreakdown(s.confidence_breakdown)),
    [sourcesForTown],
  );
  const runbookSteps = useMemo(
    () =>
      muniRow
        ? deriveRunbookSteps({
            snapshot: muniRow,
            townSources: sourcesForTown,
            hasStaleRows,
          })
        : [],
    [muniRow, sourcesForTown, hasStaleRows],
  );

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    setSelected((prev) =>
      prev.size === sourcesForTown.length
        ? new Set()
        : new Set(sourcesForTown.map((s) => s.id)),
    );
  }

  const zoningPct =
    muniRow && muniRow.parcels > 0
      ? Math.round((muniRow.parcels_with_zoning / muniRow.parcels) * 100)
      : null;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            <Link href="/admin/municipalities" className="hover:underline">
              Municipalities
            </Link>{" "}
            ·{" "}
            <Link
              href={`/admin/coverage/${jurisdictionId}`}
              className="hover:underline"
            >
              {parent?.jurisdiction_name ?? "Jurisdiction"}
            </Link>
          </p>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
            {health && <MunicipalityHealthDot health={health} />}
            <span>{municipality}</span>
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            {parent?.state && (
              <span className="font-mono">{parent.state}</span>
            )}
            {tier && (
              <>
                {" · "}
                <span>{MUNICIPALITY_TIERS[tier].stage}</span>
              </>
            )}
          </p>
        </div>
        {tier && <MunicipalityTierPill tier={tier} size="md" />}
      </header>

      {/* Onboarding progression breadcrumb */}
      {tier && (
        <section className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Onboarding progression
          </div>
          <div className="mt-1.5">
            <MunicipalityProgressionBar tier={tier} />
          </div>
        </section>
      )}

      {/* Executable runbook — replaces the static "next action" call-out
          from Iter4. Each step is one click → one endpoint → inline result. */}
      {muniRow && runbookSteps.length > 0 && (
        <MunicipalityRunbookPanel snapshot={muniRow} steps={runbookSteps} />
      )}

      {/* Stats — small inline row, not a dashboard */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Parcels"
          value={(muniRow?.parcels ?? 0).toLocaleString()}
        />
        <Stat
          label="Coverage"
          value={zoningPct != null ? `${zoningPct}%` : "—"}
          tone={
            zoningPct != null && zoningPct < 50
              ? "rose"
              : zoningPct != null && zoningPct < 99
                ? "amber"
                : "emerald"
          }
        />
        <Stat
          label="Overlays"
          value={(muniRow?.zoning_overlays ?? 0).toLocaleString()}
        />
        <Stat
          label="Unzoned (ROI)"
          value={
            muniRow
              ? (muniRow.parcels - muniRow.parcels_with_zoning).toLocaleString()
              : "—"
          }
          tone={
            muniRow && muniRow.parcels - muniRow.parcels_with_zoning > 0
              ? "rose"
              : "emerald"
          }
        />
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Sources pending"
          value={muniRow?.source_count_pending ?? 0}
          tone={muniRow && muniRow.source_count_pending > 0 ? "amber" : "slate"}
        />
        <Stat
          label="Sources verified"
          value={muniRow?.source_count_verified ?? 0}
          tone={muniRow && muniRow.source_count_verified > 0 ? "emerald" : "slate"}
        />
        <Stat
          label="Sources rejected"
          value={muniRow?.source_count_rejected ?? 0}
          tone="slate"
        />
        <Stat
          label="Spatial-blocked"
          value={muniRow?.spatial_blocked_count ?? 0}
          tone={muniRow && muniRow.spatial_blocked_count > 0 ? "rose" : "slate"}
        />
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Blockers
        </h2>
        <div className="mt-2">
          <MunicipalityBlockerList blockers={blockers} />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Sources in this municipality ({sourcesForTown.length})
          </h2>
          {sourcesForTown.length > 0 && (
            <Link
              href={`/admin/sources/${jurisdictionId}?municipality=${encodeURIComponent(municipality)}`}
              className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
            >
              Open in source review →
            </Link>
          )}
        </div>
        {sources.isPending && (
          <p className="text-[11px] italic text-slate-400">Loading sources…</p>
        )}
        {sources.isError && (
          <p className="text-[11px] text-rose-600">
            {(sources.error as Error)?.message ?? "Failed to load sources."}
          </p>
        )}
        {!sources.isPending && !sources.isError && (
          <CrossJurisdictionSourceTable
            rows={sourcesForTown}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
            onOpenRow={setDrawer}
            emptyMessage="No sources for this town."
          />
        )}
        {blockedSources.length > 0 && (
          <p className="mt-2 text-[11px] text-rose-700">
            ◆ {blockedSources.length} source{blockedSources.length === 1 ? "" : "s"}
            {" "}flagged as spatially mismatched — likely contributing to this
            town's blocker status.
          </p>
        )}
      </section>

      {drawer && (
        <SourceDetailDrawer
          jurisdictionId={drawer.jurisdiction_id}
          source={drawer}
          onClose={() => setDrawer(null)}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: number | string;
  tone?: "slate" | "amber" | "emerald" | "rose";
}) {
  const toneClass =
    tone === "rose"
      ? "text-rose-700"
      : tone === "emerald"
        ? "text-emerald-700"
        : tone === "amber"
          ? "text-amber-700"
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
