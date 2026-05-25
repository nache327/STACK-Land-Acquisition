"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CrossJurisdictionBulkBar } from "@/components/admin/CrossJurisdictionBulkBar";
import { RescoreDiffTable } from "@/components/admin/RescoreDiffTable";
import { RescoreSummaryStrip } from "@/components/admin/RescoreSummaryStrip";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import { useBulkReviewSources } from "@/hooks/useAdminSources";
import { useRescore, useRescoreRollback } from "@/hooks/useRescore";
import {
  downloadRescoreSnapshot,
  parseRollbackInput,
} from "@/lib/admin/snapshotDownload";
import { computeQueueDelta } from "@/lib/admin/staleSummary";
import type {
  BulkReviewAction,
  RescoreRequest,
  RescoreResponse,
  RescoreSnapshot,
} from "@/lib/schemas";

type StatusFilterKey =
  | "pending"
  | "needs_review"
  | "verified"
  | "rejected";

const STATUS_OPTIONS: StatusFilterKey[] = [
  "pending",
  "needs_review",
  "verified",
  "rejected",
];

export default function StaleRescorePage() {
  const params = useParams<{ jurisdictionId: string }>();
  const jurisdictionId = params.jurisdictionId;

  // ---- form state -------------------------------------------------------
  const [statuses, setStatuses] = useState<StatusFilterKey[]>(["pending"]);
  const [maxRows, setMaxRows] = useState(200);
  const [staleOnly, setStaleOnly] = useState(true);
  const [concurrency, setConcurrency] = useState(8);
  const [confirmText, setConfirmText] = useState("");
  const [rollbackText, setRollbackText] = useState("");
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [lastAppliedRes, setLastAppliedRes] = useState<RescoreResponse | null>(
    null,
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // ---- queries ----------------------------------------------------------
  const coverage = useAdminCoverage();
  const jurisdictionName = useMemo(
    () =>
      coverage.data?.jurisdictions.find(
        (j) => j.jurisdiction_id === jurisdictionId,
      )?.jurisdiction_name ?? null,
    [coverage.data, jurisdictionId],
  );

  const dryRun = useRescore(jurisdictionId);
  const apply = useRescore(jurisdictionId);
  const rollback = useRescoreRollback(jurisdictionId);
  const bulkReview = useBulkReviewSources(jurisdictionId);

  // The latest preview the operator is looking at — dry-run wins until they
  // apply, then we switch to the applied response for snapshot/rollback.
  const liveRes: RescoreResponse | null =
    lastAppliedRes ?? apply.data ?? dryRun.data ?? null;

  // ---- handlers ---------------------------------------------------------

  function buildBody(dry: boolean): RescoreRequest {
    return {
      dry_run: dry,
      max_rows: maxRows,
      only_status: statuses,
      stale_only: staleOnly,
      concurrency,
    };
  }

  function runDryRun() {
    setSelected(new Set());
    dryRun.mutate(buildBody(true));
  }

  function runApply() {
    if (confirmText.trim().toUpperCase() !== "APPLY") return;
    apply.mutate(buildBody(false), {
      onSuccess: (res) => {
        setLastAppliedRes(res);
        if (res.summary.applied > 0) {
          // Auto-prompt the snapshot save so the operator can rollback.
          downloadRescoreSnapshot(res);
        }
        setConfirmText("");
      },
    });
  }

  function runRollbackFromText() {
    setRollbackError(null);
    try {
      const snapshots: RescoreSnapshot[] = parseRollbackInput(rollbackText);
      if (snapshots.length === 0) {
        setRollbackError("No snapshots found in payload.");
        return;
      }
      rollback.mutate(snapshots);
    } catch (e) {
      setRollbackError(
        e instanceof Error ? e.message : "Failed to parse rollback JSON",
      );
    }
  }

  function handleBulkOnSelection(action: BulkReviewAction, reason?: string) {
    if (selected.size === 0 || !liveRes) return;
    const ids = Array.from(selected);
    bulkReview.mutate(
      { ids, action, rejectedReason: reason },
      {
        onSuccess: () => {
          setSelected(new Set());
        },
      },
    );
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleAllVisible(visibleIds: string[]) {
    setSelected((prev) => {
      const allSelected = visibleIds.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  // ---- render -----------------------------------------------------------

  const changes = liveRes?.changes ?? [];
  const allChangeIds = useMemo(() => changes.map((c) => c.source_id), [changes]);
  const delta = liveRes
    ? computeQueueDelta(liveRes.changes, liveRes.summary)
    : null;
  const isBusy =
    dryRun.isPending || apply.isPending || rollback.isPending || bulkReview.isPending;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            <Link href="/admin/stale" className="hover:underline">
              Stale
            </Link>{" "}
            ·{" "}
            <span className="font-mono text-slate-400">
              {jurisdictionId.slice(0, 8)}
            </span>
          </p>
          <h1 className="truncate text-lg font-semibold text-slate-900">
            {jurisdictionName ?? "Jurisdiction"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Re-score stale rows. Verified + rejected rows are never overwritten —
            operator decisions are durable.
          </p>
        </div>
      </header>

      {/* Config panel */}
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Rescore configuration
        </h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-[11px] font-medium text-slate-600">
              Statuses to scan
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {STATUS_OPTIONS.map((s) => {
                const active = statuses.includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() =>
                      setStatuses((prev) =>
                        active ? prev.filter((p) => p !== s) : [...prev, s],
                      )
                    }
                    className={[
                      "rounded-md border px-2 py-0.5 text-[11px] font-medium",
                      active
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-[10px] text-slate-400">
              Verified + rejected rows are <em>scanned</em> for the diff but
              never mutated even when "apply" runs.
            </p>
          </div>

          <div>
            <label className="text-[11px] font-medium text-slate-600">
              Max rows ({maxRows})
            </label>
            <input
              type="range"
              min={50}
              max={1000}
              step={50}
              value={maxRows}
              onChange={(e) => setMaxRows(Number(e.target.value))}
              className="mt-1 block w-full"
            />
          </div>

          <div>
            <label className="text-[11px] font-medium text-slate-600">
              Concurrency ({concurrency})
            </label>
            <input
              type="range"
              min={1}
              max={32}
              step={1}
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
              className="mt-1 block w-full"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              id="stale_only"
              type="checkbox"
              checked={staleOnly}
              onChange={(e) => setStaleOnly(e.target.checked)}
            />
            <label htmlFor="stale_only" className="text-[11px] text-slate-700">
              Stale-only (skip rows that already have bbox_overlap_* signals)
            </label>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          <button
            type="button"
            onClick={runDryRun}
            disabled={isBusy || statuses.length === 0}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {dryRun.isPending ? "Running dry-run…" : "Run dry-run preview"}
          </button>
          <span className="text-[11px] text-slate-500">
            Live probes ≈ 0.5s/row × {concurrency} concurrent; budget ~
            {Math.max(5, Math.round(maxRows * 0.5 / concurrency))}s for{" "}
            {maxRows} rows.
          </span>
        </div>
      </section>

      {dryRun.isError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(dryRun.error as Error)?.message ?? "Dry-run failed."}
        </div>
      )}

      {liveRes && (
        <>
          <RescoreSummaryStrip
            summary={liveRes.summary}
            scanned={liveRes.scanned}
            dryRun={liveRes.dry_run}
          />

          {delta && (
            <div className="rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-600">
              <span className="font-medium text-slate-700">Queue delta:</span>{" "}
              {delta.queue_70_net_delta < 0
                ? `${Math.abs(delta.queue_70_net_delta)} rows would leave the ≥70 high-confidence queue`
                : delta.queue_70_net_delta > 0
                  ? `${delta.queue_70_net_delta} rows would join the ≥70 queue`
                  : "no net change in the ≥70 queue"}
              {delta.newly_disjoint > 0 && (
                <span className="ml-2 font-medium text-rose-700">
                  · {delta.newly_disjoint} newly disjoint
                </span>
              )}
            </div>
          )}

          {liveRes.changes.length > 0 ? (
            <>
              {selected.size > 0 && (
                <CrossJurisdictionBulkBar
                  selectedCount={selected.size}
                  jurisdictionsTouched={1}
                  busy={bulkReview.isPending}
                  onAction={handleBulkOnSelection}
                  onClear={() => setSelected(new Set())}
                />
              )}
              <RescoreDiffTable
                changes={liveRes.changes}
                selected={selected}
                onToggle={toggle}
                onToggleAll={() => toggleAllVisible(allChangeIds)}
              />
              <p className="text-[11px] text-slate-500">
                Select rows + use the bulk bar to verify / reject / needs_review
                via the standard <code className="rounded bg-slate-100 px-1">/_bulk-review</code> endpoint —
                independent of rescore Apply.
              </p>
            </>
          ) : (
            <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-800">
              No changes — every scanned row already has fresh
              <code className="mx-1 rounded bg-emerald-100 px-1">bbox_overlap_*</code>
              signals.
            </p>
          )}

          {liveRes.errors.length > 0 && (
            <details className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              <summary className="cursor-pointer font-medium">
                {liveRes.errors.length} probe error
                {liveRes.errors.length === 1 ? "" : "s"} during dry-run
              </summary>
              <ul className="ml-4 mt-1 list-disc">
                {liveRes.errors.slice(0, 20).map((e, i) => (
                  <li key={i} className="font-mono text-[10px]">
                    {JSON.stringify(e)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      {/* Apply gate — only meaningful after a dry-run with changes */}
      {dryRun.data && dryRun.data.summary.changed > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">
            Apply to database
          </h2>
          <p className="mt-1 text-xs text-amber-900">
            Writes new (score, label, breakdown, reasons) to rows whose status
            is pending or needs_review. Verified + rejected rows stay untouched.
            A snapshot.json will auto-download so you can rollback.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder='type "APPLY" to enable'
              className="rounded-md border border-amber-300 bg-white px-2 py-1 text-xs"
            />
            <button
              type="button"
              onClick={runApply}
              disabled={
                confirmText.trim().toUpperCase() !== "APPLY"
                || isBusy
              }
              className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
            >
              {apply.isPending
                ? "Applying…"
                : `Apply rescore (${dryRun.data.summary.changed} writable)`}
            </button>
            {lastAppliedRes && lastAppliedRes.summary.applied > 0 && (
              <button
                type="button"
                onClick={() => downloadRescoreSnapshot(lastAppliedRes)}
                className="rounded-md border border-amber-300 bg-white px-2 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100"
              >
                Re-download snapshot.json
              </button>
            )}
          </div>
          {apply.isError && (
            <p className="mt-2 text-xs text-rose-700">
              {(apply.error as Error)?.message ?? "Apply failed."}
            </p>
          )}
          {lastAppliedRes && (
            <p className="mt-2 text-xs text-amber-900">
              Applied: {lastAppliedRes.summary.applied}. Skipped immutable:{" "}
              {lastAppliedRes.summary.skipped_immutable}.
            </p>
          )}
        </section>
      )}

      {/* Rollback panel */}
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Rollback from snapshot
        </h2>
        <p className="mt-1 text-xs text-slate-600">
          Paste a snapshot.json produced by a prior Apply to restore the
          previous (score, label, breakdown, reasons). Verified + rejected
          rows are skipped — they were re-reviewed after the rescore.
        </p>
        <textarea
          value={rollbackText}
          onChange={(e) => setRollbackText(e.target.value)}
          rows={4}
          placeholder='{"snapshots": [...]} or [...]'
          className="mt-2 w-full rounded-md border border-slate-200 px-2 py-1.5 font-mono text-[11px]"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={runRollbackFromText}
            disabled={!rollbackText.trim() || rollback.isPending}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {rollback.isPending ? "Rolling back…" : "Roll back"}
          </button>
          {rollbackError && (
            <span className="text-xs text-rose-700">{rollbackError}</span>
          )}
          {rollback.isError && (
            <span className="text-xs text-rose-700">
              {(rollback.error as Error)?.message ?? "Rollback failed."}
            </span>
          )}
          {rollback.data && (
            <span className="text-xs text-emerald-800">
              Restored {rollback.data.restored}.{" "}
              {rollback.data.skipped.length > 0 && (
                <>Skipped {rollback.data.skipped.length}. </>
              )}
              {rollback.data.not_found.length > 0 && (
                <>Not found {rollback.data.not_found.length}.</>
              )}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
