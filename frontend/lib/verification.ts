/**
 * Three-Layer Zoning Verification Engine — types, scoring, and localStorage cache.
 *
 * Layer 1: Zoneomics API   (volume filter — PLU tag matching)
 * Layer 2: City GIS match  (Zoneomics zone code vs. our DB zone code from city GIS)
 * Layer 3: Ordinance text  (on-demand AI analysis — only runs on explicit user request)
 */

// ── Use targets ───────────────────────────────────────────────────────────────

export const STORAGE_PLU_TAGS = new Set([
  "mini-warehouse",
  "self-storage",
  "warehouse",
  "light-industrial",
  "storage-facility",
  "flex-industrial",
]);

export const KEEP_PLU_TAGS = new Set([
  "condominium",
  "industrial-condo",
  "business-park",
  "light-industrial",
  "mixed-use-industrial",
  "garage",
  "commercial",
]);

export const STORAGE_KEYWORDS = ["storage", "warehouse", "industrial", "condo"];
export const INDUSTRIAL_ZONE_PATTERNS = /^(M-?\d|LI|LM|HI|HM|ML|IND|MFG|MAN|BP|I-?\d)/i;

// ── Layer types ───────────────────────────────────────────────────────────────

export type PermitType = "permitted-by-right" | "conditional" | "prohibited" | null;
export type MatchType = "exact" | "probable" | "conflict" | "unavailable";
export type Layer3Status =
  | "PERMITTED_BY_RIGHT"
  | "CUP_REQUIRED"
  | "PROHIBITED"
  | "NOT_MENTIONED";
export type AiConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface Layer1Result {
  status: "complete" | "error" | "no-coverage" | "pending";
  zoneCode: string;
  zoneDescription: string;
  pluTags: string[];
  pluMatch: boolean;
  matchedTags: string[];
  permitType: PermitType;
  score: number;
  rawResponse?: unknown;
  fetchedAt: number;
}

export interface Layer2Result {
  status: "complete" | "unavailable";
  cityZoneCode: string | null;
  zoneomicsZoneCode: string | null;
  matchType: MatchType;
  dataSource: string;
  overlayConflict: boolean;
  score: number;
  note?: string;
}

export interface Layer3Result {
  status: "complete" | "not-run" | "error" | "ordinance-not-found";
  ordinanceUrl: string | null;
  selfStorageStatus: Layer3Status | null;
  keepStatus: Layer3Status | null;
  evidence: string | null;
  aiConfidence: AiConfidence | null;
  notes: string | null;
  classificationSource: "llm" | "rule" | "human" | "unclear" | null;
  score: number;
  fetchedAt?: number;
}

export type OverallStatus =
  | "VERIFIED"
  | "PROBABLE"
  | "UNCERTAIN"
  | "WEAK"
  | "CONFLICT"
  | "PROHIBITED"
  | "UNVERIFIED";

export interface VerificationState {
  layer1: Layer1Result | null;
  layer2: Layer2Result | null;
  layer3: Layer3Result;
  compositeScore: number;
  overallStatus: OverallStatus;
  conflictFlags: string[];
  lastUpdated: number;
}

// ── Score / status calculation ────────────────────────────────────────────────

export function computeComposite(
  layer1: Layer1Result | null,
  layer2: Layer2Result | null,
  layer3: Layer3Result
): Pick<VerificationState, "compositeScore" | "overallStatus" | "conflictFlags"> {
  const flags: string[] = [];

  // Hard overrides — these always win
  if (layer3.selfStorageStatus === "PROHIBITED") {
    return { compositeScore: 0, overallStatus: "PROHIBITED", conflictFlags: ["Layer 3: ordinance explicitly prohibits this use"] };
  }
  if (layer2?.matchType === "conflict") {
    flags.push("⚠ Zoneomics and city GIS disagree — do not pursue without manual verification");
    return { compositeScore: 0, overallStatus: "CONFLICT", conflictFlags: flags };
  }

  let score = 0;

  // Layer 1 contribution
  if (layer1) {
    score += layer1.score;
    if (layer1.permitType === "prohibited") {
      return { compositeScore: 0, overallStatus: "PROHIBITED", conflictFlags: ["Layer 1: Zoneomics reports use is prohibited"] };
    }
  }

  // Layer 2 contribution
  if (layer2) score += layer2.score;

  // Layer 3 contribution
  score += layer3.score;
  if (layer3.selfStorageStatus === "CUP_REQUIRED") {
    flags.push("Conditional Use Permit required — never shown as fully permitted");
  }

  // Caps and floors
  const layersChecked = [layer1, layer2, layer3.status !== "not-run" ? layer3 : null].filter(Boolean).length;
  if (layersChecked < 2) score = Math.min(score, 65); // can't reach VERIFIED with only 1 layer

  // Status thresholds
  let status: OverallStatus;
  if (score >= 85) status = "VERIFIED";
  else if (score >= 65) status = "PROBABLE";
  else if (score >= 40) status = "UNCERTAIN";
  else if (score >= 1) status = "WEAK";
  else status = "UNVERIFIED";

  // CUP always shows YELLOW even if score is high
  if (layer3.selfStorageStatus === "CUP_REQUIRED" && status === "VERIFIED") {
    status = "PROBABLE";
  }

  return { compositeScore: score, overallStatus: status, conflictFlags: flags };
}

// ── Layer 1 helpers ───────────────────────────────────────────────────────────

export function scoreLayer1(
  pluTags: string[],
  zoneDescription: string,
  zoneCode: string,
  permitType: PermitType
): { score: number; pluMatch: boolean; matchedTags: string[] } {
  if (permitType === "prohibited") return { score: 0, pluMatch: false, matchedTags: [] };

  const matchedTags = pluTags.filter((t) => STORAGE_PLU_TAGS.has(t.toLowerCase()));
  let score = 0;

  if (matchedTags.length > 0) {
    score += permitType === "conditional" ? 25 : 35;
  }
  if (STORAGE_KEYWORDS.some((kw) => zoneDescription.toLowerCase().includes(kw))) {
    score += 20;
  }
  if (INDUSTRIAL_ZONE_PATTERNS.test(zoneCode)) {
    score += 10;
  }

  return { score, pluMatch: matchedTags.length > 0, matchedTags };
}

// ── Layer 2 helpers ───────────────────────────────────────────────────────────

export function computeLayer2(
  cityZoneCode: string | null,
  zoneomicsZoneCode: string | null
): Layer2Result {
  if (!cityZoneCode || !zoneomicsZoneCode) {
    return {
      status: "unavailable",
      cityZoneCode,
      zoneomicsZoneCode,
      matchType: "unavailable",
      dataSource: "Site Scout DB (from city ArcGIS)",
      overlayConflict: false,
      score: 0,
    };
  }

  const normalize = (s: string) => s.replace(/[\s\-_]/g, "").toLowerCase();
  const a = normalize(cityZoneCode);
  const b = normalize(zoneomicsZoneCode);

  if (a === b) {
    return {
      status: "complete",
      cityZoneCode,
      zoneomicsZoneCode,
      matchType: "exact",
      dataSource: "Site Scout DB (from city ArcGIS)",
      overlayConflict: false,
      score: 35,
      note: "Zone codes match exactly",
    };
  }

  // Probable match — same zone type family
  const zoneFamily = (s: string) => {
    const u = s.toUpperCase();
    if (/^I|^M-|^LI|^LM|^HI|^HM|^IND|^MFG|^BP/.test(u)) return "industrial";
    if (/^C-|^B-|^GC|^HC|^NC|^SC|^CC/.test(u)) return "commercial";
    if (/^R-|^RS|^RM|^RMF|^SF|^MH/.test(u)) return "residential";
    if (/^A-|^AG/.test(u)) return "agricultural";
    if (/^MU|^MXD/.test(u)) return "mixed";
    return "unknown";
  };

  const familyA = zoneFamily(cityZoneCode);
  const familyB = zoneFamily(zoneomicsZoneCode);

  if (familyA !== "unknown" && familyA === familyB) {
    return {
      status: "complete",
      cityZoneCode,
      zoneomicsZoneCode,
      matchType: "probable",
      dataSource: "Site Scout DB (from city ArcGIS)",
      overlayConflict: false,
      score: 20,
      note: `Zone codes differ but both appear to be ${familyA} — types consistent`,
    };
  }

  // Conflict
  return {
    status: "complete",
    cityZoneCode,
    zoneomicsZoneCode,
    matchType: "conflict",
    dataSource: "Site Scout DB (from city ArcGIS)",
    overlayConflict: false,
    score: 0,
    note: `City GIS says "${cityZoneCode}" but Zoneomics says "${zoneomicsZoneCode}" — zone types disagree`,
  };
}

// ── Layer 3 from zone_use_matrix data ─────────────────────────────────────────

export function layer3FromZoneRow(row: {
  self_storage: string;
  luxury_garage_condo: string;
  confidence: number | null;
  citations: Array<{ section: string; quote: string }> | null;
  notes: string | null;
  classification_source: string;
}): Layer3Result {
  const permToStatus = (p: string): Layer3Status => {
    if (p === "permitted") return "PERMITTED_BY_RIGHT";
    if (p === "conditional") return "CUP_REQUIRED";
    if (p === "prohibited") return "PROHIBITED";
    return "NOT_MENTIONED";
  };

  const ssStatus = permToStatus(row.self_storage);
  const keepStatus = permToStatus(row.luxury_garage_condo);

  let score = 0;
  const conf = row.confidence ?? 0;
  const aiConf: AiConfidence = conf >= 0.85 ? "HIGH" : conf >= 0.65 ? "MEDIUM" : "LOW";

  if (row.classification_source === "llm" || row.classification_source === "human") {
    if (ssStatus === "PERMITTED_BY_RIGHT") score = aiConf === "HIGH" ? 30 : 20;
    else if (ssStatus === "CUP_REQUIRED") score = 10;
    else if (ssStatus === "NOT_MENTIONED") score = 5;
  }

  const firstCitation = row.citations?.[0];
  const evidence = firstCitation
    ? `§${firstCitation.section}: "${firstCitation.quote}"`
    : null;

  return {
    status: "complete",
    ordinanceUrl: null, // filled in by caller
    selfStorageStatus: ssStatus,
    keepStatus,
    evidence,
    aiConfidence: row.classification_source === "llm" ? aiConf : null,
    notes: row.notes,
    classificationSource: row.classification_source as Layer3Result["classificationSource"],
    score,
    fetchedAt: Date.now(),
  };
}

// ── localStorage cache (30-day TTL) ──────────────────────────────────────────

const CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const cacheKey = (apn: string, zoneCode: string) =>
  `verify:${apn}:${zoneCode}`;

export function readCache(apn: string, zoneCode: string): VerificationState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(cacheKey(apn, zoneCode));
    if (!raw) return null;
    const state: VerificationState = JSON.parse(raw);
    if (Date.now() - state.lastUpdated > CACHE_TTL_MS) {
      localStorage.removeItem(cacheKey(apn, zoneCode));
      return null;
    }
    return state;
  } catch {
    return null;
  }
}

export function writeCache(apn: string, zoneCode: string, state: VerificationState) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(cacheKey(apn, zoneCode), JSON.stringify(state));
  } catch {
    // Ignore quota errors
  }
}

export function clearCache(apn: string, zoneCode: string) {
  if (typeof window === "undefined") return;
  localStorage.removeItem(cacheKey(apn, zoneCode));
}

// ── Status display helpers ────────────────────────────────────────────────────

export const STATUS_CONFIG: Record<
  OverallStatus,
  { label: string; color: string; bg: string; border: string; dot: string }
> = {
  VERIFIED:    { label: "High Confidence — Pursue",            color: "text-emerald-800", bg: "bg-emerald-50",  border: "border-emerald-300", dot: "bg-emerald-500" },
  PROBABLE:    { label: "Likely Viable — Verify Ordinance",    color: "text-lime-800",    bg: "bg-lime-50",     border: "border-lime-300",    dot: "bg-lime-500"    },
  UNCERTAIN:   { label: "Needs Verification",                   color: "text-amber-800",   bg: "bg-amber-50",    border: "border-amber-300",   dot: "bg-amber-500"   },
  WEAK:        { label: "Low Confidence — Not Recommended",    color: "text-orange-800",  bg: "bg-orange-50",   border: "border-orange-300",  dot: "bg-orange-500"  },
  CONFLICT:    { label: "⚠ Data Conflict — Do Not Pursue",     color: "text-red-800",     bg: "bg-red-50",      border: "border-red-300",     dot: "bg-red-500"     },
  PROHIBITED:  { label: "✗ Prohibited Use",                    color: "text-red-900",     bg: "bg-red-100",     border: "border-red-400",     dot: "bg-red-700"     },
  UNVERIFIED:  { label: "No Data — Manual Research Required",  color: "text-slate-600",   bg: "bg-slate-50",    border: "border-slate-200",   dot: "bg-slate-400"   },
};
