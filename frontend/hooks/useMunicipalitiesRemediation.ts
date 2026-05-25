"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useMunicipalitiesRemediation(
  jurisdictionId: string | null,
  municipality?: string,
) {
  return useQuery({
    queryKey: ["municipalities-remediation", jurisdictionId, municipality ?? null],
    queryFn: () =>
      api.getMunicipalitiesRemediation(jurisdictionId!, municipality),
    enabled: !!jurisdictionId,
    staleTime: 30 * 1000,
  });
}
