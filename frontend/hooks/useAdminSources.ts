"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { runBulkReview } from "@/lib/admin/bulkReview";
import type {
  BulkReviewAction,
  SourceReviewRequest,
} from "@/lib/schemas";

export interface AdminSourcesFilters {
  status?: string;
  confidence_min?: number;
  municipality?: string;
  sort_by?: "confidence" | "municipality" | "updated_at";
  limit?: number;
  offset?: number;
}

export function useAdminSources(
  jurisdictionId: string | null,
  filters: AdminSourcesFilters,
) {
  return useQuery({
    queryKey: ["admin-sources", jurisdictionId, filters],
    queryFn: () => api.listSources(jurisdictionId!, filters),
    enabled: !!jurisdictionId,
    staleTime: 30 * 1000,
  });
}

export function useReviewSource(jurisdictionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { sourceId: string; body: SourceReviewRequest }) =>
      api.reviewSource(jurisdictionId, vars.sourceId, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-sources", jurisdictionId] });
    },
  });
}

export function useBulkReviewSources(jurisdictionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      ids: string[];
      action: BulkReviewAction;
      rejectedReason?: string;
    }) =>
      runBulkReview({
        ids: vars.ids,
        action: vars.action,
        rejectedReason: vars.rejectedReason ?? null,
        send: (chunk) =>
          api.bulkReviewSources(jurisdictionId, {
            action: vars.action,
            source_ids: chunk,
            rejected_reason: vars.rejectedReason ?? null,
          }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-sources", jurisdictionId] });
    },
  });
}
