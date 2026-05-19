"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CoverageTierPill } from "@/components/admin/CoverageTierPill";
import { CrossJurisdictionBulkBar } from "@/components/admin/CrossJurisdictionBulkBar";
import { CrossJurisdictionSourceTable } from "@/components/admin/CrossJurisdictionSourceTable";
import { QueueTabBar, type QueueTab } from "@/components/admin/QueueTabBar";
import { SessionVelocityCounter } from "@/components/admin/SessionVelocityCounter";
import { SourceDetailDrawer } from "@/components/admin/SourceDetailDrawer";
import { VelocityStrip } from "@/components/admin/VelocityStrip";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import {
  useCrossJurisdictionBulkReview,
  useSourcesQueue,
} from "@/hooks/useSourcesQueue";
import { isLowSignalScore } from "@/lib/admin/confidenceTier";
import {
  computeHighRoiQueue,
  computeIngestReady,
} from "@/lib/admin/highRoi";
import {
  buildMunicipalityIndex,
  sortQueueByMode,
  type QueueSortMode,
} from "@/lib/admin/roiWeight";
import {
  appendDecision,
  computeStats,
  type SessionDecision,
} from "@/lib/admin/sessionVelocity";
import { sourceIsSpatiallyBlocked } from "@/lib/admin/municipality";
import { deriveTier } from "@/lib/admin/tier";
import type {
  BulkReviewAction,
  QueueSource,
  SourceReviewAction,
} from "@/lib/schemas";

type TabKey = "pending" | "spatial" | "rejects" | "ingest" | "roi";

const VALID_TABS: TabKey[] = ["pending", "spatial", "rejects", "ingest", "roi"];
const VELOCITY_HOURS = 24 * 7;

export default function QueuePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: TabKey = (VALID_TABS as string[]).includes(tabParam ?? "")
    ? (tabParam as TabKey)
    : "pending";

  const setTab = (next: TabKey) => {
    const sp = new URLSearchParams(Array.from(searchParams.entries()));
    sp.set("tab", next);
    router.replace(`?${sp.toString()}`, { scroll: false });
  };

  // ---- Queries (always enabled — payloads are small and cached) ---------

  const pending = useSourcesQueue({ status: "pending", limit: 500 });
  const spatial = useSourcesQueue({
    status: "pending",
    spatial_blocked: true,
    limit: 500,
  });
  const rejects = useSourcesQueue({
    status: "rejected",
    recent_hours: VELOCITY_HOURS,
    limit: 500,
  });
  const verifiedRecent = useSourcesQueue({
    status: "verified",
    recent_hours: VELOCITY_HOURS,
    limit: 1000,
  });
  const needsReviewRecent = useSourcesQueue({
    status: "needs_review",
    recent_hours: VELOCITY_HOURS,
    limit: 500,
  });
  const coverage = useAdminCoverage();

  const ingestReady = useMemo(
    () =>
      coverage.data ? computeIngestReady(coverage.data.jurisdictions) : [],
    [coverage.data],
  );
  const roiRows = useMemo(
    () =>
      coverage.data
        ? computeHighRoiQueue({ jurisdictions: coverage.data.jurisdictions })
        : [],
    [coverage.data],
  );

  // ---- Selection + decision state ----------------------------------------

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drawer, setDrawer] = useState<QueueSource | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<QueueSortMode>("confidence");
  const [hideLowSignal, setHideLowSignal] = useState(true);
  const [decisions, setDecisions] = useState<SessionDecision[]>([]);

  const municipalityIndex = useMemo(
    () => buildMunicipalityIndex(coverage.data?.jurisdictions ?? []),
    [coverage.data],
  );
  const sessionStats = useMemo(() => computeStats(decisions), [decisions]);

  function recordDecision(action: SourceReviewAction, latencyMs: number) {
    setDecisions((prev) =>
      appendDecision(prev, { action, latency_ms: latencyMs, at_ms: Date.now() }),
    );
  }

  // Switch tabs → clear selection so the operator never accidentally bulk-acts
  // on rows they can no longer see.
  useEffect(() => {
    setSelected(new Set());
  }, [tab]);

  const bulk = useCrossJurisdictionBulkReview();

  function rawRowsForTab(): QueueSource[] {
    if (tab === "pending") return pending.data?.sources ?? [];
    if (tab === "spatial") return spatial.data?.sources ?? [];
    if (tab === "rejects") return rejects.data?.sources ?? [];
    return [];
  }

  /** Rows after noise suppression + the operator's sort mode. */
  function activeRows(): QueueSource[] {
    const raw = rawRowsForTab();
    const filtered = hideLowSignal
      ? raw.filter(
          (r) =>
            !isLowSignalScore(r.confidence_score)
            || sourceIsSpatiallyBlocked(r),
        )
      : raw;
    return sortQueueByMode(filtered, sortMode, municipalityIndex);
  }

  // Drop selections that no longer appear in the active row set.
  useEffect(() => {
    if (!["pending", "spatial", "rejects"].includes(tab)) return;
    const ids = new Set(activeRows().map((r) => r.id));
    setSelected((prev) => {
      let changed = false;
      const next = new Set<string>();
      prev.forEach((id) => {
        if (ids.has(id)) next.add(id);
        else changed = true;
      });
      return changed ? next : prev;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, pending.data, spatial.data, rejects.data]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    const rows = activeRows();
    setSelected((prev) =>
      prev.size === rows.length
        ? new Set()
        : new Set(rows.map((r) => r.id)),
    );
  }

  const selectionsByJur = useMemo(() => {
    const rows = activeRows();
    const byId = new Map(rows.map((r) => [r.id, r]));
    return Array.from(selected)
      .map((id) => byId.get(id))
      .filter((r): r is QueueSource => !!r)
      .map((r) => ({
        source_id: r.id,
        jurisdiction_id: r.jurisdiction_id,
      }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, pending.data, spatial.data, rejects.data, tab]);

  const jurisdictionsTouched = useMemo(() => {
    const s = new Set<string>();
    selectionsByJur.forEach((sel) => s.add(sel.jurisdiction_id));
    return s.size;
  }, [selectionsByJur]);

  function handleBulk(action: BulkReviewAction, rejectedReason?: string) {
    if (selectionsByJur.length === 0) return;
    bulk.mutate(
      { selections: selectionsByJur, action, rejectedReason },
      {
        onSuccess: (res) => {
          setSelected(new Set());
          setToast(
            `${action}: ${res.updated} updated across ${res.jurisdictions_touched} juris (${res.skipped} skipped)`,
          );
          setTimeout(() => setToast(null), 5000);
        },
      },
    );
  }

  // ---- Tab definitions ---------------------------------------------------

  const tabs: QueueTab[] = [
    {
      key: "pending",
      label: "Pending review",
      count: pending.data?.total ?? null,
      hint: "All zoning_sources where validation_status='pending', sorted by confidence desc.",
    },
    {
      key: "spatial",
      label: "Spatially blocked",
      count: spatial.data?.total ?? null,
      hint: "Pending sources whose persisted confidence_breakdown carries wrong_state, wrong_county, or bbox_overlap_disjoint.",
    },
    {
      key: "rejects",
      label: "Recent rejects",
      count: rejects.data?.total ?? null,
      hint: "Rejected sources updated in the last 7 days — useful for spotting rejection patterns.",
    },
    {
      key: "ingest",
      label: "Ingest-ready",
      count: ingestReady.length,
      hint: "Jurisdictions with verified sources but no overlays ingested yet (tier T3).",
    },
    {
      key: "roi",
      label: "High-ROI towns",
      count: roiRows.length,
      hint: "Cross-jurisdiction ranking of municipalities with the largest unzoned-parcel count.",
    },
  ];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">
          Operator queues
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Cross-jurisdiction work surfaces, ranked by leverage. Bulk-act
          across jurisdictions in one batch.
        </p>
      </header>

      <VelocityStrip
        windowLabel={`${Math.round(VELOCITY_HOURS / 24)}d`}
        stats={[
          {
            label: "Verified",
            value: verifiedRecent.data?.total ?? "—",
            tone: "emerald",
            hint: "Sources marked verified in the last 7 days (count from last_verified_at via updated_at proxy).",
          },
          {
            label: "Rejected",
            value: rejects.data?.total ?? "—",
            tone: "rose",
          },
          {
            label: "Needs review",
            value: needsReviewRecent.data?.total ?? "—",
            tone: "amber",
          },
          {
            label: "Open pending",
            value: pending.data?.total ?? "—",
            tone: "slate",
            hint: "Backlog size right now — not time-windowed.",
          },
          {
            label: "Spatial blocked",
            value: spatial.data?.total ?? "—",
            tone: spatial.data && spatial.data.total > 0 ? "rose" : "slate",
          },
        ]}
      />

      <QueueTabBar tabs={tabs} active={tab} onSelect={(k) => setTab(k as TabKey)} />

      {toast && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          {toast}
        </div>
      )}
      {bulk.isError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(bulk.error as Error)?.message ?? "Bulk review failed."}
        </div>
      )}

      <SessionVelocityCounter stats={sessionStats} />

      {(tab === "pending" || tab === "spatial" || tab === "rejects") && (
        <SourceQueueTab
          query={
            tab === "pending" ? pending : tab === "spatial" ? spatial : rejects
          }
          rows={activeRows()}
          rawCount={rawRowsForTab().length}
          selected={selected}
          onToggle={toggle}
          onToggleAll={toggleAll}
          onOpenDrawer={setDrawer}
          municipalityIndex={municipalityIndex}
          sortMode={sortMode}
          onSortMode={setSortMode}
          hideLowSignal={hideLowSignal}
          onHideLowSignal={setHideLowSignal}
          jurisdictionsTouched={jurisdictionsTouched}
          bulkBusy={bulk.isPending}
          onBulk={handleBulk}
          onClearSelection={() => setSelected(new Set())}
          emptyMessage={emptyMessageFor(tab)}
        />
      )}

      {tab === "ingest" && (
        <IngestReadyTable rows={ingestReady} />
      )}
      {tab === "roi" && <HighRoiTable rows={roiRows} />}

      {drawer && (
        <SourceDetailDrawer
          jurisdictionId={drawer.jurisdiction_id}
          source={drawer}
          onClose={() => setDrawer(null)}
          onDecision={recordDecision}
          onAdvance={() => {
            // Look up the next row in the post-filter / post-sort list.
            const list = activeRows();
            const idx = list.findIndex((r) => r.id === drawer.id);
            const next =
              idx === -1 || idx + 1 >= list.length ? null : list[idx + 1];
            setDrawer(next);
          }}
        />
      )}
    </div>
  );
}

function emptyMessageFor(tab: TabKey): string {
  if (tab === "pending") return "No pending sources — queue is clear.";
  if (tab === "spatial")
    return "No spatially-blocked sources in the pending queue.";
  if (tab === "rejects") return "No rejections in the last 7 days.";
  return "Nothing here.";
}

// ---- Sub-components -------------------------------------------------------

interface SourceQueueTabProps {
  query: ReturnType<typeof useSourcesQueue>;
  rows: QueueSource[];
  rawCount: number;
  selected: Set<string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onOpenDrawer: (s: QueueSource) => void;
  municipalityIndex: ReturnType<typeof buildMunicipalityIndex>;
  sortMode: QueueSortMode;
  onSortMode: (m: QueueSortMode) => void;
  hideLowSignal: boolean;
  onHideLowSignal: (v: boolean) => void;
  jurisdictionsTouched: number;
  bulkBusy: boolean;
  onBulk: (action: BulkReviewAction, rejectedReason?: string) => void;
  onClearSelection: () => void;
  emptyMessage: string;
}

function SourceQueueTab({
  query,
  rows,
  rawCount,
  selected,
  onToggle,
  onToggleAll,
  onOpenDrawer,
  municipalityIndex,
  sortMode,
  onSortMode,
  hideLowSignal,
  onHideLowSignal,
  jurisdictionsTouched,
  bulkBusy,
  onBulk,
  onClearSelection,
  emptyMessage,
}: SourceQueueTabProps) {
  if (query.isError) {
    return (
      <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
        {(query.error as Error)?.message ?? "Queue load failed."}
      </p>
    );
  }
  const noisySuppressed = rawCount - rows.length;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px]">
        <span className="font-medium text-slate-600">Sort:</span>
        <SortButton
          label="Confidence"
          mode="confidence"
          active={sortMode === "confidence"}
          onClick={onSortMode}
        />
        <SortButton
          label="ROI"
          mode="roi"
          active={sortMode === "roi"}
          onClick={onSortMode}
        />
        <SortButton
          label="Conf × ROI"
          mode="confidence_x_roi"
          active={sortMode === "confidence_x_roi"}
          onClick={onSortMode}
        />
        <label className="ml-3 inline-flex items-center gap-1 text-slate-600">
          <input
            type="checkbox"
            checked={hideLowSignal}
            onChange={(e) => onHideLowSignal(e.target.checked)}
          />
          Hide low-signal (&lt; 30)
        </label>
        {noisySuppressed > 0 && hideLowSignal && (
          <span className="text-slate-400">
            · {noisySuppressed} junk rows hidden
          </span>
        )}
        <span className="ml-auto text-slate-500">
          Showing {rows.length} of {query.data?.total ?? "—"}
        </span>
      </div>

      <CrossJurisdictionBulkBar
        selectedCount={selected.size}
        jurisdictionsTouched={jurisdictionsTouched}
        busy={bulkBusy}
        onAction={onBulk}
        onClear={onClearSelection}
      />
      <CrossJurisdictionSourceTable
        rows={rows}
        selected={selected}
        onToggle={onToggle}
        onToggleAll={onToggleAll}
        onOpenRow={onOpenDrawer}
        municipalityIndex={municipalityIndex}
        emptyMessage={query.isPending ? "Loading…" : emptyMessage}
      />
      <p className="text-[11px] text-slate-500">
        Click a layer title to open the review drawer. Keyboard:{" "}
        <kbd className="rounded border border-slate-200 px-1 font-mono">V</kbd>{" "}
        verify,{" "}
        <kbd className="rounded border border-slate-200 px-1 font-mono">R</kbd>{" "}
        reject,{" "}
        <kbd className="rounded border border-slate-200 px-1 font-mono">N</kbd>{" "}
        needs-review. The drawer auto-advances to the next row after each
        decision.
      </p>
    </>
  );
}

function SortButton({
  label,
  mode,
  active,
  onClick,
}: {
  label: string;
  mode: QueueSortMode;
  active: boolean;
  onClick: (m: QueueSortMode) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(mode)}
      className={[
        "rounded px-2 py-0.5",
        active
          ? "bg-slate-900 text-white"
          : "border border-slate-200 text-slate-600 hover:bg-slate-50",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function IngestReadyTable({
  rows,
}: {
  rows: ReturnType<typeof computeIngestReady>;
}) {
  if (rows.length === 0) {
    return (
      <p className="rounded-md border border-slate-200 bg-white px-3 py-4 text-center text-xs italic text-slate-400">
        Nothing ingest-ready — verify some sources first.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Jurisdiction</th>
            <th className="px-3 py-2">Tier</th>
            <th className="px-3 py-2 text-right">Verified sources</th>
            <th className="px-3 py-2 text-right">Pending</th>
            <th className="px-3 py-2 text-right">Parcels</th>
            <th className="px-3 py-2">Next step</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((j) => {
            const tier = deriveTier(j);
            return (
              <tr key={j.jurisdiction_id} className="hover:bg-slate-50">
                <td className="px-3 py-2">
                  <Link
                    href={`/admin/coverage/${j.jurisdiction_id}`}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {j.jurisdiction_name}
                  </Link>
                  {j.county && (
                    <span className="ml-1 text-xs text-slate-500">
                      · {j.county}
                    </span>
                  )}
                  {j.state && (
                    <span className="ml-1 font-mono text-[10px] text-slate-400">
                      {j.state}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <CoverageTierPill tier={tier} />
                </td>
                <td className="px-3 py-2 text-right font-mono text-emerald-700">
                  {j.source_count_verified ?? 0}
                </td>
                <td className="px-3 py-2 text-right font-mono text-amber-700">
                  {j.source_count_pending ?? 0}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {j.parcel_count ?? 0}
                </td>
                <td className="px-3 py-2">
                  <Link
                    href={`/admin/sources/${j.jurisdiction_id}?status=verified`}
                    className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-slate-800"
                  >
                    Review verified →
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function HighRoiTable({ rows }: { rows: ReturnType<typeof computeHighRoiQueue> }) {
  if (rows.length === 0) {
    return (
      <p className="rounded-md border border-slate-200 bg-white px-3 py-4 text-center text-xs italic text-slate-400">
        No municipality_breakdown data available yet — run a coverage refresh.
      </p>
    );
  }
  const maxUnzoned = rows[0]?.unzoned_parcels ?? 1;
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Municipality</th>
            <th className="px-3 py-2">Jurisdiction</th>
            <th className="px-3 py-2 text-right">Unzoned</th>
            <th className="px-3 py-2">ROI</th>
            <th className="px-3 py-2 text-right">Coverage</th>
            <th className="px-3 py-2 text-right">Pending</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => {
            const barPct = Math.round((r.unzoned_parcels / maxUnzoned) * 100);
            return (
              <tr key={r.key} className="hover:bg-slate-50">
                <td className="px-3 py-2 font-mono text-[11px] text-slate-400">
                  {i + 1}
                </td>
                <td className="px-3 py-2 font-medium text-slate-800">
                  {r.municipality}
                </td>
                <td className="px-3 py-2 text-slate-600">
                  <Link
                    href={`/admin/coverage/${r.jurisdiction_id}`}
                    className="hover:underline"
                  >
                    {r.jurisdiction_name}
                  </Link>
                  {r.state && (
                    <span className="ml-1 font-mono text-[10px] text-slate-400">
                      {r.state}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono text-rose-700">
                  {r.unzoned_parcels.toLocaleString()}
                </td>
                <td className="px-3 py-2">
                  <span className="block h-2 rounded-full bg-slate-100">
                    <span
                      className="block h-2 rounded-full bg-rose-500"
                      style={{ width: `${barPct}%` }}
                    />
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-[11px] text-slate-600">
                  {Math.round(r.zoning_pct)}%
                </td>
                <td className="px-3 py-2 text-right font-mono text-amber-700">
                  {r.jurisdiction_pending}
                </td>
                <td className="px-3 py-2 text-right">
                  <Link
                    href={`/admin/sources/${r.jurisdiction_id}?municipality=${encodeURIComponent(r.municipality)}`}
                    className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                  >
                    Sources →
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
