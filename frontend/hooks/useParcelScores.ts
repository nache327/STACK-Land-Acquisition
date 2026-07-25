"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type ServerParcelScore } from "@/lib/api";

/** Server-computed buy-box scores for the parcels currently on screen, keyed by
 *  parcel_id.
 *
 *  Pass the ids you are about to render. The scores come from
 *  POST /api/parcels/scores, which returns a row for every requested parcel that
 *  HAS one — so a parcel is either shown with its real score or honestly shown
 *  as unscored.
 *
 *  Why not the jurisdiction-wide endpoint: GET /jurisdictions/:id/scores is
 *  `ORDER BY score DESC LIMIT n` (max 10k) while `score_jurisdiction` scores
 *  every parcel in the jurisdiction — hundreds of thousands in a county. So it
 *  silently returned only the top slice, and everything below fell through to
 *  `lib/compositeScore.computeScore`, which implements ~6 of the backend's ~13
 *  factor families and therefore reads 20-40 points HIGH. The inflated tail then
 *  sorted ABOVE genuinely better parcels that did have a server row. Fetching by
 *  id removes the truncation, and callers no longer client-compute for ranking.
 *
 *  Batched in chunks of 2,000 ids so a large page stays under the endpoint's
 *  10k cap and keeps request bodies small.
 */
const CHUNK = 2_000;

export function useParcelScores(
  parcelIds: number[],
  useCaseId?: string,
) {
  // Sorted + joined so the key is stable across re-renders that don't change
  // the visible set (react-query would otherwise refetch on every pan).
  const idKey = [...parcelIds].sort((a, b) => a - b).join(",");

  return useQuery({
    // useCaseId is part of the key so toggling the asset (self_storage ↔
    // luxury_garage_condo) refetches the scores for that use case's filter.
    queryKey: ["parcel-scores", useCaseId ?? "self_storage", idKey],
    enabled: parcelIds.length > 0,
    staleTime: 5 * 60 * 1000,
    queryFn: async () => {
      const out = new Map<number, ServerParcelScore>();
      for (let i = 0; i < parcelIds.length; i += CHUNK) {
        const chunk = parcelIds.slice(i, i + CHUNK);
        const scores = await api.getScoresForParcels(chunk, { useCaseId });
        scores.forEach((s) => out.set(s.parcel_id, s));
      }
      return out;
    },
  });
}
