/**
 * Zod schemas that mirror the FastAPI Pydantic schemas.
 * Used for runtime validation of API responses in the frontend.
 */
import { z } from "zod";

// ---- enums ----------------------------------------------------------------

export const UsePermissionSchema = z.enum([
  "permitted",
  "conditional",
  "prohibited",
  "unclear",
]);
export type UsePermission = z.infer<typeof UsePermissionSchema>;

export const JobStatusSchema = z.enum([
  "pending",
  "queued",
  "running",
  "retrying",
  "discovering_layers",
  "downloading_parcels",
  "ingesting_parcels",
  "downloading_zoning",
  "pending_zoning",
  "parsing_ordinance",
  "running_overlays",
  "cancelled",
  "ready",
  "failed",
]);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const ZoneClassSchema = z.enum([
  "residential",
  "commercial",
  "industrial",
  "mixed_use",
  "agricultural",
  "open_space",
  "special",
  "overlay",
  "unknown",
]);
export type ZoneClass = z.infer<typeof ZoneClassSchema>;

export const CoverageLevelSchema = z.enum([
  "full",
  "zoning_only",
  "parcels_only",
  "partial",
]);
export type CoverageLevel = z.infer<typeof CoverageLevelSchema>;

export const TargetUseSchema = z.enum([
  "self_storage",
  "mini_warehouse",
  "light_industrial",
  "luxury_garage_condo",
]);
export type TargetUse = z.infer<typeof TargetUseSchema>;

// ---- job ------------------------------------------------------------------

export const JobSchema = z.object({
  id: z.string().uuid(),
  jurisdiction_id: z.string().uuid().nullable(),
  status: JobStatusSchema,
  jurisdiction_input: z.string().nullable(),
  ordinance_url: z.string().nullable(),
  target_uses: z.array(z.string()).nullable(),
  error_message: z.string().nullable(),
  progress: z.record(z.unknown()).nullable(),
  queued_at: z.string().datetime().nullable().optional(),
  started_at: z.string().datetime().nullable().optional(),
  finished_at: z.string().datetime().nullable().optional(),
  cancel_requested_at: z.string().datetime().nullable().optional(),
  force: z.boolean().optional(),
  dedupe_key: z.string().nullable().optional(),
  locked_by: z.string().nullable().optional(),
  locked_at: z.string().datetime().nullable().optional(),
  attempts: z.number().int().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type Job = z.infer<typeof JobSchema>;

export const JobStepSchema = z.object({
  id: z.number().int(),
  job_id: z.string().uuid(),
  step: z.string(),
  status: z.string(),
  attempt: z.number().int(),
  started_at: z.string().datetime().nullable(),
  finished_at: z.string().datetime().nullable(),
  duration_ms: z.number().int().nullable(),
  error: z.string().nullable(),
  step_metadata: z.record(z.unknown()).nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type JobStep = z.infer<typeof JobStepSchema>;

export const JobArtifactSchema = z.object({
  id: z.number().int(),
  job_id: z.string().uuid(),
  step: z.string(),
  artifact_type: z.string(),
  artifact_metadata: z.record(z.unknown()).nullable(),
  storage_uri: z.string().nullable(),
  created_at: z.string().datetime(),
});
export type JobArtifact = z.infer<typeof JobArtifactSchema>;

export const JobAdminSchema = z.object({
  job: JobSchema,
  steps: z.array(JobStepSchema),
  artifacts: z.array(JobArtifactSchema),
});
export type JobAdmin = z.infer<typeof JobAdminSchema>;

export const JobCreateSchema = z.object({
  jurisdiction: z.string().min(2),
  ordinance_url: z.string().url().optional(),
  target_uses: z.array(TargetUseSchema).default([
    "self_storage",
    "mini_warehouse",
    "light_industrial",
    "luxury_garage_condo",
  ]),
  force: z.boolean().optional(),
});
export type JobCreate = z.infer<typeof JobCreateSchema>;

// ---- parcel ---------------------------------------------------------------

export const ParcelRowSchema = z.object({
  id: z.number().int(),
  jurisdiction_id: z.string().uuid(),
  apn: z.string(),
  address: z.string().nullable(),
  owner_name: z.string().nullable(),
  acres: z.number().nullable(),
  zoning_code: z.string().nullable(),
  zone_class: ZoneClassSchema.nullable().optional(),
  land_use_code: z.string().nullable(),
  improvement_value: z.number().nullable(),
  has_structure: z.boolean().nullable(),
  in_flood_zone: z.boolean(),
  avg_slope_pct: z.number().nullable(),
  in_wetland: z.boolean(),
  county_link: z.string().nullable(),
  storage_permission: z.string().nullable().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ParcelRow = z.infer<typeof ParcelRowSchema>;

export const ParcelDetailSchema = ParcelRowSchema.extend({
  raw: z.record(z.unknown()).nullable().optional(),
  geom: z.record(z.unknown()).nullable().optional(),
  centroid: z.record(z.unknown()).nullable().optional(),
});
export type ParcelDetail = z.infer<typeof ParcelDetailSchema>;

export const ParcelListResponseSchema = z.object({
  items: z.array(ParcelRowSchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
});
export type ParcelListResponse = z.infer<typeof ParcelListResponseSchema>;

export const ParcelSearchSortSchema = z.enum([
  "acres_desc",
  "acres_asc",
  "apn_asc",
  "address_asc",
]);
export type ParcelSearchSort = z.infer<typeof ParcelSearchSortSchema>;

export const CandidateParcelSearchFiltersSchema = z.object({
  zones: z.array(z.string()).optional(),
  zone_classes: z.array(ZoneClassSchema).optional(),
  min_acres: z.number().nullable().optional(),
  max_acres: z.number().nullable().optional(),
  vacant_only: z.boolean().default(false),
  exclude_flood: z.boolean().default(false),
  exclude_wetland: z.boolean().default(false),
});
export type CandidateParcelSearchFilters = z.infer<typeof CandidateParcelSearchFiltersSchema>;

export const CandidateParcelSearchRequestSchema = z.object({
  jurisdiction_id: z.string().uuid(),
  target_use: z.literal("self_storage"),
  filters: CandidateParcelSearchFiltersSchema.default({}),
  bbox: z.array(z.number()).length(4).nullable().optional(),
  search: z.string().nullable().optional(),
  page: z.number().int().min(1).default(1),
  page_size: z.number().int().min(1).max(5000).default(100),
  sort: ParcelSearchSortSchema.default("acres_desc"),
});
export type CandidateParcelSearchRequest = z.infer<typeof CandidateParcelSearchRequestSchema>;

export const ListingSummarySchema = z.object({
  has_listing: z.boolean().default(false),
  sale_price: z.number().nullable().optional(),
  days_on_market: z.number().int().nullable().optional(),
  sale_status: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  broker_company: z.string().nullable().optional(),
  match_method: z.string().nullable().optional(),
});
export type ListingSummary = z.infer<typeof ListingSummarySchema>;

export const CandidateParcelRowSchema = z.object({
  parcel_id: z.number().int(),
  apn: z.string(),
  address: z.string().nullable(),
  acres: z.number().nullable(),
  zoning_code: z.string().nullable().optional(),
  zone_class: ZoneClassSchema.nullable().optional(),
  storage_allowed: z.boolean(),
  storage_conditional: z.boolean(),
  storage_permission: z.string().nullable().optional(),
  garage_permission: z.string().nullable().optional(),
  in_flood_zone: z.boolean(),
  in_wetland: z.boolean(),
  aadt: z.number().int().nullable().optional(),
  has_structure: z.boolean().nullable(),
  is_viable: z.boolean(),
  violation_reasons: z.array(z.string()),
  geom: z.record(z.unknown()).nullable().optional(),
  listing_summary: ListingSummarySchema.nullable().optional(),
});
export type CandidateParcelRow = z.infer<typeof CandidateParcelRowSchema>;

export const CandidateParcelSearchResponseSchema = z.object({
  items: z.array(CandidateParcelRowSchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
});
export type CandidateParcelSearchResponse = z.infer<typeof CandidateParcelSearchResponseSchema>;

// ---- zone use matrix ------------------------------------------------------

export const CitationSchema = z.object({
  section: z.string(),
  quote: z.string(),
});

export const ClassificationSourceSchema = z.enum(["llm", "rule", "human", "unclear", "llm_low_confidence", "llm_rule"]);
export type ClassificationSource = z.infer<typeof ClassificationSourceSchema>;

export const ZoneRowSchema = z.object({
  id: z.number().int(),
  jurisdiction_id: z.string().uuid(),
  zone_code: z.string(),
  zone_name: z.string().nullable(),
  self_storage: UsePermissionSchema,
  mini_warehouse: UsePermissionSchema,
  light_industrial: UsePermissionSchema,
  luxury_garage_condo: UsePermissionSchema,
  citations: z.array(CitationSchema).nullable(),
  confidence: z.number().nullable(),
  human_reviewed: z.boolean(),
  notes: z.string().nullable(),
  classification_source: ClassificationSourceSchema.optional().default("unclear"),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ZoneRow = z.infer<typeof ZoneRowSchema>;

export const ZoneMatrixResponseSchema = z.object({
  zones: z.array(ZoneRowSchema),
  unknown_zones: z.array(z.string()),
  parser_warnings: z.array(z.string()),
});
export type ZoneMatrixResponse = z.infer<typeof ZoneMatrixResponseSchema>;

// ---- jurisdiction ---------------------------------------------------------

export const JurisdictionSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  state: z.string().length(2),
  county: z.string().nullable(),
  parcel_source: z.enum(["city_gis", "county_gis", "regrid"]).nullable(),
  parcel_endpoint: z.string().nullable(),
  zoning_endpoint: z.string().nullable(),
  ordinance_url: z.string().nullable(),
  coverage_level: CoverageLevelSchema.nullable().optional(),
  bbox: z.array(z.number()).length(4).nullable().optional(),
  last_indexed_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
});
export type Jurisdiction = z.infer<typeof JurisdictionSchema>;

// ---- zoning district ------------------------------------------------------

export const ZoningDistrictSchema = z.object({
  id: z.number().int(),
  jurisdiction_id: z.string().uuid(),
  zone_code: z.string(),
  zone_name: z.string().nullable().optional(),
  zone_class: ZoneClassSchema,
  allowed_uses: z.array(z.string()).nullable().optional(),
  max_far: z.number().nullable().optional(),
  max_height_ft: z.number().nullable().optional(),
  max_density_dua: z.number().nullable().optional(),
  min_lot_area_sqft: z.number().nullable().optional(),
  source: z.enum(["arcgis", "ordinance", "regrid", "manual"]),
  confidence: z.number().nullable().optional(),
  human_reviewed: z.boolean(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ZoningDistrict = z.infer<typeof ZoningDistrictSchema>;

export const ZoningDistrictListSchema = z.object({
  items: z.array(ZoningDistrictSchema),
  total: z.number().int(),
});
export type ZoningDistrictList = z.infer<typeof ZoningDistrictListSchema>;

// ---- saturation analysis ---------------------------------------------------

export const RingResultSchema = z.object({
  radius_miles: z.number(),
  population: z.number(),
  facility_count: z.number().int(),
  total_sqft: z.number().int(),
  sqft_per_person: z.number().nullable(),
});
export type RingResult = z.infer<typeof RingResultSchema>;

export const SaturationResponseSchema = z.object({
  parcel_id: z.number().int(),
  rings: z.array(RingResultSchema),
  primary_sqft_per_person: z.number().nullable(),
  color: z.enum(["green", "yellow", "red", "gray"]),
});
export type SaturationResponse = z.infer<typeof SaturationResponseSchema>;

export const SaturationBatchResultSchema = z.object({
  sqft_per_person: z.number().nullable(),
  color: z.enum(["green", "yellow", "red", "gray"]),
});
export type SaturationBatchResult = z.infer<typeof SaturationBatchResultSchema>;
