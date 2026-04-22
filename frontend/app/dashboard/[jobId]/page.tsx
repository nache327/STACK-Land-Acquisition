"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { useJobPoller } from "@/hooks/useJobPoller";
import { useParcelList } from "@/hooks/useParcels";
import { JobProgress } from "@/components/JobProgress";
import { ParcelTable } from "@/components/ParcelTable";
import { ParcelDrawer } from "@/components/ParcelDrawer";
import { FilterPanel, DEFAULT_FILTERS } from "@/components/FilterPanel";
import type { FilterState } from "@/components/FilterPanel";
import { initialLayerVisibility, type LayerVisibility } from "@/components/LayerControl";
import { useParcelDetail } from "@/hooks/useParcels";
import type { ParcelRow } from "@/lib/schemas";
import { api } from "@/lib/api";
import Link from "next/link";
import { ZoningChatPanel } from "@/components/ZoningChatPanel";

// MapLibre GL JS must not be SSR'd
const ParcelMap = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center bg-slate-100 text-sm text-slate-400">
      Loading map…
    </div>
  ),
});

interface Props {
  params: { jobId: string };
}

export default function DashboardPage({ params }: Props) {
  const { jobId } = params;
  const { data: job, isLoading, error } = useJobPoller(jobId);

  if (isLoading || !job) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070d1a]">
        <span className="text-sm text-slate-500">Loading…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070d1a]">
        <p className="text-sm text-red-400">Failed to load job: {String(error)}</p>
      </div>
    );
  }

  if (job.status !== "ready") {
    return <JobProgress job={job} />;
  }

  return <DashboardReady job={job} />;
}

// ─── Dashboard (ready state) ──────────────────────────────────────────────────

function DashboardReady({ job }: { job: { jurisdiction_id: string | null; status: string } }) {
  const jurisdictionId = job.jurisdiction_id;
  const [selectedParcelId, setSelectedParcelId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [verifierOpen, setVerifierOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);

  // Shortlist selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [shortlistName, setShortlistName] = useState("");
  const [shortlistSaved, setShortlistSaved] = useState<string | null>(null); // saved shortlist id

  // Layer visibility (used by Map + LayerControl)
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(
    initialLayerVisibility()
  );

  // Clear selection when filters change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [filters]);

  // Build query params from filter state
  const listParams: Record<string, string | number | boolean | string[]> = {
    page: 1,
    page_size: 200,
    vacant_only: filters.vacantOnly,
    exclude_flood: filters.excludeFlood,
    exclude_wetland: filters.excludeWetland,
  };
  if (filters.zones.length > 0) listParams.zones = filters.zones;
  if (filters.zoneClasses.length > 0)
    listParams.zone_classes = filters.zoneClasses;
  if (filters.minAcres != null) listParams.min_acres = filters.minAcres;
  if (filters.maxAcres != null) listParams.max_acres = filters.maxAcres;

  const { data: parcelList, isLoading: tableLoading } = useParcelList(
    jurisdictionId,
    listParams
  );

  const { data: parcelDetail } = useParcelDetail(drawerOpen ? selectedParcelId : null);

  const parcels = parcelList?.items ?? [];

  // ── Keyboard navigation ───────────────────────────────────────────────────
  const navigateParcel = useCallback(
    (direction: "up" | "down") => {
      if (parcels.length === 0) return;
      const currentIdx = parcels.findIndex((p) => p.id === selectedParcelId);
      let nextIdx: number;
      if (currentIdx === -1) {
        nextIdx = direction === "down" ? 0 : parcels.length - 1;
      } else {
        nextIdx =
          direction === "down"
            ? Math.min(currentIdx + 1, parcels.length - 1)
            : Math.max(currentIdx - 1, 0);
      }
      setSelectedParcelId(parcels[nextIdx].id);
      setDrawerOpen(true);
    },
    [parcels, selectedParcelId]
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Don't steal keys from input/textarea
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;

      if (e.key === "Escape") {
        setDrawerOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        navigateParcel("down");
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        navigateParcel("up");
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [navigateParcel]);

  // ── Shortlist toggle ──────────────────────────────────────────────────────
  function toggleShortlist(parcelId: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(parcelId)) next.delete(parcelId);
      else next.add(parcelId);
      return next;
    });
  }

  // ── Save shortlist + trigger CSV download ────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!jurisdictionId) throw new Error("No jurisdiction");
      return api.createShortlist({
        jurisdiction_id: jurisdictionId,
        name: shortlistName.trim() || `Shortlist ${new Date().toLocaleDateString()}`,
        filters: filters as unknown as Record<string, unknown>,
        parcel_ids: Array.from(selectedIds),
      });
    },
    onSuccess: (sl) => {
      setShortlistSaved(sl.id);
      // Trigger download
      const url = api.shortlistExportUrl(sl.id);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${shortlistName || "shortlist"}.csv`;
      a.click();
    },
  });

  // ── Parcel click ──────────────────────────────────────────────────────────
  function handleParcelClick(parcel: ParcelRow) {
    setSelectedParcelId(parcel.id);
    setDrawerOpen(true);
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Top bar — dark chrome */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-5">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="h-7 w-7 flex-shrink-0 overflow-hidden rounded-lg bg-blue-600 shadow-md shadow-blue-900/50 transition-opacity group-hover:opacity-90">
              <svg width="28" height="28" viewBox="0 0 36 36" fill="none">
                <rect x="5" y="5" width="11" height="11" rx="2" fill="white" opacity="0.95" />
                <rect x="20" y="5" width="11" height="11" rx="2" fill="white" opacity="0.45" />
                <rect x="5" y="20" width="11" height="11" rx="2" fill="white" opacity="0.45" />
                <rect x="20" y="20" width="11" height="11" rx="2" fill="white" opacity="0.95" />
              </svg>
            </div>
            <span className="text-sm font-bold text-white tracking-tight">ParcelLogic</span>
          </Link>
          <div className="h-4 w-px bg-slate-700" />
          <span className="text-sm text-slate-500">Dashboard</span>
        </div>
        <div className="flex items-center gap-2">
          {parcelList?.total != null && (
            <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 text-xs font-medium text-blue-300">
              {parcelList.total.toLocaleString()} parcels
            </span>
          )}
          {jurisdictionId && (
            <Link
              href={`/ordinance/${jurisdictionId}`}
              className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:text-white"
            >
              Zone Matrix
            </Link>
          )}
          <button
            onClick={() => setVerifierOpen((v) => !v)}
            className={[
              "rounded-lg border px-3 py-1.5 text-xs font-medium transition-all",
              verifierOpen
                ? "border-blue-500/50 bg-blue-600/20 text-blue-300"
                : "border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-600 hover:text-white",
            ].join(" ")}
          >
            ◎ Zoning Verifier
          </button>
        </div>
      </header>

      {/* Three-pane body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: filter panel — dark sidebar */}
        <aside className="dark-scroll w-64 shrink-0 overflow-y-auto border-r border-slate-800 bg-slate-950">
          <FilterPanel jurisdictionId={jurisdictionId} onChange={setFilters} />
        </aside>

        {/* Center: map */}
        <main className="relative flex-1 overflow-hidden">
          {jurisdictionId ? (
            <ParcelMap
              jurisdictionId={jurisdictionId}
              filters={filters}
              selectedParcelId={selectedParcelId}
              onParcelClick={(id) => {
                setSelectedParcelId(id);
                setDrawerOpen(true);
              }}
              visibility={layerVisibility}
              onVisibilityChange={setLayerVisibility}
            />
          ) : (
            <div className="flex h-full items-center justify-center bg-slate-100 text-sm text-slate-400">
              No jurisdiction data
            </div>
          )}
        </main>

        {/* Right: parcel table (hidden when drawer is open) */}
        <aside
          className={[
            "w-[420px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white transition-all",
            drawerOpen ? "hidden" : "",
          ].join(" ")}
        >
          {tableLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
                Loading parcels…
              </span>
            </div>
          ) : (
            <ParcelTable
              parcels={parcels}
              onRowClick={handleParcelClick}
              selectedId={selectedParcelId}
              selectedIds={selectedIds}
              onSelectionChange={setSelectedIds}
            />
          )}
        </aside>
      </div>

      {/* Parcel drawer */}
      {drawerOpen && !verifierOpen && (
        <ParcelDrawer
          parcel={parcelDetail ?? null}
          jurisdictionId={jurisdictionId ?? ""}
          onClose={() => setDrawerOpen(false)}
          isInShortlist={selectedParcelId !== null && selectedIds.has(selectedParcelId)}
          onToggleShortlist={
            selectedParcelId !== null
              ? () => toggleShortlist(selectedParcelId)
              : undefined
          }
        />
      )}

      {/* Zoning Verifier Chat Panel */}
      {verifierOpen && (
        <ZoningChatPanel
          jurisdictionId={jurisdictionId}
          cityName={undefined}
          onClose={() => setVerifierOpen(false)}
        />
      )}

      {/* Shortlist action bar */}
      {selectedIds.size > 0 && (
        <div className="flex h-14 shrink-0 items-center gap-3 border-t border-slate-800 bg-slate-950 px-5">
          <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 text-xs font-medium text-blue-300">
            {selectedIds.size} selected
          </span>
          <div className="flex flex-1 items-center gap-2">
            <input
              type="text"
              value={shortlistName}
              onChange={(e) => setShortlistName(e.target.value)}
              placeholder="Name this shortlist…"
              className="w-52 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-50"
            >
              {saveMutation.isPending ? "Saving…" : "Save & Export CSV"}
            </button>
            {saveMutation.isError && (
              <span className="text-xs text-red-400">
                {(saveMutation.error as Error)?.message}
              </span>
            )}
            {shortlistSaved && (
              <a
                href={api.shortlistExportUrl(shortlistSaved)}
                className="text-xs text-blue-400 underline"
                download
              >
                Download again
              </a>
            )}
          </div>
          <button
            onClick={() => { setSelectedIds(new Set()); setShortlistSaved(null); setShortlistName(""); }}
            className="text-xs text-slate-500 hover:text-slate-300 transition"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
