"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useJobPoller } from "@/hooks/useJobPoller";
import { useCandidateParcelSearch, useParcelDetail } from "@/hooks/useParcels";
import { useJurisdictionBounds } from "@/hooks/useJurisdictionBounds";
import { JobProgress } from "@/components/JobProgress";
import { ParcelTable } from "@/components/ParcelTable";
import { ParcelDrawer } from "@/components/ParcelDrawer";
import { FilterPanel, DEFAULT_FILTERS } from "@/components/FilterPanel";
import { ImportModal } from "@/components/ImportModal";
import type { FilterState } from "@/components/FilterPanel";
import { initialLayerVisibility, type LayerVisibility } from "@/components/LayerControl";
import type { CandidateParcelRow, CandidateParcelSearchRequest, SaturationBatchResult } from "@/lib/schemas";
import type { ColorMode } from "@/lib/layers";
import { api } from "@/lib/api";
import Link from "next/link";
import { ZoningChatPanel } from "@/components/ZoningChatPanel";
import { fetchIsochrone, fetchCensusTracts, clearIsochroneCache, type IsochroneResult, type TractData } from "@/lib/isochrone";
import type { DriveTimeMode } from "@/components/Map";
import { PIPELINE_STEPS, STAGE_LABELS } from "@/hooks/useJobPoller";
import { BuyBoxPanel } from "@/components/BuyBoxPanel";
import {
  DEFAULT_FILTER,
  getDefaultPreset,
  evaluateAll,
  isFilterActive,
  type BuyBoxFilter,
  type EvaluationStatus,
} from "@/lib/buy-box-filter";
import {
  precomputeCityIsochrones,
  saveCityCache,
  loadCityCacheAsync,
  clearCityCache,
  getCacheMetadata,
  type PrecomputedParcelData,
  type PrecomputeStatus,
} from "@/lib/isochrone-precompute";

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
  // Background mode: once parcels are loaded we're on the map — slow the poll rate
  const [inBackground, setInBackground] = useState(false);
  const { data: job, isLoading, error } = useJobPoller(jobId, inBackground);

  // Navigate to map as soon as parcels are ingested — don't wait for zoning/overlays.
  // The pipeline sets progress.status="building_zoning" the moment parcel upsert finishes.
  // Computed before early returns so hooks are always called in the same order.
  const parcelsReady = !!(
    job && (
      job.status === "ready" ||
      job.status === "downloading_zoning" ||
      job.status === "running_overlays" ||
      job.status === "parsing_ordinance" ||
      (job.status === "ingesting_parcels" &&
        ["cached", "upserting"].includes((job.progress as any)?.ingest_phase)) ||
      // Failed/cancelled jobs that have a jurisdiction_id already have parcels in the
      // DB — go straight to the map so the user isn't stuck on the error screen.
      ((job.status === "failed" || job.status === "cancelled") && !!job.jurisdiction_id)
    )
  );

  // Once parcels are ready, switch poller to background (8s interval)
  useEffect(() => {
    if (parcelsReady) setInBackground(true);
  }, [parcelsReady]);

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

  if (!parcelsReady) {
    return <JobProgress job={job} />;
  }

  return <DashboardReady job={job} />;
}

// ─────────────────────────────────────────────────────────────────────────────

function DashboardReady({ job }: { job: { jurisdiction_id: string | null; status: string; jurisdiction_input: string | null; progress?: Record<string, unknown> | null } }) {
  const jurisdictionId = job.jurisdiction_id;
  const router = useRouter();
  const [bgPanelOpen, setBgPanelOpen] = useState(false);
  const [bgComplete, setBgComplete] = useState(false);

  const isBackground = job.status !== "ready" && job.status !== "failed" && job.status !== "cancelled";

  // Flash "complete" badge briefly then hide
  useEffect(() => {
    if (job.status === "ready") {
      setBgComplete(true);
      const t = setTimeout(() => setBgComplete(false), 4000);
      return () => clearTimeout(t);
    }
  }, [job.status]);

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
  const [flyTrigger, setFlyTrigger] = useState(0);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [verifierOpen, setVerifierOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [bbox, setBBox] = useState<MapBBox>(null);

  // Saturation analysis state
  const [colorMode, setColorMode] = useState<ColorMode>("permission");
  const [saturationData, setSaturationData] = useState<Map<number, SaturationBatchResult>>(new Map());
  const [saturationLoading, setSaturationLoading] = useState(false);
  const [onlyUnderserved, setOnlyUnderserved] = useState(false);
  const [satThresholdLow, setSatThresholdLow] = useState<number>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("satThresholdLow");
      return saved ? parseFloat(saved) : 7;
    }
    return 7;
  });
  const [satThresholdHigh, setSatThresholdHigh] = useState<number>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("satThresholdHigh");
      return saved ? parseFloat(saved) : 10;
    }
    return 10;
  });

  // Drive-time isochrone state
  const [driveTimeMode, setDriveTimeMode] = useState<DriveTimeMode>("off");
  const [isochroneData, setIsochroneData] = useState<IsochroneResult | null>(null);
  const [isochroneWealth, setIsochroneWealth] = useState<TractData[] | null>(null);
  const [pinnedIsochroneData, setPinnedIsochroneData] = useState<IsochroneResult | null>(null);
  const [isochroneLoading, setIsochroneLoading] = useState(false);

  // Keep layer state
  const [keepActive, setKeepActive] = useState(false);
  const [keepMinScore, setKeepMinScore] = useState(55);

  // Buy-box precompute state
  const [precomputeData, setPrecomputeData] = useState(new Map<string, PrecomputedParcelData>());
  const [precomputeStatus, setPrecomputeStatus] = useState<PrecomputeStatus | null>(null);
  const [buyBoxFilter, setBuyBoxFilter] = useState<BuyBoxFilter>(DEFAULT_FILTER);
  const precomputeAbortRef = useRef<AbortController | null>(null);
  const pendingBatchRef = useRef(new Map<string, PrecomputedParcelData>());
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const buyBoxDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Persist saturation threshold settings to localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("satThresholdLow", String(satThresholdLow));
    }
  }, [satThresholdLow]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("satThresholdHigh", String(satThresholdHigh));
    }
  }, [satThresholdHigh]);

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

  // When colorMode switches to saturation, fetch batch saturation data for all map parcels
  useEffect(() => {
    if (colorMode !== "saturation") return;
    const ids = mapParcels.map((p) => p.parcel_id);
    if (!ids.length) return;

    setSaturationLoading(true);
    const chunks: number[][] = [];
    for (let i = 0; i < ids.length; i += 1000) chunks.push(ids.slice(i, i + 1000));

    Promise.allSettled(chunks.map((chunk) => api.getSaturationBatch(chunk, 3)))
      .then((results) => {
        const merged = new Map<number, SaturationBatchResult>();
        for (const r of results) {
          if (r.status === "fulfilled") {
            for (const [k, v] of Object.entries(r.value)) {
              merged.set(Number(k), v as SaturationBatchResult);
            }
          }
        }
        setSaturationData(merged);
      })
      .finally(() => setSaturationLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colorMode, mapParcels]);

  // Compute centroid of selected parcel for ring visualization
  const selectedParcelCentroid = useMemo<[number, number] | null>(() => {
    if (!selectedParcelId) return null;
    const parcel = mapParcels.find((p) => p.parcel_id === selectedParcelId);
    if (!parcel?.geom) return null;
    const geom = parcel.geom as unknown as GeoJSON.Geometry;
    const flat: number[][] = [];
    const collect = (c: unknown): void => {
      if (!Array.isArray(c)) return;
      if (typeof c[0] === "number") { flat.push(c as number[]); return; }
      (c as unknown[]).forEach(collect);
    };
    if ("coordinates" in geom) collect(geom.coordinates);
    if (!flat.length) return null;
    const lngs = flat.map((c) => c[0]);
    const lats = flat.map((c) => c[1]);
    return [
      (Math.min(...lngs) + Math.max(...lngs)) / 2,
      (Math.min(...lats) + Math.max(...lats)) / 2,
    ];
  }, [selectedParcelId, mapParcels]);

  // Apply threshold filter client-side (re-colors without a new API call)
  const effectiveSaturationData = useMemo(() => {
    if (!saturationData.size) return saturationData;
    const out = new Map<number, SaturationBatchResult>();
    for (const [id, v] of Array.from(saturationData.entries())) {
      const spp = v.sqft_per_person;
      let color: "green" | "yellow" | "red" | "gray";
      if (spp === null || spp === undefined) color = "gray";
      else if (spp < satThresholdLow) color = "green";
      else if (spp < satThresholdHigh) color = "yellow";
      else color = "red";
      out.set(id, { ...v, color });
    }
    return out;
  }, [saturationData, satThresholdLow, satThresholdHigh]);

  // ─── Buy-box precompute ──────────────────────────────────────────────────

  function scheduleFlush() {
    if (flushTimerRef.current) return;
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      const batch = new Map(pendingBatchRef.current);
      pendingBatchRef.current.clear();
      setPrecomputeData((prev) => new Map([...Array.from(prev), ...Array.from(batch)]));
    }, 500);
  }

  function startPrecompute(cityId: string, existingData?: Map<string, PrecomputedParcelData>) {
    precomputeAbortRef.current?.abort();
    clearIsochroneCache(); // reset in-memory tractCache so Census calls are fresh
    const ctrl = new AbortController();
    precomputeAbortRef.current = ctrl;

    precomputeCityIsochrones(mapParcels, cityId, {
      onProgress: (status) => setPrecomputeStatus(status),
      onParcelComputed: (parcelId, data) => {
        pendingBatchRef.current.set(parcelId, data);
        scheduleFlush();
      },
      signal: ctrl.signal,
      existingData,
    }).then((results) => {
      if (ctrl.signal.aborted) return;
      saveCityCache(cityId, results, results.size);
      const meta = getCacheMetadata(cityId);
      setPrecomputeStatus({
        progress: results.size,
        total: results.size,
        complete: true,
        lastComputed: meta?.lastComputed,
      });
    }).catch((err) => {
      if (!ctrl.signal.aborted) console.warn("[precompute] run failed:", err);
    });
  }

  useEffect(() => {
    if (!jurisdictionId) {
      precomputeAbortRef.current?.abort();
      return;
    }
    loadCityCacheAsync(jurisdictionId).then((cached) => {
      if (cached && cached.size > 0) {
        setPrecomputeData(cached);
        const meta = getCacheMetadata(jurisdictionId);
        setPrecomputeStatus({
          progress: cached.size,
          total: cached.size,
          complete: true,
          lastComputed: meta?.lastComputed,
        });
      } else {
        startPrecompute(jurisdictionId);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jurisdictionId]);

  const parcelEvaluations = useMemo<Map<string, EvaluationStatus>>(() => {
    if (!isFilterActive(buyBoxFilter)) {
      return new Map();
    }
    const ids = mapParcels.map((p) => String(p.parcel_id));
    const out = new Map<string, EvaluationStatus>();

    // Demographic evaluation (requires precomputed isochrone data)
    const needsDemographics =
      buyBoxFilter.minPopulation != null ||
      buyBoxFilter.minMedianHHI != null ||
      buyBoxFilter.minMedianHomeValue != null ||
      buyBoxFilter.minHnwHouseholds != null;

    if (needsDemographics && precomputeData.size > 0) {
      const results = evaluateAll(ids, precomputeData, buyBoxFilter);
      Array.from(results.entries()).forEach(([id, r]) => out.set(id, r.status));
    } else if (needsDemographics) {
      // Isochrones not yet loaded — mark all as computing
      ids.forEach((id) => out.set(id, "computing"));
    }

    // AADT override — parcel-level, no precompute needed.
    // When an explicit minimum is set, treat null AADT (unknown) as failing.
    // Otherwise the slider is invisible to the 80%+ of NJ parcels that
    // aren't on a NJDOT-counted state route. To see "everything including
    // unknowns" the user slides back to off.
    if (buyBoxFilter.minAADT != null) {
      mapParcels.forEach((p) => {
        const id = String(p.parcel_id);
        if (p.aadt == null || p.aadt < buyBoxFilter.minAADT!) {
          out.set(id, "fail");
        } else if (!out.has(id)) {
          out.set(id, "match");
        }
      });
    }

    return out;
  }, [buyBoxFilter, precomputeData, mapParcels]);

  const evaluationCounts = useMemo(() => {
    let match = 0, borderline = 0, fail = 0, computing = 0;
    Array.from(parcelEvaluations.values()).forEach((status) => {
      if (status === "match") match++;
      else if (status === "borderline") borderline++;
      else if (status === "fail") fail++;
      else computing++;
    });
    return { match, borderline, fail, computing };
  }, [parcelEvaluations]);

  const cityDataRanges = useMemo(() => {
    if (!precomputeData.size) return null;
    const pops: number[] = [];
    const hnws: number[] = [];
    Array.from(precomputeData.values()).forEach((d) => {
      const ring = d.rings[buyBoxFilter.driveTimeMinutes];
      pops.push(ring.totalPopulation);
      hnws.push(ring.hnwHouseholds);
    });
    pops.sort((a, b) => a - b);
    hnws.sort((a, b) => a - b);
    const p99 = (arr: number[]) => arr[Math.floor(arr.length * 0.99)] ?? arr[arr.length - 1] ?? 0;
    return { maxPopulation: Math.max(p99(pops), 200_000), maxHnwHouseholds: Math.max(p99(hnws), 5_000) };
  }, [precomputeData, buyBoxFilter.driveTimeMinutes]);

  const bestActualValues = useMemo(() => {
    if (!precomputeData.size) return null;
    let pop = 0, hhi = 0, homeVal = 0, hnw = 0;
    precomputeData.forEach((d) => {
      const ring = d.rings[buyBoxFilter.driveTimeMinutes];
      if (ring.totalPopulation > pop) pop = ring.totalPopulation;
      if (ring.weightedMedianHHI > hhi) hhi = ring.weightedMedianHHI;
      if (ring.weightedMedianHomeValue > homeVal) homeVal = ring.weightedMedianHomeValue;
      if (ring.hnwHouseholds > hnw) hnw = ring.hnwHouseholds;
    });
    return { population: pop, medianHHI: hhi, homeValue: homeVal, hnwHouseholds: hnw };
  }, [precomputeData, buyBoxFilter.driveTimeMinutes]);

  function handleBuyBoxChange(f: BuyBoxFilter) {
    if (buyBoxDebounceRef.current) clearTimeout(buyBoxDebounceRef.current);
    buyBoxDebounceRef.current = setTimeout(() => setBuyBoxFilter(f), 50);
  }

  function handleRecompute() {
    if (!jurisdictionId) return;
    // Pass existing data so only missing parcels are fetched — already-computed ones are skipped
    startPrecompute(jurisdictionId, precomputeData.size > 0 ? precomputeData : undefined);
  }

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

  // Fetch isochrone whenever a parcel is clicked and drive-time mode is active
  useEffect(() => {
    if (driveTimeMode === "off" || !selectedParcelCentroid) return;

    let cancelled = false;
    setIsochroneLoading(true);

    const [lng, lat] = selectedParcelCentroid;

    fetchIsochrone(lat, lng)
      .then(async (result) => {
        if (cancelled) return;

        if (driveTimeMode === "pinned" && isochroneData) {
          // Lock current rings as pinned, show new rings as primary
          setPinnedIsochroneData(isochroneData);
        }
        setIsochroneData(result);

        // Fetch wealth data for the 10-min ring
        const tracts = await fetchCensusTracts(result.polygons.min10);
        if (!cancelled) setIsochroneWealth(tracts);
      })
      .catch((err) => {
        if (!cancelled) console.warn("Isochrone fetch failed:", err);
      })
      .finally(() => {
        if (!cancelled) setIsochroneLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedParcelCentroid, driveTimeMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clear isochrone data when drive-time mode is turned off
  useEffect(() => {
    if (driveTimeMode === "off") {
      setIsochroneData(null);
      setIsochroneWealth(null);
      setPinnedIsochroneData(null);
    }
  }, [driveTimeMode]);

  const totalPages = parcelList
    ? Math.max(1, Math.ceil(parcelList.total / parcelList.page_size))
    : 1;

  return (
    <div className="flex h-screen flex-col overflow-hidden">

      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-slate-800 bg-slate-950 px-5">
        <a href="/" className="text-white font-semibold hover:text-slate-300 transition-colors">ParcelLogic</a>

        {/* Background-loading pill — visible while zoning/overlays/ordinance are still running */}
        {(isBackground || bgComplete) && (
          <div className="relative flex-1 flex justify-center">
            <button
              onClick={() => setBgPanelOpen((o) => !o)}
              className={[
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all",
                bgComplete
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : "bg-amber-950/60 text-amber-300 border border-amber-800/50 hover:bg-amber-950",
              ].join(" ")}
            >
              {bgComplete ? (
                <span className="text-emerald-400">✓</span>
              ) : (
                <span className="inline-block h-2 w-2 animate-spin rounded-full border border-amber-400/30 border-t-amber-400" />
              )}
              <span>
                {bgComplete
                  ? "Analysis complete"
                  : job.status === "ingesting_parcels"
                  ? "Building zoning index…"
                  : STAGE_LABELS[job.status] ?? "Loading…"}
              </span>
              <span className="text-amber-500/60">{bgComplete ? "" : "▾"}</span>
            </button>

            {/* Dropdown pipeline checklist */}
            {bgPanelOpen && !bgComplete && (
              <div className="absolute top-8 z-50 w-64 rounded-xl border border-slate-700 bg-slate-900 p-3 shadow-2xl">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Background progress</p>
                <ol className="space-y-0.5">
                  {PIPELINE_STEPS.filter(s => !["queued","discovering_layers","downloading_parcels","ingesting_parcels"].includes(s)).map((step) => {
                    const currentIdx = PIPELINE_STEPS.indexOf(job.status as any);
                    const stepIdx = PIPELINE_STEPS.indexOf(step);
                    const done = stepIdx < currentIdx;
                    const active = step === job.status;
                    return (
                      <li key={step} className={[
                        "flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs",
                        done ? "text-emerald-400" : active ? "bg-slate-800 text-white" : "text-slate-600",
                      ].join(" ")}>
                        <span className="w-4 text-center">
                          {done ? "✓" : active ? (
                            <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-blue-500/30 border-t-blue-400" />
                          ) : "○"}
                        </span>
                        {STAGE_LABELS[step]}
                      </li>
                    );
                  })}
                </ol>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center gap-2">
          <button
            onClick={() => setImportModalOpen(true)}
            className="text-xs text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded transition-colors"
          >
            Import KMZ
          </button>
          <button
            onClick={() => setVerifierOpen(true)}
            className="text-xs text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded transition-colors"
          >
            Zone Verifier
          </button>
          {jurisdictionId && (
            <Link
              href={`/ordinance/${jurisdictionId}`}
              className="text-xs text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded transition-colors"
            >
              Zone Matrix
            </Link>
          )}
          <button
            onClick={() => {
              const next = colorMode === "permission" ? "saturation" : "permission";
              setColorMode(next);
            }}
            className={[
              "text-xs border px-3 py-1.5 rounded transition-colors",
              colorMode === "saturation"
                ? "text-emerald-300 border-emerald-600 bg-emerald-950 hover:bg-emerald-900"
                : "text-slate-400 hover:text-white border-slate-700 hover:border-slate-500",
            ].join(" ")}
          >
            {saturationLoading
              ? "Loading saturation…"
              : colorMode === "saturation"
              ? "← Show Zoning"
              : "Show Saturation"}
          </button>
          <button
            onClick={() => {
              const count = parcelList?.total ?? 0;
              const mins = count > 20000 ? "30–60 min" : count > 10000 ? "15–30 min" : count > 5000 ? "5–15 min" : "1–5 min";
              if (!confirm(`Re-analyze will re-download and re-process all ${count.toLocaleString()} parcels for this jurisdiction.\n\nEstimated time: ${mins}\n\nOnly do this if the zoning data has changed. Continue?`)) return;
              reanalyzeMutation.mutate();
            }}
            disabled={reanalyzeMutation.isPending}
            className="text-xs text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
          >
            {reanalyzeMutation.isPending ? "Starting…" : "Re-analyze"}
          </button>
        </div>
      </header>

      {/* Layout */}
      <div className="flex flex-1 overflow-hidden">

        <aside className="w-64 border-r border-slate-800 bg-slate-950 overflow-y-auto">
          <BuyBoxPanel
            filter={buyBoxFilter}
            onChange={handleBuyBoxChange}
            precomputeStatus={precomputeStatus}
            evaluationCounts={evaluationCounts}
            cityDataRanges={cityDataRanges}
            bestActualValues={bestActualValues}
            onRecompute={handleRecompute}
          />
          <FilterPanel jurisdictionId={jurisdictionId} onChange={setFilters} />

          {/* Saturation Settings */}
          <div className="border-t border-slate-800 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-2">
              Saturation Settings
            </p>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer mb-3">
              <input
                type="checkbox"
                checked={onlyUnderserved}
                onChange={(e) => setOnlyUnderserved(e.target.checked)}
                className="rounded border-slate-600"
              />
              Only show undersupplied markets
            </label>
            <div className="space-y-2">
              <div>
                <label className="text-[10px] text-slate-500 flex justify-between">
                  <span>Underserved threshold</span>
                  <span className="text-emerald-400">&lt; {satThresholdLow} sq ft/person</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={15}
                  step={0.5}
                  value={satThresholdLow}
                  onChange={(e) => setSatThresholdLow(parseFloat(e.target.value))}
                  className="w-full accent-emerald-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-500 flex justify-between">
                  <span>Oversupplied threshold</span>
                  <span className="text-red-400">&gt; {satThresholdHigh} sq ft/person</span>
                </label>
                <input
                  type="range"
                  min={5}
                  max={20}
                  step={0.5}
                  value={satThresholdHigh}
                  onChange={(e) => setSatThresholdHigh(parseFloat(e.target.value))}
                  className="w-full accent-red-500"
                />
              </div>
            </div>
          </div>
        </aside>

        <main className="flex-1">
          <ParcelMap
            jurisdictionId={jurisdictionId!}
            parcels={
              onlyUnderserved && colorMode === "saturation"
                ? mapParcels.filter((p) => {
                    const s = effectiveSaturationData.get(p.parcel_id);
                    return s?.color === "green";
                  })
                : mapParcels
            }
            isLoading={mapLoading}
            selectedParcelId={selectedParcelId}
            selectedParcelCentroid={selectedParcelCentroid}
            onParcelClick={(id) => {
              setSelectedParcelId(id);
              setDrawerOpen(true);
            }}
            onBoundsChange={setBBox}
            visibility={layerVisibility}
            onVisibilityChange={setLayerVisibility}
            colorMode={colorMode}
            saturationData={effectiveSaturationData}
            flyTrigger={flyTrigger}
            driveTimeMode={driveTimeMode}
            isochronePolygons={isochroneData?.polygons ?? null}
            isochroneWealth={isochroneWealth}
            pinnedIsochronePolygons={pinnedIsochroneData?.polygons ?? null}
            onDriveTimeModeChange={setDriveTimeMode}
            keepActive={keepActive}
            keepMinScore={keepMinScore}
            onKeepChange={(active, score) => {
              setKeepActive(active);
              setKeepMinScore(score);
            }}
            parcelEvaluations={parcelEvaluations}
            buyBoxFilter={buyBoxFilter}
            precomputedData={precomputeData}
          />
        </main>

        <aside className="w-[500px] border-l bg-white">
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
          onShowRing={() => setFlyTrigger((n) => n + 1)}
        />
      )}

      {/* Zone Verifier Panel */}
      {verifierOpen && (
        <ZoningChatPanel
          jurisdictionId={jurisdictionId}
          cityName={job.jurisdiction_input ?? undefined}
          onClose={() => setVerifierOpen(false)}
        />
      )}

      {/* KMZ Import Modal */}
      {importModalOpen && (
        <ImportModal onClose={() => setImportModalOpen(false)} />
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