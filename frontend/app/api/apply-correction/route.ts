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
  use?: string; // "self_storage" | "mini_warehouse" | "luxury_garage_condo" | "light_industrial"
  correct_value?: string; // "permitted" | "conditional" | "prohibited"
  current_value?: string;
  evidence?: string;
  reason?: string;
  note?: string;
  display_name?: string;
  zone_name?: string;
  self_storage?: string;
  mini_warehouse?: string;
  light_industrial?: string;
  luxury_garage_condo?: string;
  classification_source?: string;
  confidence?: string | number;
  action: "UPDATE" | "DELETE" | "ADD";
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

  // Validate and group corrections by action type
  const updates: Record<string, Record<string, string>> = {};
  const adds: ZoneCorrection[] = [];
  const deletes: string[] = [];

  for (const c of corrections) {
    if (!c.zone || !c.action) continue;

    if (c.action === "DELETE") {
      deletes.push(c.zone);
    } else if (c.action === "ADD") {
      adds.push(c);
    } else if (c.action === "UPDATE") {
      if (!c.use) continue;
      const column = USE_TO_COLUMN[c.use];
      if (!column) continue;
      const value = normalizeValue(c.correct_value ?? "");
      if (!VALID_VALUES.has(value)) continue;
      if (!updates[c.zone]) updates[c.zone] = {};
      updates[c.zone][column] = value;
    }
  }

  if (Object.keys(updates).length === 0 && adds.length === 0 && deletes.length === 0) {
    return NextResponse.json(
      { error: "No valid corrections found after validation" },
      { status: 400 }
    );
  }

  const results: Array<{ zone: string; action: string; status: "ok" | "skipped" | "error"; detail?: string }> = [];

  // ── UPDATES ──
  for (const [zoneCode, fields] of Object.entries(updates)) {
    try {
      const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}`;
      const patch = {
        ...fields,
        classification_source: "human",
        human_reviewed: true,
        notes: `Verified via Site Scout Zoning Chat. Source: ${source ?? "user session"}. Date: ${verifiedDate ?? new Date().toISOString().slice(0, 10)}.`,
      };
      const res = await fetch(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch), signal: AbortSignal.timeout(8_000) });
      if (res.ok) {
        results.push({ zone: zoneCode, action: "UPDATE", status: "ok" });
      } else {
        const text = await res.text();
        results.push({ zone: zoneCode, action: "UPDATE", status: "error", detail: `${res.status}: ${text.slice(0, 200)}` });
      }
    } catch (err) {
      results.push({ zone: zoneCode, action: "UPDATE", status: "error", detail: err instanceof Error ? err.message : String(err) });
    }
  }

  // ── ADDITIONS ──
  for (const c of adds) {
    try {
      const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones`;
      const body = {
        zone_code: c.zone,
        zone_name: c.display_name ?? c.zone_name ?? c.zone,
        self_storage: c.self_storage ?? "unclear",
        mini_warehouse: c.mini_warehouse ?? "unclear",
        light_industrial: c.light_industrial ?? "unclear",
        luxury_garage_condo: c.luxury_garage_condo ?? "unclear",
        classification_source: c.classification_source ?? "rule",
        confidence: c.confidence ? parseFloat(String(c.confidence)) : 0.0,
      };
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(8_000) });
      if (res.ok) {
        results.push({ zone: c.zone, action: "ADD", status: "ok" });
      } else {
        const text = await res.text();
        results.push({ zone: c.zone, action: "ADD", status: "error", detail: `${res.status}: ${text.slice(0, 200)}` });
      }
    } catch (err) {
      results.push({ zone: c.zone, action: "ADD", status: "error", detail: err instanceof Error ? err.message : String(err) });
    }
  }

  // ── DELETES — skipped (destructive: would orphan real parcels) ──
  for (const zoneCode of deletes) {
    results.push({ zone: zoneCode, action: "DELETE", status: "skipped", detail: "DELETE skipped — use Zone Matrix to manually remove if needed" });
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
