"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { SourceReviewAction, ZoningSource } from "@/lib/schemas";
import { useReviewSource } from "@/hooks/useAdminSources";
import { ConfidenceBreakdown } from "./ConfidenceBreakdown";
import { ConfidenceTierPill } from "./ConfidenceTierPill";
import { KeyboardHint } from "./KeyboardHint";
import { SpatialCheckPanel } from "./SpatialCheckPanel";
import { ValidationStatusPill } from "./StatusPill";
import {
  QUICK_REJECT_REASONS,
  suggestActionForSource,
  suggestionTone,
} from "@/lib/admin/suggestAction";

interface Props {
  jurisdictionId: string;
  source: ZoningSource;
  onClose: () => void;
  /** Fires after a successful review mutation with the action taken and how
   *  long the drawer was open. Used by the session velocity counter. */
  onDecision?: (action: SourceReviewAction, latencyMs: number) => void;
  /** If provided, called instead of (or after) onClose when an action
   *  succeeds — lets the parent advance to the next queue row. */
  onAdvance?: () => void;
}

export function SourceDetailDrawer({
  jurisdictionId,
  source,
  onClose,
  onDecision,
  onAdvance,
}: Props) {
  const [notes, setNotes] = useState(source.notes ?? "");
  const [rejectReason, setRejectReason] = useState(
    source.rejected_reason ?? "",
  );
  const [showSpatial, setShowSpatial] = useState(false);
  const openedAtRef = useRef<number>(Date.now());
  const review = useReviewSource(jurisdictionId);

  const suggestion = useMemo(() => suggestActionForSource(source), [source]);
  const suggestionToneClass = TONE_CLASS[suggestionTone(suggestion)];

  // Reset form + open-timer when a different source is loaded.
  useEffect(() => {
    setNotes(source.notes ?? "");
    setRejectReason(source.rejected_reason ?? "");
    setShowSpatial(false);
    openedAtRef.current = Date.now();
  }, [source.id, source.notes, source.rejected_reason]);

  function doAction(action: SourceReviewAction, reasonOverride?: string) {
    const reasonToSend =
      action === "reject"
        ? (reasonOverride ?? rejectReason).trim() || "operator rejected"
        : null;
    review.mutate(
      {
        sourceId: source.id,
        body: {
          action,
          notes: notes.trim() ? notes.trim() : null,
          rejected_reason: reasonToSend,
        },
      },
      {
        onSuccess: () => {
          const latency = Date.now() - openedAtRef.current;
          onDecision?.(action, latency);
          if (onAdvance) onAdvance();
          else onClose();
        },
      },
    );
  }

  // Keyboard shortcuts — V/R/N/U/Esc when no input is focused.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (
        tag === "input"
        || tag === "textarea"
        || tag === "select"
        || target?.isContentEditable
      ) {
        if (e.key !== "Escape") return;
      }
      if (review.isPending) return;
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "v") {
        e.preventDefault();
        doAction("verify");
      } else if (k === "r") {
        e.preventDefault();
        doAction("reject");
      } else if (k === "n") {
        e.preventDefault();
        doAction("needs_review");
      } else if (k === "u") {
        e.preventDefault();
        doAction("unverify");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // doAction closes over notes/rejectReason but capturing the latest via
    // state read inside the handler is acceptable — React keeps refs fresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review.isPending, notes, rejectReason, source.id]);

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-[28rem] flex-col bg-white shadow-2xl"
        role="dialog"
        aria-label="Source detail"
      >
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
              Source
            </p>
            <h2 className="mt-0.5 truncate text-sm font-semibold text-slate-900">
              {source.municipality_name ?? "(no municipality)"}
            </h2>
            <p
              className="mt-0.5 truncate text-xs text-slate-500"
              title={source.title ?? undefined}
            >
              {source.title ?? "—"}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <ValidationStatusPill status={source.validation_status} />
              <ConfidenceTierPill score={source.confidence_score} showNumber />
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close drawer"
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4.293 4.293a1 1 0 011.414 0L8 6.586l2.293-2.293a1 1 0 111.414 1.414L9.414 8l2.293 2.293a1 1 0 01-1.414 1.414L8 9.414l-2.293 2.293a1 1 0 01-1.414-1.414L6.586 8 4.293 5.707a1 1 0 010-1.414z" />
            </svg>
          </button>
        </div>

        {/* Suggested-action banner */}
        <div
          className={[
            "border-b border-slate-200 px-5 py-3 text-xs",
            suggestionToneClass,
          ].join(" ")}
        >
          <div className="text-[10px] font-medium uppercase tracking-wide opacity-70">
            Suggested next action
          </div>
          <div className="mt-0.5 flex items-baseline justify-between gap-2">
            <span className="font-semibold capitalize">
              {suggestion.action === "review" ? "Read & decide" : suggestion.action.replace("_", " ")}
            </span>
            <span className="text-[10px] opacity-70">
              confidence: {suggestion.confidence}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] opacity-90">{suggestion.reason}</p>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5 text-sm">
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Endpoint
            </h3>
            {source.zoning_endpoint ? (
              <a
                href={source.zoning_endpoint}
                target="_blank"
                rel="noreferrer"
                className="mt-1 block break-all rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-sky-700 hover:underline"
              >
                {source.zoning_endpoint}
              </a>
            ) : (
              <p className="mt-1 text-xs italic text-slate-400">—</p>
            )}
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-600">
              <dt className="text-slate-400">type</dt>
              <dd>{source.source_type ?? "—"}</dd>
              <dt className="text-slate-400">geometry</dt>
              <dd>{source.geometry_type ?? "—"}</dd>
              <dt className="text-slate-400">features</dt>
              <dd className="font-mono">{source.feature_count ?? "—"}</dd>
              <dt className="text-slate-400">discovered by</dt>
              <dd>{source.discovered_by ?? "—"}</dd>
              <dt className="text-slate-400">verified at</dt>
              <dd className="font-mono">{source.last_verified_at ?? "—"}</dd>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Confidence
            </h3>
            <ConfidenceBreakdown
              breakdown={source.confidence_breakdown}
              reasons={source.reasons}
            />
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Spatial diagnostics
              </h3>
              {!showSpatial && (
                <button
                  type="button"
                  onClick={() => setShowSpatial(true)}
                  className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                >
                  Run check
                </button>
              )}
            </div>
            {showSpatial ? (
              <SpatialCheckPanel
                jurisdictionId={jurisdictionId}
                sourceId={source.id}
                enabled
              />
            ) : (
              <p className="text-[11px] italic text-slate-400">
                Probes the upstream FeatureServer; click Run check.
              </p>
            )}
          </section>

          {source.rejected_reason && (
            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Current rejected_reason
              </h3>
              <p className="mt-1 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-800">
                {source.rejected_reason}
              </p>
            </section>
          )}

          <section>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Reject reason
            </h3>
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="custom reason (optional)"
              className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs focus:border-slate-400 focus:outline-none"
            />
            <div className="mt-2 flex flex-wrap gap-1">
              {QUICK_REJECT_REASONS.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  disabled={review.isPending}
                  onClick={() => doAction("reject", r.label)}
                  className="rounded-md border border-rose-200 bg-white px-2 py-0.5 text-[10px] font-medium text-rose-800 hover:bg-rose-50 disabled:opacity-50"
                  title={`Reject and record: "${r.label}"`}
                >
                  ✗ {r.label}
                </button>
              ))}
            </div>
            <h3 className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Notes
            </h3>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Optional notes attached to any action"
              className="w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-xs focus:border-slate-400 focus:outline-none"
            />
          </section>
        </div>

        <div className="space-y-2 border-t border-slate-200 p-4">
          {review.isError && (
            <p className="text-xs text-rose-600">
              {(review.error as Error)?.message ?? "Save failed."}
            </p>
          )}
          <ActionRow
            suggestion={suggestion.action}
            busy={review.isPending}
            onAct={doAction}
            onClose={onClose}
          />
          <p className="text-[10px] text-slate-400">
            Shortcuts:
            <KeyboardHint keys={["V"]} /> verify
            <KeyboardHint keys={["R"]} /> reject
            <KeyboardHint keys={["N"]} /> needs review
            <KeyboardHint keys={["U"]} /> unverify
            <KeyboardHint keys={["Esc"]} /> close
          </p>
        </div>
      </aside>
    </>
  );
}

function ActionRow({
  suggestion,
  busy,
  onAct,
  onClose,
}: {
  suggestion: ReturnType<typeof suggestActionForSource>["action"];
  busy: boolean;
  onAct: (action: SourceReviewAction) => void;
  onClose: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <ActionButton
        kind="verify"
        primary={suggestion === "verify"}
        busy={busy}
        onClick={() => onAct("verify")}
      />
      <ActionButton
        kind="needs_review"
        primary={suggestion === "needs_review"}
        busy={busy}
        onClick={() => onAct("needs_review")}
      />
      <ActionButton
        kind="reject"
        primary={suggestion === "reject"}
        busy={busy}
        onClick={() => onAct("reject")}
      />
      <ActionButton
        kind="unverify"
        primary={false}
        busy={busy}
        onClick={() => onAct("unverify")}
      />
      <button
        onClick={onClose}
        className="ml-auto rounded-md px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100"
      >
        Close
      </button>
    </div>
  );
}

interface ActionButtonProps {
  kind: SourceReviewAction;
  primary: boolean;
  busy: boolean;
  onClick: () => void;
}

function ActionButton({ kind, primary, busy, onClick }: ActionButtonProps) {
  const label =
    kind === "verify"
      ? "Verify"
      : kind === "reject"
        ? "Reject"
        : kind === "needs_review"
          ? "Needs review"
          : "Unverify";
  const hintKey =
    kind === "verify"
      ? "V"
      : kind === "reject"
        ? "R"
        : kind === "needs_review"
          ? "N"
          : "U";

  const baseTone =
    kind === "verify"
      ? "emerald"
      : kind === "reject"
        ? "rose"
        : kind === "needs_review"
          ? "indigo"
          : "slate";

  const primaryClass =
    baseTone === "emerald"
      ? "bg-emerald-600 text-white hover:bg-emerald-700"
      : baseTone === "rose"
        ? "bg-rose-600 text-white hover:bg-rose-700"
        : baseTone === "indigo"
          ? "bg-indigo-600 text-white hover:bg-indigo-700"
          : "bg-slate-700 text-white hover:bg-slate-800";

  const mutedClass =
    baseTone === "emerald"
      ? "border border-emerald-200 bg-white text-emerald-800 hover:bg-emerald-50"
      : baseTone === "rose"
        ? "border border-rose-200 bg-white text-rose-800 hover:bg-rose-50"
        : baseTone === "indigo"
          ? "border border-indigo-200 bg-white text-indigo-800 hover:bg-indigo-50"
          : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50";

  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={[
        "inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50",
        primary ? primaryClass : mutedClass,
      ].join(" ")}
      data-primary={primary || undefined}
    >
      {label}
      <KeyboardHint keys={[hintKey]} inline />
    </button>
  );
}

const TONE_CLASS = {
  emerald: "bg-emerald-50 text-emerald-900",
  rose: "bg-rose-50 text-rose-900",
  indigo: "bg-indigo-50 text-indigo-900",
  slate: "bg-slate-50 text-slate-700",
};
