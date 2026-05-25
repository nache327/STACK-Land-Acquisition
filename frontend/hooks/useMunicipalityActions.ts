"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** All municipality action mutations invalidate the same data scope —
 *  every query that depends on jurisdiction-or-source state. After any
 *  successful action the operator's view should reflect the new tier
 *  without a manual refresh. */
function useInvalidateAfterMunicipalAction() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["admin-coverage"] });
    qc.invalidateQueries({ queryKey: ["admin-sources"] });
    qc.invalidateQueries({ queryKey: ["admin-sources-queue"] });
  };
}

export function useDiscoverMunicipalZoning(countyId: string) {
  const invalidate = useInvalidateAfterMunicipalAction();
  return useMutation({
    mutationFn: (municipalityNames: string[]) =>
      api.discoverMunicipalZoning(countyId, municipalityNames),
    onSuccess: invalidate,
  });
}

export function useIngestMunicipalZoning(countyId: string) {
  const invalidate = useInvalidateAfterMunicipalAction();
  return useMutation({
    mutationFn: (sourceIds: string[]) =>
      api.ingestMunicipalZoning(countyId, sourceIds),
    onSuccess: invalidate,
  });
}
