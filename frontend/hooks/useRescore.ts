"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  RescoreRequest,
  RescoreResponse,
  RescoreSnapshot,
  RollbackResponse,
} from "@/lib/schemas";

export function useRescore(jurisdictionId: string) {
  const qc = useQueryClient();
  return useMutation<RescoreResponse, Error, RescoreRequest>({
    mutationFn: (body) => api.rescoreStaleSources(jurisdictionId, body),
    onSuccess: (res) => {
      // Only invalidate live data when the operator just applied — a dry-run
      // should not invalidate query caches.
      if (!res.dry_run && res.summary.applied > 0) {
        qc.invalidateQueries({ queryKey: ["admin-sources-queue"] });
        qc.invalidateQueries({ queryKey: ["admin-sources"] });
        qc.invalidateQueries({ queryKey: ["admin-coverage"] });
      }
    },
  });
}

export function useRescoreRollback(jurisdictionId: string) {
  const qc = useQueryClient();
  return useMutation<RollbackResponse, Error, RescoreSnapshot[]>({
    mutationFn: (snapshots) => api.rescoreRollback(jurisdictionId, snapshots),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-sources-queue"] });
      qc.invalidateQueries({ queryKey: ["admin-sources"] });
      qc.invalidateQueries({ queryKey: ["admin-coverage"] });
    },
  });
}
