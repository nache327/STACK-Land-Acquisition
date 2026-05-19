"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useCoverageProgression(
  jurisdictionId: string | null,
  days: number = 30,
) {
  return useQuery({
    queryKey: ["coverage-progression", jurisdictionId, days],
    queryFn: () => api.getCoverageProgression(jurisdictionId!, days),
    enabled: !!jurisdictionId,
    staleTime: 60 * 1000,
  });
}
