"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  runCrossJurisdictionBulk,
  type QueueSelection,
} from "@/lib/admin/crossJurisdictionBulk";
import type { BulkReviewAction } from "@/lib/schemas";

export interface SourcesQueueFilters {
  status?: string;
  confidence_min?: number;
  spatial_blocked?: boolean;
  stale_only?: boolean;
  recent_hours?: number;
  municipality?: string;
  limit?: number;
}

export function useSourcesQueue(
  filters: SourcesQueueFilters,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ["admin-sources-queue", filters],
    queryFn: () => api.getSourcesQueue(filters),
    staleTime: 30 * 1000,
    enabled: options.enabled ?? true,
  });
}

export function useCrossJurisdictionBulkReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      selections: QueueSelection[];
      action: BulkReviewAction;
      rejectedReason?: string;
    }) =>
      runCrossJurisdictionBulk({
        selections: vars.selections,
        send: (jurisdictionId, chunk) =>
          api.bulkReviewSources(jurisdictionId, {
            action: vars.action,
            source_ids: chunk,
            rejected_reason: vars.rejectedReason ?? null,
          }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-sources-queue"] });
      qc.invalidateQueries({ queryKey: ["admin-sources"] });
      qc.invalidateQueries({ queryKey: ["admin-coverage"] });
    },
  });
}
