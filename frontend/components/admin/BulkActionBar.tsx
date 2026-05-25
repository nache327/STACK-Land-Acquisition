"use client";

import { useState } from "react";
import type { BulkReviewAction } from "@/lib/schemas";

interface Props {
  selectedCount: number;
  busy: boolean;
  onAction: (action: BulkReviewAction, rejectedReason?: string) => void;
  onClear: () => void;
}

export function BulkActionBar({
  selectedCount,
  busy,
  onAction,
  onClear,
}: Props) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  if (selectedCount === 0) return null;

  return (
    <div
      role="region"
      aria-label="bulk actions"
      className="sticky top-0 z-20 -mx-4 mb-3 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur"
    >
      <span className="text-sm font-medium text-slate-700">
        {selectedCount} selected
      </span>

      <button
        type="button"
        disabled={busy}
        onClick={() => onAction("verify")}
        className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Verify
      </button>

      <button
        type="button"
        disabled={busy}
        onClick={() => onAction("needs_review")}
        className="rounded-md border border-indigo-300 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Needs review
      </button>

      {showRejectInput ? (
        <>
          <input
            type="text"
            value={rejectReason}
            placeholder="Rejection reason (optional)"
            onChange={(e) => setRejectReason(e.target.value)}
            className="rounded-md border border-rose-300 px-2 py-1 text-xs"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              onAction("reject", rejectReason.trim() || undefined);
              setRejectReason("");
              setShowRejectInput(false);
            }}
            className="rounded-md bg-rose-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Confirm reject
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setShowRejectInput(false);
              setRejectReason("");
            }}
            className="text-xs text-slate-500 hover:underline"
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => setShowRejectInput(true)}
          className="rounded-md border border-rose-300 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-800 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Reject…
        </button>
      )}

      <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
        {selectedCount > 50 && (
          <span title="Backend caps each call at 50 — the client chunks transparently.">
            chunked into {Math.ceil(selectedCount / 50)} calls
          </span>
        )}
        <button
          type="button"
          onClick={onClear}
          className="rounded-md px-2 py-1 hover:bg-slate-100"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
