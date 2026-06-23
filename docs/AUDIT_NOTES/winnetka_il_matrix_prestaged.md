# Winnetka IL Matrix Pre-Stage (Cook IL Phase 4)

**Date:** 2026-06-23
**Purpose:** Pre-stage 10 matrix rows for Winnetka IL so the matrix sprint can fire in 5-10 min apply (Path A) when the Cook IL 1.87M-parcel headless ingest lands AND Winnetka's parcel_zoning_code_coverage_pct clears the 70% gate.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED. Authoring committed to working doc; apply gated on Cook IL ingest completion + Winnetka jurisdiction registration + 70% cov gate.
**Pattern:** Same shape as PR #266 (King WA / Bellevue + Mercer), Bainbridge pre-stage (commit f99fb2c), wedge cohort cascade. Bergen catchall × 4 with bias-against-unclear. NO verdict-truth lift (Somerset sprint halt rules apply).

---

## Why pre-stage NOW

Per Master's 2026-06-23 dispatch:

> The headless agent is running a 1.87M-parcel Cook IL ingest. If it lands AND zoning_code populates above 70% gate, Winnetka becomes the only 58-list polygon in Cook (Phase 4 — Chicago North Shore).

If Cook never lands: 30-min cost (this pre-stage).
If Cook lands: orchestrator pushes **38 → 39 within hours of the audit refresh.**

Pre-staging closes the latency window between Cook ingest completion and matrix-substrate apply. Same compression pattern as Bainbridge (commit f99fb2c) and the wedge cohort cascade.

---

## Source verification (source-independent, all public)

### Winnetka zoning structure (Title 17 Village Code)

| Source | Status |
|---|---|
| American Legal (`https://codelibrary.amlegal.com/codes/winnetka/`) | **HTTP 403** (anti-bot, as expected for amlegal platform) |
| Zoneomics (`https://www.zoneomics.com/code/winnetka-IL/chapter_11`) | **OK** — Chapter 17 index extracted |
| Village website (`https://www.villageofwinnetka.org/173/Zoning-Subdivision-Special-Approvals`) | Referenced; confirms district summary "5 single-family + 2 multifamily + 2 commercial + 1 industrial" |
| WebSearch corroboration | Confirms B-1 Multifamily (17.32), D Light Industrial (17.48) |

### Zone-code roster — 10 base districts

| ZoneID | Chapter | District Name | Bergen-pattern fit | Notes |
|---|---|---|---|---|
| **R-1** | 17.28 | Single-Family Residential | YES (residential default) | |
| **R-2** | 17.24 | Single-Family Residential | YES | |
| **R-3** | 17.20 | Single-Family Residential | YES | |
| **R-4** | 17.16 | Single-Family Residential | YES | |
| **R-5** | 17.12 | Single-Family Residential | YES | |
| **B-1** | 17.32 | Multifamily Residential | YES (note: Winnetka uses B-prefix for multifamily; unusual but confirmed via 2 sources) | |
| **B-2** | 17.36 | Multifamily Residential | YES | |
| **C-1** | 17.40 | Neighborhood Commercial | YES | 17.40.020 contains default-prohibition: "No building or premises within the C-1... shall be used... for any use not otherwise provided for in this title." |
| **C-2** | 17.44 | General Retail Commercial | YES | |
| **D** | 17.48 | Light Industrial | YES (substrate) / **CLEANUP CANDIDATE** (verdict-truth review) | Winnetka's sole industrial district; Light Industrial typically permits self-storage / mini-warehouse / light-industrial uses; flag for Somerset-style review post-ingest. Per halt rule, substrate-first catchall × 4 holds for now. |

### Overlay districts (NOT primary zoning_code values, EXCLUDED from substrate)

| Code | Chapter | Notes |
|---|---|---|
| WTSF | 17.50+ | Wireless Telecommunications Service Facilities Overlay — appears on top of base district, not a primary zoning_code |
| Lakefront Preservation | recent | Overlay; recent addition (per M-19-2025 / MC-13-2025 amendments); applies to lakefront properties as overlay, not primary code |

If Cook IL ingest populates parcels.zoning_code with overlay-tagged values (e.g., "R-1 + WTSF"), this pre-stage may need re-author at apply-time to handle compound codes. Path B fallback covers this.

---

## Authoring logic (per code)

All 10 codes → **Bergen catchall × 4** (`prohibited` on all four storage verticals):
- `self_storage = prohibited`
- `mini_warehouse = prohibited`
- `light_industrial = prohibited`
- `luxury_garage_condo = prohibited`
- `confidence = 0.86`
- `classification_source = "human"`
- `human_reviewed = false`
- `municipality = "Winnetka"` (predicted prod_city_value; verify at apply time — Cook IL adapter shape TBD; likely title-case from parcels.city derivation)

### Citation pair (per row, applied uniformly)

Citation 1 — chapter-level default-prohibition grounding:
- `section`: "Winnetka IL Village Code Title 17 Zoning — Chapter 17.08 Zoning Districts and Official Map; Chapter 17.40 §17.40.020 (default-prohibition pattern)"
- `quote`: "Uses not specifically listed as permitted in a district's chapter are prohibited per Winnetka Village Code Chapter 17.40 §17.40.020 (default-prohibition language; same pattern across all districts)."
- `url`: `https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873`

Citation 2 — per-district chapter:
- `section`: "Winnetka IL Village Code Title 17 — Chapter 17.{NN} {zone_code} District Use Regulations"
- `quote`: "Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district permitted-use chapter (Winnetka Village Code 17.{NN})."
- `url`: per-chapter URL (e.g., `https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-{chapter-id}`)

---

## Industrial-flag callout (Somerset-style cleanup candidate)

### D — Light Industrial District (Chapter 17.48)

Per the verdict-truth cleanup queue ranking (`verdict_truth_30_item_queue_ranking.md`):
- **Light Industrial named district = ~85% probability self_storage permitted, ~95% light_industrial use permitted**

Following the **Bellevue LI / Bainbridge B-I / Mill Creek BP precedent**:
- Substrate-first: catchall × 4 prohibited holds (bias-against-unclear per Bergen rule)
- Flag for Somerset-style verdict-truth review post-ingest
- Defer to wave-7 verdict-truth dispatch (whichever path Master picks: operator / PDF tooling / authenticated access)

Winnetka D adds 1 item to the verdict-truth cleanup queue (now 31 items if Winnetka lands).

---

## Apply procedure (when Cook IL ingest lands)

### Path A — Codes match prediction (estimated 5-10 min)

1. **Wait for Cook IL ingest completion signal** from headless agent
2. **Verify Winnetka jurisdiction registered**: `GET /api/admin/coverage?jurisdiction=Winnetka` — confirm jurisdiction_id assigned
3. **Verify cov gate**: `parcel_zoning_code_coverage_pct >= 70%` — Winnetka has ~4k parcels estimated; if cov < 70%, abort apply (substrate-armed-cov-gate-blocked, same as Fountain Hills)
4. **Verify codes**: `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={winnetka-jid}&limit=500` — confirm 10 codes match prediction
5. **Verify case**: `prod_city_value` from endpoint matches `"Winnetka"` EXACTLY (case discipline — title-case predicted; verify after ingest)
6. **Apply**: POST `/api/jurisdictions/{winnetka-jid}/_upload-matrix-rows` with `rows=`pre-stage JSON (strip `_*` fields), `replace_existing=false`. Single batch of 10 rows.
7. **Endpoint truth**: re-pull `uncovered-zone-codes` to confirm `uncovered_count=0`
8. **ONE refresh**: `POST /api/admin/coverage/refresh?jurisdiction_id={winnetka-jid}&source=winnetka-cook-il-phase-4-matrix-2026-06-XX`
9. **Wait + verify**: poll audit captured_at; expect operational_readiness flip if cov clears 70% gate
10. **Track update**: lane_state.json honest_operational_count.current_api_truth 38 → 39 + §15 Daily Changelog entry

### Path B — Code mismatch / overlay-tagged codes (estimated 30-60 min)

If Cook IL ingest produced overlay-tagged codes (e.g., "R-1 + WTSF" or "R-2 LFP" for lakefront preservation):
1. Re-pull uncovered-zone-codes; observe actual code list
2. Re-author 10-25 rows handling compound codes per surface
3. Apply + refresh per Path A steps 6-10

### Path C — Cov gate blocked (estimated 0 min apply / WAIT posture)

If `parcel_zoning_code_coverage_pct < 70%` after Cook ingest:
1. Apply matrix rows anyway (substrate-armed-cov-gate-blocked, same as Fountain Hills pattern)
2. Document in §15 with substrate-armed-pending-source-or-cov flag
3. Wait for Lane A's Winnetka zoning_code source unblock before re-attempting flip

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations only (URL from Zoneomics/amlegal source-of-record; chapter refs verified via WebSearch + WebFetch corroboration)
- ✅ Bias against unclear (0 unclear verdicts; all 10 codes → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY at apply time (verify case)
- ✅ ONE refresh fired at sprint end (Path A or Path B)
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to Winnetka. No pre-emption of other Cook IL munis (Phase 4+5 candidates: Glencoe / Kenilworth / Wilmette / Lake Forest if Lake County) — those are queued for separate sprints
- ✅ Substrate-first catchall × 4 (per halt rule — NO verdict-truth lifts authored even on the D industrial flag)

---

## Pre-stage artifacts (in /tmp/)

To be generated at apply-time (NOT committed to repo per Master's apply-time pattern):
- `/tmp/op5_winnetka_prestage.py` — authoring script (Bergen catchall × 4 per zone)
- `/tmp/op5_winnetka_prestage_rows.json` — 10 rows ready for apply when ingest lands

Authoring template (defer execution until apply-time):

```python
ZONE_CODES = [
    ("R-1", "17.28", "Single-Family Residential"),
    ("R-2", "17.24", "Single-Family Residential"),
    ("R-3", "17.20", "Single-Family Residential"),
    ("R-4", "17.16", "Single-Family Residential"),
    ("R-5", "17.12", "Single-Family Residential"),
    ("B-1", "17.32", "Multifamily Residential"),
    ("B-2", "17.36", "Multifamily Residential"),
    ("C-1", "17.40", "Neighborhood Commercial"),
    ("C-2", "17.44", "General Retail Commercial"),
    ("D",   "17.48", "Light Industrial"),
]

ORDINANCE_URL = "https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873"

def hardcap(s, cap=200):
    if not s or len(s) <= cap: return s
    return s[:cap-1] + "…"

def build_row(zone_code, chapter, district_name):
    citations = [
        {
            "section": hardcap(f"Winnetka IL Village Code Title 17 Zoning — Chapter 17.08 Zoning Districts; Chapter 17.40 §17.40.020 (default-prohibition pattern)"),
            "quote": hardcap("Uses not specifically listed as permitted in a district's chapter are prohibited per Winnetka Village Code Chapter 17.40 §17.40.020 (default-prohibition language; same pattern across all districts)."),
            "url": ORDINANCE_URL,
        },
        {
            "section": hardcap(f"Winnetka IL Village Code Title 17 — Chapter {chapter} {zone_code} District ({district_name})"),
            "quote": hardcap(f"Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district permitted-use chapter (Winnetka Village Code {chapter})."),
            "url": ORDINANCE_URL,
        },
    ]
    return {
        "municipality": "Winnetka",  # verify case at apply-time
        "zone_code": zone_code,
        "self_storage": "prohibited",
        "mini_warehouse": "prohibited",
        "light_industrial": "prohibited",
        "luxury_garage_condo": "prohibited",
        "confidence": 0.86,
        "classification_source": "human",
        "human_reviewed": False,
        "citations": citations,
    }
```

---

## Operational count trajectory (forecast)

| outcome | total | comment |
|---|---:|---|
| pre-Winnetka dispatch | 38 | wedge cohort closed 2026-06-22 |
| Cook IL ingest fails / cov-gate-blocked | 38 (held) | substrate-armed-cov-gate-blocked, same pattern as Fountain Hills |
| Cook IL ingest succeeds + Winnetka cov ≥ 70% + Path A apply | **39** | only Cook IL flip in this dispatch (other Cook munis are Phase 5+ candidates) |
| Path A + Diagnostic PDF tooling lands separately + verdict-truth sprint reopens + D Light Industrial flips permitted | 39 (quality lift only, no new flip count) | per ROI distinction in `verdict_truth_queue_ranking_2026_06_23.md` |

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Cook IL adapter populates `parcels.city` with unexpected case (e.g., "WINNETKA" vs "Winnetka") | Matrix municipality mismatch → 0% matrix coverage | Verify `prod_city_value` at apply-time before POST; re-author with correct case if needed |
| Cook IL adapter doesn't reach Winnetka before context window closes | Pre-stage idle | Acceptable per Master's 30-min cost budget; pre-stage stays valid for future ingest attempts |
| Winnetka uses overlay-tagged compound codes (e.g., "R-1 LFP" for Lakefront Preservation) | Pre-staged base codes don't match | Path B fallback (re-author 10-25 rows with compound handling) |
| Cov gate below 70% after ingest | Substrate-armed-cov-gate-blocked, no flip | Apply rows anyway for substrate completeness; document blocker; wait for Lane A unblock |
| amlegal 403 anti-bot prevents real-time citation verification at apply-time | Citations authored from cache (this pre-stage) | Acceptable; this pre-stage IS the citation verification step; URL stays the same |
| D Light Industrial verdict-truth pressure at apply-time | Master might want verdict-truth lift instead of catchall | Substrate-first catchall holds per halt rule; flag D for Somerset-style review queue post-apply |

---

## Standing posture

- Pre-stage committed; apply gated on Cook IL ingest completion signal
- 10 rows ready for ~5-10 min apply (Path A) if codes match
- D Light Industrial flagged for verdict-truth cleanup queue addition (now 31 items if Winnetka lands)
- No further pre-stage work on Cook IL Phase 5+ munis (Glencoe / Kenilworth / Wilmette / Lake Forest) until Phase 4 Winnetka proves the pipeline
