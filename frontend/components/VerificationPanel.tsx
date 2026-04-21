"use client";

/**
 * Three-layer zoning verification panel — embedded in ParcelDrawer.
 * Shows Layer 1 (Zoneomics), Layer 2 (City GIS match), Layer 3 (Ordinance AI).
 */

import { useState } from "react";
import {
  STATUS_CONFIG,
  type VerificationState,
  type Layer1Result,
  type Layer2Result,
  type Layer3Result,
} from "@/lib/verification";

interface VerificationPanelProps {
  state: VerificationState | null;
  layer1Loading: boolean;
  layer3Loading: boolean;
  error: string | null;
  onRunLayer3: () => void;
  onReset: () => void;
}

export function VerificationPanel({
  state,
  layer1Loading,
  layer3Loading,
  error,
  onRunLayer3,
  onReset,
}: VerificationPanelProps) {
  const [expanded, setExpanded] = useState<"l1" | "l2" | "l3" | null>(null);

  const cfg = state ? STATUS_CONFIG[state.overallStatus] : STATUS_CONFIG.UNVERIFIED;

  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold text-slate-700 text-[11px] uppercase tracking-wide">
          Zoning Verification
        </h3>
        {state && (
          <button
            onClick={onReset}
            className="text-slate-400 hover:text-slate-600 text-[10px]"
            title="Clear cached verification"
          >
            reset
          </button>
        )}
      </div>

      {/* Composite score badge */}
      {state && (
        <div
          className={[
            "mb-3 flex items-center gap-2 rounded-md border px-2.5 py-1.5",
            cfg.bg,
            cfg.border,
          ].join(" ")}
        >
          <span className={["h-2 w-2 rounded-full shrink-0", cfg.dot].join(" ")} />
          <span className={["font-semibold", cfg.color].join(" ")}>
            {state.compositeScore}/100 — {cfg.label}
          </span>
        </div>
      )}

      {/* Conflict flags */}
      {state?.conflictFlags.map((flag, i) => (
        <p key={i} className="mb-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-red-700">
          {flag}
        </p>
      ))}

      {/* Layer rows */}
      <div className="space-y-1">
        <LayerRow
          id="l1"
          label="Layer 1: Zoneomics API"
          loading={layer1Loading}
          expanded={expanded === "l1"}
          onToggle={() => setExpanded(expanded === "l1" ? null : "l1")}
          result={state?.layer1 ?? null}
          renderSummary={(l1: Layer1Result) => (
            <span>
              Zone: <strong>{l1.zoneCode || "—"}</strong>
              {l1.pluMatch && (
                <span className="ml-1 text-emerald-700">
                  · PLU: {l1.matchedTags.join(", ")}
                </span>
              )}
              {!l1.pluMatch && l1.status === "complete" && (
                <span className="ml-1 text-slate-400">· No PLU match</span>
              )}
              {l1.status === "no-coverage" && (
                <span className="ml-1 text-slate-400">· No coverage</span>
              )}
            </span>
          )}
          renderDetail={(l1: Layer1Result) => (
            <div className="space-y-1">
              <DetailRow label="Zone" value={l1.zoneCode} />
              <DetailRow label="Description" value={l1.zoneDescription} />
              <DetailRow label="PLU tags" value={l1.pluTags.join(", ") || "none"} />
              <DetailRow label="Permit type" value={l1.permitType ?? "unknown"} />
              <DetailRow label="Score" value={`+${l1.score} pts`} />
              <DetailRow label="Fetched" value={new Date(l1.fetchedAt).toLocaleString()} />
            </div>
          )}
        />

        <LayerRow
          id="l2"
          label="Layer 2: City GIS"
          loading={false}
          expanded={expanded === "l2"}
          onToggle={() => setExpanded(expanded === "l2" ? null : "l2")}
          result={state?.layer2 ?? null}
          renderSummary={(l2: Layer2Result) => (
            <span>
              {l2.matchType === "exact" && (
                <span className="text-emerald-700">✓ Exact match</span>
              )}
              {l2.matchType === "probable" && (
                <span className="text-lime-700">~ Probable match</span>
              )}
              {l2.matchType === "conflict" && (
                <span className="text-red-700 font-semibold">⚠ CONFLICT</span>
              )}
              {l2.matchType === "unavailable" && (
                <span className="text-slate-400">Unavailable</span>
              )}
              {l2.cityZoneCode && (
                <span className="ml-1 text-slate-500">
                  · City: {l2.cityZoneCode}
                </span>
              )}
            </span>
          )}
          renderDetail={(l2: Layer2Result) => (
            <div className="space-y-1">
              <DetailRow label="City zone code" value={l2.cityZoneCode ?? "—"} />
              <DetailRow label="Zoneomics code" value={l2.zoneomicsZoneCode ?? "—"} />
              <DetailRow label="Match type" value={l2.matchType} />
              <DetailRow label="Data source" value={l2.dataSource} />
              {l2.note && <DetailRow label="Note" value={l2.note} />}
              <DetailRow label="Score" value={`+${l2.score} pts`} />
            </div>
          )}
        />

        <LayerRow
          id="l3"
          label="Layer 3: Ordinance Text"
          loading={layer3Loading}
          expanded={expanded === "l3"}
          onToggle={() => setExpanded(expanded === "l3" ? null : "l3")}
          result={state?.layer3.status !== "not-run" ? state?.layer3 ?? null : null}
          notRunAction={
            state?.layer3.status === "not-run" || !state ? (
              <button
                onClick={onRunLayer3}
                disabled={layer3Loading}
                className="rounded bg-emerald-600 px-2 py-0.5 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {layer3Loading ? "Analyzing…" : "Verify Now"}
              </button>
            ) : undefined
          }
          renderSummary={(l3: Layer3Result) => (
            <span>
              {l3.status === "ordinance-not-found" && (
                <span className="text-slate-400">Ordinance not found</span>
              )}
              {l3.status === "complete" && l3.selfStorageStatus && (
                <span>
                  <StatusBadge status={l3.selfStorageStatus} />
                  {l3.classificationSource === "rule" && (
                    <span className="ml-1 text-amber-600">⚠ rule-based</span>
                  )}
                </span>
              )}
            </span>
          )}
          renderDetail={(l3: Layer3Result) => (
            <div className="space-y-1">
              <DetailRow label="Self-storage" value={l3.selfStorageStatus ?? "—"} />
              <DetailRow label="Keep/garage condo" value={l3.keepStatus ?? "—"} />
              <DetailRow label="AI confidence" value={l3.aiConfidence ?? "—"} />
              <DetailRow label="Source" value={l3.classificationSource ?? "—"} />
              {l3.evidence && (
                <div>
                  <p className="text-slate-500 mb-0.5">Evidence:</p>
                  <p className="italic text-slate-600 leading-snug">{l3.evidence}</p>
                </div>
              )}
              {l3.notes && <DetailRow label="Notes" value={l3.notes} />}
              <DetailRow label="Score" value={`+${l3.score} pts`} />
              <p className="mt-1 text-slate-400 leading-snug">
                AI interpretation — always verify with city planning staff before executing an LOI.
              </p>
            </div>
          )}
        />
      </div>

      {error && (
        <p className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-red-600">
          {error}
        </p>
      )}

      {/* Legend */}
      <div className="mt-3 border-t border-slate-200 pt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <span key={key} className="flex items-center gap-1">
            <span className={["h-1.5 w-1.5 rounded-full", cfg.dot].join(" ")} />
            {key}
          </span>
        ))}
      </div>
    </section>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function LayerRow<T>({
  id,
  label,
  loading,
  expanded,
  onToggle,
  result,
  notRunAction,
  renderSummary,
  renderDetail,
}: {
  id: string;
  label: string;
  loading: boolean;
  expanded: boolean;
  onToggle: () => void;
  result: T | null;
  notRunAction?: React.ReactNode;
  renderSummary: (r: T) => React.ReactNode;
  renderDetail: (r: T) => React.ReactNode;
}) {
  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        onClick={result ? onToggle : undefined}
        className={[
          "flex w-full items-start justify-between gap-2 px-2.5 py-2 text-left",
          result ? "cursor-pointer hover:bg-slate-50" : "cursor-default",
        ].join(" ")}
      >
        <span className="shrink-0 font-medium text-slate-700 text-[11px]">{label}</span>
        <span className="text-right text-[11px]">
          {loading ? (
            <span className="text-slate-400">Loading…</span>
          ) : result ? (
            renderSummary(result)
          ) : notRunAction ? (
            notRunAction
          ) : (
            <span className="text-slate-300">—</span>
          )}
        </span>
        {result && (
          <span className="shrink-0 text-slate-400 text-[10px]">
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </button>
      {expanded && result && (
        <div className="border-t border-slate-100 px-2.5 py-2 text-[11px] text-slate-600">
          {renderDetail(result)}
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-400 shrink-0">{label}</span>
      <span className="text-right text-slate-700">{value}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    PERMITTED_BY_RIGHT: "bg-emerald-100 text-emerald-800",
    CUP_REQUIRED:       "bg-amber-100 text-amber-800",
    PROHIBITED:         "bg-red-100 text-red-800",
    NOT_MENTIONED:      "bg-slate-100 text-slate-600",
  };
  const labels: Record<string, string> = {
    PERMITTED_BY_RIGHT: "Permitted",
    CUP_REQUIRED:       "CUP Required",
    PROHIBITED:         "Prohibited",
    NOT_MENTIONED:      "Not Mentioned",
  };
  return (
    <span
      className={[
        "rounded px-1.5 py-0.5 text-[10px] font-medium",
        colors[status] ?? "bg-slate-100 text-slate-600",
      ].join(" ")}
    >
      {labels[status] ?? status}
    </span>
  );
}
