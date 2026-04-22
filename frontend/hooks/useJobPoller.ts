/**
 * TanStack Query hook that polls GET /api/jobs/:id every 2 seconds
 * until the job reaches a terminal state (ready | failed).
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/schemas";

const TERMINAL: JobStatus[] = ["ready", "failed"];

export function useJobPoller(jobId: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL.includes(status)) return false;
      return 2_000; // poll every 2 s while processing
    },
    staleTime: 0,
    enabled: !!jobId,
  });
}

/** Human-readable label for each pipeline stage. */
export const STAGE_LABELS: Record<string, string> = {
  pending: "Queuing job…",
  discovering_layers: "Discovering GIS layers…",
  downloading_parcels: "Downloading parcels…",
  parsing_ordinance: "Parsing zoning ordinance…",
  running_overlays: "Running flood / wetland overlays…",
  ready: "Complete",
  failed: "Failed",
};

/** Ordered steps for the progress bar. */
export const PIPELINE_STEPS: JobStatus[] = [
  "discovering_layers",
  "downloading_parcels",
  "parsing_ordinance",
  "running_overlays",
  "ready",
];

export function stepIndex(status: JobStatus): number {
  return PIPELINE_STEPS.indexOf(status);
}
