"use client";

import { PIPELINE_STEPS, STAGE_LABELS, stepIndex } from "@/hooks/useJobPoller";
import type { Job } from "@/lib/schemas";

interface JobProgressProps {
  job: Job;
}

const STEP_ICONS: Record<string, string> = {
  queued: "…",
  discovering_layers: "◎",
  downloading_parcels: "⬇",
  ingesting_parcels: "◌",
  downloading_zoning: "🧭",
  pending_zoning: "◌",
  parsing_ordinance: "◈",
  running_overlays: "◉",
  ready: "✓",
  cancelled: "×",
};

const DISCOVERY_SOURCE_LABELS: Record<string, string> = {
  city_gis: "via ArcGIS Hub",
  county_gis: "via ArcGIS Hub",
  regrid: "via Regrid",
  direct: "direct URL",
  webmap: "from Web Map",
  hub: "via ArcGIS Hub",
};

export function JobProgress({ job }: JobProgressProps) {
  const currentIdx = stepIndex(job.status as any);
  const parcelsDownloaded = (job.progress as any)?.parcels_downloaded as
    | number
    | undefined;
  const parcelsIngested = (job.progress as any)?.parcels_ingested as
    | number
    | undefined;
  const parcelsMapped = (job.progress as any)?.parcels_mapped as
    | number
    | undefined;
  const parcelsTotal = (job.progress as any)?.parcels_total as
    | number
    | undefined;
  const discoverySource = (job.progress as any)?.discovery_source as
    | string
    | undefined;
  const ingestPhase = (job.progress as any)?.ingest_phase as
    | string
    | undefined;
  const statusCopy =
    job.status === "discovering_layers"
      ? "Looking up parcel and zoning sources for this jurisdiction"
      : job.status === "queued" || job.status === "running" || job.status === "retrying"
        ? "Waiting for a worker to start this analysis"
      : job.status === "downloading_parcels"
        ? "Pulling parcel records from the source GIS service"
        : job.status === "ingesting_parcels"
          ? ingestPhase === "upserting"
            ? "Writing parcel records into PostGIS"
            : "Normalizing parcel geometry and preparing records"
          : job.status === "downloading_zoning"
            ? "Fetching zoning district polygons for parcel backfill"
            : job.status === "pending_zoning"
              ? "Zoning data is being ingested and cached"
              : job.status === "parsing_ordinance"
              ? "Extracting permitted uses from the zoning ordinance"
              : job.status === "running_overlays"
                ? "Applying flood and wetland constraints to the parcel set"
	                : job.status !== "failed"
	                ? job.status === "cancelled"
	                  ? "This analysis was cancelled"
	                  : "Building the final parcel index"
	                  : "Something went wrong with the pipeline";

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-[#070d1a] px-4">
      {/* Background blobs */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-1/2 h-[600px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600/8 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md space-y-8">
        {/* Logo + status */}
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="flex items-center gap-2.5">
            <ParcelLogicMark size={32} />
            <span className="text-lg font-bold text-white">ParcelLogic</span>
          </div>

          <div>
            <h1 className="text-xl font-semibold text-white">
              {job.status === "failed"
                ? "Analysis failed"
                : job.status === "cancelled"
                  ? "Analysis cancelled"
                  : job.status === "pending_zoning"
                    ? "Pending zoning"
                : "Analyzing jurisdiction…"}
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              {statusCopy}
            </p>
          </div>
        </div>

        {/* Step list */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 backdrop-blur-sm">
          <ol className="space-y-1">
            {PIPELINE_STEPS.map((step, idx) => {
              const done = idx < currentIdx;
              const active = idx === currentIdx;

              return (
                <li
                  key={step}
                  className={[
                    "flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition-all",
                    done
                      ? "text-emerald-400"
                      : active
                        ? "bg-slate-800 text-white"
                        : "text-slate-600",
                  ].join(" ")}
                >
                  {/* Icon */}
                  <span className="w-5 text-center font-mono text-base leading-none">
                    {done ? (
                      <span className="text-emerald-500">✓</span>
                    ) : active ? (
                      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
                    ) : (
                      <span className="text-slate-700">
                        {STEP_ICONS[step] ?? "○"}
                      </span>
                    )}
                  </span>

                  {/* Label */}
                  <span className={active ? "font-medium" : ""}>
                    {STAGE_LABELS[step]}
                  </span>

                  {/* Right badge */}
                  <span className="ml-auto text-xs tabular-nums">
                    {active && step === "downloading_parcels" && parcelsTotal ? (
                      <span className="text-blue-400">
                        {parcelsDownloaded?.toLocaleString()} /{" "}
                        {parcelsTotal.toLocaleString()}
                      </span>
                    ) : active && step === "ingesting_parcels" && parcelsTotal ? (
                      <span className="text-blue-400">
                        {(ingestPhase === "upserting"
                          ? parcelsIngested
                          : parcelsMapped
                        )?.toLocaleString()} /{" "}
                        {parcelsTotal.toLocaleString()}
                      </span>
                    ) : done && step === "discovering_layers" && discoverySource ? (
                      <span className="text-emerald-600">
                        {DISCOVERY_SOURCE_LABELS[discoverySource] ??
                          discoverySource}
                      </span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>

        {/* Error state */}
        {job.status === "failed" && (
          <div className="rounded-xl border border-red-900/50 bg-red-950/40 p-4">
            <p className="text-sm font-semibold text-red-400">
              Pipeline error
            </p>
            <p className="mt-1.5 font-mono text-xs text-red-500/80">
              {job.error_message}
            </p>
          </div>
        )}

        {/* Footer note */}
        {job.status !== "failed" && (
          <p className="text-center text-xs text-slate-600">
            Typically 30–90 seconds for a full city
          </p>
        )}
      </div>
    </div>
  );
}

function ParcelLogicMark({ size = 32 }: { size?: number }) {
  return (
    <div
      style={{ width: size, height: size }}
      className="flex-shrink-0 overflow-hidden rounded-lg bg-blue-600 shadow-lg shadow-blue-900/40"
    >
      <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
        <rect
          x="5"
          y="5"
          width="11"
          height="11"
          rx="2"
          fill="white"
          opacity="0.95"
        />
        <rect
          x="20"
          y="5"
          width="11"
          height="11"
          rx="2"
          fill="white"
          opacity="0.45"
        />
        <rect
          x="5"
          y="20"
          width="11"
          height="11"
          rx="2"
          fill="white"
          opacity="0.45"
        />
        <rect
          x="20"
          y="20"
          width="11"
          height="11"
          rx="2"
          fill="white"
          opacity="0.95"
        />
      </svg>
    </div>
  );
}
