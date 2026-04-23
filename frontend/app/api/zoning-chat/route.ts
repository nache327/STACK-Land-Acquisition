/**
 * Zoning Verifier Chat — streaming API route.
 * Handles URL fetch, pasted text, and image (vision) inputs.
 * Server-side only — ANTHROPIC_API_KEY never reaches the browser.
 *
 * POST /api/zoning-chat
 */
import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";

export const maxDuration = 30;

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Domain allowlist for URL fetching ────────────────────────────────────────
const ALLOWED_DOMAINS = [
  "codelibrary.amlegal.com",
  "library.municode.com",
  "ecode360.com",
  "municipal.codes",
  "sterlingcodifiers.com",
  "codepublishing.com",
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

// ── System prompt ─────────────────────────────────────────────────────────────
const SYSTEM_PROMPT = `You are a zoning verification engine for Site Scout, a real estate site selection tool for a self-storage and luxury garage condo development company called The Keep.

YOUR ONLY JOB:
When ordinance text is provided (fetched from a URL, pasted, or uploaded as an image), read it completely, compare every zone against the Site Scout database, and report all conflicts. Do this automatically without being asked. Do not ask the user for more information — work with what you have.

THE DATABASE (provided in context) contains the current Site Scout classifications:
- zone_code, self_storage, mini_warehouse, light_industrial, luxury_garage_condo
- Values: "permitted" | "conditional" | "prohibited" | "unclear"
- classification_source: "llm" | "rule" | "human"

ORDINANCE FORMAT IDENTIFICATION (Step 0 — do this before anything else):
Ordinances come in multiple formats. Identify which format applies before extracting data:

FORMAT A — Consolidated Use Matrix / Table of Uses:
  A single table listing all zones as columns and uses as rows, with P/C/blank cells.
  Extraction: Read P=permitted, C=conditional, blank or dash = prohibited.

FORMAT B — Per-Zone Chapter (prose or list):
  Each zone has its own chapter with sections like "Permitted Uses:", "Conditional Uses:",
  "Accessory Uses:". Uses not listed in any section are PROHIBITED.
  Example: "17.47.020 Permitted Uses. The following uses are permitted in the LI zone:
    1. Warehousing and storage  2. Mini-storage facilities..."
  Extraction: For each zone chapter, list what's explicitly permitted, what's conditional.
  Any use NOT in those lists = prohibited for that zone.

FORMAT C — Use-by-Use Sections:
  Each USE has its own section listing which zones allow it.
  Example: "Self-storage is permitted in: C-2, I-1, I-2. Conditional in: C-1."
  Extraction: Build zone→use map by reading each use section.

FORMAT D — Hybrid (matrix + supplemental prose):
  A use matrix plus narrative sections that add conditions or exceptions.
  Extraction: Use the matrix as the base, then apply prose modifications.

CRITICAL RULE FOR ALL FORMATS: If a use is not explicitly listed as permitted or conditional for a zone, it is PROHIBITED. Silence = prohibited.

AUTOMATIC ANALYSIS STEPS (run these every time ordinance text is present):
1. Identify which format the ordinance uses (A/B/C/D above)
2. For FORMAT B (per-zone prose): scan EVERY zone section for "permitted uses", "conditional uses", "accessory uses" lists. Check for self-storage, mini-storage, warehousing, storage facilities, garage condominiums, luxury garages, industrial uses.
3. For each zone, determine self_storage and luxury_garage_condo status: permitted / conditional / prohibited
4. Compare each zone against the database
5. List all conflicts where the ordinance says something different from the database
6. List zones in the ordinance that are missing from the database entirely

OUTPUT FORMAT:

**Ordinance vs Database Comparison — [City Name]**
Source: [URL or "pasted text"]

CONFLICTS FOUND:
| Zone | Use | Ordinance Says | DB Has | Action Needed |
|------|-----|---------------|--------|---------------|
| C-1  | self_storage | permitted | conditional | UPDATE DB |

MISSING FROM DB:
- List any zones in the ordinance not found in the database

NO CONFLICTS:
- If everything matches, say so explicitly

When the user asks for a VS Code / Claude Code prompt to fix the backend, generate EXACTLY this format:

---CORRECTION REPORT---
City: [City Name, State]
Source: [URL]
Verified: [today's date]

ZONING RULE CORRECTIONS:
[
  {
    "zone": "C-1",
    "use": "self_storage",
    "correct_value": "permitted",
    "current_value": "conditional",
    "evidence": "[exact quote or table reference from ordinance]",
    "action": "UPDATE"
  }
]
---END CORRECTION REPORT---

WHEN STRUCTURED_TABLE DATA IS PROVIDED:
- This means the PDF was parsed with coordinate analysis — the P/C/blank values are EXACT, not interpreted from text.
- Do NOT try to re-read column positions from the raw text. Trust the structured data completely.
- Compare each use row directly against the database: for each zone in structured_table.uses, look up that zone in the database and compare the values.
- "permitted" in structured_table = P in the ordinance. "conditional" = C. Any zone NOT listed under a use = prohibited.
- Generate the CONFLICTS FOUND table immediately with high confidence.

WHEN NO USABLE ORDINANCE TEXT IS PROVIDED (URL failed to fetch, or first message):
- Do NOT ask the user to paste text or navigate websites
- Instead: immediately produce the database state table, mark every row where classification_source is "rule" or "unclear" as UNVERIFIED, and end with ONE sentence: "Load a URL or paste ordinance text above to verify these values against the actual ordinance."
- If the text starts with "[Could not automatically locate" or "[Could not fetch", acknowledge in one sentence then proceed to the database report

DO NOT GIVE UP when the ordinance text lacks a formal "Table of Uses":
- If you receive per-zone chapter text (Format B), extract the use lists directly from the prose
- Look for self-storage, mini-storage, storage facilities, warehousing, personal storage, garage condominiums, luxury garages, vehicle storage in the permitted/conditional use lists
- If a zone chapter says "Permitted Uses: [list that includes storage]" → that zone = permitted
- If the chapter says "Conditional Uses: [list that includes storage]" → conditional
- If storage is not mentioned in any permitted/conditional list for a zone → prohibited

IMPORTANT: Never give multi-step instructions asking the user to do manual work. Always output data.`;

// ── HTML stripping ────────────────────────────────────────────────────────────
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

// ── Fetch ordinance URL ───────────────────────────────────────────────────────
async function fetchOrdinanceUrl(url: string): Promise<string> {
  let hostname: string;
  try {
    hostname = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    throw new Error("Invalid URL");
  }

  const allowed = ALLOWED_DOMAINS.some(
    (d) => hostname === d || hostname.endsWith(`.${d}`)
  );
  if (!allowed) {
    throw new Error(
      `Domain not in allowlist. Paste the text directly instead.`
    );
  }

  const res = await fetch(url, {
    headers: { "User-Agent": "SiteScout/1.0 ZoningVerifier" },
    signal: AbortSignal.timeout(7_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  const text = stripHtml(html);
  // Trim to ~60k chars to stay within token budget
  return text.slice(0, 60_000);
}

// ── Backend zone data lookup ──────────────────────────────────────────────────
async function getZoningRulesForCity(
  jurisdictionId: string
): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(
      `${BACKEND}/api/jurisdictions/${jurisdictionId}/zones`,
      { signal: AbortSignal.timeout(8_000) }
    );
    if (!res.ok) return null;
    const data = await res.json();
    // Normalize to zone→use map
    const zones: Record<string, Record<string, string>> = {};
    for (const row of data.zones ?? []) {
      zones[row.zone_code] = {
        self_storage: row.self_storage,
        mini_warehouse: row.mini_warehouse,
        light_industrial: row.light_industrial,
        luxury_garage_condo: row.luxury_garage_condo,
        classification_source: row.classification_source,
        confidence: String(row.confidence ?? ""),
      };
    }
    return { jurisdictionId, zones };
  } catch {
    return null;
  }
}

// ── Main handler ──────────────────────────────────────────────────────────────
export async function POST(req: NextRequest) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "ANTHROPIC_API_KEY not configured" },
      { status: 503 }
    );
  }

  let body: {
    messages: Array<{ role: "user" | "assistant"; content: string }>;
    ordinanceUrl?: string;
    pastedText?: string;
    images?: Array<{ base64: string; mediaType: string }>;
    productType?: string;
    jurisdictionId?: string;
    checkBackend?: boolean;
    structuredTable?: {
      uses: Record<string, Record<string, string>>;
      zone_columns: string[];
      confidence: number;
      method: string;
      warnings: string[];
    };
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const {
    messages,
    ordinanceUrl,
    pastedText,
    images,
    jurisdictionId,
    checkBackend,
    structuredTable,
  } = body;

  // Build extra context blocks for the current user message
  const extraBlocks: Anthropic.ContentBlockParam[] = [];

  // URL fetch skipped server-side (Vercel Hobby 10s limit).
  // Tell Claude the URL was provided so it can reference it in answers.
  if (ordinanceUrl) {
    extraBlocks.push({
      type: "text",
      text: `\n\n[The user has provided this ordinance URL for reference: ${ordinanceUrl}. You cannot fetch it directly — ask the user to paste the relevant table or section text if you need specifics. You may still answer general questions about the city's zoning based on your training knowledge.]`,
    });
  }

  // Add pasted or pre-fetched ordinance text
  if (pastedText?.trim()) {
    extraBlocks.push({
      type: "text",
      text: `\n\n--- ORDINANCE TEXT (source: ${ordinanceUrl ?? "pasted"}) ---\n${pastedText.slice(0, 150_000)}\n--- END ORDINANCE TEXT ---`,
    });
  }

  // Structured PDF table — pre-extracted with coordinate analysis, high confidence
  if (structuredTable && Object.keys(structuredTable.uses).length > 0) {
    extraBlocks.push({
      type: "text",
      text: `\n\n--- STRUCTURED_TABLE (pre-extracted from PDF, method: ${structuredTable.method}, confidence: ${(structuredTable.confidence * 100).toFixed(0)}%) ---\nZone columns: ${structuredTable.zone_columns.join(", ")}\n${JSON.stringify(structuredTable.uses, null, 2)}\n\nINSTRUCTION: Use this structured data as the authoritative source for what the ordinance says. Each key is a use name, each value maps zone_code → "permitted" | "conditional". Any zone NOT present under a use means PROHIBITED for that use. Compare directly against the database — do not try to re-parse raw text.\n--- END STRUCTURED_TABLE ---`,
    });
  }

  // Always load backend data when jurisdictionId is available — this is our primary source
  if (jurisdictionId) {
    const backendData = await getZoningRulesForCity(jurisdictionId);
    if (backendData) {
      const compareNote = checkBackend
        ? "\n\nThe user wants you to compare this against the ordinance source provided and flag any discrepancies. Generate a CORRECTION REPORT if any values are wrong."
        : "\n\nUse this data to answer questions directly. Only ask for an ordinance URL if the user wants to verify or correct specific entries.";
      extraBlocks.push({
        type: "text",
        text: `\n\n--- CURRENT SITE SCOUT DATABASE FOR THIS CITY ---\n${JSON.stringify(backendData, null, 2)}${compareNote}\n--- END DATABASE ---`,
      });
    }
  }

  // Build Anthropic messages array
  // Clone prior messages, then append extra context to last user message
  const claudeMessages: Anthropic.MessageParam[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const isLast = i === messages.length - 1;

    if (isLast && msg.role === "user") {
      // Build rich content for the final user message
      const contentBlocks: Anthropic.ContentBlockParam[] = [];

      // Main user text
      if (msg.content) {
        contentBlocks.push({ type: "text", text: msg.content });
      }

      // Append extra context blocks
      contentBlocks.push(...extraBlocks);

      // Attach images
      if (images && images.length > 0) {
        for (const img of images) {
          const mediaType = img.mediaType as
            | "image/jpeg"
            | "image/png"
            | "image/gif"
            | "image/webp";
          contentBlocks.push({
            type: "image",
            source: {
              type: "base64",
              media_type: mediaType,
              data: img.base64,
            },
          });
        }
      }

      claudeMessages.push({ role: "user", content: contentBlocks });
    } else {
      claudeMessages.push({
        role: msg.role,
        content: msg.content,
      });
    }
  }

  // Non-streaming response (reliable on Vercel Hobby; Haiku responds in <3s)
  const anthropic = new Anthropic({ apiKey });

  try {
    const message = await anthropic.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 2048,
      system: SYSTEM_PROMPT,
      messages: claudeMessages,
    });

    const text = message.content
      .filter((b): b is Anthropic.TextBlock => b.type === "text")
      .map((b) => b.text)
      .join("");

    return NextResponse.json({ text });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
