/**
 * Zoning Verifier Chat — streaming API route.
 * Handles URL fetch, pasted text, and image (vision) inputs.
 * Server-side only — ANTHROPIC_API_KEY never reaches the browser.
 *
 * POST /api/zoning-chat
 */
import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { sameOriginOnly } from "@/lib/api-guard";

export const runtime = "edge";
export const maxDuration = 60;

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

ACTION FIELD RULES — this is critical:
- The "action" field MUST be exactly one of these three strings: "UPDATE", "ADD", or "DELETE". Nothing else.
- NEVER write "UPDATE_METADATA", "VERIFY", "VERIFY — no change needed", or any other variation.
- When values already match and you are only confirming/verifying: use "UPDATE" with the confirmed correct_value.
- There is no "VERIFY" action. Verification is always expressed as "UPDATE".

CRITICAL — NEVER generate an empty corrections array []. When ordinance text has been provided and verified:
- Even if all DB values already match the ordinance, ALWAYS generate one UPDATE entry per use (self_storage, mini_warehouse, light_industrial, luxury_garage_condo) for every zone that was verified.
- This records the human verification in the database (classification_source → "human", human_reviewed → true).
- An empty [] array means the user cannot click "Apply Correction" to mark the zone as verified. Always give them something to apply.

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

FORMAT B IS THE MOST COMMON FORMAT. Most cities write one chapter per zone with "Permitted Uses:" and "Conditional Uses:" lists. There is no table. This is normal. Work with it directly.

NEVER ask the user for a "table of uses" or tell them to find a different section. If a per-zone chapter is provided, that IS the source — extract from it immediately.

For Format B extraction:
- "Permitted Uses:" section → everything listed = permitted
- "Conditional Uses:" section → everything listed = conditional
- Anything not in either list = prohibited (silence = prohibited)
- Search for: self-storage, mini-storage, storage facility, warehousing, personal storage, garage condominium, luxury garage, vehicle storage, light manufacturing, industrial
- If the chapter says "No other permitted uses are allowed" or similar closed-list language, that confirms silence = prohibited

NEVER ask for more information when ordinance text is present. Read what was given and produce the analysis.

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
  const blocked = sameOriginOnly(req);
  if (blocked) return blocked;
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

  // Fetch URL server-side if provided and no pasted text already present
  let resolvedText = pastedText;
  if (ordinanceUrl && !pastedText?.trim()) {
    try {
      resolvedText = await fetchOrdinanceUrl(ordinanceUrl);
    } catch (err) {
      extraBlocks.push({
        type: "text",
        text: `\n\n[Could not fetch ${ordinanceUrl}: ${err instanceof Error ? err.message : String(err)}. Ask the user to paste the ordinance text directly.]`,
      });
    }
  }

  // Add fetched or pasted ordinance text
  if (resolvedText?.trim()) {
    extraBlocks.push({
      type: "text",
      text: `\n\n--- ORDINANCE TEXT (source: ${ordinanceUrl ?? "pasted"}) ---\n${resolvedText.slice(0, 150_000)}\n--- END ORDINANCE TEXT ---`,
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

  const anthropic = new Anthropic({ apiKey });

  try {
    const stream = anthropic.messages.stream({
      model: "claude-opus-4-7",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      messages: claudeMessages,
    });

    const encoder = new TextEncoder();
    const readable = new ReadableStream({
      async start(controller) {
        try {
          for await (const chunk of stream) {
            if (
              chunk.type === "content_block_delta" &&
              chunk.delta.type === "text_delta"
            ) {
              controller.enqueue(encoder.encode(chunk.delta.text));
            }
          }
        } finally {
          controller.close();
        }
      },
    });

    return new Response(readable, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
