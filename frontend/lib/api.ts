/**
 * Typed API client for the FastAPI backend.
 *
 * All functions throw on non-2xx responses with the error detail from the API.
 * Phase 1: all endpoints wired to the correct paths.
 * Phase 2+: response schemas validated with Zod at runtime.
 */

import {
  CandidateParcelSearchResponseSchema,
  JobSchema,
  JurisdictionSchema,
  SaturationResponseSchema,
  type CandidateParcelSearchRequest,
  type CandidateParcelSearchResponse,
  ParcelDetailSchema,
  ParcelListResponseSchema,
  ZoneMatrixResponseSchema,
  ZoningDistrictListSchema,
  type Job,
  type JobCreate,
  type Jurisdiction,
  type ParcelDetail,
  type ParcelListResponse,
  type SaturationBatchResult,
  type SaturationResponse,
  type ZoneMatrixResponse,
  type ZoningDistrictList,
} from "./schemas";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchJSON<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ---- jobs -----------------------------------------------------------------

export const api = {
  async createJob(payload: JobCreate): Promise<Job> {
    const raw = await fetchJSON<unknown>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return JobSchema.parse(raw);
  },

  async getJob(jobId: string): Promise<Job> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}`);
    return JobSchema.parse(raw);
  },

  // ---- parcels ------------------------------------------------------------

  async listParcels(
    jurisdictionId: string,
    params: Record<string, string | number | boolean | string[]> = {}
  ): Promise<ParcelListResponse> {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        value.forEach((v) => qs.append(key, String(v)));
      } else {
        qs.set(key, String(value));
      }
    }
    const raw = await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/parcels?${qs}`
    );
    return ParcelListResponseSchema.parse(raw);
  },

  async getParcel(parcelId: number): Promise<ParcelDetail> {
    const raw = await fetchJSON<unknown>(`/api/parcels/${parcelId}`);
    return ParcelDetailSchema.parse(raw);
  },

  async searchParcels(
    payload: CandidateParcelSearchRequest
  ): Promise<CandidateParcelSearchResponse> {
    const raw = await fetchJSON<unknown>("/api/parcels/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return CandidateParcelSearchResponseSchema.parse(raw);
  },

  // ---- zones --------------------------------------------------------------

  async getZoneMatrix(jurisdictionId: string): Promise<ZoneMatrixResponse> {
    const raw = await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/zones`
    );
    return ZoneMatrixResponseSchema.parse(raw);
  },

  async updateZone(
    jurisdictionId: string,
    zoneCode: string,
    patch: Record<string, unknown>
  ): Promise<void> {
    await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}`,
      {
        method: "PATCH",
        body: JSON.stringify(patch),
      }
    );
  },

  async getZoneSummary(jurisdictionId: string): Promise<Record<string, number>> {
    return fetchJSON<Record<string, number>>(
      `/api/jurisdictions/${jurisdictionId}/parcels/zone-summary`
    );
  },

  async getZoneClassSummary(
    jurisdictionId: string
  ): Promise<Record<string, number>> {
    return fetchJSON<Record<string, number>>(
      `/api/jurisdictions/${jurisdictionId}/parcels/zone-class-summary`
    );
  },

  // ---- jurisdictions / zoning districts ----------------------------------

  async getJurisdiction(jurisdictionId: string): Promise<Jurisdiction> {
    const raw = await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}`
    );
    return JurisdictionSchema.parse(raw);
  },

  async getZoningDistricts(jurisdictionId: string): Promise<ZoningDistrictList> {
    const raw = await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/zoning-districts`
    );
    return ZoningDistrictListSchema.parse(raw);
  },

  zoningDistrictsMapUrl(jurisdictionId: string): string {
    return `${BASE_URL}/api/jurisdictions/${jurisdictionId}/zoning-districts/map`;
  },

  // ---- ordinances ---------------------------------------------------------

  async triggerParse(
    jurisdictionId: string,
    ordinanceUrl?: string
  ): Promise<{ status: string; message: string }> {
    return fetchJSON<{ status: string; message: string }>(
      `/api/ordinances/${jurisdictionId}/parse`,
      {
        method: "POST",
        body: JSON.stringify({ ordinance_url: ordinanceUrl ?? null }),
      }
    );
  },

  // ---- shortlists ---------------------------------------------------------

  async createShortlist(payload: {
    jurisdiction_id: string;
    name: string;
    filters: Record<string, unknown>;
    parcel_ids: number[];
  }): Promise<{ id: string }> {
    return fetchJSON<{ id: string }>("/api/shortlists", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  shortlistExportUrl(shortlistId: string): string {
    return `${BASE_URL}/api/shortlists/${shortlistId}/export.csv`;
  },

  // ---- competition & saturation -------------------------------------------

  competitorsUrl(jurisdictionId: string, bbox?: [number, number, number, number]): string {
    const bboxParam = bbox ? `?bbox=${bbox.join(",")}` : "";
    return `${BASE_URL}/api/jurisdictions/${jurisdictionId}/competitors${bboxParam}`;
  },

  async syncCompetitors(jurisdictionId: string): Promise<{ status: string; message: string }> {
    return fetchJSON<{ status: string; message: string }>(
      `/api/jurisdictions/${jurisdictionId}/competitors/sync`,
      { method: "POST" }
    );
  },

  async importKmz(file: File): Promise<{ inserted: number; skipped: number; message: string }> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/api/competitors/import-kmz`, {
      method: "POST",
      body: form,
      // No Content-Type header — let browser set multipart boundary
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail ?? detail;
      } catch { /* ignore */ }
      throw new Error(detail);
    }
    return res.json();
  },

  async clearKmzCompetitors(): Promise<{ deleted: number }> {
    return fetchJSON<{ deleted: number }>("/api/competitors/kmz/clear", {
      method: "DELETE",
    });
  },

  async getParcelSaturation(parcelId: number): Promise<SaturationResponse> {
    const raw = await fetchJSON<unknown>(`/api/parcels/${parcelId}/saturation`);
    return SaturationResponseSchema.parse(raw);
  },

  async getSaturationBatch(
    parcelIds: number[],
    ringMiles: number = 3
  ): Promise<Record<string, SaturationBatchResult>> {
    const raw = await fetchJSON<{ results: Record<string, SaturationBatchResult> }>(
      "/api/parcels/saturation-batch",
      {
        method: "POST",
        body: JSON.stringify({ parcel_ids: parcelIds, ring_miles: ringMiles }),
      }
    );
    return raw.results;
  },
};
