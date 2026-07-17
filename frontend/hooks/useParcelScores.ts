"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type ServerParcelScore } from "@/lib/api";

/** Fetch top-N pre-computed buy-box scores for a jurisdiction and return
 *  them keyed by parcel_id for fast lookup.
 *
 *  The dashboard prefers these server-side scores (which use the same
 *  formula as `lib/compositeScore.ts` but are computed once in the
 *  backend instead of per-render in every browser). For parcels that
 *  don't have a server row yet — newly-ingested cities, or parcels in
 *  zones we don't score — the table falls back to client compute.
 *
 *  Limit defaults to 10,000 (the API's max) which is more than enough
 *  for any single jurisdiction we care about today. If/when a single
 *  jurisdiction has >10K scored parcels, swap to pagination keyed by
 *  the parcel_ids actually visible in the viewport.
 */
export function useParcelScores(
  jurisdictionId: string | null | undefined,
  useCaseId?: string,
) {
  return useQuery({
    // useCaseId is part of the key so toggling the asset (self_storage ↔
    // luxury_garage_condo) refetches the scores for that use case's filter.
    queryKey: ["parcel-scores", jurisdictionId, useCaseId ?? "self_storage"],
    enabled: !!jurisdictionId,
    staleTime: 5 * 60 * 1000,
    queryFn: async () => {
      if (!jurisdictionId) return new Map<number, ServerParcelScore>();
      const scores = await api.getJurisdictionScores(jurisdictionId, {
        minScore: 0,
        limit: 10_000,
        useCaseId,
      });
      return new Map(scores.map((s) => [s.parcel_id, s]));
    },
  });
}
