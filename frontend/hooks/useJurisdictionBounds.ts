/**
 * Fetch jurisdiction metadata and return its stored bbox.
 *
 * Jurisdiction.bbox is populated at ingest time (pipeline.py →
 * _refresh_jurisdiction_bbox) and stored as [minLng, minLat, maxLng, maxLat]
 * in EPSG:4326. The map uses it to fit-bounds on first load.
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useJurisdictionBounds(jurisdictionId: string | null) {
  return useQuery({
    queryKey: ["jurisdiction", jurisdictionId, "bbox"],
    queryFn: async () => {
      if (!jurisdictionId) return null;
      const j = await api.getJurisdiction(jurisdictionId);
      return j.bbox ?? null;
    },
    enabled: !!jurisdictionId,
    staleTime: 10 * 60 * 1000,
  });
}
