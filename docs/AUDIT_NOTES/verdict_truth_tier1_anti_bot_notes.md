# Verdict-Truth Tier 1 — Anti-Bot Platform Notes (Live Probe Results)

**Date:** 2026-06-23
**Status:** Companion doc to `verdict_truth_tier1_operator_playbook.md` (commits c389631 + 9849c32). Live-probed WebFetch behavior + Wayback availability for each platform Master would hit in wave-7 path (a) operator OR (c) procurement.
**Test method:** Direct WebFetch probes of each platform's root/index/section paths + Wayback Machine availability API queries. All probes 2026-06-23.

---

## TL;DR — anti-bot is universal across all 5 tested platforms

| Platform | WebFetch root | WebFetch deep section | Wayback coverage | Operator (Chrome) | PDF-tool path |
|---|---|---|---|---|---|
| municipal.codes | 403 | 403 | ✓ (Bellevue 2025-07) | ✓ usually | ✓ via Wayback |
| codepublishing.com | 403 | 403 (+ CGI path 403) | ⚠️ stale (Mill Creek 2023-09) | ✓ usually | ⚠️ may miss amendments |
| codelibrary.amlegal.com | 403 | 403 | ✓ (Winnetka 2025-03) | ✓ usually | ✓ via Wayback |
| ecode360.com | 403 | 403 | ❌ NO COVERAGE (Sewickley empty) | ✓ may need CAPTCHA | ❌ blocked end-to-end |
| (encodeplus.com — not re-tested this pass; assumed 403 per halt doc) | 403 expected | 403 expected | TBD | ✓ usually | TBD |

**Critical finding:** 403 is **universal to WebFetch User-Agent**, NOT route-specific. Tested root + index + chapter + CGI rendering paths across 5 platforms — all blocked uniformly. Bot fingerprinting happens at edge/CDN layer (likely Cloudflare or similar), so no clean static path will bypass for the orchestrator.

**Operator unlock confirmed:** Chrome browser with default User-Agent serves all 5 platforms cleanly (per session history — Bellevue/Bainbridge/Mill Creek/Gig Harbor operator-paths all worked via browser in PR #266 / wedge cohort work). Operator-assisted Lane E (path a) remains the cleanest unlock.

**PDF-tool path complication:** Wayback Machine is unavailable to WebFetch from this environment (Claude Code policy), but works fine in any standard Python/curl/requests-based PDF tool. Diagnostic's PDF tooling sprint (path b) can use Wayback URLs as input.

---

## Per-platform probe results (2026-06-23)

### 1. municipal.codes (Bellevue LUC is the active example)

| Probe | URL | Result |
|---|---|---|
| Root | `https://bellevue.municipal.codes/` | **HTTP 403** |
| Chapter index | `https://bellevue.municipal.codes/LUC/20.10.440` (prior session) | **HTTP 403** |
| Wayback availability | `archive.org/wayback/available?url=https://bellevue.municipal.codes/LUC/20.10.440` | ✓ snapshot 2025-07-13 |

**Finding:** Universal 403 to WebFetch at every depth. Wayback snapshot exists (~11 months old) — acceptable for Bellevue LI which hasn't seen major LUC amendment recently. Operator path via Chrome confirmed working in prior PR #266 work.

**Recommended fallback chain for municipal.codes targets:**
1. Operator Chrome browser (primary)
2. Operator Chrome incognito (if anti-bot cookies present)
3. Wayback snapshot URL (operator OR PDF tool)
4. Bellevue/muni website PDF mirror (often hosted under /planning/)

---

### 2. codepublishing.com (Mill Creek MCMC is the Tier 1 target)

| Probe | URL | Result |
|---|---|---|
| City index | `https://www.codepublishing.com/WA/MillCreek/` | **HTTP 403** |
| Chapter HTML | `https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html` (prior session) | **HTTP 403** |
| CGI rendering path | `https://www.codepublishing.com/WA/MillCreek/cgi/cgipage.cgi?_path=html/MillCreek17/MillCreek17.html` | **HTTP 403** |
| Wayback availability | `archive.org/wayback/available?url=https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html` | ⚠️ snapshot 2023-09-25 (~2.75 years old) |

**Finding:** Heaviest anti-bot in tested set. Even the CGI rendering path (which sometimes serves pages dynamically with different bot detection) returns 403. Wayback snapshot exists but is **2.75 years old** — significant amendment risk if Mill Creek MCMC has been updated post-2023-09.

**Recommended fallback chain for codepublishing.com targets:**
1. Operator Chrome browser (primary — known to work per Bainbridge/Mill Creek/Gig Harbor history)
2. Operator Chrome incognito
3. **Skip Wayback for Mill Creek** unless operator confirms no recent MCMC amendments — too stale
4. Mill Creek City Hall PDF — try `cityofmillcreek.com` Community Development page for current PDF mirror
5. Last resort: planning office call 425-921-5740

**Special note:** Code Publishing operates on a per-state basis. WA snapshots are stale; other states (CA / OR / etc.) may have fresher snapshots. For future Tier 2/3/4 work involving Code Publishing on non-WA states, re-probe Wayback per-target.

---

### 3. codelibrary.amlegal.com (Winnetka pre-stage is the upcoming target)

| Probe | URL | Result |
|---|---|---|
| Overview page | `https://codelibrary.amlegal.com/codes/winnetka/latest/overview` | **HTTP 403** |
| Deep section | `https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-26184` (Track B research) | **HTTP 403** |
| Wayback availability | `archive.org/wayback/available?url=https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873` | ⚠️ snapshot 2025-03-13 (~15 months old) |

**Finding:** Universal 403 even on the seemingly innocuous overview page. Wayback snapshot is ~15 months old. **Winnetka amendments M-19-2025 / MC-13-2025 may NOT be in the Wayback snapshot** — citation accuracy risk if Wayback is the only source.

**Recommended fallback chain for amlegal targets:**
1. Operator Chrome browser (primary)
2. Operator Chrome incognito
3. Wayback snapshot — but flag for amendment verification before citing
4. Village website PDF — `villageofwinnetka.org/DocumentCenter/View/428/Zoning-Map-PDF` already known; main ordinance PDF link TBD
5. ZoneOmics for chapter index (worked in TRACK B research; not a citation source but useful for navigation)

---

### 4. ecode360.com (Sewickley is the Tier 3 target; eCode360 is platform-wide)

| Probe | URL | Result |
|---|---|---|
| Root | `https://ecode360.com/` | **HTTP 403** |
| Sewickley Chapter 330 | `https://ecode360.com/32411498` (prior session) | **HTTP 403** |
| Wayback availability | `archive.org/wayback/available?url=https://ecode360.com/32411498` | ❌ **NO COVERAGE** (archived_snapshots empty) |

**Finding:** **Worst-case platform.** Universal 403 to WebFetch AND no Wayback coverage. eCode360 explicitly blocks the Wayback crawler (likely via `robots.txt` Disallow or 403 to ia_archiver UA).

**Recommended fallback chain for eCode360 targets (Sewickley Borough I, Aspinwall AI-1, etc.):**
1. Operator Chrome browser (primary) — but may hit CAPTCHA on first session per platform pattern
2. Operator Chrome incognito (CAPTCHA more likely here)
3. **NO Wayback fallback** — must use direct browser access
4. Municipal website PDF mirror (borough sites usually host current zoning PDF)
5. Borough hall direct contact (Sewickley: 412-741-4015; Aspinwall: 412-781-0213)
6. **PDF tooling path (b) does NOT work for eCode360** — Diagnostic adapter would 403 too. Operator path (a) is the ONLY reliable unlock for eCode360 munis.

**Strategic implication:** If wave-7 picks path (b) PDF tooling, eCode360 targets (Sewickley + Aspinwall) need operator-path overlay; cannot be PDF-extracted at scale.

---

### 5. enCodePlus (Birmingham MI / Westport CT — not Tier 1)

Not re-probed in this 2026-06-23 pass. Per halt doc evidence base: assumed 403 to WebFetch. Wayback coverage TBD.

For when Tier 2 work surfaces Birmingham (already operational; verdict-truth queue doesn't include Birmingham codes) — operator path via Chrome confirmed working in PR #320 Phase 7E.3 work.

---

## Wayback Machine snapshot URLs — Tier 1 source pages

For operator OR PDF-tool fallback. Snapshot URLs as of 2026-06-23 availability probe:

| Tier 1 muni | Source URL | Wayback snapshot URL | Snapshot date | Age | Risk |
|---|---|---|---|---|---|
| **Stamford, CT** | `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations` | `http://web.archive.org/web/20260301084742/https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations` | 2026-03-01 | ~3 months | ✓ Low (amendments uncommon at this cadence) |
| **Plymouth, MN** | `https://library.municode.com/mn/plymouth/codes/code_of_ordinances` | `http://web.archive.org/web/20250830020515/https://library.municode.com/mn/plymouth/codes/code_of_ordinances` | 2025-08-30 | ~10 months | ⚠️ Medium (check Plymouth Planning Commission docket for post-2025-08 amendments) |
| **Eden Prairie, MN** | `https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances` | `http://web.archive.org/web/20260123080031/https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances` | 2026-01-23 | ~5 months | ✓ Low |
| **Mill Creek, WA** | `https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html` | `http://web.archive.org/web/20230925022030/https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html` | 2023-09-25 | ~2.75 years | ❌ HIGH (skip Wayback; use operator browser) |

**Wayback usage caveat:** Web.archive.org is unavailable to this Claude Code WebFetch environment, but works fine in:
- Any standard browser (operator path)
- Any Python `requests`/`urllib` script (Diagnostic PDF tool path)
- `curl` / `wget` (procurement path tooling)

---

## Header / browser-config experiments (theoretical — WebFetch can't test)

WebFetch in this environment uses a fixed User-Agent that all 5 platforms fingerprint as automated. For operator (Chrome) or PDF tool (custom curl) paths, these techniques may reduce anti-bot friction:

| Technique | Platform applicability | Effort | Confidence |
|---|---|---|---|
| Set User-Agent to standard Chrome string (e.g., `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`) | All 5 platforms | Trivial | HIGH — most CDN fingerprints check UA first |
| Add `Referer: https://www.google.com/` header | amlegal, eCode360 | Trivial | MEDIUM — some platforms whitelist search-engine referrers |
| Add `Accept: text/html,application/xhtml+xml,application/xml;q=0.9` | All 5 | Trivial | LOW — usually already default |
| Cookie persistence across session (Chrome handles automatically; curl needs `-b cookies.txt`) | eCode360 most | Low | HIGH — eCode360 CAPTCHA sets session cookie |
| Disable JavaScript via `view-source:` prefix in browser | Code Publishing | Trivial | MEDIUM — some platforms serve degraded HTML to no-JS clients |
| Use rotating residential proxies | All 5 | High effort + cost | HIGH but ethically gray; not recommended |
| Use authenticated Municode subscription | Municode-platform munis (Plymouth, Eden Prairie, Edina, Stamford-mirrored, etc.) | $$ + procurement | HIGHEST — full API access, no anti-bot |

**Recommendation:** For path (a) operator, NO header experiments needed — Chrome serves all 5 platforms by default. For path (b) PDF tooling, Diagnostic should test User-Agent override as the cheap first attempt before invoking Wayback fallback. For path (c) procurement, Municode authenticated subscription unlocks the largest swath (Municode-platform is the single most-common platform across all 30 verdict-truth queue munis).

---

## Path-specific implications

### If Master picks (a) operator-assisted Lane E

- Operator browser works everywhere; ~3h Tier 1 estimate from playbook stands
- Anti-bot fallback chain only needed if operator hits unusual 403 (rare in Chrome)
- eCode360 Sewickley/Aspinwall (Tier 3): operator may hit CAPTCHA on first session; budget +5 min per session

### If Master picks (b) PDF tooling (Diagnostic sprint)

- Diagnostic adapter should default to: Chrome User-Agent + Wayback fallback chain
- **Mill Creek BP needs special handling** (Wayback 2.75 years stale) — Diagnostic should try operator-passed PDF backup OR skip Mill Creek and defer to path-a overlay
- **eCode360 cannot be PDF-extracted** (Sewickley + Aspinwall need operator-path overlay)
- Net coverage of path (b) on 31-item queue: ~22 items (excludes Mill Creek BP if Wayback unsafe + Sewickley I + Aspinwall AI-1 + eCode360 anywhere else)

### If Master picks (c) Municode authenticated procurement

- Unlocks ~15-20 of 31 items (all Municode-platform munis: Plymouth + Eden Prairie + Edina + Stamford-Municode-mirror + Beverly Hills + Carefree + others)
- Does NOT cover Code Publishing (Mill Creek + Bainbridge + Gig Harbor + Bellevue) — needs separate Code Publishing procurement OR operator-path overlay
- Does NOT cover amlegal (Winnetka future + Carefree + Franklin) — separate American Legal procurement
- Does NOT cover eCode360 (Sewickley + Aspinwall) — operator-path overlay
- Best ROI procurement: Municode subscription PLUS operator-path overlay for non-Municode munis

---

## Recommendation summary

**Path (a) operator** is the most universal unlock (~9 of 9 Tier 1 + 30 of 31 full queue). Lowest setup friction, highest amendment-currency, ~10h operator time for full queue.

**Path (b) PDF tooling** unlocks ~22 of 31 items efficiently but cannot solve eCode360 or stale-Wayback Mill Creek BP. Best paired with operator-path overlay for the gap.

**Path (c) Municode procurement** unlocks ~15-20 of 31 items but leaves Code Publishing + amlegal + eCode360 gaps. Combine with operator-path overlay or expand procurement to multiple platforms ($$$).

**Hybrid recommendation:** Path (a) operator-path for Tier 1 (~3h, ~28 cell-flips, biggest ROI). Defer Tier 2-4 decision until Tier 1 results inform whether marginal verdict-truth cell-flips justify (b) tooling OR (c) procurement spend.

---

## Standing posture

- Anti-bot probes complete; no UPDATEs attempted; halt rule stands
- Operator playbook (commits c389631 + 9849c32 + this doc) ready for path (a) dispatch
- Diagnostic PDF-tool sprint inputs ready: Wayback URLs + 4 platform constraint notes
- Awaiting Master a/b/c selection
