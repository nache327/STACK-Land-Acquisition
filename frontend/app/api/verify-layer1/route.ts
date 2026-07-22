/**
 * Layer 1 — Our own zone_use_matrix lookup.
 * No external API. Reads our DB via the FastAPI backend.
 *
 * POST /api/verify-layer1
 * Body: { jurisdictionId: string, zoneCode: string, municipality?: string }
 *
 * municipality (= parcels.city, case-sensitive) is forwarded so the backend
 * reads the SAME municipality-scoped zone_use_matrix row the Site Score uses
 * (fallback_default=true prefers it, falls back to the NULL county-default).
 */
import { NextRequest, NextResponse } from "next/server";
import { scoreLayer1DB, type Layer1Result, type UseStatus } from "@/lib/verification";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  let jurisdictionId: string, zoneCode: string, municipality: string;
  try {
    const body = await req.json();
    jurisdictionId = String(body.jurisdictionId ?? "");
    zoneCode = String(body.zoneCode ?? "");
    municipality = String(body.municipality ?? "");
    if (!jurisdictionId || !zoneCode) throw new Error("missing fields");
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  try {
    const params = new URLSearchParams();
    if (municipality) {
      params.set("municipality", municipality);
      params.set("fallback_default", "true");
    }
    const qs = params.toString();
    const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}${qs ? `?${qs}` : ""}`;
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8_000),
    });

    if (res.status === 404) {
      const result: Layer1Result = {
        status: "no-coverage",
        zoneCode,
        zoneName: "",
        selfStorageStatus: "unclear",
        miniWarehouseStatus: "unclear",
        lightIndustrialStatus: "unclear",
        luxuryGarageStatus: "unclear",
        classificationSource: "unclear",
        confidence: null,
        humanReviewed: false,
        grounded: false,
        notes: null,
        permitType: null,
        score: 0,
        fetchedAt: Date.now(),
      };
      return NextResponse.json(result);
    }

    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend returned ${res.status}` },
        { status: 502 }
      );
    }

    const row = await res.json();

    // Pass the raw zone_use_matrix source enum through — do NOT collapse
    // grounded sources (op5_factory, llm_rule, crosswalk, …) to "unclear".
    // scoreLayer1DB decides trust via isGrounded, not a hard-coded whitelist.
    const classificationSource: string = String(row.classification_source ?? "unclear");
    const humanReviewed: boolean = row.human_reviewed ?? false;
    const confidence: number | null = row.confidence ?? null;

    const toUseStatus = (v: string | null | undefined): UseStatus => {
      if (v === "permitted" || v === "conditional" || v === "prohibited") return v;
      return "unclear";
    };

    const selfStorageStatus = toUseStatus(row.self_storage);

    const { score, permitType, grounded } = scoreLayer1DB({
      selfStorageStatus,
      classificationSource,
      confidence,
      humanReviewed,
    });

    const result: Layer1Result = {
      status: "complete",
      zoneCode: row.zone_code ?? zoneCode,
      zoneName: row.zone_name ?? "",
      selfStorageStatus,
      miniWarehouseStatus: toUseStatus(row.mini_warehouse),
      lightIndustrialStatus: toUseStatus(row.light_industrial),
      luxuryGarageStatus: toUseStatus(row.luxury_garage_condo),
      classificationSource,
      confidence,
      humanReviewed,
      grounded,
      notes: row.notes ?? null,
      permitType,
      score,
      fetchedAt: Date.now(),
    };

    return NextResponse.json(result);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const errorResult: Layer1Result = {
      status: "error",
      zoneCode,
      zoneName: "",
      selfStorageStatus: "unclear",
      miniWarehouseStatus: "unclear",
      lightIndustrialStatus: "unclear",
      luxuryGarageStatus: "unclear",
      classificationSource: "unclear",
      confidence: null,
      humanReviewed: false,
      grounded: false,
      notes: null,
      permitType: null,
      score: 0,
      fetchedAt: Date.now(),
    };
    if (msg.includes("timeout") || msg.includes("abort")) {
      return NextResponse.json(errorResult, { status: 200 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
