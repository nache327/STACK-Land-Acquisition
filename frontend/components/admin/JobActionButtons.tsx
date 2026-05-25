"use client";

import { useState } from "react";
import {
  useCancelJob,
  useForceRerunJob,
  useRetryJob,
} from "@/hooks/useAdminJobs";
import type { Job } from "@/lib/schemas";

const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);

interface Props {
  job: Job;
  /** When true, render the action labels inline. Otherwise show compact
   *  icons/abbreviations to fit a tighter table row. */
  compact?: boolean;
}

export function JobActionButtons({ job, compact = false }: Props) {
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const forceRerun = useForceRerunJob();
  const [confirmText, setConfirmText] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const isTerminal = TERMINAL_STATUSES.has(job.status);
  const canCancel = !isTerminal;
  const canRetry = job.status === "failed";
  // Force-rerun is always available — it ignores dedupe and creates a fresh job.

  const anyBusy =
    cancel.isPending || retry.isPending || forceRerun.isPending;

  function handleForceRerun() {
    if (confirmText.trim().toUpperCase() !== "RERUN") return;
    forceRerun.mutate(job.id, {
      onSuccess: () => {
        setConfirmText("");
        setShowConfirm(false);
      },
    });
  }

  if (showConfirm) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="type RERUN"
          className="w-24 rounded-md border border-rose-300 px-2 py-1 text-[11px]"
        />
        <button
          type="button"
          disabled={anyBusy || confirmText.trim().toUpperCase() !== "RERUN"}
          onClick={handleForceRerun}
          className="rounded-md bg-rose-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {forceRerun.isPending ? "Running…" : "Confirm rerun"}
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirmText("");
            setShowConfirm(false);
          }}
          className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 hover:bg-slate-100"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        disabled={!canCancel || anyBusy}
        onClick={() => cancel.mutate(job.id)}
        title={
          canCancel ? "Cancel this job" : `Job is already ${job.status}`
        }
        className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {cancel.isPending ? "…" : compact ? "✕" : "Cancel"}
      </button>
      <button
        type="button"
        disabled={!canRetry || anyBusy}
        onClick={() => retry.mutate(job.id)}
        title={
          canRetry
            ? "Retry — same job, fresh attempt"
            : "Retry only works on failed jobs"
        }
        className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {retry.isPending ? "…" : compact ? "↻" : "Retry"}
      </button>
      <button
        type="button"
        disabled={anyBusy}
        onClick={() => setShowConfirm(true)}
        title="Force re-run — creates a NEW job that ignores dedupe. Requires confirmation."
        className="rounded-md border border-rose-200 bg-white px-2 py-1 text-[11px] font-medium text-rose-800 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {compact ? "⟳⟳" : "Force rerun…"}
      </button>
      {cancel.isError && (
        <span
          title={(cancel.error as Error)?.message}
          className="text-[10px] text-rose-600"
        >
          err
        </span>
      )}
      {retry.isError && (
        <span
          title={(retry.error as Error)?.message}
          className="text-[10px] text-rose-600"
        >
          err
        </span>
      )}
      {forceRerun.isError && (
        <span
          title={(forceRerun.error as Error)?.message}
          className="text-[10px] text-rose-600"
        >
          err
        </span>
      )}
    </div>
  );
}
