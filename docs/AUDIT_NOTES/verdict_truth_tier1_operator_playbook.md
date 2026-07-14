# Verdict-Truth Tier 1 — Operator-Sprint Playbook

**Date:** 2026-06-23
**Status:** Cheap insurance prep — drafted during HOLD POSTURE in case Master picks wave-7 path (a) operator-assisted Lane E sprint
**Scope:** Tier 1 only (9 items / 4 munis / ~3h operator / ~28 expected cell-flips per `verdict_truth_queue_ranking_2026_06_23.md`)
**Bergen hard-rule reminder:** Real ordinance citations only. Operator confirms/refutes hypothesis from actual ordinance text and returns 1-line citation quote per cell. No fabrication; if section text doesn't address the use, return `prohibited` (catchall holds, bias-against-unclear).

---

## How to use this playbook

1. Per code, open the URL listed
2. Find the section anchor (search the page for the keyword string)
3. Read 1-3 paragraphs around the anchor
4. Apply the per-cell decision matrix below to each of 4 use cells
5. Return verdict + 1-line citation quote per cell
6. Net per-code time: ~5-15 min (depending on platform UI / search friction)

**Pre-flight check:** If a URL returns 403 anti-bot to the operator, switch to incognito mode / different browser / fallback to PDF download from the village website. Most platforms (Municode, Code Publishing, eCode360) accept human browser traffic but block automated WebFetch.

---

## Anti-bot fallback paths (per-platform + per-muni)

**Critical distinction:** 403 to **WebFetch / curl / orchestrator** ≠ 403 to **human browser**. Most platforms below serve content fine to standard Chrome with default User-Agent; they fingerprint and block automated requests. If the operator hits a 403 in their normal browser, that's the unusual case — try fallbacks below.

### Universal platform reference table

| Platform | WebFetch status | Human browser status | Notes |
|---|---|---|---|
| **codepublishing.com** | 403 confirmed (Bainbridge BIMC / Mill Creek MCMC / Gig Harbor GHMC) | Usually OK | Stable URLs; snapshotted on Wayback Machine reliably |
| **amlegal / codelibrary.amlegal.com** | 403 confirmed (Carefree / Franklin / Sewickley / Winnetka) | Usually OK | Strong anti-bot; even browser may need cookies set |
| **municipal.codes** | 403 confirmed (Bellevue LUC) | Usually OK | Newer platform; static HTML often cached on Wayback |
| **library.municode.com** | Likely 403 (per halt doc — Beverly Hills MI / Stamford / Mercer Island WA / Edina MN) | Usually OK | Most common municipal-code platform; reliable backup via village PDF |
| **encodeplus.com** | Likely 403 (Birmingham MI / Westport CT) | Usually OK | Returns HTML on browser; export PDF option often available in UI |
| **ecode360.com** | Anti-bot strict per halt doc | Usually OK after CAPTCHA | May require operator to solve CAPTCHA first time per session |
| **stamfordct.gov / village .gov sites** | Usually OK | OK | Direct municipal sites generally no anti-bot; PDF downloads work |

### Universal backup-path hierarchy (try in order)

1. **Direct platform URL in operator's normal Chrome browser** (works ~90% of time)
2. **Direct platform URL in Chrome incognito mode** (clears any anti-bot cookies; works ~95%)
3. **Village municipal website backup** — most villages host a PDF mirror of their zoning ordinance under /planning/ or /community-development/ paths (works ~70% for full ordinance; ~95% for zoning map)
4. **Wayback Machine snapshot**: `https://web.archive.org/web/*/{original_url}` — shows all snapshots; pick a recent one (note: may not reflect latest amendments)
5. **Direct village planning department contact** — email or phone (1-day delay; reliable last resort)

**DO NOT use:**
- Google's "cached" feature — retired by Google in early 2024
- Random PDF mirrors on third-party real-estate sites — citation provenance unverifiable; violates Bergen hard-rule
- ChatGPT/LLM summaries of ordinances — same provenance issue

### Per-muni anti-bot fallback notes

#### Stamford, CT (codes 1, 2 = M-G, M-L)

| Path | URL | Notes |
|---|---|---|
| Primary | https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations | Municipal site; usually no anti-bot |
| Backup 1 | Stamford regs PDF (linked from primary page) | Direct PDF download; full Section 4 + Section 5 + Appendix A |
| Backup 2 | https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-map | Zoning map PDF (for district code confirmation, NOT use rules) |
| Backup 3 | Wayback: `https://web.archive.org/web/*/https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations` | High snapshot frequency expected |
| Backup 4 | Stamford Zoning Board planning office: zoning@stamfordct.gov | Last resort; 1-day response typical |
| Risk | Recent amendments may move use rules to Appendix A (per Hennepin/Fairfield citation directory) — check both Section 5 district section AND Appendix A | |

#### Plymouth, MN (codes 3, 4, 5 = I-1, I-2, I-3)

| Path | URL | Notes |
|---|---|---|
| Primary | https://library.municode.com/mn/plymouth/codes/code_of_ordinances?nodeId=CICO_CHXXIZOOR | Municode platform — likely 403 to WebFetch; usually OK to browser |
| Backup 1 | https://www.plymouthmn.gov/departments/community-economic-development/planning/zoning-ordinance | Municipal site; per Hennepin citation directory — may host PDF backup |
| Backup 2 | Plymouth `link-backed zoning map layer` URLs (per Hennepin directory) | The link-backed ZoningMap/MapServer/4 returns 16 values with direct Municode URLs per district — may have different cache behavior than chapter overview URL |
| Backup 3 | Wayback Machine snapshot of Municode chapter URL | Reliable for non-amendment-sensitive sections |
| Backup 4 | Plymouth Community & Economic Development: planning@plymouthmn.gov | Last resort |
| Risk | I-1 / I-2 / I-3 chapter section numbers were not captured in pre-stage research (citation directory says "Sec 21680-21690 range") — operator must navigate Chapter XXI index to find exact section per code | |

#### Eden Prairie, MN (codes 6, 7, 8 = I-GEN, I-2, I-5)

| Path | URL | Notes |
|---|---|---|
| Primary | https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances?nodeId=CH11LAUSREZO | Municode — likely 403 to WebFetch; usually OK to browser |
| Backup 1 | Eden Prairie city zoning page (linked from edenprairie.org Community Development) | Specific URL TBD; may have PDF mirror of Chapter 11 |
| Backup 2 | https://gis.edenprairie.org/CommDev/Zoning.pdf | This is the zoning MAP PDF (district boundaries) — NOT use rules; only useful for confirming district code spelling (I-GEN vs IGEN etc.) |
| Backup 3 | Wayback snapshot of Municode chapter URL | |
| Backup 4 | Eden Prairie Community Development: communitydev@edenprairiemn.gov | Last resort |
| Risk | Chapter 11 is large (covers all districts); operator must use page search for "I-GEN", "I-2", "I-5" to find district sections quickly. Eden Prairie may have non-contiguous district numbering (I-5 without I-3/I-4). | |

#### Mill Creek, WA (code 9 = BP)

| Path | URL | Notes |
|---|---|---|
| Primary | https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html | Code Publishing — 403 confirmed to WebFetch; usually OK to browser per WA platform pattern |
| Backup 1 | https://www.cityofmillcreek.com/ (Community Development / Planning / Zoning) | Municipal site likely hosts PDF backup of MCMC Title 17 (check menu) |
| Backup 2 | Wayback snapshot of Code Publishing URL — HIGH probability of recent snapshot since WA platform sites get regular crawls | `https://web.archive.org/web/*/https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html` |
| Backup 3 | Snohomish County library or Mill Creek City Hall: 425-921-5740 (planning) | Hard-copy reference; last resort |
| Risk | MCMC Title 17 is per-district narrative (not master use table per `mill_creek_citation_anchors_prestaged.md`) — operator must find the specific BP chapter number (Chapter 17.16-17.20 range expected; not yet confirmed). Pre-stage doc flags this as TBD. | |
| Special note | If Code Publishing browser-block is unusual: 5,406 WAZA polygons per Mill Creek suggests heavy parcel-level traffic — site likely whitelists Snohomish-region IPs but blocks others. Try VPN to Pacific Northwest if standard browser fails. | |

### Wayback Machine usage tips

- Wayback URL pattern: `https://web.archive.org/web/{timestamp}/{original_url}` where `{timestamp}` is `YYYYMMDDHHMMSS` or `*` for wildcard
- For latest snapshot: visit `https://web.archive.org/web/2026/{original_url}` (year-only timestamp uses latest snapshot in year)
- **Amendment risk**: Wayback snapshot may be older than current ordinance amendments. Always note the snapshot date in citation: "(per Wayback snapshot 2026-MM-DD; verify against current amendments)"
- **Bergen hard-rule compatibility**: Wayback citations are acceptable per "real ordinance citations" rule IF the snapshot URL is included alongside the original URL. Format: `url: "https://web.archive.org/web/2026XXXX/{original_url}"` with note in `section` field that this is a Wayback snapshot.

---

## Per-cell decision matrix (universal, applies across all 9 codes)

| Cell | PERMITTED if district use list contains | CONDITIONAL if | PROHIBITED if (catchall default) |
|---|---|---|---|
| **self_storage** | "self-storage", "mini-storage", "mini-warehouse", "self-service storage facility" | "warehouse" (generic, may include retail self-storage) without explicit "self-storage" exclusion | None of the above; or use list silent on storage |
| **mini_warehouse** | "mini-warehouse", "self-storage", "mini-storage", "personal storage" | Same as self_storage conditional triggers | Use list silent |
| **light_industrial USE** | "light manufacturing", "light industrial", "assembly", "fabrication", "warehouse and distribution" | "manufacturing" with restrictions on noxious/heavy uses | Use list explicitly restricts to non-industrial; or silent and district is non-industrial |
| **luxury_garage_condo** | "private garage condominium", "indoor vehicle storage condominium", "garage condominium" | "indoor vehicle storage", "warehouse with private vehicle access", "accessory recreational storage" | Use list silent on indoor vehicle/garage storage |

**Special rule:** If the district has a "permitted uses" list AND a separate "prohibited uses" list, BOTH must be checked. A use silent in permitted list but absent from prohibited list defaults to prohibited per default-prohibition principle in most ordinances.

**Special rule (overlay districts):** Tier 1 has zero overlay items; this rule applies only to Tier 4 Scottsdale overlays — skip in Tier 1 work.

---

## Code-by-code drilldown (9 items)

### 1. Stamford M-G (General Industrial)

| Field | Value |
|---|---|
| URL | https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations |
| Section anchor | "Section 5 Districts and District Regulations" → find "M-G" or "General Industrial" subsection |
| Backup section | "Section 4 Use Regulations and Standards" — if M-G section refers to Section 4 |
| Appendix A | Check Appendix A for moved district use regulations (Stamford recently relocated some use rules) |
| Search keywords | "M-G", "General Industrial", "self-storage", "mini-warehouse", "warehouse" |
| **Hypothesis** | self_storage=**permitted** (90%), mini_warehouse=**permitted** (90%), light_industrial=**permitted** (95%), luxury_garage_condo=**conditional** (50%) |
| Decision criterion | M-G is Stamford's broadest industrial district; high probability all 4 cells permit or condition |

### 2. Stamford M-L (Light Industrial)

| Field | Value |
|---|---|
| URL | (same as M-G) |
| Section anchor | "Section 5" → "M-L" or "Light Industrial" subsection |
| Search keywords | "M-L", "Light Industrial", "self-storage", "mini-warehouse" |
| **Hypothesis** | self_storage=**permitted** (90%), mini_warehouse=**permitted** (90%), light_industrial=**permitted** (95%), luxury_garage_condo=**conditional** (50%) |
| Decision criterion | M-L is named Light Industrial — highest permit probability across all 4 cells; if storage not explicitly permitted, look for "warehouse" generic permission |

### 3. Plymouth MN I-1 (Industrial)

| Field | Value |
|---|---|
| URL | https://library.municode.com/mn/plymouth/codes/code_of_ordinances?nodeId=CICO_CHXXIZOOR |
| Section anchor | Chapter XXI Zoning Ordinance → find "Section 21680" (or similar; I-1 industrial section in 21680-21690 range per citation directory) |
| Search keywords | "I-1", "Industrial", "self-storage", "mini-warehouse", "warehouse and distribution" |
| **Hypothesis** | self_storage=**permitted** (85%), mini_warehouse=**permitted** (85%), light_industrial=**permitted** (95%), luxury_garage_condo=**conditional** (50%) |
| Decision criterion | Plymouth uses long-form use list per section; check for "self-service storage" or "mini-storage" explicit mention |

### 4. Plymouth MN I-2 (Industrial sub-numbered)

| Field | Value |
|---|---|
| URL | (same as I-1) |
| Section anchor | Chapter XXI → find I-2 industrial section (likely adjacent to I-1; same Sec 216XX range) |
| Search keywords | "I-2", "Industrial 2", "self-storage" |
| **Hypothesis** | self_storage=**permitted** (80%), mini_warehouse=**permitted** (80%), light_industrial=**permitted** (90%), luxury_garage_condo=**conditional** (45%) |
| Decision criterion | I-2 typically narrower than I-1 (more restrictive); if I-1 explicitly permits self-storage, I-2 usually does too |

### 5. Plymouth MN I-3 (Industrial sub-numbered)

| Field | Value |
|---|---|
| URL | (same as I-1) |
| Section anchor | Chapter XXI → find I-3 industrial section |
| Search keywords | "I-3", "Industrial 3", "self-storage" |
| **Hypothesis** | self_storage=**permitted** (80%), mini_warehouse=**permitted** (80%), light_industrial=**permitted** (90%), luxury_garage_condo=**conditional** (45%) |
| Decision criterion | Same as I-2; check parallel district structure |

### 6. Eden Prairie I-GEN (General Industrial)

| Field | Value |
|---|---|
| URL | https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances?nodeId=CH11LAUSREZO |
| Section anchor | Chapter 11 Land Use Regulations → find "I-GEN" or "General Industrial" district section |
| Search keywords | "I-GEN", "General Industrial", "self-storage", "warehouse" |
| **Hypothesis** | self_storage=**permitted** (85%), mini_warehouse=**permitted** (85%), light_industrial=**permitted** (95%), luxury_garage_condo=**conditional** (50%) |
| Decision criterion | I-GEN is Eden Prairie's broadest industrial district; check if "warehousing" or "self-storage" appears in permitted uses |

### 7. Eden Prairie I-2 (Industrial sub-numbered)

| Field | Value |
|---|---|
| URL | (same as I-GEN) |
| Section anchor | Chapter 11 → find I-2 industrial section |
| Search keywords | "I-2", "Industrial 2", "self-storage" |
| **Hypothesis** | self_storage=**permitted** (80%), mini_warehouse=**permitted** (80%), light_industrial=**permitted** (90%), luxury_garage_condo=**conditional** (45%) |

### 8. Eden Prairie I-5 (Industrial sub-numbered)

| Field | Value |
|---|---|
| URL | (same as I-GEN) |
| Section anchor | Chapter 11 → find I-5 industrial section |
| Search keywords | "I-5", "Industrial 5", "self-storage" |
| **Hypothesis** | self_storage=**permitted** (80%), mini_warehouse=**permitted** (80%), light_industrial=**permitted** (90%), luxury_garage_condo=**conditional** (45%) |
| Decision criterion | I-5 may be more specialized/restrictive than I-GEN; check for site-specific or use-specific restrictions |

### 9. Mill Creek BP (Business and Industrial Park — Heavy Industrial per WAZA INDHVY)

| Field | Value |
|---|---|
| URL | https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html (Title 17 index) |
| Section anchor | Find "BP" or "Business and Industrial Park" chapter in Title 17 (chapter number TBD per `mill_creek_citation_anchors_prestaged.md`; expect 17.16-17.20 range) |
| Backup | MCMC 17.22 General Provisions and Standards (default-prohibition language) |
| Search keywords | "BP", "Business and Industrial Park", "self-storage", "warehouse" |
| **Hypothesis** | self_storage=**permitted** (80%), mini_warehouse=**permitted** (80%), light_industrial=**permitted** (95%), luxury_garage_condo=**conditional** (45%) |
| Decision criterion | WAZA classified BP as INDHVY Heavy Industrial; Heavy permits storage by-right in most ordinances; check BP chapter for warehouse/distribution/storage permitted-use language |
| Operator note | Code Publishing platform returns 403 to WebFetch but works in human browser; if 403 in browser, try CodePublishing.com search bar from root |

---

## Return format (operator → orchestrator)

Per code, return JSON like:

```json
{
  "muni": "Stamford",
  "zone_code": "M-G",
  "cells": {
    "self_storage": {"verdict": "permitted", "citation": "Section 5 §x.x M-G District permitted uses include 'self-service storage facilities' (Stamford Zoning Regs §x.x.x)"},
    "mini_warehouse": {"verdict": "permitted", "citation": "(same section enumerates mini-warehouse alongside self-storage)"},
    "light_industrial": {"verdict": "permitted", "citation": "Section 5 M-G permitted uses include 'light manufacturing, assembly, and fabrication' (§x.x.x)"},
    "luxury_garage_condo": {"verdict": "prohibited", "citation": "M-G district use list silent on indoor vehicle storage condominium; catchall holds per default-prohibition (Section 4 §y.y.y)"}
  },
  "operator_notes": "free-form notes — e.g., 'Section 5 references Appendix A for moved use rules; verified both'"
}
```

---

## Apply procedure (orchestrator side, after operator returns)

1. For each cell-flip received, build a verdict UPDATE row via `_upload-matrix-rows` with `replace_existing=true` (in-place update)
2. Single batch per muni (Stamford 5 rows × 4 cells = up to 20 cell-updates; Plymouth 3 rows × 4 = 12; Eden Prairie 3 × 4 = 12; Mill Creek 1 × 4 = 4)
3. Quote hard-cap 200 chars per Stamford precedent (`hardcap` function from prior cascades)
4. Post-apply: `_uncovered-zone-codes` verification (should stay at 0 since these are UPDATEs, not inserts)
5. ONE refresh per muni at sprint end
6. §15 Daily Changelog entry per muni with operator attribution + cell-flip count

---

## Anti-pattern reminders

- **DO NOT** infer verdicts from WebSearch summaries — those return generic ordinance descriptions, not the per-district per-use chart. Only direct ordinance-text reads count per Bergen hard-rule.
- **DO NOT** flip catchall to permitted on hypothesis alone — if operator can't find the section, return prohibited (catchall holds, bias-against-unclear)
- **DO NOT** write `human_reviewed=true` on top of nache's hand-verdicted rows (Howard MD / Montgomery MD / Fairfax VA / etc.) — these wedge-cohort munis don't overlap with nache's verdicted set, but verify before apply
- **DO NOT** scope-creep outside the 9 Tier 1 items — Tier 2-4 dispatched separately
- **DO** preserve operator attribution in §15 changelog (Lane E sprint marker)

---

## Expected output (after 9-code sprint)

| Muni | Codes | Cell-flips expected | Cumulative |
|---|---:|---:|---:|
| Stamford | 2 (M-L, M-G) | ~6.35 (3.2 + 3.15) | 6.35 |
| Plymouth MN | 3 (I-1, I-2, I-3) | ~9.05 (3.15 + 2.95 + 2.95) | 15.4 |
| Eden Prairie | 3 (I-GEN, I-2, I-5) | ~9.05 | 24.45 |
| Mill Creek | 1 (BP) | ~3.0 | 27.45 |
| **TOTAL** | **9** | **~27.5 cell-flips** | **27.5** |

**Result delivered to Master:** ~28 cell-flips applied; 0 new operational flips; query-quality lift on STACK's highest-value industrial parcels (Stamford 25k + Plymouth MN industrial + Eden Prairie I-494 corridor + Mill Creek I-405 corridor).

---

## Standing posture

- Playbook authored as cheap insurance during HOLD POSTURE
- Apply gated on Master's wave-7 path (a) selection AND operator availability
- If Master picks (b) PDF tooling: this playbook is STILL USEFUL — tells the PDF adapter exactly which sections to extract per code
- If Master picks (c) authenticated access: same — playbook tells the authenticated WebFetch which URL anchors to hit
- Halt rule stands: no UPDATEs without source-text grounding from operator/PDF/authenticated read
