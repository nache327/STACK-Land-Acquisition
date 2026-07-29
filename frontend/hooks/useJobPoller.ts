/**
 * TanStack Query hook that polls GET /api/jobs/:id every 2 seconds
 * until the job reaches a terminal state (ready | failed).
 *
 * The URL segment may be a job id OR a jurisdiction id — digest / deal-board
 * deep links fall back to the jurisdiction id when no ready job exists, which
 * is the majority case. `api.resolveDashboardJob` accepts either.
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/schemas";

const TERMINAL: JobStatus[] = ["ready", "failed", "cancelled", "pending_zoning"];

// Statuses where parcels are in the DB and the user is on the map
const BACKGROUND_STATUSES: JobStatus[] = [
  "downloading_zoning",
  "running_overlays",
  "parsing_ordinance",
];

export function useJobPoller(jobId: string, backgroundMode = false) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.resolveDashboardJob(jobId),
    // A 404 means neither a job nor a jurisdiction matches the segment —
    // retrying can't change that, and the default retry only delays showing
    // the error. Still retry everything else (cold starts, network blips).
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404 ? false : failureCount < 1,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL.includes(status)) return false;
      // Poll slowly while user is working on the map and we're just waiting for Layer 2/3
      if (backgroundMode || BACKGROUND_STATUSES.includes(status as JobStatus)) return 8_000;
      return 2_000;
    },
    staleTime: 0,
    enabled: !!jobId,
  });
}

/** Human-readable label for each pipeline stage. */
export const STAGE_LABELS: Record<string, string> = {
  pending: "Queuing job…",
  queued: "Queued…",
  running: "Starting analysis…",
  retrying: "Retrying job…",
  discovering_layers: "Discovering GIS layers…",
  downloading_parcels: "Downloading parcels…",
  ingesting_parcels: "Ingesting parcels…",
  downloading_zoning: "Downloading zoning…",
  pending_zoning: "Waiting for zoning data…",
  parsing_ordinance: "Parsing zoning ordinance…",
  running_overlays: "Running flood / wetland overlays…",
  ready: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Ordered steps for the progress bar. */
export const PIPELINE_STEPS: JobStatus[] = [
  "queued",
  "discovering_layers",
  "downloading_parcels",
  "ingesting_parcels",
  "downloading_zoning",
  "pending_zoning",
  "running_overlays",
  "parsing_ordinance",
  "ready",
];

export function stepIndex(status: JobStatus): number {
  if (status === "pending" || status === "running" || status === "retrying") {
    return 0;
  }
  return PIPELINE_STEPS.indexOf(status);
}
