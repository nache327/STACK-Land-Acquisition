# Verdict-Truth Cleanup Queue — Impact Ranking (30 items)

**Date:** 2026-06-23
**Status:** Source-independent prep work during verdict-truth Somerset sprint HALT (per `verdict_truth_somerset_sprint_results.md`)
**Use:** Sequence wave-7 operator/PDF-tooling dispatch by expected verdict-lift impact and source-friction batching so the first hours of work deliver the biggest wins.

---

## Methodology

Each item ranked along 4 dimensions:

| Dimension | Why it matters |
|---|---|
| **Verdict-direction probability** | How likely is the ordinance to permit self-storage / mini-warehouse / light-industrial / luxury-garage-condo in this district? Pure Light Industrial named districts are ~85% permitted; General Industrial ~80%; Industrial Park ~70%; Heavy Industrial ~90%; Water-Dependent ~5%; High-Technology research ~20%. |
| **Parcel-base size in the zone-code** | More parcels under the code = more downstream query/match lift when verdict flips. Proxied by (muni industrial concentration × district polygon count where known). |
| **STACK acquisition fit** | Would land-acq actually pursue parcels here? Industrial corridors near I-95 / I-405 / I-494 / Loop 101 rank high; wealth-pocket residential munis rank low even if verdict flips. |
| **Source friction** | Operator/PDF-tooling time per muni. Single-source Municode/eCode reads (Stamford, Plymouth, Eden Prairie) = low. Overlay-heavy (Scottsdale) or PDF-only (Wayzata/Fountain Hills/Greenwich) = high. |

**Composite priority** = (Verdict-direction × Parcel-base × STACK-fit) ÷ Source-friction. Items grouped into 4 tiers; within each tier, ordered by single-source-batch grouping (so an operator can knock down a whole muni in one read).

---

## TIER 1 — HIGH IMPACT (apply first; biggest verdict-lift ROI)

These items combine high permit probability + large parcel base + strong STACK fit + low source friction. Operator can clear all 9 with ~2-3h of focused ordinance reading across 3 munis.

| # | Muni | Code | Permit prob | Notes |
|---|---|---|---|---|
| 1 | **Stamford, CT** | M-G | ~85% | General Industrial; Stamford is industrial-anchored Fairfield muni (25,524 parcels); I-95 corridor STACK fit; Section 4/5 + Appendix A single-source pass |
| 2 | **Stamford, CT** | M-L | ~90% | Light Industrial; same single-source pass as M-G; explicit LI label = highest permit probability |
| 3 | **Plymouth, MN** | I-1 | ~80% | Industrial; Plymouth has substantial industrial concentration along I-494 / US-169; single Municode Chapter XXI read covers I-1/I-2/I-3 |
| 4 | **Plymouth, MN** | I-2 | ~80% | Industrial; same Chapter XXI pass |
| 5 | **Plymouth, MN** | I-3 | ~80% | Industrial; same Chapter XXI pass |
| 6 | **Eden Prairie, MN** | I-GEN | ~85% | General Industrial; Eden Prairie has industrial cluster along I-494 / US-169; single Municode Chapter 11 read covers all 3 industrial codes |
| 7 | **Eden Prairie, MN** | I-2 | ~80% | Industrial; same Chapter 11 pass |
| 8 | **Eden Prairie, MN** | I-5 | ~80% | Industrial; same Chapter 11 pass |
| 9 | **Mill Creek, WA** | BP | ~90% | Business and Industrial Park, WAZAZoneSpecific=**INDHVY** Heavy Industrial (68 polygons); I-405 corridor STACK fit; Mill Creek MCMC Title 17 per-district chapter (Code Publishing 403 → operator-browsable HTML) |

**Operator dispatch (Tier 1):** ~2-3h covers all 9 items via 4 single-source reads (Stamford, Plymouth, Eden Prairie, Mill Creek).

---

## TIER 2 — MEDIUM IMPACT (apply second; single-pass operations, smaller bases)

These have moderate verdict probability OR smaller parcel bases, but remain low-friction reads inside munis already opened by Tier 1.

| # | Muni | Code | Permit prob | Notes |
|---|---|---|---|---|
| 10 | **Stamford, CT** | IP-D | ~65% | Industrial Park Designed; mixed-use designed district may permit subset (flex/light industrial); same single-Stamford pass as Tier 1 #1-2 (FREE in batch) |
| 11 | **Stamford, CT** | M-D | ~55% | Industrial Mixed; designed district variable; same single-Stamford pass (FREE in batch) |
| 12 | **Stamford, CT** | HT-D | ~25% | High Technology District; research/lab-focused; storage typically NOT permitted; LOW probability but FREE in Stamford batch — read and confirm |
| 13 | **Edina, MN** | PID | ~70% | Planned Industrial District; Edina has small industrial concentration along I-494; single Chapter 36 PID section read |
| 14 | **Minnetonka, MN** | I-1 | ~80% | Industrial; Minnetonka has industrial along US-169; Chapter 3 Sec. 300.20 single section read |
| 15 | **Bellevue, WA** | LI | ~85% | Light Industrial; BelRed area; HIGH permit probability but small parcel base (~61 parcels per prior Bellevue PR #266 audit); single Bellevue LUC 20.10.440 read |
| 16 | **Scottsdale, AZ** | I-1 | ~80% | Industrial; Scottsdale Airpark + south industrial corridors; Article XI Land Use Table single read |
| 17 | **Scottsdale, AZ** | I-G | ~80% | General Industrial; same Article XI read as I-1 (FREE in Scottsdale batch) |

**Operator dispatch (Tier 2):** ~2-3h covers 8 items; #10-12 are zero-marginal-cost adds on the Stamford batch from Tier 1.

---

## TIER 3 — LOW IMPACT (small parcel bases × wealth-pocket residential munis × little STACK demand)

Verdict-truth lifts here improve query accuracy but unlock minimal downstream land-acq value. Worth doing for completeness, but defer if operator budget is tight.

| # | Muni | Code | Permit prob | Notes |
|---|---|---|---|---|
| 18 | **Gig Harbor, WA** | ED | ~75% | Employment District, WAZA INDLHT; 1 polygon (schematic WAZA layer — actual parcel coverage TBD); residential bay-town context, low STACK fit |
| 19 | **Bainbridge Island, WA** | B/I | ~75% | Business/Industrial, WAZA INDLHT (6 polygons); BIMC 18.06.050.B confirms "light manufacturing"; island wealth-pocket, low STACK industrial demand |
| 20 | **Aspinwall, PA** | AI-1 | ~75% | Limited Industrial (§27-310); small borough (1,125 parcels muni-wide); compact eCode360 read |
| 21 | **Sewickley, PA** | I | ~75% | Industrial; small borough (1,699 parcels); eCode360 Chapter 330 Article IV use-table read; case note: prod uses `INST.` UPPERCASE (different from this `I`) — verify code spelling at apply time |
| 22 | **Bloomfield Hills, MI** | I-1 | ~70% | Industrial; ultra-wealth muni (1,833 parcels TOTAL); minimal industrial footprint; Chapter 54 single section read |
| 23 | **Greenwich, CT** | GB-IND-RE | ~50% | Greenwich Business / Industrial / Real Estate hybrid; Greenwich has very limited industrial (mostly research/exec corridors); Division 9 + Division 21 multi-section read = higher friction |

**Operator dispatch (Tier 3):** ~3-4h covers 6 items, but downstream value low. Defer behind Tier 1 + Tier 2 unless operator wants completeness pass.

---

## TIER 4 — VERDICT-TRUTH UNLIKELY (catchall × 4 probably holds; low expected lift)

Reading these confirms the existing prohibited × 4 verdict rather than flipping it. Worth doing for documentation precision but expect zero verdict change in most cases.

| # | Muni | Code | Permit prob | Notes |
|---|---|---|---|---|
| 24 | **Bainbridge Island, WA** | WD-I | ~5% | Water-Dependent Industrial (port/marine, WAZA INDPORT); self-storage is NOT water-dependent; catchall × 4 expected to HOLD |
| 25 | **Fountain Hills, AZ** | IND-2 | ~40% | Industrial-2; currently **substrate-armed-cov-gate-blocked** per `verdict_truth_somerset_sprint_results.md` (cov=55.9%, below 70% gate); even verdict-truth lift doesn't enable flip until cov gate passes |
| 26 | **Fountain Hills, AZ** | M-1 | ~40% | Industrial; same cov-gate constraint as IND-2 |
| 27 | **Scottsdale, AZ** | I-1 + overlay var 1 | ~60% | Overlay districts (PCD/ESL/etc.) impose additional restrictions on top of base; verdict often goes to conditional or stays prohibited |
| 28 | **Scottsdale, AZ** | I-1 + overlay var 2 | ~60% | same — overlay-specific reads required |
| 29 | **Scottsdale, AZ** | I-1 + overlay var 3 | ~60% | same |
| 30 | **Scottsdale, AZ** | I-G + overlay var 1 | ~60% | same |
| 31 | **Scottsdale, AZ** | I-G + overlay var 2 | ~60% | same |

**Operator dispatch (Tier 4):** ~2-3h for completeness; expect ~1-2 actual verdict flips out of 8 items.

(Note: queue total is 31 here vs halt doc's 30 — minor classification difference on Bainbridge WD-I and Scottsdale overlay split. Doesn't affect ranking logic.)

---

## Recommended operator dispatch sequence (assuming 8h budget)

If Master picks path (a) **operator-assisted Lane E sprint** with 8h budget:

| Hour | Batch | Items cleared | Expected verdict flips |
|---|---|---|---|
| 1-2 | Stamford 5-code batch (M-G, M-L, IP-D, M-D, HT-D) | 5 | ~3-4 flips (M-G, M-L, IP-D high prob; M-D moderate; HT-D probably holds) |
| 3 | Plymouth MN 3-code batch (I-1, I-2, I-3) | 3 | ~3 flips |
| 4 | Eden Prairie 3-code batch (I-GEN, I-2, I-5) | 3 | ~3 flips |
| 5 | Edina PID + Minnetonka I-1 | 2 | ~2 flips |
| 6 | Mill Creek BP + Bellevue LI | 2 | ~2 flips |
| 7 | Scottsdale I-1 + I-G base codes | 2 | ~2 flips |
| 8 | Tier 3 cleanup (Bloomfield Hills I-1 + Bainbridge B/I + Aspinwall AI-1 + Sewickley I) | 4 | ~2-3 flips |

**8h yields ~17-19 verdict flips across 21 items.** Tier 4 (overlay variants + Fountain Hills cov-gate + Bainbridge WD-I) deferred to a wave-8 completeness pass.

---

## Recommended PDF-tooling dispatch (if Master picks path b)

If Master picks path (b) **PDF extraction tooling sprint via Diagnostic**:

Sequence Diagnostic adapter validation against the highest-impact items first so we ship the tooling AND clear the high-ROI queue in the same sprint:

1. **Stamford validation** (Stamford zoning regulations PDF) — proves Connecticut platform compatibility + clears 5 codes
2. **Plymouth MN validation** (Municode XXI PDF or chapter HTML) — proves Minnesota Municode compatibility + clears 3 codes
3. **Mill Creek validation** (Code Publishing MCMC HTML behind 403) — proves WA Code Publishing platform unlock + clears BP + opens Bainbridge/Gig Harbor batches
4. **Scottsdale validation** (Article XI overlay-aware extraction) — proves Maricopa Municode + overlay handling + clears 2 base codes + opens 5 overlay variants

This gives Diagnostic 4 validation targets that span 4 different platform substrates (Stamford's stamfordct.gov PDF, Hennepin's Municode HTML, WA's Code Publishing 403-protected HTML, AZ's Municode with overlays) — the same tool unlocks ~80% of the queue.

---

## Notes on parcel-count estimation

The composite ranking uses district-polygon-count proxies where direct per-code parcel counts aren't in pre-stage docs. To make this exact (and validate the ordering), an `/api/admin/op5/zone-code-stats?jurisdiction_id={jid}&zone_code={code}` lookup would give actual `parcel_count` per code. That endpoint may not exist yet — if Master wants exact parcel-weighted ranking before dispatch, that's a small Lane A ask (~30 min adapter on existing zoning_code group-by).

**Without exact parcel counts**, the ranking is directionally correct but Tier 1 vs Tier 2 boundaries could shift by ~1-2 positions when actual counts land.

---

## Standing posture (unchanged from halt doc)

- Sprint halted at item 0/30 (no UPDATEs applied) — Bergen "real ordinance citations only" hard rule prevents orchestrator from applying verdict-truth lifts without source-text grounding
- Wedge cohort count holds at 38
- This ranking is **dispatch-prep only** — no rows authored, no apply attempted
- Standing by for Master's wave-7 path selection (a / b / c)
