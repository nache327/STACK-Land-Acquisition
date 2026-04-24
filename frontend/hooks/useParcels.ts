/**
 * TanStack Query hooks for parcel data.
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CandidateParcelSearchRequest } from "@/lib/schemas";

/** Fetch candidate parcels from the unified server-side search endpoint. */
export function useCandidateParcelSearch(
  payload: CandidateParcelSearchRequest | null
) {
  return useQuery({
    queryKey: ["candidate-parcels", payload],
    queryFn: () => api.searchParcels(payload!),
    enabled: !!payload?.jurisdiction_id,
    staleTime: 60 * 1000,
  });
}

/** Fetch a single parcel detail (for the drawer). */
export function useParcelDetail(parcelId: number | null) {
  return useQuery({
    queryKey: ["parcel-detail", parcelId],
    queryFn: () => api.getParcel(parcelId!),
    enabled: parcelId !== null,
    staleTime: 5 * 60 * 1000,
  });
}
