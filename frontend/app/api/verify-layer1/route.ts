/**
 * Layer 1 — Zoneomics API server-side proxy.
 * Keeps ZONEOMICS_API_KEY out of the browser.
 *
 * POST /api/verify-layer1
 * Body: { lat: number, lng: number, productType: "storage" | "keep" }
 */
import { NextRequest, NextResponse } from "next/server";
import { scoreLayer1, STORAGE_PLU_TAGS, type Layer1Result } from "@/lib/verification";

const ZONEOMICS_BASE = "https://api.zoneomics.com/v2";

export async function POST(req: NextRequest) {
  const apiKey = process.env.ZONEOMICS_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "ZONEOMICS_API_KEY not configured" },
      { status: 503 }
    );
  }

  let lat: number, lng: number;
  try {
    const body = await req.json();
    lat = Number(body.lat);
    lng = Number(body.lng);
    if (isNaN(lat) || isNaN(lng)) throw new Error("invalid coordinates");
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  try {
    const url = new URL(`${ZONEOMICS_BASE}/zoneDetail`);
    url.searchParams.set("lat", String(lat));
    url.searchParams.set("lng", String(lng));
    url.searchParams.set("api_key", apiKey);
    url.searchParams.set("output_fields", "zoning,plu,plu-tags,controls");

    const zRes = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(10_000),
    });

    if (!zRes.ok) {
      const text = await zRes.text();
      if (zRes.status === 404 || zRes.status === 422) {
        // No coverage for this location
        const result: Layer1Result = {
          status: "no-coverage",
          zoneCode: "",
          zoneDescription: "",
          pluTags: [],
          pluMatch: false,
          matchedTags: [],
          permitType: null,
          score: 0,
          fetchedAt: Date.now(),
        };
        return NextResponse.json(result);
      }
      return NextResponse.json(
        { error: `Zoneomics returned ${zRes.status}: ${text.slice(0, 200)}` },
        { status: 502 }
      );
    }

    const data = await zRes.json();

    // Parse Zoneomics response — field names may vary by subscription tier
    const zoneCode: string =
      data.zoning?.zone_code ?? data.zone_code ?? data.zoning ?? "";
    const zoneDescription: string =
      data.zoning?.zone_name ?? data.zone_name ?? data.description ?? "";
    const rawPluTags: string[] = (
      data["plu-tags"] ?? data.plu_tags ?? data.plu?.tags ?? []
    ).map((t: string) => t.toLowerCase());

    // Determine permit type from PLU controls
    const controls: unknown[] = data.controls ?? data.plu?.controls ?? [];
    let permitType: Layer1Result["permitType"] = null;
    for (const ctrl of controls as Array<Record<string, string>>) {
      const tag = (ctrl.use_tag ?? ctrl.tag ?? "").toLowerCase();
      const type = (ctrl.permit_type ?? ctrl.type ?? "").toLowerCase();
      if (STORAGE_PLU_TAGS.has(tag)) {
        if (type.includes("prohibit")) { permitType = "prohibited"; break; }
        if (type.includes("condition") || type.includes("cup")) { permitType = "conditional"; }
        else if (!permitType) { permitType = "permitted-by-right"; }
      }
    }

    const { score, pluMatch, matchedTags } = scoreLayer1(
      rawPluTags,
      zoneDescription,
      zoneCode,
      permitType
    );

    const result: Layer1Result = {
      status: "complete",
      zoneCode,
      zoneDescription,
      pluTags: rawPluTags,
      pluMatch,
      matchedTags,
      permitType,
      score,
      rawResponse: data,
      fetchedAt: Date.now(),
    };

    return NextResponse.json(result);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("timeout") || msg.includes("abort")) {
      return NextResponse.json(
        {
          status: "error",
          zoneCode: "",
          zoneDescription: "",
          pluTags: [],
          pluMatch: false,
          matchedTags: [],
          permitType: null,
          score: 0,
          fetchedAt: Date.now(),
          error: "Zoneomics request timed out",
        } satisfies Layer1Result & { error: string },
        { status: 200 } // Return 200 so map doesn't break
      );
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
