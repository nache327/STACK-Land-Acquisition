"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { OpsTownQueue } from "@/components/admin/OpsTownQueue";
import { RemediationStepRow } from "@/components/admin/RemediationStepRow";
import { SessionVelocityCounter } from "@/components/admin/SessionVelocityCounter";
import { TrustworthinessPill } from "@/components/admin/TrustworthinessPill";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useMunicipalitiesRemediation } from "@/hooks/useMunicipalitiesRemediation";
import {
  computeStats,
  type SessionDecision,
} from "@/lib/admin/sessionVelocity";
import type { RemediationMunicipality } from "@/lib/schemas";

export default function OpsCommandCenterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();

  const jurisdictionId = searchParams.get("jurisdiction_id");
  const municipalityParam = searchParams.get("municipality");

  const setParams = (next: Record<string, string | null>) => {
    const sp = new URLSearchParams(Array.from(searchParams.entries()));
    for (const [k, v] of Object.entries(next)) {
      if (v == null || v === "") sp.delete(k);
      else sp.set(k, v);
    }
    router.replace(`?${sp.toString()}`, { scroll: false });
  };

  const coverage = useAdminCoverage();
  const remediation = useMunicipalitiesRemediation(jurisdictionId);

  // Resolve the active town. URL wins; otherwise fall back to the backend's
  // next_actionable_municipality. Operator can override at any time.
  const activeMunicipality = useMemo(() => {
    if (municipalityParam) return municipalityParam;
    return remediation.data?.next_actionable_municipality ?? null;
  }, [municipalityParam, remediation.data]);

  const activePlan: RemediationMunicipality | null = useMemo(() => {
    if (!remediation.data || !activeMunicipality) return null;
    return (
      remediation.data.municipalities.find(
        (m) => m.municipality === activeMunicipality,
      ) ?? null
    );
  }, [remediation.data, activeMunicipality]);

  // Session velocity — track step.action_code commits as a coarse "decision"
  // so the counter shows operator throughput across the muni workspace.
  const [decisions, setDecisions] = useState<SessionDecision[]>([]);
  const stats = computeStats(decisions);
  function recordStepCommit() {
    setDecisions((prev) => [
      ...prev,
      { action: "verify", at_ms: Date.now(), latency_ms: 0 },
    ]);
  }

  // After any step run, refetch the plan so completed steps disappear.
  function onStepSuccess() {
    recordStepCommit();
    qc.invalidateQueries({ queryKey: ["municipalities-remediation"] });
  }

  // If the URL has no jurisdiction yet but coverage has loaded, pick the
  // first one whose plan is likely to have actionable work (most pending
  // sources). Operator can change via the dropdown.
  useEffect(() => {
    if (jurisdictionId || !coverage.data) return;
    const next = [...coverage.data.jurisdictions]
      .sort((a, b) =>
        (b.source_count_pending ?? 0) - (a.source_count_pending ?? 0))
      [0];
    if (next) setParams({ jurisdiction_id: next.jurisdiction_id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coverage.data, jurisdictionId]);

  return (
    <div className="space-y-4">
      <Header
        jurisdictions={coverage.data?.jurisdictions ?? []}
        jurisdictionId={jurisdictionId}
        onPickJurisdiction={(id) =>
          setParams({ jurisdiction_id: id, municipality: null })
        }
        bandCounts={remediation.data?.band_counts}
        nextActionable={remediation.data?.next_actionable_municipality ?? null}
      />

      <SessionVelocityCounter stats={stats} />

      {!jurisdictionId && (
        <p className="rounded-md border border-slate-200 bg-white px-3 py-4 text-center text-xs italic text-slate-500">
          Pick a jurisdiction to begin.
        </p>
      )}

      {jurisdictionId && remediation.isPending && (
        <p className="text-[11px] italic text-slate-400">
          Loading remediation plan…
        </p>
      )}

      {jurisdictionId && remediation.isError && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(remediation.error as Error)?.message ?? "Failed to load."}
        </p>
      )}

      {remediation.data && (
        <div className="grid gap-4 md:grid-cols-[1fr_240px]">
          {/* Main workspace */}
          <main className="min-w-0 space-y-4">
            {activePlan ? (
              <ActiveTownWorkspace
                plan={activePlan}
                jurisdictionId={jurisdictionId!}
                onStepSuccess={onStepSuccess}
              />
            ) : (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-4 text-center text-xs text-emerald-800">
                Nothing actionable in this jurisdiction — all municipalities
                are operational or already-escalated.
              </p>
            )}
          </main>

          {/* Side rail */}
          {remediation.data.municipalities.length > 1 && (
            <OpsTownQueue
              rows={remediation.data.municipalities.filter(
                (m): m is RemediationMunicipality => m.municipality != null,
              )}
              active={activeMunicipality}
              onPick={(muni) => setParams({ municipality: muni })}
            />
          )}
        </div>
      )}
    </div>
  );
}

interface HeaderProps {
  jurisdictions: { jurisdiction_id: string; jurisdiction_name: string; state: string | null }[];
  jurisdictionId: string | null;
  onPickJurisdiction: (id: string) => void;
  bandCounts: Record<string, number> | undefined;
  nextActionable: string | null;
}

function Header({
  jurisdictions,
  jurisdictionId,
  onPickJurisdiction,
  bandCounts,
  nextActionable,
}: HeaderProps) {
  return (
    <header className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">
            Ops · municipality command center
          </h1>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Single-page execution surface. Backend remediation plan drives
            the steps; the dispatcher allow-list determines what runs from
            the UI vs. CLI.
          </p>
        </div>
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Jurisdiction
          </span>
          <select
            value={jurisdictionId ?? ""}
            onChange={(e) => onPickJurisdiction(e.target.value)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
          >
            <option value="">— choose —</option>
            {[...jurisdictions]
              .sort((a, b) => a.jurisdiction_name.localeCompare(b.jurisdiction_name))
              .map((j) => (
                <option key={j.jurisdiction_id} value={j.jurisdiction_id}>
                  {j.jurisdiction_name}
                  {j.state ? ` (${j.state})` : ""}
                </option>
              ))}
          </select>
        </label>
      </div>
      {(bandCounts || nextActionable) && (
        <p className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
          {bandCounts && (
            <span>
              {Object.entries(bandCounts).map(([band, n]) => (
                <span key={band} className="mr-3">
                  <span className="font-mono">{n}</span> {band}
                </span>
              ))}
            </span>
          )}
          {nextActionable && (
            <span className="ml-auto">
              next actionable →{" "}
              <span className="font-semibold text-slate-800">
                {nextActionable}
              </span>
            </span>
          )}
        </p>
      )}
    </header>
  );
}

function ActiveTownWorkspace({
  plan,
  jurisdictionId,
  onStepSuccess,
}: {
  plan: RemediationMunicipality;
  jurisdictionId: string;
  onStepSuccess: () => void;
}) {
  const muni = plan.municipality ?? "(no municipality)";
  const steps = plan.remediation.steps;
  const unresolvedDeps = useMemo(
    () => new Set(steps.map((s) => s.step)),
    [steps],
  );
  return (
    <section className="space-y-3">
      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-base font-semibold text-slate-900">
                {muni}
              </h2>
              <TrustworthinessPill band={plan.trustworthiness} size="md" />
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {plan.gaps.length === 0
                ? "No gaps reported."
                : plan.gaps.join(" · ")}
            </p>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <Link
              href={`/admin/municipalities/${jurisdictionId}/${encodeURIComponent(muni)}`}
              className="rounded-md border border-slate-200 px-2 py-1 hover:bg-slate-50"
            >
              Open in muni view →
            </Link>
            <Link
              href={`/admin/sources/${jurisdictionId}?municipality=${encodeURIComponent(muni)}`}
              className="rounded-md border border-slate-200 px-2 py-1 hover:bg-slate-50"
            >
              Sources →
            </Link>
          </div>
        </div>
        {plan.remediation.escalate_to_engineer && (
          <p className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-800">
            ⚠ Escalate to engineer — at least one step requires
            engineer-only intervention.
          </p>
        )}
        {plan.remediation.needs_operator_input.length > 0 && (
          <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
            Needs operator input:{" "}
            {plan.remediation.needs_operator_input.join(" · ")}
          </p>
        )}
      </div>

      {steps.length === 0 ? (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3 text-center text-xs text-emerald-800">
          No remediation steps — this municipality is operational.
        </p>
      ) : (
        <ol className="space-y-2">
          {steps.map((step) => (
            <RemediationStepRow
              key={step.step}
              step={step}
              unresolvedDeps={unresolvedDeps}
              onSuccess={onStepSuccess}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
