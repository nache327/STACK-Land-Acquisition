# Allegheny PA Wealth Munis Matrix Pre-Stage — FINAL WEDGE COUNTY

**Date:** 2026-06-18
**Purpose:** Pre-author 26 rows across 5 Allegheny PA wealth munis. **Fifth and FINAL wedge cohort county** — closes the WA + MN + AZ + CT + MI + PA per-muni cohort. Master-dispatched forward-velocity push during Hennepin wave Plymouth/Eden Prairie wait.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** ALL ordinance-derived per Diagnostic PR #263 (no live ArcGIS sources verified). Per-district narrative pattern. Bergen catchall × 4.

**⚠️ CASE-DISCIPLINE NOTE (6TH PATTERN)**: PA Allegheny uses **title-case + Borough/Township suffix**:
- `Fox Chapel Borough`
- `O Hara Township` ← **apostrophe-to-space transform** ("O'Hara" → "O Hara")
- `Aspinwall Borough`
- `Sewickley Borough`
- `Sewickley Heights Borough`

Sixth distinct case discipline in wedge cohort:
1. WA/MN/CT: title-case bare (Bellevue, Edina, Stamford)
2. AZ Maricopa: UPPERCASE bare (SCOTTSDALE)
3. MI Oakland: UPPERCASE + political-entity prefix (CITY OF BIRMINGHAM, VILLAGE OF FRANKLIN, CHARTER TOWNSHIP OF BLOOMFIELD)
4. **PA Allegheny: title-case + Borough/Township suffix + apostrophe-to-space**

---

## Per-muni summary

| muni | parcels (spec) | rows | industrial flag | source |
|---|---:|---:|---|---|
| Fox Chapel Borough (57-list) | 2,179 | 5 | none | eCode360 + Chapter 400 |
| O Hara Township | 4,348 | 6 | SM (1) | eCode360 + Chapter 455 |
| Aspinwall Borough | 1,125 | 6 | AI-1 (1) | eCode360 + Chapter 27 |
| Sewickley Borough | 1,699 | 6 | none | eCode360 + Chapter 330 |
| Sewickley Heights Borough | 452 | 3 | none | Ordinance No. 294 (PDF extraction required) |
| **Total** | **9,803** | **26** | **2** | — |

**Smallest wedge county pre-stage** (vs Maricopa 301, Oakland 65, Hennepin 120). Allegheny is **low-ROI Class B/manual fallback** per Diagnostic — useful for 57-list completion but won't flip countywide readiness.

---

## Fox Chapel Borough (5 codes — direct 57-list polygon)

**Wealth pocket primary target.** eCode360 Chapter 400 Zoning + Attachment 1 (schedule) + Attachment 2 (district map).

| Code | Category |
|---|---|
| A | Class A Residence (3-acre min lot) |
| B | Class B Residence (2-acre min lot) |
| C | Class C Residence (1-acre min lot) |
| D | Class D Residence (recorded lots) |
| I-O | Institutional/Open Space |

No industrial. Pure wealth-pocket borough (estate-residential + institutional only).

URL: `https://ecode360.com/31904910`

---

## O Hara Township (6 codes — apostrophe-to-space)

eCode360 Chapter 455 Zoning + §455-3.2 + zoning map PDF.

| Code | Category |
|---|---|
| R-1 | Special Residential |
| R-2 | Suburban Residential |
| R-3 | Urban Residential |
| R-4 | Special Moderate-Density Residential |
| C | Commercial |
| **SM** | **Suburban Manufacturing — cleanup candidate** |

`SM` flagged for verdict-truth post-ingest.

URL: `https://ecode360.com/31391570`

---

## Aspinwall Borough (6 codes)

eCode360 Chapter 27 + Part 3 schedule + §§27-303 to 27-311.

| Code | Category |
|---|---|
| AR-1 | Single Family Residential |
| AR-2 | Residential |
| AR-3 | Single and Multiple Family |
| AR-4 | Multifamily Residential |
| AC-2 | General Commercial |
| **AI-1** | **Limited Industrial — cleanup candidate** |

`AI-1` flagged for verdict-truth post-ingest.

URL: `https://ecode360.com/30911259`

---

## Sewickley Borough (6 codes)

eCode360 Chapter 330 + §330-401 + Article IV + principal/accessory use tables.

| Code | Category |
|---|---|
| R-1 | Single-Family Residential |
| R-1A | Single-Family Residential |
| R-2 | Multifamily Residential |
| C-1 | General Commercial |
| C-2 | Highway Commercial |
| Inst. | Institutional |

No industrial.

URL: `https://ecode360.com/32411085`

---

## Sewickley Heights Borough (3 PREDICTED codes — source extraction required)

**HIGHEST PATH B RISK in the wedge cohort.** No eCode360. Codes derived from Diagnostic guesses against Ordinance No. 294. Source extraction required at apply-time.

| Code | Category | Confidence |
|---|---|---|
| Residential estate | Residential Estate (predicted) | LOW |
| Conservation | Conservation/Open Space (predicted) | LOW |
| Institutional | Institutional/Club-related (predicted) | LOW |

URL: `https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances`

**Sewickley Heights warning per Diagnostic**: "Do not include in a first Allegheny proof unless Master explicitly values the small high-end enclave over clean execution. Only 452 parcels and has the highest citation/source friction in this set."

---

## Cleanup candidate queue update

**Allegheny additions (2)**:
- O Hara Township: SM (Suburban Manufacturing)
- Aspinwall Borough: AI-1 (Limited Industrial)

**Campaign total cleanup queue now: 19 items** (WA 4 + Hennepin 4 + Maricopa 2 + Stamford 5 + Oakland 2 + Allegheny 2).

---

## Apply procedure

When Lane A's Allegheny Phase 7D ingest lands (low priority per Diagnostic — only Fox Chapel is 57-list):

### Path A (Fox Chapel — most likely)

Apply 5 rows; expected fast Path A given small district count and clear ordinance citations.

### Path B (O Hara + Aspinwall + Sewickley)

eCode360-derived codes well-documented but no live layer to verify. Apply pre-stage + re-author any surfaced codes.

### Path C (Sewickley Heights)

Apply only after Lane A extracts Ordinance No. 294 codes. 3 predicted rows are placeholders; verify or replace at apply-time.

---

## Pre-stage artifacts

- `/tmp/op5_allegheny_prestage.py` — authoring script for all 5
- `/tmp/op5_allegheny_fox_chapel_borough_prestage_rows.json` (5 rows)
- `/tmp/op5_allegheny_o_hara_township_prestage_rows.json` (6 rows)
- `/tmp/op5_allegheny_aspinwall_borough_prestage_rows.json` (6 rows)
- `/tmp/op5_allegheny_sewickley_borough_prestage_rows.json` (6 rows)
- `/tmp/op5_allegheny_sewickley_heights_borough_prestage_rows.json` (3 PREDICTED rows; verify at apply)

---

## WEDGE COHORT CAMPAIGN-LEVEL COMPLETION

**5 of 5 wedge counties now pre-staged** (per-muni Op-5 cohort complete):

| county | state | munis | total rows | status |
|---|---|---:|---:|---|
| King (Bellevue/Mercer/Bainbridge/Mill Creek/Gig Harbor) | WA | 5 | 105 | **ALL FLIPPED** (campaign-week count → 25) |
| Hennepin (Edina/Plymouth/Eden Prairie/Minnetonka/Wayzata) | MN | 5 | 120 | 1/5 flipped (Edina → 26); 4 pending Lane A |
| Maricopa (Scottsdale/Fountain Hills/Paradise Valley/Cave Creek/Carefree) | AZ | 5 | 301 | Pre-staged; awaiting Lane A Phase 7B |
| Fairfield (Stamford full + 4 citations-only) | CT | 5 | 42 + chapter anchors | Pre-staged; awaiting Lane A Phase 7C |
| Oakland (Birmingham/Bloomfield Hills/Beverly Hills/Bloomfield Township/Franklin) | MI | 5 | 65 | Pre-staged; awaiting Lane A Phase 7E |
| **Allegheny (Fox Chapel/O Hara/Aspinwall/Sewickley/Sewickley Hts)** | **PA** | **5** | **26** | **Pre-staged; awaiting Lane A Phase 7F** |

**Total per-muni pre-stage substrate: 659 rows across 25 munis** spanning **6 case-discipline patterns** + 4 ordinance pattern shapes + **19 cleanup candidates**.

---

## Operational count campaign trajectory

Confirmed (this campaign-week): **26** (13 baseline + WA wave 5 + Edina + 2 regressions = 13+15-2=26)

If all wedge cohort flips execute cleanly:
- + Plymouth + Eden Prairie + Minnetonka + Wayzata: +4 (Hennepin completion) → 30
- + Maricopa 5: +5 → 35
- + Fairfield 5: +5 → 40
- + Oakland 5: +5 → 45
- + Allegheny 5: +5 → 50

**Theoretical maximum: 50 operational by end of wedge cohort execution.** (Subject to per-muni cov gates, ingest source quality, and Lane A's Phase landings.)
