import { useQuery } from "@tanstack/react-query";

export interface JurisdictionListing {
  id: string;
  source: string;
  address: string;
  city: string | null;
  state: string | null;
  zip: string | null;
  sale_status: string;
  sale_price: number | null;
  days_on_market: number | null;
  listing_broker_company: string | null;
  listing_broker_contact: string | null;
  listing_broker_phone: string | null;
  listing_broker_email: string | null;
  owner_name: string | null;
  owner_phone: string | null;
  owner_contact: string | null;
  owner_address: string | null;
  recorded_owner_name: string | null;
  recorded_owner_phone: string | null;
  last_sale_price: number | null;
  last_sale_date: string | null;
  matched_parcel_id: number | null;
  match_confidence: number | null;
  match_method: string | null;
  lat: number | null;
  lon: number | null;
  is_current: boolean;
  last_seen_at: string | null;
  /** When the same owner is selling multiple adjacent parcels, the
   *  matcher records every parcel in the cluster here. is_primary
   *  flags the largest-acreage one (the row matched_parcel_id points
   *  to). null for normal single-parcel matches. */
  co_listed_parcels: Array<{
    id: number;
    apn: string;
    acres: number | null;
    is_primary: boolean;
  }> | null;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Fetch all current for-sale listings for a jurisdiction. Used by
 * the parcel drawer to surface a ListingCard when the open parcel
 * matches a current listing, and (future) by the map listings layer. */
export function useJurisdictionListings(jurisdictionId: string | null) {
  return useQuery<JurisdictionListing[], Error>({
    queryKey: ["jurisdiction-listings", jurisdictionId],
    queryFn: async () => {
      const res = await fetch(
        `${API_BASE}/api/jurisdictions/${jurisdictionId}/listings`,
      );
      if (!res.ok) {
        if (res.status === 404) return [];
        throw new Error(`Listings fetch failed: HTTP ${res.status}`);
      }
      return res.json();
    },
    enabled: !!jurisdictionId,
    staleTime: 60 * 1000, // 1 min — uploads can change this any time
    retry: 1,
  });
}
