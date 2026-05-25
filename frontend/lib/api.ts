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
  JobAdminSchema,
  JobArtifactSchema,
  JobStepSchema,
  JurisdictionSchema,
  SaturationResponseSchema,
  type CandidateParcelSearchRequest,
  type CandidateParcelSearchResponse,
  ParcelDetailSchema,
  ParcelListResponseSchema,
  ZoneMatrixResponseSchema,
  ZoningDistrictListSchema,
  type Job,
  type JobAdmin,
  type JobArtifact,
  type JobCreate,
  type JobStep,
  type Jurisdiction,
  type ParcelDetail,
  type ParcelListResponse,
  type SaturationBatchResult,
  type SaturationResponse,
  type ZoneMatrixResponse,
  type ZoningDistrictList,
} from "./schemas";

/** A row from `parcel_buybox_scores` joined to a parcel — the same
 *  shape the backend returns from `/api/jurisdictions/{id}/scores`. */
export interface ServerParcelScore {
  parcel_id: number;
  buybox_filter_id: string;
  score: number;
  tier: "excellent" | "strong" | "decent" | "weak" | "avoid" | string;
  factors: Array<{ label: string; delta: number; reason: string }>;
  computed_at: string;
}

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

  async cancelJob(jobId: string): Promise<Job> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}/cancel`, {
      method: "POST",
    });
    return JobSchema.parse(raw);
  },

  async retryJob(jobId: string): Promise<Job> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}/retry`, {
      method: "POST",
    });
    return JobSchema.parse(raw);
  },

  async forceRerunJob(jobId: string): Promise<Job> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}/force-rerun`, {
      method: "POST",
    });
    return JobSchema.parse(raw);
  },

  async getJobSteps(jobId: string): Promise<JobStep[]> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}/steps`);
    return JobStepSchema.array().parse(raw);
  },

  async getJobArtifacts(jobId: string): Promise<JobArtifact[]> {
    const raw = await fetchJSON<unknown>(`/api/jobs/${jobId}/artifacts`);
    return JobArtifactSchema.array().parse(raw);
  },

  async listAdminJobs(): Promise<Job[]> {
    const raw = await fetchJSON<unknown>("/api/admin/jobs");
    return JobSchema.array().parse(raw);
  },

  async getAdminJob(jobId: string): Promise<JobAdmin> {
    const raw = await fetchJSON<unknown>(`/api/admin/jobs/${jobId}`);
    return JobAdminSchema.parse(raw);
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

  async deleteCompetitor(competitorId: number): Promise<void> {
    await fetchJSON<unknown>(`/api/competitors/${competitorId}`, { method: "DELETE" });
  },

  async createCompetitor(payload: { lng: number; lat: number; name?: string; sq_ft?: number; jurisdiction_id?: string }): Promise<{ id: number }> {
    return fetchJSON<{ id: number }>("/api/competitors", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getParcelSaturation(parcelId: number): Promise<SaturationResponse> {
    const raw = await fetchJSON<unknown>(`/api/parcels/${parcelId}/saturation`);
    return SaturationResponseSchema.parse(raw);
  },

  async getJurisdictionScores(
    jurisdictionId: string,
    opts: { minScore?: number; limit?: number } = {}
  ): Promise<ServerParcelScore[]> {
    const params = new URLSearchParams();
    if (opts.minScore != null) params.set("min_score", String(opts.minScore));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return fetchJSON<ServerParcelScore[]>(
      `/api/jurisdictions/${jurisdictionId}/scores${qs ? `?${qs}` : ""}`,
    );
  },

  async getSaturationBatch(
    parcelIds: number[],
    ringMiles: number = 3
  ): Promise<Record<string, SaturationBatchResult>> {
    // Uses the Next.js proxy route (/api/saturation-batch) so the request
    // is made server-side to Railway, bypassing browser CORS restrictions.
    const res = await fetch("/api/saturation-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parcel_ids: parcelIds, ring_miles: ringMiles }),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const b = await res.json();
        detail = b.error ?? b.detail ?? detail;
      } catch { /* ignore */ }
      throw new Error(detail);
    }
    const raw = await res.json() as { results: Record<string, SaturationBatchResult> };
    return raw.results;
  },

  // ---- admin / source review ----------------------------------------------

  async listSources(
    jurisdictionId: string,
    opts: {
      status?: string;
      municipality?: string;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<{ sources: import("./schemas").ZoningSource[]; total?: number }> {
    const params = new URLSearchParams();
    if (opts.status) params.set("status", opts.status);
    if (opts.municipality) params.set("municipality", opts.municipality);
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.offset != null) params.set("offset", String(opts.offset));
    const qs = params.toString();
    const raw = await fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/_sources${qs ? `?${qs}` : ""}`,
    );
    if (Array.isArray(raw)) return { sources: raw as import("./schemas").ZoningSource[] };
    return raw as { sources: import("./schemas").ZoningSource[]; total?: number };
  },

  async reviewSource(
    jurisdictionId: string,
    sourceId: string,
    body: import("./schemas").SourceReviewRequest,
  ): Promise<unknown> {
    return fetchJSON<unknown>(
      `/api/jurisdictions/${jurisdictionId}/_sources/${sourceId}/_review`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async bulkReviewSources(
    jurisdictionId: string,
    body: import("./schemas").BulkReviewRequest,
  ): Promise<import("./schemas").BulkReviewResponse> {
    return fetchJSON<import("./schemas").BulkReviewResponse>(
      `/api/jurisdictions/${jurisdictionId}/_sources/_bulk-review`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async getSpatialCheck(
    jurisdictionId: string,
    sourceId: string,
  ): Promise<import("./schemas").SpatialCheckResponse> {
    return fetchJSON<import("./schemas").SpatialCheckResponse>(
      `/api/jurisdictions/${jurisdictionId}/_sources/${sourceId}/_spatial-check`,
    );
  },

  // ---- admin / coverage ---------------------------------------------------

  async listAdminCoverage(): Promise<{
    count: number;
    jurisdictions: import("./schemas").CoverageJurisdiction[];
  }> {
    return fetchJSON("/api/admin/coverage");
  },

  async getCoverageProgression(
    jurisdictionId: string,
  ): Promise<{ snapshots: import("./schemas").ProgressionSnapshot[] }> {
    return fetchJSON(
      `/api/admin/coverage/progression?jurisdiction_id=${jurisdictionId}`,
    );
  },

  async refreshCoverage(
    jurisdictionId?: string,
  ): Promise<{ snapshots_written: number; summary?: unknown }> {
    const qs = jurisdictionId ? `?jurisdiction_id=${jurisdictionId}` : "";
    return fetchJSON(`/api/admin/coverage/refresh${qs}`, { method: "POST" });
  },

  // ---- admin / discovery + ingest ----------------------------------------

  async discoverMunicipalZoning(
    countyId: string,
  ): Promise<unknown> {
    return fetchJSON(
      `/api/jurisdictions/${countyId}/_discover-municipal-zoning`,
      { method: "POST" },
    );
  },

  async ingestMunicipalZoning(
    countyId: string,
    body: { source_id?: string; municipality?: string } = {},
  ): Promise<unknown> {
    return fetchJSON(
      `/api/jurisdictions/${countyId}/_ingest-municipal-zoning`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  // ---- admin / sources queue (stub — backend endpoint not yet wired) ------

  async getSourcesQueue(opts: {
    status?: string;
    state?: string;
    limit?: number;
  } = {}): Promise<{
    sources: import("./schemas").QueueSource[];
    total?: number;
  }> {
    // Falls back to a cross-jurisdiction aggregate; until /admin/sources/queue
    // ships, this returns an empty queue gracefully.
    void opts;
    return { sources: [] };
  },

  // ---- admin / rescore (stubs — backend endpoints not yet wired) ----------

  async rescoreStaleSources(
    jurisdictionId: string,
    body: import("./schemas").RescoreRequest = {},
  ): Promise<import("./schemas").RescoreResponse> {
    void jurisdictionId;
    void body;
    throw new Error("rescoreStaleSources: endpoint not yet deployed");
  },

  async rescoreRollback(
    jurisdictionId: string,
    snapshot: import("./schemas").RescoreSnapshot,
  ): Promise<import("./schemas").RollbackResponse> {
    void jurisdictionId;
    void snapshot;
    throw new Error("rescoreRollback: endpoint not yet deployed");
  },

  // ---- admin / remediation (stub — backend endpoint not yet wired) -------

  async getMunicipalitiesRemediation(
    jurisdictionId: string,
  ): Promise<{ municipalities: import("./schemas").RemediationMunicipality[] }> {
    void jurisdictionId;
    return { municipalities: [] };
  },
};
