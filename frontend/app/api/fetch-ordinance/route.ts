/**
 * Edge function to fetch ordinance content from any URL type.
 * For municipalcodeonline.com SPAs: fetches TOC, finds Table of Uses section,
 * then fetches that specific section. For all other sites: Jina Reader first,
 * direct fetch fallback.
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

const TABLE_OF_USES_KEYWORDS = [
  "table of uses",
  "table of permitted",
  "use matrix",
  "use regulations",
  "permitted uses",
  "use table",
  "allowed uses",
];

function hasTableOfUses(text: string): boolean {
  const lower = text.toLowerCase();
  return TABLE_OF_USES_KEYWORDS.some(k => lower.includes(k)) &&
    (lower.includes(" p ") || lower.includes("permitted") || lower.includes("conditional"));
}

async function jinaFetch(url: string, timeoutMs = 18_000): Promise<string> {
  const res = await fetch(`https://r.jina.ai/${url}`, {
    headers: { "Accept": "text/plain", "X-Return-Format": "text" },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) throw new Error(`Jina ${res.status}`);
  return res.text();
}

// Extract section links from TOC text for municipalcodeonline.com
function extractSectionUrls(tocText: string, baseUrl: string): string[] {
  const lower = tocText.toLowerCase();
  const urls: string[] = [];
  const base = baseUrl.split("#")[0];

  // Find section names that likely contain the Table of Uses
  const lines = tocText.split("\n");
  for (const line of lines) {
    const lineLower = line.toLowerCase();
    if (TABLE_OF_USES_KEYWORDS.some(k => lineLower.includes(k))) {
      // Extract the section name from patterns like "11.70.030 Table of Uses"
      const sectionMatch = line.match(/(\d+\.\d+[\.\d]*)\s+(.+)/);
      if (sectionMatch) {
        const sectionNum = sectionMatch[1];
        const sectionName = sectionMatch[2].trim().toUpperCase().replace(/\s+/g, "_");
        urls.push(`${base}#name=${sectionNum}_${sectionName}`);
        urls.push(`${base}#name=${sectionNum.replace(/\./g, "")}_${sectionName}`);
      }
    }
  }

  // Also try common patterns for use tables in Utah municipal codes
  const chapterMatch = baseUrl.match(/#name=(\d+)/);
  if (chapterMatch) {
    const chapter = chapterMatch[1];
    for (const keyword of ["TABLE_OF_USES", "TABLE_OF_PERMITTED_USES", "USE_REGULATIONS", "USE_TABLE", "PERMITTED_USES"]) {
      urls.push(`${base}#name=${chapter}.030_${keyword}`);
      urls.push(`${base}#name=${chapter}.040_${keyword}`);
      urls.push(`${base}#name=${chapter}.050_${keyword}`);
    }
  }

  return [...new Set(urls)]; // deduplicate
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
      { error: `Domain "${hostname}" not in allowlist. Try a Municode, amlegal, or ecode360 URL, or paste the text directly.` },
      { status: 403 }
    );
  }

  // ── Step 1: Fetch the given URL via Jina ──────────────────────────────────
  let initialText = "";
  try {
    initialText = (await jinaFetch(url, 18_000)).slice(0, 200_000);
  } catch {
    // Will try fallback below
  }

  // ── Step 2: Check if we already have the Table of Uses ───────────────────
  if (initialText.length > 500 && hasTableOfUses(initialText)) {
    return Response.json({ text: initialText, url, via: "jina" });
  }

  // ── Step 3: Smart section discovery for SPA sites (municipalcodeonline etc)
  if (initialText.length > 200) {
    const candidateUrls = extractSectionUrls(initialText, url);

    // Try up to 4 candidate section URLs in parallel
    const attempts = candidateUrls.slice(0, 4).map(async (sectionUrl) => {
      try {
        const text = (await jinaFetch(sectionUrl, 12_000)).slice(0, 200_000);
        return { text, url: sectionUrl, hasTable: hasTableOfUses(text) };
      } catch {
        return null;
      }
    });

    const results = await Promise.all(attempts);
    const best = results.find(r => r?.hasTable);
    if (best) {
      return Response.json({ text: best.text, url: best.url, via: "jina-smart" });
    }

    // Return best non-null result even without confirmed table
    const anyResult = results.find(r => r && r.text.length > 500);
    if (anyResult) {
      return Response.json({ text: anyResult.text, url: anyResult.url, via: "jina-smart" });
    }
  }

  // ── Step 4: Return initial text with a note if nothing better found ───────
  if (initialText.length > 200) {
    return Response.json({
      text: initialText + "\n\n[NOTE: Table of Uses section not automatically found. Try navigating to the Table of Uses chapter in the ordinance website and loading that specific page URL.]",
      url,
      via: "jina-partial",
    });
  }

  // ── Step 5: Direct HTML fallback ─────────────────────────────────────────
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "SiteScout/1.0 ZoningVerifier" },
      signal: AbortSignal.timeout(12_000),
    });
    if (!res.ok) {
      return Response.json({ error: `HTTP ${res.status}` }, { status: 502 });
    }
    const html = await res.text();
    const text = html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim()
      .slice(0, 200_000);
    return Response.json({ text, url, via: "direct" });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return Response.json({ error: msg }, { status: 502 });
  }
}
