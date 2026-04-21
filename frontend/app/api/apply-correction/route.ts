/**
 * Apply Correction — writes verified zoning corrections to the backend DB.
 * Calls PATCH /api/jurisdictions/{id}/zones/{zone_code} for each correction,
 * setting classification_source='human' and human_reviewed=true.
 *
 * POST /api/apply-correction
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Correction schema ─────────────────────────────────────────────────────────
interface ZoneCorrection {
  zone: string;
  use: string; // "self_storage" | "mini_warehouse" | "luxury_garage_condo" | "light_industrial"
  correct_value: string; // "permitted" | "conditional" | "prohibited"
  current_value?: string;
  evidence?: string;
  action: "UPDATE";
}

// Map use field names from correction report to DB column names
const USE_TO_COLUMN: Record<string, string> = {
  self_storage: "self_storage",
  storage_climate_controlled: "self_storage",
  storage_outdoor_access: "mini_warehouse",
  mini_warehouse: "mini_warehouse",
  garage_condo: "luxury_garage_condo",
  luxury_garage_condo: "luxury_garage_condo",
  light_industrial: "light_industrial",
};

const VALID_VALUES = new Set(["permitted", "conditional", "prohibited"]);

function normalizeValue(v: string): string {
  const lower = v.toLowerCase();
  if (lower === "permitted" || lower.includes("by_right") || lower.includes("by right"))
    return "permitted";
  if (lower === "conditional" || lower.includes("cup") || lower.includes("conditional"))
    return "conditional";
  if (lower === "prohibited" || lower.includes("prohibit")) return "prohibited";
  return lower;
}

export async function POST(req: NextRequest) {
  let body: {
    jurisdictionId: string;
    corrections: ZoneCorrection[];
    source?: string;
    sourceType?: string;
    verifiedDate?: string;
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { jurisdictionId, corrections, source, verifiedDate } = body;

  if (!jurisdictionId || !Array.isArray(corrections) || corrections.length === 0) {
    return NextResponse.json(
      { error: "jurisdictionId and corrections[] are required" },
      { status: 400 }
    );
  }

  // Validate and group corrections by zone_code
  const grouped: Record<string, Record<string, string>> = {};

  for (const c of corrections) {
    if (!c.zone || !c.use || !c.action || c.action !== "UPDATE") continue;

    const column = USE_TO_COLUMN[c.use];
    if (!column) continue;

    const value = normalizeValue(c.correct_value ?? "");
    if (!VALID_VALUES.has(value)) continue;

    if (!grouped[c.zone]) grouped[c.zone] = {};
    grouped[c.zone][column] = value;
  }

  if (Object.keys(grouped).length === 0) {
    return NextResponse.json(
      { error: "No valid corrections found after validation" },
      { status: 400 }
    );
  }

  // Apply each zone correction via PATCH
  const results: Array<{ zone: string; status: "ok" | "error"; detail?: string }> = [];

  for (const [zoneCode, fields] of Object.entries(grouped)) {
    try {
      const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}`;
      const patch = {
        ...fields,
        classification_source: "human",
        human_reviewed: true,
        notes: `Verified via Site Scout Zoning Chat. Source: ${source ?? "user session"}. Date: ${verifiedDate ?? new Date().toISOString().slice(0, 10)}.`,
      };

      const res = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal: AbortSignal.timeout(8_000),
      });

      if (res.ok) {
        results.push({ zone: zoneCode, status: "ok" });
      } else {
        const text = await res.text();
        results.push({ zone: zoneCode, status: "error", detail: `${res.status}: ${text.slice(0, 200)}` });
      }
    } catch (err) {
      results.push({
        zone: zoneCode,
        status: "error",
        detail: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const succeeded = results.filter((r) => r.status === "ok").length;
  const failed = results.filter((r) => r.status === "error").length;

  return NextResponse.json({
    success: failed === 0,
    succeeded,
    failed,
    results,
    message:
      failed === 0
        ? `${succeeded} zone${succeeded !== 1 ? "s" : ""} updated successfully. Corrections are permanent.`
        : `${succeeded} succeeded, ${failed} failed. Check results for details.`,
  });
}
