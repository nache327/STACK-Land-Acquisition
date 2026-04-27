import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SaturationResponse } from "@/lib/schemas";

export function useParcelSaturation(parcelId: number | null) {
  return useQuery<SaturationResponse, Error>({
    queryKey: ["parcel-saturation", parcelId],
    queryFn: () => api.getParcelSaturation(parcelId!),
    enabled: parcelId !== null,
    staleTime: 10 * 60 * 1000,  // 10 min — saturation changes slowly
    retry: 1,
  });
}
