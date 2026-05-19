"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { JobActionButtons } from "@/components/admin/JobActionButtons";
import { JobDetailDrawer } from "@/components/admin/JobDetailDrawer";
import { JobStatusPill } from "@/components/admin/JobStatusPill";
import { useAdminJobs } from "@/hooks/useAdminJobs";
import type { Job } from "@/lib/schemas";

const STATUS_OPTIONS = [
  "",
  "pending",
  "queued",
  "running",
  "retrying",
  "discovering_layers",
  "downloading_parcels",
  "ingesting_parcels",
  "downloading_zoning",
  "pending_zoning",
  "parsing_ordinance",
  "running_overlays",
  "cancelled",
  "ready",
  "failed",
];

type ScopeFilter = "all" | "active" | "stale" | "terminal";

export default function JobsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const status = searchParams.get("status") ?? "";
  const jurisdiction = searchParams.get("jurisdiction") ?? "";
  const scopeParam = searchParams.get("scope") ?? "active";
  const scope: ScopeFilter = (["all", "active", "stale", "terminal"] as ScopeFilter[]).includes(
    scopeParam as ScopeFilter,
  )
    ? (scopeParam as ScopeFilter)
    : "active";

  const setParam = (k: string, v: string | null) => {
    const sp = new URLSearchParams(Array.from(searchParams.entries()));
    if (!v) sp.delete(k);
    else sp.set(k, v);
    router.replace(`?${sp.toString()}`, { scroll: false });
  };

  const filters = useMemo(
    () => ({
      status: status || undefined,
      jurisdiction: jurisdiction || undefined,
      active_only: scope === "active" || undefined,
      stale_only: scope === "stale" || undefined,
      limit: 200,
    }),
    [status, jurisdiction, scope],
  );

  const jobs = useAdminJobs(filters);
  const [drawerJobId, setDrawerJobId] = useState<string | null>(null);

  // Client-side "terminal" filter when scope=terminal (backend has no
  // `terminal_only` flag; trivial to do client-side over the page).
  const rows = useMemo(() => {
    const all = jobs.data ?? [];
    if (scope === "terminal") {
      return all.filter((j) =>
        ["ready", "failed", "cancelled"].includes(j.status),
      );
    }
    return all;
  }, [jobs.data, scope]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">
            Jobs
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Pipeline jobs across all jurisdictions. Cancel / Retry / Force
            re-run inline — replaces the psql workflow for stuck jobs.
          </p>
        </div>
        <div className="text-[11px] text-slate-500">
          {scope === "active" && "polling every 5s"}
          {jobs.isFetching && " · refetching…"}
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-3 text-xs">
        <div className="flex gap-1 rounded-md border border-slate-200 p-0.5">
          {(["active", "stale", "terminal", "all"] as ScopeFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setParam("scope", s)}
              className={[
                "rounded px-2 py-1 capitalize",
                scope === s
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-50",
              ].join(" ")}
            >
              {s}
            </button>
          ))}
        </div>
        <label className="text-[11px]">
          <span className="block font-medium uppercase tracking-wide text-slate-500">
            Status
          </span>
          <select
            value={status}
            onChange={(e) => setParam("status", e.target.value || null)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s || "all"} value={s}>
                {s || "any"}
              </option>
            ))}
          </select>
        </label>
        <label className="flex-1 text-[11px]">
          <span className="block font-medium uppercase tracking-wide text-slate-500">
            Jurisdiction (substring)
          </span>
          <input
            type="search"
            value={jurisdiction}
            onChange={(e) => setParam("jurisdiction", e.target.value || null)}
            placeholder="e.g. Bergen"
            className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1"
          />
        </label>
        <button
          type="button"
          onClick={() => jobs.refetch()}
          className="rounded-md border border-slate-200 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50"
        >
          Reload
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Jurisdiction</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Started</th>
              <th className="px-3 py-2 text-right">Attempts</th>
              <th className="px-3 py-2">Duration</th>
              <th className="px-3 py-2">Error</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {jobs.isPending && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
            {jobs.isError && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-rose-600">
                  {(jobs.error as Error)?.message ?? "Failed to load."}
                </td>
              </tr>
            )}
            {!jobs.isPending && !jobs.isError && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No jobs match these filters.
                </td>
              </tr>
            )}
            {rows.map((j) => (
              <Row
                key={j.id}
                job={j}
                onOpen={() => setDrawerJobId(j.id)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {drawerJobId && (
        <JobDetailDrawer
          jobId={drawerJobId}
          onClose={() => setDrawerJobId(null)}
        />
      )}
    </div>
  );
}

function Row({ job, onOpen }: { job: Job; onOpen: () => void }) {
  const duration = computeDuration(job);
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-3 py-2">
        <button
          type="button"
          onClick={onOpen}
          className="font-medium text-slate-900 hover:underline"
        >
          {job.jurisdiction_input ?? "(no input)"}
        </button>
        <div className="font-mono text-[10px] text-slate-400">
          {job.id.slice(0, 8)}…
        </div>
      </td>
      <td className="px-3 py-2">
        <JobStatusPill status={job.status} />
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
        {job.started_at
          ? job.started_at.slice(0, 19).replace("T", " ")
          : job.queued_at
            ? `q ${job.queued_at.slice(11, 19)}`
            : "—"}
      </td>
      <td className="px-3 py-2 text-right font-mono text-slate-600">
        {job.attempts ?? 0}
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
        {duration}
      </td>
      <td className="px-3 py-2">
        {job.error_message ? (
          <span
            className="block max-w-[280px] truncate text-[11px] text-rose-700"
            title={job.error_message}
          >
            {job.error_message}
          </span>
        ) : (
          <span className="text-[11px] text-slate-300">—</span>
        )}
      </td>
      <td className="px-3 py-2">
        <JobActionButtons job={job} compact />
      </td>
    </tr>
  );
}

function computeDuration(job: Job): string {
  const start = job.started_at;
  if (!start) return "—";
  const end = job.finished_at ?? new Date().toISOString();
  const startMs = Date.parse(start);
  const endMs = Date.parse(end);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return "—";
  const seconds = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}
