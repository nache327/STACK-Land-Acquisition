/**
 * Unit tests for Zod schemas — verifies the frontend schema layer
 * correctly validates API response shapes.
 */
import { JobSchema, ParcelRowSchema, UsePermissionSchema } from "@/lib/schemas";

describe("UsePermissionSchema", () => {
  it("accepts valid values", () => {
    expect(UsePermissionSchema.parse("permitted")).toBe("permitted");
    expect(UsePermissionSchema.parse("conditional")).toBe("conditional");
    expect(UsePermissionSchema.parse("prohibited")).toBe("prohibited");
    expect(UsePermissionSchema.parse("unclear")).toBe("unclear");
  });

  it("rejects invalid values", () => {
    expect(() => UsePermissionSchema.parse("allowed")).toThrow();
    expect(() => UsePermissionSchema.parse("")).toThrow();
  });
});

describe("JobSchema", () => {
  const valid = {
    id: "00000000-0000-0000-0000-000000000001",
    jurisdiction_id: null,
    status: "pending",
    jurisdiction_input: "Draper, UT",
    ordinance_url: null,
    target_uses: ["self_storage", "mini_warehouse"],
    error_message: null,
    progress: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  };

  it("parses a valid job", () => {
    const job = JobSchema.parse(valid);
    expect(job.id).toBe(valid.id);
    expect(job.status).toBe("pending");
  });

  it("rejects unknown status", () => {
    expect(() => JobSchema.parse({ ...valid, status: "running" })).toThrow();
  });
});

describe("ParcelRowSchema", () => {
  const valid = {
    id: 1,
    jurisdiction_id: "00000000-0000-0000-0000-000000000001",
    apn: "27-01-100-001",
    address: "1234 Main St",
    owner_name: "Acme LLC",
    acres: 2.5,
    zoning_code: "M1",
    land_use_code: "VACANT LAND",
    improvement_value: 0,
    has_structure: false,
    in_flood_zone: false,
    avg_slope_pct: 3.2,
    in_wetland: false,
    county_link: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  };

  it("parses a valid parcel", () => {
    const parcel = ParcelRowSchema.parse(valid);
    expect(parcel.apn).toBe("27-01-100-001");
    expect(parcel.has_structure).toBe(false);
  });

  it("allows null has_structure", () => {
    const parcel = ParcelRowSchema.parse({ ...valid, has_structure: null });
    expect(parcel.has_structure).toBeNull();
  });
});
