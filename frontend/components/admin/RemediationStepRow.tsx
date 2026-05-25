"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import {
  describeDispatch,
  dispatchPlanCommand,
} from "@/lib/admin/planCommandDispatcher";
import type { RemediationStep } from "@/lib/schemas";

const SEVERITY_TONE = {
  must: "bg-rose-50 text-rose-800 border-rose-200",
  should: "bg-amber-50 text-amber-800 border-amber-200",
  consider: "bg-slate-50 text-slate-600 border-slate-200",
};

interface Props {
  step: RemediationStep;
  /** Set of step.step numbers that are still incomplete. Used to render
   *  dependency-blocked steps as disabled. */
  unresolvedDeps?: Set<number>;
  /** Fired after a successful run so the parent can mark this step done
   *  and refetch the plan. */
  onSuccess?: () => void;
}

export function RemediationStepRow({
  step,
  unresolvedDeps,
  onSuccess,
}: Props) {
  const dispatch = dispatchPlanCommand(step.command);
  const blockedByDeps = step.dependencies.some(
    (d) => unresolvedDeps?.has(d) ?? false,
  );
  const isUnsupported = dispatch.kind === "unsupported";
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (isUnsupported || blockedByDeps || running) return;
    setRunning(true);
    setError(null);
    try {
      const out = await runDispatch(dispatch);
      setResult(out);
      onSuccess?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <li
      className={[
        "rounded-md border p-3 text-xs",
        step.severity === "must"
          ? "border-rose-200 bg-rose-50/30"
          : "border-slate-200 bg-white",
      ].join(" ")}
    >
      <div className="flex flex-wrap items-start gap-3">
        <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-slate-900 px-1 font-mono text-[10px] font-semibold text-white">
          {step.step}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-slate-800">{step.label}</span>
            <span
              className={[
                "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium uppercase",
                SEVERITY_TONE[step.severity],
              ].join(" ")}
            >
              {step.severity}
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              {step.action_code}
            </span>
            {step.dependencies.length > 0 && (
              <span
                title={`Depends on step${step.dependencies.length === 1 ? "" : "s"} ${step.dependencies.join(", ")}`}
                className="font-mono text-[10px] text-slate-500"
              >
                ↳ needs {step.dependencies.join(", ")}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] leading-snug text-slate-600">
            {step.rationale}
          </p>
          {step.cli_hint && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[10px] text-slate-400 hover:text-slate-600">
                CLI equivalent
              </summary>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-md bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-600">
                {step.cli_hint}
              </pre>
            </details>
          )}
          {result != null && <ResultLine body={result} />}
          {error && (
            <p className="mt-1 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
              {error}
            </p>
          )}
          {isUnsupported && (
            <p className="mt-1 text-[10px] text-amber-700">
              {(dispatch as { reason: string }).reason}
            </p>
          )}
        </div>
        <button
          type="button"
          disabled={isUnsupported || blockedByDeps || running}
          onClick={run}
          className={[
            "shrink-0 rounded-md px-3 py-1.5 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-50",
            step.severity === "must"
              ? "bg-rose-600 text-white hover:bg-rose-700"
              : "bg-slate-900 text-white hover:bg-slate-800",
          ].join(" ")}
          title={
            blockedByDeps
              ? `Blocked by unresolved dependency step${step.dependencies.length === 1 ? "" : "s"}.`
              : isUnsupported
                ? "Not on UI allow-list — use the CLI hint."
                : "Execute this step."
          }
        >
          {running ? "Running…" : isUnsupported ? "CLI only" : "Run"}
        </button>
      </div>
    </li>
  );
}

async function runDispatch(
  d: ReturnType<typeof dispatchPlanCommand>,
): Promise<unknown> {
  switch (d.kind) {
    case "discover":
      return api.discoverMunicipalZoning(d.countyId, d.municipalityNames);
    case "ingest":
      return api.ingestMunicipalZoning(d.countyId, d.sourceIds);
    case "review":
      return api.reviewSource(d.jurisdictionId, d.sourceId, d.body);
    case "bulk_review":
      return api.bulkReviewSources(d.jurisdictionId, d.body);
    case "rescore":
      return api.rescoreStaleSources(d.jurisdictionId, d.body);
    case "refresh_coverage":
      return api.refreshCoverage(d.jurisdictionId);
    case "unsupported":
      throw new Error(d.reason);
  }
}

function ResultLine({ body }: { body: unknown }) {
  const summary = summarise(body);
  return (
    <details className="mt-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-900 open:max-h-72 open:overflow-y-auto">
      <summary className="cursor-pointer font-medium">✓ {summary}</summary>
      <pre className="mt-1 whitespace-pre-wrap font-mono text-[10px] leading-tight">
        {JSON.stringify(body, null, 2)}
      </pre>
    </details>
  );
}

function summarise(body: unknown): string {
  if (!body || typeof body !== "object") return "Done.";
  const b = body as Record<string, unknown>;
  const ingested = num(b, ["ingested", "features_ingested"]);
  const discovered = num(b, ["candidates_inserted", "candidates_total"]);
  const updated = num(b, ["updated", "spatial_updated", "applied"]);
  const restored = num(b, ["restored"]);
  const parts: string[] = [];
  if (discovered != null) parts.push(`${discovered} discovered`);
  if (ingested != null) parts.push(`${ingested} ingested`);
  if (updated != null) parts.push(`${updated} updated`);
  if (restored != null) parts.push(`${restored} restored`);
  return parts.length > 0 ? parts.join(" · ") : "Done.";
}
function num(b: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    if (typeof b[k] === "number" && Number.isFinite(b[k])) return b[k] as number;
  }
  return null;
}
