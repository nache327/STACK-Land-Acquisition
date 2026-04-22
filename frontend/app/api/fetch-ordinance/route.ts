/**
 * Edge function to fetch ordinance content from any URL type.
 *
 * For municipalcodeonline.com SPAs:
 *   1. Try the original URL (hash) directly via Jina — works if the site does SSR
 *   2. Probe likely REST API endpoints the SPA uses to load section content
 *   3. Fetch base TOC, parse for table-of-uses section links
 *   4. Try chapter-based URL guesses in parallel
 *
 * For all other sites: Jina Reader first, direct HTML fallback.
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
  "schedule of uses",
  "schedule of permitted",
  "land use table",
  "land use tables",
];

// Keywords that match section names in hash URLs (underscore-separated, uppercase)
const HASH_USE_TABLE_PATTERNS = [
  "TABLE_OF_USES",
  "USE_MATRIX",
  "PERMITTED_USES",
  "SCHEDULE_OF_USES",
  "USE_TABLE",
  "USE_REGULATIONS",
  "LAND_USE_TABLE",
  "LAND_USE_TABLES",
  "USE_PERMITTED",
  "ALLOWED_USES",
];

function hasTableOfUses(text: string): boolean {
  const lower = text.toLowerCase();
  const hasKeyword = TABLE_OF_USES_KEYWORDS.some(k => lower.includes(k));
  const hasPermissionData = (
    lower.includes("permitted") ||
    lower.includes("conditional") ||
    // table cell with just "p" or "c" — common in printed use tables
    /\|\s*p\s*\|/i.test(text) ||
    /\bp\b.*\bc\b/i.test(text.slice(0, 5000))
  );
  return hasKeyword && hasPermissionData;
}

async function jinaFetch(url: string, timeoutMs = 18_000): Promise<string> {
  // URLs with query strings or hash fragments must be fully encoded so they arrive
  // at Jina's server as a single opaque path segment. Without encoding:
  //   - '?' causes query params to be parsed as Jina's own parameters (not the target URL's)
  //   - '#' is stripped at the HTTP layer before reaching Jina's server
  const jinaTarget = (url.includes("?") || url.includes("#"))
    ? encodeURIComponent(url)
    : url;
  const res = await fetch(`https://r.jina.ai/${jinaTarget}`, {
    headers: {
      "Accept": "text/plain",
      "X-Return-Format": "text",
      "X-Timeout": "25",  // extra time for JS-heavy SPAs to render section content
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) throw new Error(`Jina ${res.status}`);
  return res.text();
}

// Try to directly hit the municipalcodeonline.com REST API that the SPA uses
async function probeMunicipalCodeApi(origin: string, hashName: string, queryType: string): Promise<string | null> {
  const endpoints = [
    `${origin}/api/content?type=${queryType}&name=${hashName}`,
    `${origin}/api/section?type=${queryType}&name=${hashName}`,
    `${origin}/api/ordinances?section=${hashName}`,
    `${origin}/content?type=${queryType}&name=${hashName}`,
    `${origin}/book/content?type=${queryType}&name=${hashName}`,
  ];

  const attempts = endpoints.map(async (ep) => {
    try {
      const res = await fetch(ep, {
        headers: { "Accept": "application/json, text/html, text/plain" },
        signal: AbortSignal.timeout(6_000),
      });
      if (!res.ok) return null;
      const ct = res.headers.get("content-type") ?? "";
      if (ct.includes("json")) {
        const json = await res.json() as Record<string, unknown>;
        const content = (json.content ?? json.text ?? json.html ?? json.body ?? "") as string;
        return typeof content === "string" && content.length > 100 ? content : null;
      }
      const text = await res.text();
      return text.length > 100 ? text : null;
    } catch {
      return null;
    }
  });

  const results = await Promise.all(attempts);
  return results.find(r => r !== null) ?? null;
}

// Extract candidate section URLs from TOC text
function extractSectionUrls(tocText: string, baseWithQuery: string): string[] {
  const urls: string[] = [];

  // Lines like "11.350 Land Use Tables"
  const lines = tocText.split("\n");
  for (const line of lines) {
    const lineLower = line.toLowerCase();
    if (TABLE_OF_USES_KEYWORDS.some(k => lineLower.includes(k))) {
      const sectionMatch = line.match(/(\d+\.\d+(?:\.\d+)?)\s+(.+)/);
      if (sectionMatch) {
        const sectionNum = sectionMatch[1];
        const sectionName = sectionMatch[2].trim().toUpperCase().replace(/[^A-Z0-9]+/g, "_");
        urls.push(`${baseWithQuery}#name=${sectionNum}_${sectionName}`);
      }
    }
  }

  // Embedded hash links in the TOC text
  const hashPatternStr = HASH_USE_TABLE_PATTERNS.join("|");
  const hashRe = new RegExp(`#name=([A-Z0-9_.]+(?:${hashPatternStr})[A-Z0-9_.]*)`, "gi");
  let m: RegExpExecArray | null;
  while ((m = hashRe.exec(tocText)) !== null) {
    urls.push(`${baseWithQuery}#name=${m[1].toUpperCase()}`);
  }

  return Array.from(new Set(urls));
}

// Main handler for municipalcodeonline.com SPAs
async function fetchMunicipalCodeOnline(url: string): Promise<{ text: string; url: string } | null> {
  let urlObj: URL;
  try { urlObj = new URL(url); } catch { return null; }

  const origin = urlObj.origin;
  const hashName = urlObj.hash.replace(/^#name=/i, "");
  const queryType = urlObj.searchParams.get("type") ?? "ordinances";
  const baseWithQuery = `${origin}${urlObj.pathname}${urlObj.search}`;

  // ── 1. Direct API probe — fastest if it works ──────────────────────────────
  if (hashName) {
    const apiText = await probeMunicipalCodeApi(origin, hashName, queryType);
    if (apiText && hasTableOfUses(apiText)) {
      return { text: apiText, url };
    }
  }

  // ── 2. Try the original hash URL via Jina (works on some SPAs) ─────────────
  if (hashName) {
    try {
      const text = (await jinaFetch(url, 20_000)).slice(0, 200_000);
      if (hasTableOfUses(text)) return { text, url };
    } catch { /* fall through */ }
  }

  // ── 3. Fetch base TOC to find the correct section link ─────────────────────
  let tocText = "";
  try {
    tocText = (await jinaFetch(baseWithQuery, 20_000)).slice(0, 300_000);
    if (hasTableOfUses(tocText)) return { text: tocText, url: baseWithQuery };
  } catch { /* fall through */ }

  // ── 4. Build candidate section URLs ────────────────────────────────────────
  const candidateUrls: string[] = [];

  // From TOC content
  candidateUrls.push(...extractSectionUrls(tocText, baseWithQuery));

  // Chapter guesses — derive chapter from the hash name
  const chapterFromHash = hashName ? hashName.match(/^(\d+)\./) : null;
  const chapter = chapterFromHash ? chapterFromHash[1] : null;

  if (chapter) {
    for (const kw of HASH_USE_TABLE_PATTERNS) {
      // Try sub-sections common in Utah zoning codes
      for (const sub of ["350", "360", "300", "06", "07", "08", "030", "040", "050", "200"]) {
        candidateUrls.push(`${baseWithQuery}#name=${chapter}.${sub}_${kw}`);
      }
    }
  }

  // Utah-specific common patterns across chapters 11 and 17
  for (const chap of ["11.350", "11.360", "11.06", "11.07", "11.08", "11.10",
                       "17.350", "17.06", "10.04", "10.06"]) {
    for (const kw of HASH_USE_TABLE_PATTERNS) {
      candidateUrls.push(`${baseWithQuery}#name=${chap}_${kw}`);
    }
  }

  const unique = Array.from(new Set(candidateUrls)).slice(0, 16);

  // ── 5. Fetch candidates in parallel ────────────────────────────────────────
  const attempts = unique.map(async (sectionUrl) => {
    try {
      const text = (await jinaFetch(sectionUrl, 12_000)).slice(0, 200_000);
      return { text, url: sectionUrl, hasTable: hasTableOfUses(text), len: text.length };
    } catch {
      return null;
    }
  });

  const results = await Promise.all(attempts);

  // Only return content if we actually found a use table — no preface/TOC fallbacks
  const best = results.find(r => r?.hasTable);
  if (best) return { text: best.text, url: best.url };

  return null;
}

// ── Main GET handler ──────────────────────────────────────────────────────────

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

  // ── municipalcodeonline.com: dedicated multi-step path ────────────────────
  if (hostname.includes("municipalcodeonline.com")) {
    const result = await fetchMunicipalCodeOnline(url);
    if (result) {
      return Response.json({ text: result.text, url: result.url, via: "jina-smart" });
    }
    return Response.json({
      text: "[Could not automatically locate the Table of Uses for this URL. Navigate to the specific section in the ordinance website and paste the text directly.]",
      url,
      via: "jina-failed",
    });
  }

  // ── Generic path ──────────────────────────────────────────────────────────
  let initialText = "";
  try {
    initialText = (await jinaFetch(url, 18_000)).slice(0, 200_000);
  } catch { /* try fallback below */ }

  if (initialText.length > 500 && hasTableOfUses(initialText)) {
    return Response.json({ text: initialText, url, via: "jina" });
  }

  if (initialText.length > 200) {
    const candidateUrls = extractSectionUrls(initialText, url);
    const attempts = candidateUrls.slice(0, 4).map(async (sectionUrl) => {
      try {
        const text = (await jinaFetch(sectionUrl, 12_000)).slice(0, 200_000);
        return { text, url: sectionUrl, hasTable: hasTableOfUses(text) };
      } catch { return null; }
    });
    const results = await Promise.all(attempts);
    const best = results.find(r => r?.hasTable);
    if (best) return Response.json({ text: best.text, url: best.url, via: "jina-smart" });

    const anyResult = results.find(r => r && r.text.length > 500);
    if (anyResult) return Response.json({ text: anyResult.text, url: anyResult.url, via: "jina-smart" });
  }

  if (initialText.length > 200) {
    return Response.json({
      text: initialText + "\n\n[NOTE: Table of Uses section not automatically found. Try navigating to the Table of Uses chapter in the ordinance website and copying that URL.]",
      url,
      via: "jina-partial",
    });
  }

  // ── Direct HTML fallback ──────────────────────────────────────────────────
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "SiteScout/1.0 ZoningVerifier" },
      signal: AbortSignal.timeout(12_000),
    });
    if (!res.ok) return Response.json({ error: `HTTP ${res.status}` }, { status: 502 });
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
