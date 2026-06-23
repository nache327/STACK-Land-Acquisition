# Verdict-Truth Queue Re-Ranking — Per-Cell × Muni-State × ROI (2026-06-23)

**Date:** 2026-06-23
**Status:** Source-independent prep work during verdict-truth Somerset sprint HALT (per `verdict_truth_somerset_sprint_results.md` — commit b4734b2)
**Supersedes:** `verdict_truth_30_item_queue_ranking.md` (initial ranking grouped at code-level; this re-rank adds per-cell × muni-state × ROI granularity per Master's 2026-06-23 TRACK A dispatch)

---

## TL;DR — critical framing for Master

**All 30 verdict-truth items are query-quality lifts, NOT new-flip drivers.**

Per coordination/lane_state.json (`wedge_cohort_closure` field):
- 19/25 wedge munis operational
- 4 substrate-armed-pending-source (Fox Chapel + O'Hara + Bloomfield Twp + Franklin — not in this 30-item queue; separate cleanup pattern)
- 2 deferred (Wayzata + Sewickley Heights — GeoPDF tooling gap; not in this queue)
- 1 substrate-armed-cov-gate-blocked (**Fountain Hills** — cov 55.9% < 70%; 2 of our 30 items live here)

ROI analysis:
- **28 items** sit on already-operational munis → verdict-truth = pure query-quality lift, **0 new operational flips**
- **2 items** (Fountain Hills IND-2 + M-1) sit on cov-gate-blocked muni → verdict-truth UPDATEs change existing row verdicts; they do NOT add new matrix rows, so cov% stays at 55.9%, so Fountain Hills stays substrate-armed regardless of verdict-truth work, **0 new operational flips here either**

**Verdict-truth completion of all 30 items would move operational count by 0.** Value is downstream STACK acquisitions query accuracy ("find permitted self-storage parcels in Stamford M-G" returns matches instead of zero results) — not headline ops count.

This is critical for wave-7 path selection:
- If Master's goal is **operational count growth**: defer verdict-truth queue; prioritize new-ingestion sprints (Cook IL / Plymouth MA / DuPage IL / Maryland MDP / Vessel Tech B2B)
- If Master's goal is **query-quality / acquisitions-team trust**: verdict-truth queue lifts ~79 cell-decisions across ~21-25 high-impact rows (see Tier 1 below)

---

## Methodology — per-cell verdict-lift estimation

Each of the 4 use cells (self_storage / mini_warehouse / light_industrial / luxury_garage_condo) has different permit probabilities by district type. Heuristics calibrated from US municipal zoning corpus observation:

| District type | self_storage | mini_warehouse | light_industrial USE | luxury_garage_condo |
|---|---:|---:|---:|---:|
| Pure Light Industrial named (LI, M-L, INDLHT) | 85% | 85% | 95% | 50% |
| General Industrial (I-1, I-G, I-GEN, M-G, AI-1, I-named) | 85% | 85% | 95% | 50% |
| Industrial sub-numbered (I-2/I-3/I-5/IND-2) | 80% | 80% | 90% | 45% |
| Industrial Park / Business Park (BP, IP-D, ED, B-I) | 75% | 75% | 85% | 45% |
| Heavy Industrial (INDHVY) | 80% | 80% | 95% | 45% |
| Industrial Mixed / Designed (M-D) | 60% | 60% | 75% | 35% |
| Planned Industrial District (PID) | 70% | 70% | 80% | 40% |
| Hybrid Business/Industrial/RE (GB-IND-RE) | 40% | 40% | 50% | 25% |
| Industrial overlay (base + overlay constraints) | 60% | 60% | 75% | 30% |
| High Technology research (HT-D) | 25% | 25% | 40% | 10% |
| Water-Dependent Industrial (WD-I) | 5% | 5% | 30% | 5% |

**Expected cell-flip count per item** = sum of 4 probabilities; **expected verdict-lift impact** = expected cell-flip count × parcel-base proxy.

luxury_garage_condo is consistently lowest because most ordinances don't enumerate it explicitly; it falls under "indoor warehouse / vehicle storage / accessory recreational" — interpretation varies by jurisdiction. Conservative bias toward catchall holds for ~50% of industrial districts.

---

## Re-ranked queue (30 items, ordered by composite impact)

### TIER 1 — HIGH IMPACT (large parcel base × high cell-flip count × low source friction)

| # | Muni | Code | District type | Muni state | Expected cell-flips (of 4) | Notes |
|---|---|---|---|---|---:|---|
| 1 | Stamford, CT | M-L | Pure Light Industrial | OPERATIONAL | 3.2 (90+90+95+50) | Industrial-anchored muni (25.5k parcels); Light Industrial = highest permit probability; single Section 5 Industrial Districts read |
| 2 | Stamford, CT | M-G | General Industrial | OPERATIONAL | 3.15 (85+85+95+50) | Same muni single-pass; General Industrial high permit probability |
| 3 | Plymouth, MN | I-1 | General Industrial | OPERATIONAL | 3.15 | I-494 corridor STACK fit; Plymouth Municode Chapter XXI single read covers I-1/I-2/I-3 |
| 4 | Plymouth, MN | I-2 | Industrial sub-numbered | OPERATIONAL | 2.95 | same Chapter XXI pass |
| 5 | Plymouth, MN | I-3 | Industrial sub-numbered | OPERATIONAL | 2.95 | same Chapter XXI pass |
| 6 | Eden Prairie, MN | I-GEN | General Industrial | OPERATIONAL | 3.15 | I-494 + US-169 corridor; Chapter 11 single read covers all 3 industrial codes |
| 7 | Eden Prairie, MN | I-2 | Industrial sub-numbered | OPERATIONAL | 2.95 | same Chapter 11 pass |
| 8 | Eden Prairie, MN | I-5 | Industrial sub-numbered | OPERATIONAL | 2.95 | same Chapter 11 pass |
| 9 | Mill Creek, WA | BP | Heavy Industrial (INDHVY) | OPERATIONAL | 3.0 (80+80+95+45) | 68 polygons; I-405 corridor; MCMC Title 17 per-district chapter (Code Publishing 403 → operator-browsable) |

**Tier 1 totals: 9 items / ~28 expected cell-flips / 4 single-source-read batches (Stamford + Plymouth + Eden Prairie + Mill Creek) / ~2-3h operator time**

### TIER 2 — MEDIUM IMPACT (moderate cell-flip count OR smaller parcel base, but still low friction)

| # | Muni | Code | District type | Muni state | Expected cell-flips | Notes |
|---|---|---|---|---|---:|---|
| 10 | Stamford, CT | IP-D | Industrial Park | OPERATIONAL | 2.8 (75+75+85+45) | Designed industrial park; FREE in Stamford batch alongside Tier 1 #1-2 |
| 11 | Stamford, CT | M-D | Industrial Mixed | OPERATIONAL | 2.3 (60+60+75+35) | Designed district variable; FREE in Stamford batch |
| 12 | Stamford, CT | HT-D | High Technology research | OPERATIONAL | 1.0 (25+25+40+10) | LOW cell-flip count but FREE in Stamford batch — read once and confirm catchall holds |
| 13 | Edina, MN | PID | Planned Industrial District | OPERATIONAL | 2.6 (70+70+80+40) | Single Chapter 36 PID section read; modest industrial concentration along I-494 |
| 14 | Minnetonka, MN | I-1 | General Industrial | OPERATIONAL | 3.15 | US-169 corridor; Chapter 3 Sec. 300.20 single read |
| 15 | Bellevue, WA | LI | Pure Light Industrial | OPERATIONAL | 3.2 | HIGH per-cell probability but small parcel base (~61 parcels per PR #266 audit); single LUC 20.10.440 read |
| 16 | Scottsdale, AZ | I-1 | General Industrial | OPERATIONAL | 3.15 | Scottsdale Airpark + south corridors; Article XI Land Use Table single read |
| 17 | Scottsdale, AZ | I-G | General Industrial | OPERATIONAL | 3.15 | same Article XI read as I-1 (FREE in Scottsdale batch) |

**Tier 2 totals: 8 items / ~21 expected cell-flips / 5 batches (Stamford remainder + Edina + Minnetonka + Bellevue + Scottsdale base) / ~2-3h operator time**

### TIER 3 — LOW IMPACT (small wealth-pocket munis; verdict-truth completeness)

| # | Muni | Code | District type | Muni state | Expected cell-flips | Notes |
|---|---|---|---|---|---:|---|
| 18 | Gig Harbor, WA | ED | Industrial Park (INDLHT) | OPERATIONAL | 2.8 | 1 polygon (schematic); residential bay-town context |
| 19 | Bainbridge Island, WA | B/I | Light Industrial (INDLHT) | OPERATIONAL | 3.2 | 6 polygons; BIMC 18.06.050.B confirms light manufacturing |
| 20 | Aspinwall, PA | AI-1 | General Industrial | OPERATIONAL | 3.15 | Small borough (1,125 parcels); compact eCode360 §27-310 read |
| 21 | Sewickley, PA | I | General Industrial | OPERATIONAL | 3.15 | Small borough (1,699 parcels); Chapter 330 Article IV; **case note**: prod uses `INST.` UPPERCASE — verify code spelling |
| 22 | Bloomfield Hills, MI | I-1 | General Industrial | OPERATIONAL | 3.15 | Ultra-wealth muni (1,833 parcels TOTAL); minimal industrial footprint; Chapter 54 read |
| 23 | Greenwich, CT | GB-IND-RE | Hybrid Business/Industrial/RE | OPERATIONAL | 1.55 (40+40+50+25) | Greenwich has very limited industrial; Division 9 + Division 21 multi-section read = higher friction |

**Tier 3 totals: 6 items / ~17 expected cell-flips / ~3-4h operator time**

### TIER 4 — VERDICT-TRUTH UNLIKELY (catchall × 4 probably holds; documentation-grade)

| # | Muni | Code | District type | Muni state | Expected cell-flips | Notes |
|---|---|---|---|---|---:|---|
| 24 | Bainbridge Island, WA | WD-I | Water-Dependent Industrial | OPERATIONAL | 0.45 (5+5+30+5) | Self-storage NOT water-dependent; catchall × 4 expected to HOLD across all cells except possibly light_industrial USE |
| 25 | Fountain Hills, AZ | IND-2 | Industrial sub-numbered | **COV-GATE-BLOCKED** | 2.95 | Cov 55.9% < 70%; **verdict-truth here doesn't help flip** (cov gate is the blocker, not the verdict) |
| 26 | Fountain Hills, AZ | M-1 | General Industrial | **COV-GATE-BLOCKED** | 3.15 | Same cov-gate constraint as IND-2 |
| 27 | Scottsdale, AZ | I-1 + overlay var 1 | Industrial overlay | OPERATIONAL | 2.25 (60+60+75+30) | Overlay imposes additional restrictions on base I-1 verdict |
| 28 | Scottsdale, AZ | I-1 + overlay var 2 | Industrial overlay | OPERATIONAL | 2.25 | overlay-specific reads required |
| 29 | Scottsdale, AZ | I-1 + overlay var 3 | Industrial overlay | OPERATIONAL | 2.25 | same |
| 30 | Scottsdale, AZ | I-G + overlay var 1 | Industrial overlay | OPERATIONAL | 2.25 | same |
| 31 | Scottsdale, AZ | I-G + overlay var 2 | Industrial overlay | OPERATIONAL | 2.25 | same |

**Tier 4 totals: 8 items / ~17 expected cell-flips / ~2-3h operator time / mostly catchall confirmations**

*(Note: queue total 31 here vs halt doc's 30 — minor classification difference on Bainbridge WD-I and Scottsdale overlay split. Doesn't affect ranking logic.)*

---

## Per-cell expected lift totals across all 31 items

Sum of probabilities across all 31 codes × 4 cells = 124 cell-decisions:

| Cell | Sum of probabilities | Expected verdict-lifts | Catchall-holds |
|---|---:|---:|---:|
| self_storage | ~21.0 | ~21 of 31 (68%) | ~10 |
| mini_warehouse | ~21.0 | ~21 of 31 (68%) | ~10 |
| light_industrial USE | ~24.5 | ~25 of 31 (81%) | ~6 |
| luxury_garage_condo | ~12.0 | ~12 of 31 (39%) | ~19 |
| **TOTAL** | **~78.5** | **~79 cell-flips of 124** | **~45 catchall-holds** |

light_industrial as a USE has the highest expected flip rate (81%) — most industrial districts permit light-industrial uses by definition. luxury_garage_condo has the lowest (39%) — niche use, catchall holds for most non-Light-Industrial-Park districts.

---

## ROI distinction by tier (operational flip potential vs query-quality lift)

| Tier | Items | Expected cell-flips | New operational flips | Query-quality lift |
|---|---:|---:|---:|---|
| Tier 1 | 9 | ~28 | **0** | HIGH (industrial-anchored munis with strong STACK acquisitions corridor fit; Stamford 25k parcels + Plymouth/Eden Prairie 494 corridor) |
| Tier 2 | 8 | ~21 | **0** | MEDIUM (mixed bag — Scottsdale Airpark fit, Bellevue BelRed fit, Edina smaller industrial footprint) |
| Tier 3 | 6 | ~17 | **0** | LOW (wealth-pocket small-borough industrial footprints; query value minimal) |
| Tier 4 | 8 | ~17 | **0** | NEGLIGIBLE (overlays + cov-blocked + water-dependent — mostly catchall holds) |
| **TOTAL** | **31** | **~79** | **0** | Net: ~79 cell-flips across ~21-25 high-value rows |

**Critical observation:** Even completing ALL 31 items at full operator-assisted cost (~10-12h Lane E time) yields **0 new operational flips**. Value is entirely downstream query accuracy.

If the goal is operational count growth, recommend:
- **Cook IL Phase 4 (Winnetka)** — gated on headless agent ingest landing; pre-staged at `winnetka_il_matrix_prestaged.md` (commit pending); 1 flip potential (38 → 39)
- **Vessel Tech B2B** — 3-5 flips
- **Maryland MDP** (nache push pending) — 4-8 flips
- **4 substrate-armed unlock** (Fox Chapel + O'Hara + Bloomfield Twp + Franklin — Diagnostic source probe gates this) — 4 flips when source unblock lands

If the goal is query-quality / acquisitions-team trust, recommend:
- **Tier 1 verdict-truth sprint** (Stamford + Plymouth + Eden Prairie + Mill Creek) — ~2-3h operator time for ~28 cell-flips on highest-value parcels

---

## Source-batching strategy (for operator dispatch)

Re-confirmed from prior ranking; batches grouped by single-source-read efficiency:

| Batch | Items | Munis | Source pass | Operator time |
|---|---|---|---|---:|
| A | 1, 2, 10, 11, 12 | Stamford (5 codes) | Section 4/5 + Appendix A | ~1.5h |
| B | 3, 4, 5 | Plymouth MN (3 codes) | Municode Chapter XXI | ~30 min |
| C | 6, 7, 8 | Eden Prairie (3 codes) | Municode Chapter 11 | ~30 min |
| D | 13, 14 | Edina + Minnetonka (2 codes) | Edina Ch. 36 PID + Minnetonka Sec. 300.20 | ~30 min |
| E | 9, 15, 18, 19, 24 | WA Code Publishing (5 codes: Mill Creek + Bellevue + Gig Harbor + 2 Bainbridge) | Multiple Code Publishing reads (operator-browsable through 403) | ~1.5h |
| F | 16, 17, 27-31 | Scottsdale base + 5 overlays (7 codes) | Article XI + overlay-specific sections | ~2h |
| G | 20, 21, 22 | Aspinwall + Sewickley + Bloomfield Hills (3 codes) | eCode360 + Chapter 54 | ~1h |
| H | 23 | Greenwich (1 code) | Division 9 + Division 21 multi-section | ~1h |
| I | 25, 26 | Fountain Hills (2 codes) | town.codes + zoning ordinance PDF | ~45 min |

**Total operator time for all 31 items: ~9-10h.**
**Tier 1 (Batches A + B + C + E partial): ~3.5h for 28 expected cell-flips on highest-value parcels.**

---

## Recommended wave-7 dispatch sequence

Sequenced by ROI-per-hour (highest cell-flips-per-operator-hour first):

| Hour | Batch | Items cleared | Expected cell-flips | Cumulative |
|---|---|---|---:|---:|
| 1-1.5 | A (Stamford 5) | 5 | ~13.5 (Tier 1: 6.35; Tier 2: 7.1) | 13.5 |
| 1.5-2 | B (Plymouth 3) | 3 | ~9.05 | 22.55 |
| 2-2.5 | C (Eden Prairie 3) | 3 | ~9.05 | 31.6 |
| 2.5-3 | D (Edina + Minnetonka 2) | 2 | ~5.75 | 37.35 |
| 3-4.5 | E (WA Code Publishing 5) | 5 | ~12.65 | 50.0 |
| 4.5-6.5 | F (Scottsdale 7) | 7 | ~17.55 | 67.55 |
| 6.5-7.5 | G (Allegheny + Oakland 3) | 3 | ~9.45 | 77.0 |
| 7.5-8.25 | I (Fountain Hills 2) | 2 | ~6.1 | 83.1 |
| 8.25-9.25 | H (Greenwich 1) | 1 | ~1.55 | 84.65 |

If operator budget capped at 4.5h, Batches A + B + C + D + E deliver ~50 cell-flips on 18 items — ~60% of total expected value in ~50% of total time.

---

## What the prior ranking missed (per Master's TRACK A spec)

| Dimension | Prior ranking | This re-ranking |
|---|---|---|
| Per-use-cell granularity | Lumped all 4 cells together as "permit probability" | Per-cell probabilities (self_storage / mini_warehouse / light_industrial / luxury_garage_condo) with district-type heuristics |
| Muni operational state cross-ref | Implicit (mostly assumed operational) | Explicit cross-ref vs lane_state.json (28 operational + 2 cov-gate-blocked + 0 substrate-pending) |
| ROI distinction | Implied all flips were valuable | **Critical correction: ALL 31 items = 0 new operational flips, pure query-quality lift** |
| Expected cell-flip count | Single 0-100% per code | Sum of 4 cell-probabilities (max 4.0 per code); total ~79 of 124 cell-decisions across all 31 items |

---

## Standing posture (unchanged)

- Verdict-truth Somerset sprint halted at 0/30 — Bergen "real ordinance citations only" hard-rule prevents orchestrator from applying lifts without source-text grounding
- Wedge cohort count holds at 38
- This re-ranking is **dispatch-prep only** — no rows authored, no apply attempted
- Standing by for Master's wave-7 path selection (a/b/c per halt doc); ROI framing above should inform whether verdict-truth ranks above or below new-ingestion sprints in the wave-7 priority queue
