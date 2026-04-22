/**
 * Edge function to fetch and strip ordinance HTML from allowed domains.
 * Edge runtime = 30s timeout on Vercel Hobby (vs 10s serverless).
 * No Anthropic SDK here — just fetch + HTML strip.
 *
 * GET /api/fetch-ordinance?url=...
 */
export const runtime = "edge";

const ALLOWED_DOMAINS = [
  "codelibrary.amlegal.com",
  "library.municode.com",
  "ecode360.com",
  "sterlingcodifiers.com",
  "codepublishing.com",
  "municipalcodeonline.com",
  "lehi-ut.gov",
  "alpine.utah.gov",
  "bluffdale.com",
  "murray.utah.gov",
  "salemutah.gov",
  "springville.org",
  "mapleton.utah.gov",
  "payson.utah.gov",
  "eagle-mountain.utah.gov",
  "herriman.utah.gov",
  "riverton.utah.gov",
  "draper.ut.us",
  "southjordan.com",
  "westjordan.com",
  "cityofwestjordan.com",
  "sandy.utah.gov",
  "provo.org",
  "orem.org",
  "american-fork.gov",
  "lindon.utah.gov",
  "pleasantgrove.utah.gov",
  "kaysville.utah.gov",
  "codexonline.com",
  "generalcode.com",
];

function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/\s{2,}/g, " ")
    .trim();
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const url = searchParams.get("url");

  if (!url) {
    return Response.json({ error: "url parameter required" }, { status: 400 });
  }

  let hostname: string;
  try {
    hostname = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return Response.json({ error: "Invalid URL" }, { status: 400 });
  }

  const allowed = ALLOWED_DOMAINS.some(
    (d) => hostname === d || hostname.endsWith(`.${d}`)
  );
  if (!allowed) {
    return Response.json(
      { error: `Domain "${hostname}" is not in the allowlist. Paste the text directly instead.` },
      { status: 403 }
    );
  }

  // Try Jina Reader first — handles JavaScript-rendered SPAs (municipalcodeonline, etc.)
  // Falls back to direct fetch for standard HTML sites.
  try {
    const jinaRes = await fetch(`https://r.jina.ai/${url}`, {
      headers: {
        "Accept": "text/plain",
        "User-Agent": "SiteScout/1.0 ZoningVerifier",
      },
      signal: AbortSignal.timeout(20_000),
    });

    if (jinaRes.ok) {
      const text = (await jinaRes.text()).slice(0, 80_000);
      if (text.length > 200) {
        return Response.json({ text, url, via: "jina" });
      }
    }
  } catch {
    // Jina unavailable — fall through to direct fetch
  }

  // Direct fetch fallback for standard HTML sites
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "SiteScout/1.0 ZoningVerifier" },
      signal: AbortSignal.timeout(15_000),
    });

    if (!res.ok) {
      return Response.json({ error: `HTTP ${res.status} from source` }, { status: 502 });
    }

    const html = await res.text();
    const text = stripHtml(html).slice(0, 80_000);
    return Response.json({ text, url, via: "direct" });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return Response.json({ error: msg }, { status: 502 });
  }
}
