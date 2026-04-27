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

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Structured PDF result type ────────────────────────────────────────────────

interface StructuredPdfResult {
  uses: Record<string, Record<string, string>>;
  zone_columns: string[];
  confidence: number;
  method: string;
  warnings: string[];
}

// ── PDF detection ─────────────────────────────────────────────────────────────

function isPdfUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.pathname.toLowerCase().endsWith(".pdf");
  } catch {
    return false;
  }
}

// Convert structured PDF result to a human-readable markdown table
function structuredResultToText(result: StructuredPdfResult, sourceUrl: string): string {
  const { uses, zone_columns } = result;
  if (zone_columns.length === 0 || Object.keys(uses).length === 0) {
    return "[PDF parsed but no Table of Uses rows found — try pasting the text directly]";
  }

  const lines: string[] = [
    `Table of Uses — extracted from PDF (method: ${result.method}, confidence: ${(result.confidence * 100).toFixed(0)}%)`,
    `Source: ${sourceUrl}`,
    "",
    "NOTE: Blank = PROHIBITED per ordinance rule (uses not listed as P or C are prohibited)",
    "",
    `| Use | ${zone_columns.join(" | ")} |`,
    `|-----|${zone_columns.map(() => "---").join("|")}|`,
  ];

  for (const [useName, perms] of Object.entries(uses)) {
    const cells = zone_columns.map((z) => {
      const v = perms[z];
      if (v === "permitted") return "P";
      if (v === "conditional") return "C";
      return "—";
    });
    lines.push(`| ${useName} | ${cells.join(" | ")} |`);
  }

  lines.push("");
  lines.push("P = Permitted   C = Conditional   — = Prohibited");

  if (result.warnings.length > 0) {
    lines.push("", `Warnings: ${result.warnings.join("; ")}`);
  }

  return lines.join("\n");
}

// ── PDF fetch via backend parser ──────────────────────────────────────────────

async function fetchPdfViaBackend(
  url: string,
): Promise<{ text: string; structuredTable: StructuredPdfResult; via: string } | null> {
  try {
    const res = await fetch(`${BACKEND}/api/parse-pdf-table`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(55_000),
    });
    if (!res.ok) return null;
    const result = await res.json() as StructuredPdfResult;
    const text = structuredResultToText(result, url);
    const via = result.confidence >= 0.65 ? "pdf-structured" : "pdf-low-confidence";
    return { text, structuredTable: result, via };
  } catch {
    return null;
  }
}

const ALLOWED_DOMAINS = [
  "codelibrary.amlegal.com",
  "library.municode.com",
  "ecode360.com",
  "municipal.codes",
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
      { error: `Domain "${hostname}" not in allowlist. Try a Municode, municipal.codes, amlegal, or ecode360 URL, or paste the text directly.` },
      { status: 403 }
    );
  }

  // ── PDF: coordinate-based parser + Claude Vision fallback ────────────────
  if (isPdfUrl(url)) {
    const pdfResult = await fetchPdfViaBackend(url);
    if (pdfResult) {
      return Response.json({
        text: pdfResult.text,
        structuredTable: pdfResult.structuredTable,
        url,
        via: pdfResult.via,
      });
    }
    // Backend unreachable — fall through to Jina (best-effort for PDFs)
  }

  // ── All allowlisted domains: try Playwright backend first, Jina as fallback ──
  // The backend uses Playwright for JS SPAs (municode, municipalcodeonline, ecode360,
  // sterlingcodifiers, codepublishing, etc.) and plain HTTP for static city sites.
  // Adding a new municipal code platform only requires updating the backend's
  // detect_source_type() — no frontend changes needed.
  try {
    const res = await fetch(`${BACKEND}/api/ordinances/fetch-text?url=${encodeURIComponent(url)}`, {
      signal: AbortSignal.timeout(55_000),
    });
    if (res.ok) {
      const data = await res.json() as { text: string; section_count: number; error?: string };
      if (data.text && data.text.length > 200) {
        return Response.json({ text: data.text, url, via: "backend-playwright" });
      }
    }
  } catch { /* fall through to Jina */ }

  // Jina fallback — works for static HTML sites, may work for some SPAs
  try {
    const text = (await jinaFetch(url, 20_000)).slice(0, 200_000);
    if (text.length > 300) return Response.json({ text, url, via: "jina" });
  } catch { /* fall through */ }

  return Response.json({
    text: "[Could not fetch this URL — the site may require a real browser or block automated access. Try pasting the relevant ordinance text directly into the chat.]",
    url,
    via: "failed",
  });
}
