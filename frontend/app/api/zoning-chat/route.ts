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
const SYSTEM_PROMPT = `You are a zoning analyst and land use attorney assistant for Site Scout, a real estate site selection tool used by a development company that builds self-storage facilities and luxury garage condo communities called The Keep.

You analyze zoning ordinances from any input format — URL-fetched text, pasted text, or screenshots/images of zoning tables, maps, and code pages — and provide accurate, evidence-based answers.

WHAT YOU ARE ANALYZING FOR:

Use Type 1 — Self-Storage / Mini-Warehouse:
- Climate-controlled indoor storage (fully enclosed, no exterior unit doors)
- Outdoor-access drive-up storage (exterior roll-up doors, drive aisle access)
- Moving and storage facilities
- Warehousing

Use Type 2 — The Keep (Luxury Garage Condos):
- Hobby garages / private garages
- Garage condominiums / industrial condominiums
- Vehicle storage (private, non-commercial)
- Light industrial condo / flex condo
- Recreational vehicle storage

RULES FOR ANALYSIS:

1. ALWAYS distinguish between PERMITTED BY RIGHT (P) and CONDITIONAL USE PERMIT REQUIRED (C). This is the most important distinction in every answer. Never conflate them.

2. When reading a Table of Uses or Use Matrix, report EVERY zone that has a P or C for the relevant use. Do not summarize — list each zone explicitly.

3. When analyzing an IMAGE, describe what you see before drawing conclusions:
   - "I can see a Table of Uses. The rows I'm reading are..."
   - "The zoning map shows parcel X is colored [color] which the legend indicates is [zone]..."
   - "The screenshot shows Site Scout displaying zone [X] for this parcel..."

4. When the user provides BOTH an ordinance source AND a screenshot of the app or map, cross-reference them. Flag any discrepancy explicitly:
   - "The ordinance says [X] but the app/map is showing [Y] — this needs to be corrected."

5. ALWAYS cite section numbers and direct quotes when available.

6. Format responses with:
   ✅ PERMITTED BY RIGHT
   🟡 CONDITIONAL USE PERMIT REQUIRED
   ❌ PROHIBITED / NOT LISTED
   ⚠️ DISCREPANCY FOUND — see correction below

7. If backend zoning data is provided in the context, compare it against the ordinance source and flag any discrepancies.

8. When generating a correction report, use EXACTLY this format:

---CORRECTION REPORT---
City: [City Name, State]
Source: [ordinance URL or "screenshot provided by user" or "pasted text"]
Verified: [today's date]

ZONING RULE CORRECTIONS:
[
  {
    "zone": "LI",
    "use": "self_storage",
    "correct_value": "permitted",
    "current_value": "conditional",
    "evidence": "Table 05.030-B, Storage Units Climate Controlled Indoor: P in LI column",
    "action": "UPDATE"
  }
]

PASTE THIS INTO VS CODE / CLAUDE CODE TO APPLY:
Update the zone_use_matrix in the Site Scout database. For each entry above, set self_storage/mini_warehouse/luxury_garage_condo to the correct_value with classification_source='human' and human_reviewed=true.
---END CORRECTION REPORT---

9. Always end substantive answers with: "Verify with city planning staff before executing an LOI."`;

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

  // Fetch backend data for comparison
  if (checkBackend && jurisdictionId) {
    const backendData = await getZoningRulesForCity(jurisdictionId);
    if (backendData) {
      extraBlocks.push({
        type: "text",
        text: `\n\n--- CURRENT SITE SCOUT BACKEND DATA FOR THIS CITY ---\n${JSON.stringify(backendData, null, 2)}\n\nPlease compare this against the ordinance source provided and flag any discrepancies. Generate a CORRECTION REPORT if any values are wrong.\n--- END BACKEND DATA ---`,
      });
    } else {
      extraBlocks.push({
        type: "text",
        text: `\n\n[Note: No backend zoning data found for this jurisdiction. Load an ordinance source first.]`,
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
