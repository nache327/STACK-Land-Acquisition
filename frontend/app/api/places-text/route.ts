/**
 * Server-side proxy for Google Places Text Search.
 * Keeps GOOGLE_PLACES_API_KEY off the browser bundle.
 *
 * POST /api/places-text
 * Body: { query, lat?, lng?, radius_meters? }
 */
import { NextRequest, NextResponse } from "next/server";
import { sameOriginOnly } from "@/lib/api-guard";

export const runtime = "edge";

export async function POST(req: NextRequest) {
  const blocked = sameOriginOnly(req);
  if (blocked) return blocked;
  const apiKey = process.env.GOOGLE_PLACES_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "GOOGLE_PLACES_API_KEY not configured" }, { status: 503 });
  }

  let body: { query: string; lat?: number; lng?: number; radius_meters?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { query, lat, lng, radius_meters } = body;
  if (!query?.trim()) {
    return NextResponse.json({ error: "query required" }, { status: 400 });
  }

  const params = new URLSearchParams({
    query: query.trim(),
    key: apiKey,
  });
  if (lat != null && lng != null) {
    params.set("location", `${lat},${lng}`);
    if (radius_meters) params.set("radius", String(Math.round(radius_meters)));
  }

  const url = `https://maps.googleapis.com/maps/api/place/textsearch/json?${params}`;

  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (!res.ok) {
      return NextResponse.json({ error: `Places API HTTP ${res.status}` }, { status: 502 });
    }
    const data = await res.json();
    const results = (data.results ?? []).map((r: Record<string, unknown>) => ({
      name: r.name,
      formatted_address: r.formatted_address,
      geometry: (r.geometry as Record<string, unknown>)?.location ?? null,
    }));
    return NextResponse.json({ results });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    );
  }
}
