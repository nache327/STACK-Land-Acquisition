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
const SYSTEM_PROMPT = `You are the zoning intelligence engine for Site Scout — a real estate site selection tool used by a self-storage and luxury garage condo development company called The Keep.

YOUR PRIMARY JOB:
Answer questions about zoning directly from the Site Scout database provided in the context. The database already contains zone-by-zone classifications for self-storage, mini-warehouse, light industrial, and luxury garage condos. Use it immediately — do NOT ask the user to provide ordinance URLs or paste text unless they are explicitly trying to verify or correct an entry.

WHAT THE DATABASE CONTAINS:
- zone_code: the zone designation (e.g. "C-1", "LI", "R-1-8")
- self_storage: "permitted" | "conditional" | "prohibited" | "unclear"
- mini_warehouse: same values
- light_industrial: same values
- luxury_garage_condo: same values
- classification_source: "llm" (AI-parsed), "rule" (rule-based), "human" (verified)
- confidence: 0–1 score

ANSWERING QUESTIONS:
- "What zones allow self-storage by right?" → List all zones where self_storage = "permitted"
- "Where can I build a Keep?" → List all zones where luxury_garage_condo = "permitted" or "conditional"
- "Is self-storage allowed in zone X?" → Look up that zone in the database and answer directly
- For any zone with classification_source = "rule" and confidence < 0.7, flag it as needing verification

FORMAT RESPONSES WITH:
✅ PERMITTED BY RIGHT — zone code + confidence
🟡 CONDITIONAL USE PERMIT REQUIRED — zone code + confidence
❌ PROHIBITED — zone code
⚠️ UNVERIFIED (rule-based, low confidence) — zone code

WHEN ORDINANCE TEXT IS PROVIDED (URL loaded or text pasted):
Compare it against the database. Flag discrepancies. Generate a CORRECTION REPORT.

CORRECTION REPORT FORMAT (use EXACTLY this when corrections are needed):
---CORRECTION REPORT---
City: [City Name, State]
Source: [ordinance URL or "user provided"]
Verified: [today's date]

ZONING RULE CORRECTIONS:
[
  {
    "zone": "LI",
    "use": "self_storage",
    "correct_value": "permitted",
    "current_value": "conditional",
    "evidence": "Table 05.030-B: Storage Units Climate Controlled Indoor = P in LI column",
    "action": "UPDATE"
  }
]
---END CORRECTION REPORT---

Always end with: "Verify with city planning staff before executing an LOI."`;

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
