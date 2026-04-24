"use client";

import { PIPELINE_STEPS, STAGE_LABELS, stepIndex } from "@/hooks/useJobPoller";
import type { Job } from "@/lib/schemas";

interface JobProgressProps {
  job: Job;
}

const STEP_ICONS: Record<string, string> = {
  discovering_layers: "🔍",
  downloading_parcels: "⬇",
  downloading_zoning: "🧭",
  parsing_ordinance: "📄",
  running_overlays: "🗺",
  ready: "✓",
};

const DISCOVERY_SOURCE_LABELS: Record<string, string> = {
  city_gis: "found via ArcGIS Hub",
  county_gis: "found via ArcGIS Hub",
  regrid: "via Regrid fallback",
  direct: "direct URL",
  webmap: "found in Web Map",
  hub: "found via ArcGIS Hub",
};

export function JobProgress({ job }: JobProgressProps) {
  const currentIdx = stepIndex(job.status as any);
  const parcelsDownloaded = (job.progress as any)?.parcels_downloaded as number | undefined;
  const parcelsTotal = (job.progress as any)?.parcels_total as number | undefined;
  const discoverySource = (job.progress as any)?.discovery_source as string | undefined;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-lg space-y-8">
        <div className="text-center">
          <h1 className="text-xl font-semibold text-slate-900">Loading parcels…</h1>
          <p className="mt-1 text-sm text-slate-500">
            This usually takes 30–90 seconds for a full city.
          </p>
        </div>

        {/* Step list */}
        <ol className="space-y-3">
          {PIPELINE_STEPS.map((step, idx) => {
            const done = idx < currentIdx;
            const active = idx === currentIdx;
            return (
              <li
                key={step}
                className={[
                  "flex items-center gap-3 rounded-lg px-4 py-3 text-sm",
                  done
                    ? "bg-emerald-50 text-emerald-800"
                    : active
                    ? "bg-white border border-slate-200 text-slate-900 shadow-sm"
                    : "text-slate-400",
                ].join(" ")}
              >
                <span className="text-base">{done ? "✓" : STEP_ICONS[step] ?? "○"}</span>
                <span className={active ? "font-medium" : ""}>
                  {STAGE_LABELS[step]}
                </span>
                {active && step === "downloading_parcels" && parcelsTotal && (
                  <span className="ml-auto text-xs tabular-nums text-slate-400">
                    {parcelsDownloaded?.toLocaleString()} / {parcelsTotal.toLocaleString()}
                  </span>
                )}
                {done && step === "discovering_layers" && discoverySource && (
                  <span className="ml-auto text-xs text-emerald-600">
                    {DISCOVERY_SOURCE_LABELS[discoverySource] ?? discoverySource}
                  </span>
                )}
                {active && step !== "downloading_parcels" && (
                  <span className="ml-auto h-3 w-3 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
                )}
              </li>
            );
          })}
        </ol>

        {/* Error state */}
        {job.status === "failed" && (
          <div className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
            <p className="font-semibold">Pipeline failed</p>
            <p className="mt-1 font-mono text-xs">{job.error_message}</p>
          </div>
        )}
      </div>
    </div>
  );
}
