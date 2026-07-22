/**
 * Three-Layer Zoning Verification Engine — types, scoring, and localStorage cache.
 *
 * Layer 1: Our zone_use_matrix DB  (auto — immediate, no external API cost)
 * Layer 2: Zone code integrity check (computation only)
 * Layer 3: Ordinance text AI        (on-demand — only runs when user requests it)
 */

// ── Layer types ───────────────────────────────────────────────────────────────

export type UseStatus = "permitted" | "conditional" | "prohibited" | "unclear";
export type PermitType = "permitted-by-right" | "conditional" | "incompatible" | null;
export type MatchType = "exact" | "probable" | "conflict" | "unavailable";
export type Layer3Status =
  | "PERMITTED_BY_RIGHT"
  | "CUP_REQUIRED"
  | "PROHIBITED"
  | "NOT_MENTIONED";
export type AiConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface Layer1Result {
  status: "complete" | "error" | "no-coverage" | "pending";
  // Zone identity
  zoneCode: string;
  zoneName: string;
  // Per-use classifications from zone_use_matrix
  selfStorageStatus: UseStatus;
  miniWarehouseStatus: UseStatus;
  lightIndustrialStatus: UseStatus;
  luxuryGarageStatus: UseStatus;
  // Data quality. classificationSource is the raw zone_use_matrix enum — one
  // of ~10 values (llm, rule, human, unclear, llm_rule, op5_factory,
  // crosswalk, llm_low_confidence, inherited_pending, …). Kept as a string so
  // grounded sources aren't collapsed to "unclear" and penalized.
  classificationSource: string;
  confidence: number | null;
  humanReviewed: boolean;
  // True when the verdict is trusted: human-reviewed OR a grounded source with
  // sufficient confidence. Drives the L1 multiplier and auto-VERIFIED path.
  grounded: boolean;
  notes: string | null;
  // Derived for composite scoring
  permitType: PermitType;
  score: number;
  fetchedAt: number;
}

// Grounded classification sources — keep in lock-step with
// GROUNDED_SOURCES in backend/app/services/verdict_gate.py.
export const GROUNDED_SOURCES = ["human", "llm", "llm_rule", "op5_factory"];
const LEAD_CONFIDENCE_FLOOR = 0.5;

/** Whether a verdict is trusted enough to score at full weight / auto-verify. */
export function isGrounded(params: {
  classificationSource: string;
  confidence: number | null;
  humanReviewed: boolean;
}): boolean {
  if (params.humanReviewed) return true;
  return (
    GROUNDED_SOURCES.includes(params.classificationSource) &&
    (params.confidence ?? 0) >= LEAD_CONFIDENCE_FLOOR
  );
}

export interface Layer2Result {
  status: "complete" | "unavailable";
  cityZoneCode: string | null;
  dbZoneCode: string | null;
  matchType: MatchType;
  dataSource: string;
  overlayConflict: boolean;
  score: number;
  note?: string;
}

export interface Layer3Result {
  status: "complete" | "not-run" | "error" | "ordinance-not-found";
  ordinanceUrl: string | null;
  ordinanceSource: "discovered" | null;
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

// ── Layer 1 scoring (our DB) ──────────────────────────────────────────────────

export function scoreLayer1DB(params: {
  selfStorageStatus: UseStatus;
  classificationSource: string;
  confidence: number | null;
  humanReviewed: boolean;
}): { score: number; permitType: PermitType; grounded: boolean } {
  const { selfStorageStatus, classificationSource, confidence, humanReviewed } = params;

  if (selfStorageStatus === "prohibited") {
    return { score: 0, permitType: "incompatible", grounded: false };
  }
  if (selfStorageStatus === "unclear") {
    return { score: 0, permitType: null, grounded: false };
  }

  const conf = confidence ?? 0.7;
  let base = 0;
  let permitType: PermitType = null;

  if (selfStorageStatus === "permitted") {
    base = 35;
    permitType = "permitted-by-right";
  } else if (selfStorageStatus === "conditional") {
    base = 15;
    permitType = "conditional";
  }

  // A human-reviewed OR grounded verdict scores at full weight — it is exactly
  // as trustworthy as a row whose source literal happens to be "human". This
  // is the fix for grounded needles (op5_factory / llm_rule) previously hit
  // with the 0.25 "Unknown Source" multiplier.
  const grounded = isGrounded({ classificationSource, confidence, humanReviewed });
  const multiplier = grounded
    ? 1.0
    : classificationSource === "llm" ? Math.min(conf + 0.1, 1.0)
    : classificationSource === "rule" ? 0.45
    : 0.25;

  return { score: Math.round(base * multiplier), permitType, grounded };
}

// ── Composite score / status ──────────────────────────────────────────────────

export function computeComposite(
  layer1: Layer1Result | null,
  layer2: Layer2Result | null,
  layer3: Layer3Result
): Pick<VerificationState, "compositeScore" | "overallStatus" | "conflictFlags"> {
  const flags: string[] = [];

  // Hard overrides — always win
  if (layer3.selfStorageStatus === "PROHIBITED") {
    return {
      compositeScore: 0,
      overallStatus: "PROHIBITED",
      conflictFlags: ["Layer 3: ordinance explicitly prohibits this use"],
    };
  }
  if (layer2?.matchType === "conflict") {
    flags.push("⚠ Zone code mismatch — do not pursue without manual verification");
    return { compositeScore: 0, overallStatus: "CONFLICT", conflictFlags: flags };
  }

  if (layer1?.permitType === "incompatible") {
    return {
      compositeScore: 0,
      overallStatus: "PROHIBITED",
      conflictFlags: ["Layer 1: zone classified as prohibited for storage uses"],
    };
  }

  let score = 0;
  if (layer1) score += layer1.score;
  if (layer2) score += layer2.score;
  score += layer3.score;

  if (layer3.selfStorageStatus === "CUP_REQUIRED") {
    flags.push("Conditional Use Permit required — never shown as fully permitted");
  }

  if (layer1?.classificationSource === "rule") {
    flags.push("⚠ Rule-based classification — click 'Verify Now' for AI ordinance analysis");
  }

  const layersChecked = [
    layer1,
    layer2,
    layer3.status !== "not-run" ? layer3 : null,
  ].filter(Boolean).length;
  if (layersChecked < 2) score = Math.min(score, 65);

  // Auto-VERIFIED: a grounded verdict (human-reviewed or grounded source)
  // whose zone code matches our DB (Layer 2 exact) is trustworthy without
  // waiting for a manual Layer-3 AI pass. Without this, thousands of
  // already-grounded needles read "Needs Verification" forever. The CUP
  // demotion below still applies to conditional verdicts.
  if (layer1?.grounded && layer2?.matchType === "exact") {
    score = Math.max(score, 85);
  }

  let status: OverallStatus;
  if (score >= 85) status = "VERIFIED";
  else if (score >= 65) status = "PROBABLE";
  else if (score >= 40) status = "UNCERTAIN";
  else if (score >= 1) status = "WEAK";
  else status = "UNVERIFIED";

  // A conditional/CUP use is never "fully permitted" — cap it at PROBABLE
  // even when grounded, since it still needs a permit hearing.
  const isConditional =
    layer3.selfStorageStatus === "CUP_REQUIRED" ||
    layer1?.permitType === "conditional";
  if (isConditional && status === "VERIFIED") {
    status = "PROBABLE";
  }

  return { compositeScore: score, overallStatus: status, conflictFlags: flags };
}

// ── Layer 2 — zone code integrity check ──────────────────────────────────────

export function computeLayer2(
  cityZoneCode: string | null,
  dbZoneCode: string | null
): Layer2Result {
  if (!cityZoneCode || !dbZoneCode) {
    return {
      status: "unavailable",
      cityZoneCode,
      dbZoneCode,
      matchType: "unavailable",
      dataSource: "Site Scout DB (from city ArcGIS)",
      overlayConflict: false,
      score: 0,
    };
  }

  const normalize = (s: string) => s.replace(/[\s\-_]/g, "").toLowerCase();
  if (normalize(cityZoneCode) === normalize(dbZoneCode)) {
    return {
      status: "complete",
      cityZoneCode,
      dbZoneCode,
      matchType: "exact",
      dataSource: "Site Scout DB (from city ArcGIS)",
      overlayConflict: false,
      score: 35,
      note: "Zone code confirmed in database",
    };
  }

  return {
    status: "complete",
    cityZoneCode,
    dbZoneCode,
    matchType: "conflict",
    dataSource: "Site Scout DB (from city ArcGIS)",
    overlayConflict: false,
    score: 0,
    note: `Parcel zone code "${cityZoneCode}" differs from DB record "${dbZoneCode}"`,
  };
}

// ── Layer 3 from zone_use_matrix data ─────────────────────────────────────────

export function layer3FromZoneRow(
  row: {
    self_storage: string;
    luxury_garage_condo: string;
    confidence: number | null;
    citations: Array<{ section: string; quote: string }> | null;
    notes: string | null;
    classification_source: string;
  },
  ordinanceUrl?: string | null,
  ordinanceSource?: Layer3Result["ordinanceSource"]
): Layer3Result {
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
    ordinanceUrl: ordinanceUrl ?? null,
    ordinanceSource: ordinanceSource ?? null,
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
// v2: grounded scoring + auto-VERIFIED landed; retire cached v1 (44/100) states.
const cacheKey = (apn: string, zoneCode: string) => `verify2:${apn}:${zoneCode}`;

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
  VERIFIED:   { label: "High Confidence — Pursue",           color: "text-emerald-800", bg: "bg-emerald-50", border: "border-emerald-300", dot: "bg-emerald-500" },
  PROBABLE:   { label: "Likely Viable — Verify Ordinance",   color: "text-lime-800",    bg: "bg-lime-50",    border: "border-lime-300",    dot: "bg-lime-500"    },
  UNCERTAIN:  { label: "Needs Verification",                  color: "text-amber-800",   bg: "bg-amber-50",   border: "border-amber-300",   dot: "bg-amber-500"   },
  WEAK:       { label: "Low Confidence — Not Recommended",   color: "text-orange-800",  bg: "bg-orange-50",  border: "border-orange-300",  dot: "bg-orange-500"  },
  CONFLICT:   { label: "⚠ Data Conflict — Do Not Pursue",    color: "text-red-800",     bg: "bg-red-50",     border: "border-red-300",     dot: "bg-red-500"     },
  PROHIBITED: { label: "✗ Prohibited Use",                   color: "text-red-900",     bg: "bg-red-100",    border: "border-red-400",     dot: "bg-red-700"     },
  UNVERIFIED: { label: "No Data — Manual Research Required", color: "text-slate-600",   bg: "bg-slate-50",   border: "border-slate-200",   dot: "bg-slate-400"   },
};

type SourceStyle = { label: string; color: string; bg: string };

export const SOURCE_CONFIG: Record<string, SourceStyle> = {
  human:              { label: "Human Verified",    color: "text-emerald-700", bg: "bg-emerald-50"  },
  llm:                { label: "AI Parsed",         color: "text-blue-700",    bg: "bg-blue-50"     },
  llm_rule:           { label: "AI + Rule",         color: "text-blue-700",    bg: "bg-blue-50"     },
  op5_factory:        { label: "Ordinance-Parsed",  color: "text-blue-700",    bg: "bg-blue-50"     },
  op5_factory_catchall: { label: "Ordinance-Parsed", color: "text-blue-700",   bg: "bg-blue-50"     },
  crosswalk:          { label: "Crosswalk",         color: "text-sky-700",     bg: "bg-sky-50"      },
  rule:               { label: "Rule-Based",        color: "text-amber-700",   bg: "bg-amber-50"    },
  llm_low_confidence: { label: "AI (low conf.)",    color: "text-amber-700",   bg: "bg-amber-50"    },
  inherited_pending:  { label: "Inherited (pending)", color: "text-slate-500", bg: "bg-slate-50"    },
  unclear:            { label: "Unknown Source",    color: "text-slate-500",   bg: "bg-slate-50"    },
};

const _UNKNOWN_SOURCE: SourceStyle = SOURCE_CONFIG.unclear;

/** Look up a source's display style, falling back to "Unknown Source". */
export function sourceStyle(source: string | null | undefined): SourceStyle {
  return (source && SOURCE_CONFIG[source]) || _UNKNOWN_SOURCE;
}

export const USE_STATUS_CONFIG: Record<
  UseStatus,
  { label: string; color: string; bg: string }
> = {
  permitted:   { label: "Permitted",   color: "text-emerald-700", bg: "bg-emerald-100" },
  conditional: { label: "CUP Req.",    color: "text-amber-700",   bg: "bg-amber-100"   },
  prohibited:  { label: "Prohibited",  color: "text-red-700",     bg: "bg-red-100"     },
  unclear:     { label: "Unclear",     color: "text-slate-500",   bg: "bg-slate-100"   },
};
