/**
 * Server-side proxy for Google Places Nearby Search.
 * Keeps GOOGLE_PLACES_API_KEY off the browser bundle.
 *
 * POST /api/places-nearby
 * Body: { lat, lng, radius_meters, type?, keyword? }
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

export async function POST(req: NextRequest) {
  const apiKey = process.env.GOOGLE_PLACES_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "GOOGLE_PLACES_API_KEY not configured" }, { status: 503 });
  }

  let body: { lat: number; lng: number; radius_meters: number; type?: string; keyword?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { lat, lng, radius_meters, type, keyword } = body;
  if (typeof lat !== "number" || typeof lng !== "number" || typeof radius_meters !== "number") {
    return NextResponse.json({ error: "lat, lng, radius_meters required" }, { status: 400 });
  }

  const params = new URLSearchParams({
    location: `${lat},${lng}`,
    radius: String(Math.round(radius_meters)),
    key: apiKey,
  });
  if (type) params.set("type", type);
  if (keyword) params.set("keyword", keyword);

  const url = `https://maps.googleapis.com/maps/api/place/nearbysearch/json?${params}`;

  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (!res.ok) {
      return NextResponse.json({ error: `Places API HTTP ${res.status}` }, { status: 502 });
    }
    const data = await res.json();
    // Return only name + vicinity + geometry to keep payload small
    const results = (data.results ?? []).map((r: Record<string, unknown>) => ({
      name: r.name,
      vicinity: r.vicinity,
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
