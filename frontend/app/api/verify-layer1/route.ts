/**
 * Layer 1 — Our own zone_use_matrix lookup.
 * No external API. Reads our DB via the FastAPI backend.
 *
 * POST /api/verify-layer1
 * Body: { jurisdictionId: string, zoneCode: string }
 */
import { NextRequest, NextResponse } from "next/server";
import { scoreLayer1DB, type Layer1Result, type UseStatus } from "@/lib/verification";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  let jurisdictionId: string, zoneCode: string;
  try {
    const body = await req.json();
    jurisdictionId = String(body.jurisdictionId ?? "");
    zoneCode = String(body.zoneCode ?? "");
    if (!jurisdictionId || !zoneCode) throw new Error("missing fields");
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  try {
    const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}`;
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

    const classificationSource: Layer1Result["classificationSource"] =
      (["llm", "rule", "human", "unclear"].includes(row.classification_source)
        ? row.classification_source
        : "unclear") as Layer1Result["classificationSource"];

    const toUseStatus = (v: string | null | undefined): UseStatus => {
      if (v === "permitted" || v === "conditional" || v === "prohibited") return v;
      return "unclear";
    };

    const selfStorageStatus = toUseStatus(row.self_storage);

    const { score, permitType } = scoreLayer1DB({
      selfStorageStatus,
      classificationSource,
      confidence: row.confidence ?? null,
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
      confidence: row.confidence ?? null,
      humanReviewed: row.human_reviewed ?? false,
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
