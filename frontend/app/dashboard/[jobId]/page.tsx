"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { useJobPoller } from "@/hooks/useJobPoller";
import { useCandidateParcelSearch, useParcelDetail } from "@/hooks/useParcels";
import { useJurisdictionBounds } from "@/hooks/useJurisdictionBounds";
import { JobProgress } from "@/components/JobProgress";
import { ParcelTable } from "@/components/ParcelTable";
import { ParcelDrawer } from "@/components/ParcelDrawer";
import { FilterPanel, DEFAULT_FILTERS } from "@/components/FilterPanel";
import type { FilterState } from "@/components/FilterPanel";
import { initialLayerVisibility, type LayerVisibility } from "@/components/LayerControl";
import type { CandidateParcelRow, CandidateParcelSearchRequest } from "@/lib/schemas";
import { api } from "@/lib/api";
import Link from "next/link";

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

type MapBBox = [number, number, number, number] | null;

const TABLE_PAGE_SIZE = 100;
const MAP_PAGE_SIZE = 5000;

export default function DashboardPage({ params }: Props) {
  const { jobId } = params;
  const { data: job, isLoading, error } = useJobPoller(jobId);

  if (isLoading || !job) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <span className="text-sm text-slate-400">Loading…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm text-red-600">Failed to load job: {String(error)}</p>
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
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [bbox, setBBox] = useState<MapBBox>(null);

  // Shortlist selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [shortlistName, setShortlistName] = useState("");
  const [shortlistSaved, setShortlistSaved] = useState<string | null>(null); // saved shortlist id

  // Layer visibility (used by Map + LayerControl)
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(
    initialLayerVisibility()
  );
  const { data: jurisdictionBounds } = useJurisdictionBounds(jurisdictionId);

  // Clear selection when filters change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [filters]);

  useEffect(() => {
    if (!jurisdictionBounds || bbox) return;
    setBBox(jurisdictionBounds as [number, number, number, number]);
  }, [bbox, jurisdictionBounds]);

  useEffect(() => {
    setPage(1);
  }, [filters, bbox]);

  const activeBbox = bbox ?? (jurisdictionBounds as [number, number, number, number] | null) ?? null;

  const basePayload = useMemo<CandidateParcelSearchRequest | null>(() => {
    if (!jurisdictionId) return null;
    return {
      jurisdiction_id: jurisdictionId,
      target_use: "self_storage",
      filters: {
        ...(filters.zones.length > 0 ? { zones: filters.zones } : {}),
        ...(filters.zoneClasses.length > 0 ? { zone_classes: filters.zoneClasses } : {}),
        ...(filters.minAcres != null ? { min_acres: filters.minAcres } : {}),
        ...(filters.maxAcres != null ? { max_acres: filters.maxAcres } : {}),
        vacant_only: filters.vacantOnly,
        exclude_flood: filters.excludeFlood,
        exclude_wetland: filters.excludeWetland,
      },
      bbox: activeBbox,
      search: filters.search.trim() || null,
      page: 1,
      page_size: TABLE_PAGE_SIZE,
      sort: "acres_desc",
    };
  }, [activeBbox, filters, jurisdictionId]);

  const tablePayload = useMemo<CandidateParcelSearchRequest | null>(() => {
    if (!basePayload) return null;
    return { ...basePayload, page, page_size: TABLE_PAGE_SIZE };
  }, [basePayload, page]);

  const mapPayload = useMemo<CandidateParcelSearchRequest | null>(() => {
    if (!basePayload) return null;
    return { ...basePayload, page: 1, page_size: MAP_PAGE_SIZE };
  }, [basePayload]);

  const { data: parcelList, isLoading: tableLoading } = useCandidateParcelSearch(tablePayload);
  const { data: mapResults, isLoading: mapLoading } = useCandidateParcelSearch(mapPayload);

  const { data: parcelDetail } = useParcelDetail(drawerOpen ? selectedParcelId : null);

  const parcels = parcelList?.items ?? [];
  const mapParcels = mapResults?.items ?? [];

  // ── Keyboard navigation ───────────────────────────────────────────────────
  const navigateParcel = useCallback(
    (direction: "up" | "down") => {
      if (parcels.length === 0) return;
      const currentIdx = parcels.findIndex((p) => p.parcel_id === selectedParcelId);
      let nextIdx: number;
      if (currentIdx === -1) {
        nextIdx = direction === "down" ? 0 : parcels.length - 1;
      } else {
        nextIdx =
          direction === "down"
            ? Math.min(currentIdx + 1, parcels.length - 1)
            : Math.max(currentIdx - 1, 0);
      }
      setSelectedParcelId(parcels[nextIdx].parcel_id);
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
        filters: (tablePayload ?? {}) as unknown as Record<string, unknown>,
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
  function handleParcelClick(parcel: CandidateParcelRow) {
    setSelectedParcelId(parcel.parcel_id);
    setDrawerOpen(true);
  }

  const totalPages = parcelList ? Math.max(1, Math.ceil(parcelList.total / parcelList.page_size)) : 1;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="text-sm font-semibold text-slate-900 hover:text-emerald-600"
          >
            Zoning Finder
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-sm text-slate-500">Dashboard</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">
            {parcelList?.total?.toLocaleString() ?? "…"} parcels
          </span>
          {jurisdictionId && (
            <Link
              href={`/ordinance/${jurisdictionId}`}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Zone Matrix
            </Link>
          )}
        </div>
      </header>

      {/* Three-pane body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: filter panel */}
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
          <FilterPanel jurisdictionId={jurisdictionId} onChange={setFilters} />
        </aside>

        {/* Center: map */}
        <main className="relative flex-1 overflow-hidden">
          {jurisdictionId ? (
            <ParcelMap
              jurisdictionId={jurisdictionId}
              parcels={mapParcels}
              isLoading={mapLoading}
              selectedParcelId={selectedParcelId}
              onParcelClick={(id) => {
                setSelectedParcelId(id);
                setDrawerOpen(true);
              }}
              onBoundsChange={setBBox}
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
            "flex w-[420px] shrink-0 flex-col overflow-hidden border-l border-slate-200 bg-white transition-all",
            drawerOpen ? "hidden" : "",
          ].join(" ")}
        >
          {tableLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              Loading parcels…
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-y-auto">
                <ParcelTable
                  parcels={parcels}
                  onRowClick={handleParcelClick}
                  selectedId={selectedParcelId}
                  selectedIds={selectedIds}
                  onSelectionChange={setSelectedIds}
                />
              </div>
              <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-xs text-slate-500">
                <span>
                  Page {page} of {totalPages}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={page <= 1}
                    className="rounded border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Prev
                  </button>
                  <button
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                    disabled={page >= totalPages}
                    className="rounded border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </aside>
      </div>

      {/* Parcel drawer */}
      {drawerOpen && (
        <ParcelDrawer
          parcel={parcelDetail ?? null}
          onClose={() => setDrawerOpen(false)}
          isInShortlist={selectedParcelId !== null && selectedIds.has(selectedParcelId)}
          onToggleShortlist={
            selectedParcelId !== null
              ? () => toggleShortlist(selectedParcelId)
              : undefined
          }
        />
      )}

      {/* Shortlist action bar — appears when parcels are checked */}
      {selectedIds.size > 0 && (
        <div className="flex h-14 shrink-0 items-center gap-3 border-t border-slate-200 bg-white px-4 shadow-md">
          <span className="text-sm font-medium text-slate-700">
            {selectedIds.size} parcel{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
          <div className="flex flex-1 items-center gap-2">
            <input
              type="text"
              value={shortlistName}
              onChange={(e) => setShortlistName(e.target.value)}
              placeholder="Name your shortlist…"
              className="w-56 rounded-md border border-slate-200 px-3 py-1.5 text-sm placeholder-slate-400 focus:border-emerald-500 focus:outline-none"
            />
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {saveMutation.isPending ? "Saving…" : "Save & Export CSV"}
            </button>
            {saveMutation.isError && (
              <span className="text-xs text-red-600">
                {(saveMutation.error as Error)?.message}
              </span>
            )}
            {shortlistSaved && (
              <a
                href={api.shortlistExportUrl(shortlistSaved)}
                className="text-xs text-emerald-600 underline"
                download
              >
                Download again
              </a>
            )}
          </div>
          <button
            onClick={() => {
              setSelectedIds(new Set());
              setShortlistSaved(null);
              setShortlistName("");
            }}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
