"use client";

import Link from "next/link";
import { useState } from "react";
import {
  useDiscoverMunicipalZoning,
  useIngestMunicipalZoning,
} from "@/hooks/useMunicipalityActions";
import { useRefreshCoverage } from "@/hooks/useRefreshCoverage";
import type {
  RunbookStep,
  RunbookStepKind,
} from "@/lib/admin/municipalityRunbook";
import type { MunicipalitySnapshot } from "@/lib/admin/municipalityOps";

interface Props {
  snapshot: MunicipalitySnapshot;
  steps: RunbookStep[];
}

/** Inline-execution panel. Each step is one click → one endpoint → terse
 *  inline result line. No charts, no cards, no analytics. */
export function MunicipalityRunbookPanel({ snapshot, steps }: Props) {
  const jId = snapshot.jurisdiction_id;
  const muni = snapshot.municipality;

  const discover = useDiscoverMunicipalZoning(jId);
  const ingest = useIngestMunicipalZoning(jId);
  const refresh = useRefreshCoverage();

  const [lastResult, setLastResult] = useState<{
    stepKey: string;
    body: unknown;
  } | null>(null);
  const [lastError, setLastError] = useState<{
    stepKey: string;
    message: string;
  } | null>(null);

  function fire(step: RunbookStep) {
    setLastError(null);
    if (step.blocked_reason) return;
    if (step.kind === "discover") {
      discover.mutate([muni], {
        onSuccess: (body) =>
          setLastResult({ stepKey: step.key, body: body ?? {} }),
        onError: (e) =>
          setLastError({
            stepKey: step.key,
            message: (e as Error)?.message ?? "discover failed",
          }),
      });
    } else if (step.kind === "ingest_verified") {
      ingest.mutate(step.source_ids ?? [], {
        onSuccess: (body) =>
          setLastResult({ stepKey: step.key, body: body ?? {} }),
        onError: (e) =>
          setLastError({
            stepKey: step.key,
            message: (e as Error)?.message ?? "ingest failed",
          }),
      });
    } else if (step.kind === "refresh_audit") {
      refresh.mutate(jId, {
        onSuccess: (body) =>
          setLastResult({ stepKey: step.key, body }),
        onError: (e) =>
          setLastError({
            stepKey: step.key,
            message: (e as Error)?.message ?? "refresh failed",
          }),
      });
    }
  }

  function pendingFor(kind: RunbookStepKind): boolean {
    switch (kind) {
      case "discover":
        return discover.isPending;
      case "ingest_verified":
        return ingest.isPending;
      case "refresh_audit":
        return refresh.isPending;
      default:
        return false;
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Runbook · execute in place
        </h2>
        <p className="text-[10px] text-slate-400">
          Each step calls one backend endpoint. No multi-step automation —
          re-render after each click.
        </p>
      </div>

      <ul className="space-y-1.5">
        {steps.map((step) => (
          <li
            key={step.key}
            className={[
              "flex flex-wrap items-start gap-3 rounded-md border px-3 py-2 text-xs",
              step.primary
                ? "border-slate-900 bg-slate-900/[0.03]"
                : "border-slate-200 bg-white",
              step.blocked_reason ? "opacity-60" : "",
            ].join(" ")}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                {step.primary && (
                  <span className="rounded bg-slate-900 px-1 py-0.5 text-[9px] font-semibold text-white">
                    PRIMARY
                  </span>
                )}
                <span className="font-medium text-slate-800">{step.title}</span>
              </div>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {step.description}
              </p>
              {step.blocked_reason && (
                <p className="mt-1 text-[11px] text-rose-700">
                  Blocked: {step.blocked_reason}
                </p>
              )}
              {lastResult?.stepKey === step.key && (
                <ResultRow body={lastResult.body} />
              )}
              {lastError?.stepKey === step.key && (
                <p className="mt-1 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
                  {lastError.message}
                </p>
              )}
            </div>
            <StepAction
              step={step}
              busy={pendingFor(step.kind)}
              onFire={() => fire(step)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function StepAction({
  step,
  busy,
  onFire,
}: {
  step: RunbookStep;
  busy: boolean;
  onFire: () => void;
}) {
  // Steps that route somewhere else are rendered as links — operator
  // crosses the boundary and acts in the existing surface (source review,
  // stale workspace, jurisdiction coverage).
  if (step.href) {
    return (
      <Link
        href={step.href}
        className={[
          "shrink-0 rounded-md px-3 py-1.5 text-[11px] font-medium",
          step.primary
            ? "bg-slate-900 text-white hover:bg-slate-800"
            : "border border-slate-200 text-slate-700 hover:bg-slate-50",
        ].join(" ")}
      >
        Open →
      </Link>
    );
  }
  // Steps with kind="none" are informational placeholders — render
  // nothing actionable.
  if (step.kind === "none") {
    return (
      <span className="shrink-0 px-2 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
        N/A
      </span>
    );
  }
  // Executable buttons.
  return (
    <button
      type="button"
      disabled={!!step.blocked_reason || busy}
      onClick={onFire}
      className={[
        "shrink-0 rounded-md px-3 py-1.5 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-50",
        step.danger
          ? "bg-rose-600 text-white hover:bg-rose-700"
          : step.primary
            ? "bg-slate-900 text-white hover:bg-slate-800"
            : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
      ].join(" ")}
    >
      {busy ? "Running…" : "Run"}
    </button>
  );
}

function ResultRow({ body }: { body: unknown }) {
  const summary = summariseResult(body);
  return (
    <details className="mt-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-900 open:max-h-72 open:overflow-y-auto">
      <summary className="cursor-pointer font-medium">{summary}</summary>
      <pre className="mt-1 whitespace-pre-wrap font-mono text-[10px] leading-tight">
        {JSON.stringify(body, null, 2)}
      </pre>
    </details>
  );
}

/** Compress a discover / ingest / refresh response into a one-line operator
 *  summary. Falls back to "Done" when the shape is unfamiliar — the full
 *  response is always visible by expanding the details block. */
function summariseResult(body: unknown): string {
  if (!body || typeof body !== "object") return "Done.";
  const b = body as Record<string, unknown>;

  const ingested = pickNumber(b, ["ingested", "ingested_features", "features_ingested"]);
  const spatial = pickNumber(b, ["spatial_updated", "parcels_updated"]);
  const discovered = pickNumber(b, ["candidates_inserted", "candidates", "candidates_total"]);
  const snapshots = pickNumber(b, ["snapshots_written"]);
  const errors = pickNumber(b, ["errors", "error_count"]);

  const parts: string[] = [];
  if (discovered != null) parts.push(`${discovered} candidates discovered`);
  if (ingested != null) parts.push(`${ingested} features ingested`);
  if (spatial != null) parts.push(`${spatial} parcels updated`);
  if (snapshots != null) parts.push(`${snapshots} snapshots written`);
  if (errors != null && errors > 0) parts.push(`${errors} errors`);

  return parts.length > 0 ? parts.join(" · ") : "Done.";
}

function pickNumber(
  obj: Record<string, unknown>,
  keys: string[],
): number | null {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}
