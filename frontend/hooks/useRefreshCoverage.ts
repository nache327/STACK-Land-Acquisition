"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useRefreshCoverage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jurisdictionId?: string | null) =>
      api.refreshCoverage(jurisdictionId ?? null),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-coverage"] });
      qc.invalidateQueries({ queryKey: ["coverage-progression"] });
    },
  });
}
