/**
 * TanStack Query hooks for parcel data.
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ParcelDetail } from "@/lib/schemas";

/** Fetch the GeoJSON FeatureCollection for the map layer. */
export function useParcelMapLayer(jurisdictionId: string | null) {
  return useQuery({
    queryKey: ["parcels-map", jurisdictionId],
    queryFn: async () => {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/jurisdictions/${jurisdictionId}/parcels/map`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<GeoJSON.FeatureCollection>;
    },
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000, // 5 min cache
  });
}

/** Fetch a paginated list of parcels for the table. */
export function useParcelList(
  jurisdictionId: string | null,
  params: Record<string, string | number | boolean | string[]> = {}
) {
  return useQuery({
    queryKey: ["parcels-list", jurisdictionId, params],
    queryFn: () => api.listParcels(jurisdictionId!, params),
    enabled: !!jurisdictionId,
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
