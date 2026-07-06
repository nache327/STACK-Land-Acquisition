import { NextRequest, NextResponse } from "next/server";

/**
 * Reject cross-origin / originless calls to the browser-only proxy routes
 * (zoning-chat, places-*). These proxies spend Anthropic / Google credits per
 * call and were previously callable by any anonymous client.
 *
 * A public SPA can't hold a shared secret, so the minimum viable guard is to
 * require the request to originate from our own page (same Origin as Host).
 * This blocks naive drive-by abuse (no-Origin curl loops, cross-site calls).
 *
 * NOTE: the Origin header is spoofable via curl, so this is NOT robust rate
 * abuse protection — that needs a real rate limiter (e.g. Upstash Ratelimit on
 * Vercel Edge), which is a follow-up once Upstash is provisioned.
 */
export function sameOriginOnly(req: NextRequest): NextResponse | null {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  if (!origin || !host) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  try {
    if (new URL(origin).host !== host) {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
  } catch {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  return null;
}
