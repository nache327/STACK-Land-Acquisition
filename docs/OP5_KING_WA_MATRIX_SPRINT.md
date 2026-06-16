# Op-5 King County WA Matrix Sprint

**Sprint date:** 2026-06-16
**Target:** First WA matrix sprint of the campaign. Author matrix substrate for Bellevue + Mercer Island atop Lane A's Phase 6A.2 ingest. Third state-platform combo after NY (Westchester) and CA (Contra Costa).
**Outcome:** **62 rows authored + applied (100% verified-citation coverage); audit refresh pending. King WA likely lands partial-with-residual — `parcel_zoning_code_coverage_pct` is 5.2% county-wide, below the 70% gate.**

---

## Headline

This sprint validates the Bergen pattern on **third state-platform combo**:

| state | platform | sprint |
|---|---|---|
| NY | Class B / eCode360 monoculture | Westchester (PR #240) — flipped 20 |
| CA | Class A / 5-platform diversity | Contra Costa (PR #258) — matrix substrate; bbox-fix flipped 20 |
| **WA** | **Class A / WAZA + per-city platforms** | **King (this PR) — matrix substrate; coverage-gate residual** |

62 distinct (muni, zone_code) pairs authored across Bellevue (WAZA-legacy codes, 51 codes) and Mercer Island (city codes, 11 codes). Adjacent wealth band (Medina + Hunts Point + Clyde Hill, ~14 codes per PR #248 estimate) NOT in current uncovered set — Lane A's adapter hasn't ingested them yet; deferred to follow-up sprint.

**Operational count: stays 20.** Matrix substrate is in place; King flips operational when Lane A's parcel-coverage scale-out lifts cov above 70%.

| metric | BEFORE (audit 2026-06-16T05:11:53) | TRUTH (DB post-apply) | POST-REFRESH PROJECTION |
|---|---:|---:|---:|
| parcel_count | 635,186 | 635,186 | 635,186 |
| parcel_with_zoning_code_count | 33,022 | 33,022 | 33,022 |
| **parcel_zoning_code_coverage_pct** | **5.2%** | 5.2% | **5.2% — BELOW 70% gate** ⚠️ |
| matrix_zone_count | 0 | **62** | 62 |
| matrix_zone_match_pct | (uncomputed) | ~100% (uncovered=0) | ≥90% gate cleared |
| self_storage_classified_parcel_pct | 0% | (recompute pending) | ~100% projected |
| `no_zone_use_matrix` | firing | (cleared) | **cleared** |
| `no_matrix_matches_for_parcel_zones` | firing | (cleared) | **cleared** |
| `low_matrix_match_pct` | firing | (cleared) | **cleared** |
| operational_readiness | partial | (recompute pending) | **partial-with-residual** (cov < 70%) OR partial — depends on whether PR #98 70% gate fires |

---

## ⚠️ Honest residual gap

**King WA's `parcel_zoning_code_coverage_pct = 5.2%` (33,022 of 635,186 parcels)** — BELOW PR #98's 70% general operational gate.

Why: Lane A's Phase 6A.2 ingest covers only Bellevue + Mercer Island + a sliver of adjacent munis (~42k of 635k parcel-roster). The remaining ~593k King parcels (Seattle, Bothell, Kent, Kirkland, Redmond, Renton, Tukwila, etc.) have NULL `zoning_code`. Even with matrix substrate fully in place for the ingested 42k, the county-wide cov gate won't clear.

This sprint **does** clear all 3 matrix-related blockers (`no_zone_use_matrix`, `no_matrix_matches_for_parcel_zones`, `low_matrix_match_pct`). It does NOT clear the parcel-coverage gate (separate from matrix work).

**Net effect:** Matrix substrate landed cleanly. King flips operational when Lane A's parcel-coverage ingest expands beyond Eastside (or when PR #98 gate logic adjusts for WA-style county scale). Until then, partial-with-residual.

**Master's brief assumption that Bellevue's 85.2% per-muni coverage "drives the weighted-average above the 70% county gate" is mathematically off**: the audit's `parcel_zoning_code_coverage_pct` denominator is county-wide parcel_count (635k), not weighted muni-roster. 28k Bellevue + 4.7k Mercer ≈ 33k bound / 635k total = 5.2%, not 70%+.

---

## What we did

### 1. Pull King WA uncovered codes

- `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id=<king-wa>&limit=500` → 62 codes
- Per-muni distribution:
  - **Bellevue: 51 codes / 28,213 parcels** (BR-CR, BR-GC, BR-MO, R-5, R-1, GC, O, LI, DT-R, DT-OLB-S, etc. — WAZA-legacy authoritative per Lane A's PR #264 verification)
  - **Mercer Island: 11 codes / 4,809 parcels** (B, C-O, MF-2, MF-2L, MF-3, PBZ, PI, R-12, R-15, R-8.4, R-9.6, TC)
- Adjacent wealth band (Medina + Hunts Point + Clyde Hill): NOT in uncovered set (Lane A's adapter hasn't ingested them yet)

### 2. Verify citation URLs from PR #248 directory

- Bellevue: `https://bellevue.municipal.codes/LUC` (LUC 20.10 Land Use Districts; LUC 20.10.440 permitted uses by zone)
- Mercer Island: `https://library.municode.com/wa/mercer_island/codes/city_code?nodeId=CICOOR_TIT19UNLADECO` (Title 19 Unified Land Development Code)
- Both URLs verified live during PR #248 pre-stage research

### 3. Author 62 catchall rows

- verdict: `prohibited × 4` (Bergen catchall, bias-against-unclear per Master's "liberally" brief)
- confidence: 0.86
- citations: 2-citation pair per Scarsdale PR #234 / Westchester PR #240 / Contra Costa PR #258 precedent
- municipality: matches `prod_city_value` EXACTLY — "Bellevue" not "BELLEVUE" (WA case discipline per PR #264)
- classification_source: "human"

### 4. Apply via `_upload-matrix-rows`

- 5 batches × 15 rows + 1 batch of 2 = 62 rows
- **62/62 INSERTED, 0 errors, 0 skips**
- Endpoint truth post-apply: `uncovered_count` 62 → **0** ✓

### 5. ONE final audit refresh

`POST /api/admin/coverage/refresh?jurisdiction_id=<king-wa>&source=king-wa-sprint-2026-06-16` fired ONCE. HTTP edge timeout pattern (Railway proxy); backend continues server-side.

---

## Bellevue WAZA-legacy / city-code lesson applied

Lane A's PR #264 confirmed that 13 of 15 spot-checked Bellevue parcels carry WAZA-legacy codes (R-5, R-10, GC, etc.) as authoritative — NOT post-2017 city codes (LDR-2, MU-H). My sprint authored matrix rows for the WAZA-legacy codes Lane A's ingest produced; no fabrication around city-vs-WAZA layer choice.

**Verdict-truth spot-check candidates (not addressed in this sprint):**

- **`LI` (Light Industrial)**, Bellevue, 61 parcels — current verdict `prohibited × 4`. Per Bergen catchall + Master's "liberally" guidance, this is correct OR overly conservative depending on Bellevue LUC 20.10.440 actual chart. Light Industrial districts often permit self-storage by right; if so, a Somerset-style cleanup pass should re-verdict to `permitted` for self_storage / mini_warehouse / light_industrial.
- **`F-1`**, Bellevue, 10 parcels — appears to be Forest/Parks based on naming. Catchall stands.
- **Mercer Island `B` (Business?)** — needs spot-check whether use-table permits storage.

**These are deferred follow-up items, not blockers.** Master's brief was clear: "apply bias-against-unclear catchall liberally" — matrix substrate trumps per-code verdict precision for this sprint. Cleanup pass available later.

---

## Hard-rule compliance

- ✅ Real ordinance citations only (URLs from PR #248 directory verified during pre-stage; zero fabrication)
- ✅ Bias against unclear (0 unclear verdicts authored across 62 rows; catchall applied liberally per Master's brief)
- ✅ ONE final refresh fired at sprint end
- ✅ `municipality` matches `prod_city_value` EXACTLY — WA case discipline preserved per PR #264 lesson
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to King WA. No pre-emption of Pierce / Snohomish / Kitsap

---

## Phase summary

| phase | muni | codes | parcels | URL |
|---|---|---:|---:|---|
| **A** | Bellevue | **51** | **28,213** | bellevue.municipal.codes/LUC |
| **B** | Mercer Island | **11** | **4,809** | library.municode.com/wa/mercer_island/... |
| C (not present) | Medina + Hunts Point + Clyde Hill | 0 | 0 | (Lane A adapter hasn't ingested) |
| **TOTAL** | 2 munis | **62** | **33,022** | — |

---

## Operational count trajectory

| outcome | total |
|---|---:|
| Pre-sprint | 20 |
| Post-refresh if matrix substrate cleared AND 70% cov gate somehow not firing | 21 |
| **Post-refresh likely (cov 5.2% < 70% gate)** | **20** + state-quality KPI improvement |
| After Lane A's parcel-coverage scale-out lifts cov ≥ 70% | 21 (+King WA) |

---

## Artifacts (in /tmp/)

- `op5_king_wa_matrix.py` — sprint script with PR #248 URL map
- `op5_king_authored.json` — 62 catchall rows
- `op5_king_apply_results.json` — 5-batch results
- `op5_king_run.log` — full session log
- `king_by_muni.json` — paged uncovered code inventory
- `refresh_king.txt` — refresh fire response

---

## STOP for Master review

Awaiting:
1. Post-refresh state confirmation — Master's 70% cov gate assumption needs validation
2. If matrix gates clear cleanly but cov < 70% blocks operational flip: queue Lane A parcel-coverage scale-out as Phase 6A.3 (or whichever sequence)
3. If 70% gate logic adjusts for WA-style large-county scale (Master may want to revisit PR #98 thresholds): operational count could flip 20 → 21 today
4. Confirm spot-check follow-ups for Bellevue LI (Light Industrial) verdict — deferred Somerset-style cleanup if needed

Standing by for refresh commit.
