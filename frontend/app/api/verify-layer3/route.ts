/**
 * Layer 3 — Ordinance text verification.
 * Checks our zone_use_matrix for existing LLM-parsed data (free).
 * If only rule-based data exists, triggers ordinance parse via backend.
 *
 * POST /api/verify-layer3
 * Body: { jurisdictionId: string, zoneCode: string }
 */
import { NextRequest, NextResponse } from "next/server";
import { layer3FromZoneRow, type Layer3Result } from "@/lib/verification";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  let jurisdictionId: string, zoneCode: string;
  try {
    const body = await req.json();
    jurisdictionId = String(body.jurisdictionId);
    zoneCode = String(body.zoneCode);
    if (!jurisdictionId || !zoneCode) throw new Error("missing fields");
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  // 1. Fetch the single zone row from our backend
  let zoneRow: Record<string, unknown> | null = null;
  try {
    const url = `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones/${encodeURIComponent(zoneCode)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (res.ok) {
      zoneRow = await res.json();
    }
  } catch {
    // Backend unreachable — fall through to ordinance-not-found
  }

  // 2. If we have LLM or human classification with citations, return it directly
  if (
    zoneRow &&
    (zoneRow.classification_source === "llm" ||
      zoneRow.classification_source === "human") &&
    zoneRow.self_storage
  ) {
    const result = layer3FromZoneRow(zoneRow as Parameters<typeof layer3FromZoneRow>[0]);
    return NextResponse.json(result);
  }

  // 3. If only rule-based data, trigger fresh ordinance parse and return partial result
  if (zoneRow && zoneRow.self_storage) {
    // Return what we have but flag it as rule-based (lower confidence)
    const result = layer3FromZoneRow(zoneRow as Parameters<typeof layer3FromZoneRow>[0]);
    result.notes = [
      result.notes,
      "Rule-based classification — ordinance not yet parsed for this zone.",
    ]
      .filter(Boolean)
      .join(" ");

    // Kick off async ordinance parse — don't wait for it
    fetch(`${BACKEND}/api/ordinances/${jurisdictionId}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordinance_url: null }),
    }).catch(() => {
      // Ignore — background job
    });

    return NextResponse.json(result);
  }

  // 4. No zone data at all
  const notFound: Layer3Result = {
    status: "ordinance-not-found",
    ordinanceUrl: null,
    selfStorageStatus: null,
    keepStatus: null,
    evidence: null,
    aiConfidence: null,
    notes: null,
    classificationSource: null,
    score: 0,
    fetchedAt: Date.now(),
  };
  return NextResponse.json(notFound);
}
