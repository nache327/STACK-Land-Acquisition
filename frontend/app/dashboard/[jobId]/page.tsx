"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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

type MapBBox = [number, number, number, number] | null;

const TABLE_PAGE_SIZE = 100;
const MAP_PAGE_SIZE = 5000;

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

// ─────────────────────────────────────────────────────────────────────────────

function DashboardReady({ job }: { job: { jurisdiction_id: string | null; status: string; jurisdiction_input: string | null } }) {
  const jurisdictionId = job.jurisdiction_id;
  const router = useRouter();

  const reanalyzeMutation = useMutation({
    mutationFn: async () => {
      if (!job.jurisdiction_input) throw new Error("No jurisdiction input");
      return api.createJob({
        jurisdiction: job.jurisdiction_input,
        target_uses: ["self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"],
        force: true,
      });
    },
    onSuccess: (newJob) => {
      router.push(`/dashboard/${newJob.id}`);
    },
  });

  const [selectedParcelId, setSelectedParcelId] = useState<number | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [verifierOpen, setVerifierOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [bbox, setBBox] = useState<MapBBox>(null);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [shortlistName, setShortlistName] = useState("");
  const [shortlistSaved, setShortlistSaved] = useState<string | null>(null);

  // Layer visibility
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(
    initialLayerVisibility()
  );

  const { data: jurisdictionBounds } = useJurisdictionBounds(jurisdictionId);

  // Reset selection on filter change
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

  const activeBbox =
    bbox ??
    (jurisdictionBounds as [number, number, number, number] | null) ??
    null;

  const basePayload = useMemo<CandidateParcelSearchRequest | null>(() => {
    if (!jurisdictionId) return null;

    return {
      jurisdiction_id: jurisdictionId,
      target_use: "self_storage",
      filters: {
        ...(filters.zones.length > 0 ? { zones: filters.zones } : {}),
        ...(filters.zoneClasses.length > 0
          ? { zone_classes: filters.zoneClasses }
          : {}),
        ...(filters.storagePermissions.length > 0
          ? { storage_permissions: filters.storagePermissions }
          : {}),
        ...(filters.minAcres != null
          ? { min_acres: filters.minAcres }
          : {}),
        ...(filters.maxAcres != null
          ? { max_acres: filters.maxAcres }
          : {}),
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

  const tablePayload = useMemo(() => {
    if (!basePayload) return null;
    return { ...basePayload, page, page_size: TABLE_PAGE_SIZE };
  }, [basePayload, page]);

  const mapPayload = useMemo(() => {
    if (!basePayload) return null;
    return { ...basePayload, page: 1, page_size: MAP_PAGE_SIZE };
  }, [basePayload]);

  const { data: parcelList, isLoading: tableLoading } =
    useCandidateParcelSearch(tablePayload);

  const { data: mapResults, isLoading: mapLoading } =
    useCandidateParcelSearch(mapPayload);

  const { data: parcelDetail } = useParcelDetail(
    drawerOpen ? selectedParcelId : null
  );

  const parcels = parcelList?.items ?? [];
  const mapParcels = mapResults?.items ?? [];

  // ─── Shortlist save ─────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!jurisdictionId) throw new Error("No jurisdiction");
      return api.createShortlist({
        jurisdiction_id: jurisdictionId,
        name:
          shortlistName.trim() ||
          `Shortlist ${new Date().toLocaleDateString()}`,
        filters: (tablePayload ?? {}) as unknown as Record<string, unknown>,
        parcel_ids: Array.from(selectedIds),
      });
    },
    onSuccess: (sl) => {
      setShortlistSaved(sl.id);
      const url = api.shortlistExportUrl(sl.id);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${shortlistName || "shortlist"}.csv`;
      a.click();
    },
  });

  function handleParcelClick(parcel: CandidateParcelRow) {
    setSelectedParcelId(parcel.parcel_id);
    setDrawerOpen(true);
  }

  const totalPages = parcelList
    ? Math.max(1, Math.ceil(parcelList.total / parcelList.page_size))
    : 1;

  return (
    <div className="flex h-screen flex-col overflow-hidden">

      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-slate-800 bg-slate-950 px-5">
        <span className="text-white font-semibold">ParcelLogic</span>
        <button
          onClick={() => reanalyzeMutation.mutate()}
          disabled={reanalyzeMutation.isPending}
          className="text-xs text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          {reanalyzeMutation.isPending ? "Starting…" : "Re-analyze"}
        </button>
      </header>

      {/* Layout */}
      <div className="flex flex-1 overflow-hidden">

        <aside className="w-64 border-r border-slate-800 bg-slate-950">
          <FilterPanel jurisdictionId={jurisdictionId} onChange={setFilters} />
        </aside>

        <main className="flex-1">
          <ParcelMap
            jurisdictionId={jurisdictionId!}
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
        </main>

        <aside className="w-[420px] border-l bg-white">
          <ParcelTable
            parcels={parcels}
            onRowClick={handleParcelClick}
            selectedId={selectedParcelId}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
          />
        </aside>
      </div>

      {/* Drawer */}
      {drawerOpen && (
        <ParcelDrawer
          parcel={parcelDetail ?? null}
          jurisdictionId={jurisdictionId ?? ""}
          onClose={() => setDrawerOpen(false)}
        />
      )}

      {/* Shortlist Bar */}
      {selectedIds.size > 0 && (
        <div className="flex h-14 items-center gap-3 border-t border-slate-800 bg-slate-950 px-5">
          <span className="text-blue-300 text-xs">
            {selectedIds.size} selected
          </span>

          <input
            value={shortlistName}
            onChange={(e) => setShortlistName(e.target.value)}
            placeholder="Name shortlist…"
            className="bg-slate-800 text-white px-3 py-1.5 text-sm"
          />

          <button
            onClick={() => saveMutation.mutate()}
            className="bg-blue-600 px-4 py-1.5 text-white text-sm"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}