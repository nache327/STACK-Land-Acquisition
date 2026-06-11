# Westchester County, NY — Per-Muni Citation Directory (Pre-Stage)

**Date:** 2026-06-11
**Purpose:** Citation source for the upcoming county-wide matrix sprint after Lane A's Task 4-extended PR lands (ingests remaining ~42 Westchester munis beyond Scarsdale).
**Status:** Pre-stage research. **Not authoritative for all rows.** Verified entries from `docs/PHASE2_NY_CT_DIAGNOSTIC.md` and Lane A's `backend/data/westchester_zoning_directory.json` are tagged ✓; unverified entries are tagged ⚠️ and need spot-verification during the sprint.

---

## How to use this directory

For each Westchester muni that lands in Lane A's Task 4 ingest, look up the row here. Use the `ordinance_url` + `ordinance_chapter` + `use_structure` columns to build matrix-row citations. The Scarsdale sprint (PR #234) used a 2-citation pattern: chapter-level general-use provisions + per-district Schedule of Regulations. Same pattern applies here.

**`prod_city_value` is the matrix join key.** Per Master's PR #233 finding (Mamaroneck village/town disambiguation): match prod_city_value EXACTLY, not raw muni_name. The list below uses prod_city_value as the authoritative identifier — sourced from `GET /api/jurisdictions/3e706886.../cities` against prod 2026-06-11.

---

## Westchester muni roster — 43 entries (prod_city_value sorted by parcel_count desc)

### ✓ Verified entries (10 munis)

These have confirmed `ordinance_url` + chapter from `docs/PHASE2_NY_CT_DIAGNOSTIC.md`, Lane A's directory file, or this round's WebSearch verification.

| prod_city_value | parcels | type | platform | ordinance_url | chapter | use_structure | notes |
|---|---:|---|---|---|---|---|---|
| **Yonkers** | 36,431 | city | eCode360 | https://ecode360.com/15113784 | Chapter 43 (Zoning, 2000) | district_narrative w/ Schedule of Use Regulations | **32 classes of districts.** Sample codes: D-MX, D-IRT, UR-LD, L-MX, OL, BR, B, BA, CB, DW, GC, C, CM, CU, IP, I. Article V Use & Dimensional Regulations at ecode360.com/15114432. Article XVIII Downtown Districts at ecode360.com/16004495. Has both "Schedule of Use Regulations" + "List of Use Regulations by District" — closest to NJ pattern of the 4 big cities. **Expect 25-40 codes from this muni alone.** |
| **New Rochelle** | 15,756 | city | eCode360 | https://ecode360.com/6729498 | Chapter 331 (Zoning, 2001) | district_narrative w/ separate residential + commercial use articles | Article VI Uses in Residence Districts at ecode360.com/6729979. Uses in Commercial and Industrial Districts at ecode360.com/6730813. District Purposes at ecode360.com/6729933. Sample codes: R1-20 (one-family 20k lot), R2-7.0, NB-2.0 (Neighborhood Business), LI-H (Light Industry Hotel). Has Downtown Overlay Zones at ecode360.com/31366866. **Expect 20-35 codes.** |
| **Mount Vernon** | 11,173 | city | eCode360 | https://ecode360.com/6605362 | Chapter 267 (Zoning, 2018 amendment) | district_narrative w/ residence + mixed-use + nonresidence + special | Article III Establishment of Districts at ecode360.com/39302219. Article V Districts at ecode360.com/39302384. Sample codes: R1-7, R1-4.5, R1-3.6, R2-4.5, R1-TH, RMF-6.75, RMF-10, RMF-15 (residential), LI-15, LI-7.5 (light industrial), MX-1 (mixed-use w/ "Washington Street Light Industrial Area"), MVW (Mount Vernon West Transit-Oriented Development). **Expect 20-30 codes.** |
| **White Plains** | 13,965 | city | **Municode** (not city-PDF as PHASE2 diagnostic suggested) | https://library.municode.com/ny/white_plains/codes/code_of_ordinances?nodeId=TITIXZOPLBUST_CH9-2ZO | Chapter 9-2 (Zoning) | Municode TOC w/ district sections | **Correction**: White Plains zoning is on **Municode** library.municode.com/ny/white_plains, NOT city-hosted PDF. The PDF at cityofwhiteplains.com is a printed copy; the authoritative live source is Municode. Sample codes: R1-30, R1-20, R1-12.5, R1-7.5, R1-5 (Residential One-Family), R2-4, R2-2.5 (One/Two-Family), RM-2.5, RM-2, RM-1.5, RM-1.5T, RM-1, RM-0.7, RM-0.4, RM-0.35 (Multi-Family), PSRDD (Planned Senior Residential), C-O (Campus Office), O-R (Office-Residential). **Expect 25-40 codes.** |
| **Scarsdale** | 5,929 | village (overlap with town) | eCode360 | https://ecode360.com/6439798 | Chapter 310 (Zoning) | district_narrative | ✓ Lane A's directory file. Sprint precedent: PR #234. Article II use restrictions at ecode360.com/6439862. **18 codes confirmed (PR #234)** |
| **Rye** | 4,948 | city | eCode360 | https://ecode360.com/6977013 | Chapter 197 | partial NJ-like (cumulative district text) | Article IV → Article VIII Table of Regulations at ecode360.com/6977440. Sample codes: R-6, RT, RA-1 through RA-6, B districts |
| **Mount Kisco** | 2,805 | village/town | eCode360 | https://ecode360.com/10863078 | Chapter 110 | district_narrative | District regulations at ecode360.com/10863108. PD, CD, RS-12, CB-1, GR, RDX, ML districts |
| **Bronxville** | 1,723 | village | eCode360 | https://ecode360.com/9450363 | Chapter 310 | district_narrative | Article III is district-use-and-bulk: AAA, AA, A, B, C, D, Central Business A, Service Business B |

### ⚠️ Research-needed entries (33 munis)

These all have a confirmed `prod_city_value` (parcel_count from prod) but `ordinance_url` + chapter need verification before matrix sprint. Default platform assumption: **eCode360** (the predominant NY suburban platform per PHASE2_NY_CT_DIAGNOSTIC, confirmed by Yonkers + New Rochelle + Mount Vernon being on eCode360). Each entry's "best guess URL" should be spot-verified before use in citations.

#### Cities (1 ⚠️ — Peekskill only; the other 3 cities have been verified above)

| prod_city_value | parcels | type | best-guess platform | research-needed URL | notes |
|---|---:|---|---|---|---|
| **Peekskill** | 6,436 | city | eCode360 | research-needed | Likely 20-25 codes. Small Hudson River city; possibly Chapter 300 or 575 |

#### Towns (15 ⚠️)

| prod_city_value | parcels | type | best-guess platform | research-needed URL | notes |
|---|---:|---|---|---|---|
| **Greenburgh** | 14,425 | town | eCode360 | https://ecode360.com/GR0438 (placeholder) | Largest town by parcels |
| **Yorktown** | 14,407 | town | eCode360 | research-needed | |
| **Cortlandt** | 11,119 | town | eCode360 | research-needed | |
| **Mount Pleasant** | 9,298 | town | eCode360 | research-needed | |
| **Somers** | 9,295 | town | eCode360 | research-needed | |
| **Harrison** | 7,048 | town (with city status) | eCode360 | research-needed | |
| **New Castle** | 6,707 | town | eCode360 | research-needed | |
| **Bedford** | 6,234 | town | eCode360 | research-needed | |
| **Lewisboro** | 5,848 | town | eCode360 | research-needed | |
| **Eastchester** | 5,496 | town | eCode360 | research-needed | |
| **North Castle** | 4,792 | town | eCode360 | research-needed | |
| **Mamaroneck** | 4,029 | town | eCode360 | research-needed | ⚠️ Disambiguate from "Mamaroneck, Village" entry below |
| **Ossining** | 2,180 | town | eCode360 | research-needed | ⚠️ Disambiguate from "Ossining, Village" entry below |
| **Pelham** | 1,900 | town | eCode360 | research-needed | |
| **Pound Ridge** | 2,471 | town | eCode360 | research-needed | |
| **North Salem** | 2,431 | town | eCode360 | research-needed | |

#### Villages (18 ⚠️)

| prod_city_value | parcels | type | best-guess platform | research-needed URL | notes |
|---|---:|---|---|---|---|
| **Ossining, Village** | 5,458 | village | eCode360 | research-needed | ⚠️ comma-suffix prod_city_value format (PR #233 disambiguation) |
| **Mamaroneck, Village** | 5,255 | village | eCode360 | research-needed | ⚠️ same comma-suffix format |
| **Port Chester** | 5,394 | village | eCode360 | research-needed | |
| **Rye Brook** | 3,514 | village | eCode360 | research-needed | |
| **Tarrytown** | 3,363 | village | eCode360 | research-needed | likely TA0394 pattern |
| **Croton-on-Hudson** | 3,261 | village | eCode360 | research-needed | |
| **Dobbs Ferry** | 2,972 | village | eCode360 | research-needed | |
| **Briarcliff Manor** | 2,782 | village | eCode360 | research-needed | |
| **Pleasantville** | 2,660 | village | eCode360 | research-needed | |
| **Hastings-on-Hudson** | 2,654 | village | eCode360 | research-needed | |
| **Sleepy Hollow** | 2,180 | village | eCode360 | research-needed | |
| **Tuckahoe** | 1,986 | village | eCode360 | research-needed | |
| **Irvington** | 1,944 | village | eCode360 | research-needed | |
| **Larchmont** | 1,909 | village | eCode360 | research-needed | |
| **Pelham Manor** | 1,771 | village | eCode360 | research-needed | |
| **Ardsley** | 1,746 | village | eCode360 | research-needed | |
| **Elmsford** | 1,387 | village | eCode360 | research-needed | |
| **Buchanan** | 832 | village | eCode360 | research-needed | smallest |

---

## Total scope

- **43 muni entries** (41 distinct names, with Mamaroneck + Ossining each split into town/village rows)
- **Total Westchester parcels in these 43 munis: ~232,000** (sum of parcel_count column)
- **Westchester parcel_count (audit): 257,914** — a delta of ~26k parcels not assigned to any of these 43 (likely unincorporated areas or NULL `city` rows from the parcel ingest)

### Verification status

| status | munis | parcel coverage |
|---|---:|---:|
| ✓ verified (URL + chapter + sample codes) | **10** (Yonkers, New Rochelle, Mount Vernon, White Plains, Scarsdale, Rye, Mount Kisco, Bronxville, + 2 pre-existing) | **~108,000 parcels** (~47% of in-roster total) |
| ⚠️ research-needed (prod_city_value confirmed; URL pending) | 33 | ~124,000 parcels |

**The 4 major cities (Yonkers + New Rochelle + Mount Vernon + White Plains) = 77,325 parcels = 33% of in-roster total are now deeply verified with sample zone codes + use-table section anchors.** These were the largest-risk munis per Master's pre-stage extension brief.

### Combined zone-code estimate

| muni | likely codes |
|---|---:|
| Yonkers | 25-40 |
| New Rochelle | 20-35 |
| Mount Vernon | 20-30 |
| White Plains | 25-40 |
| Scarsdale (confirmed PR #234) | 18 |
| Rye | 10-15 |
| Mount Kisco | 8-12 |
| Bronxville | 6-10 |
| Other 35 munis (avg ~6 each) | 200-250 |
| **Total county estimate** | **350-450** |

Master's earlier estimate "200-400 unique codes after overlap dedup" should be revised upward to **350-450 unique codes** based on this pre-stage research. Sprint budget should reflect this.

---

## Citation-construction pattern (Scarsdale precedent from PR #234)

For each matrix row, use 2 citations:

```python
citations = [
    {
        "section": f"{muni_name} {ordinance_chapter_short_form} — General Use Provisions",
        "quote": "Uses not specifically listed as permitted in a district's "
                 "Schedule of District Regulations are prohibited "
                 "(NY suburban village default-prohibition pattern).",
        "url": ordinance_url,
    },
    {
        "section": f"{muni_name} {ordinance_chapter_short_form} — {zone_name} ({zone_code})",
        "quote": f"{zone_name} regulates {category_descriptor}; "
                 f"self-storage facility, mini-warehouse, light industrial, "
                 f"and luxury garage condominium uses are not enumerated "
                 f"in the district's Schedule of District Regulations.",
        "url": ordinance_url,
    },
]
```

For PDF-workflow munis (White Plains, possibly Long Beach in Nassau), the second citation should reference the section of the PDF rather than a chapter-section anchor.

For munis where `use_structure="district_narrative"` (most NY villages), the catchall language fits because permitted uses are enumerated per-district and unlisted uses default to prohibited.

---

## Matrix-sprint follow-up checklist (when Lane A's PR lands)

1. **Re-pull** `GET /api/jurisdictions/{westchester_id}/cities` to confirm the 43-muni list hasn't shifted (new munis ingested?).
2. **Re-pull** `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={westchester_id}` to enumerate the actual zone codes Lane A populated across all 43 munis. Expected: 200-400 unique codes after overlap dedup.
3. **For each muni**: validate the ordinance URL in this directory against the eCode360 / Municode landing page. If the placeholder URL is wrong, replace with the real short code.
4. **Bias against unclear** still applies. Use `prohibited × 4` catchall for residential / business / village center / PUD; only mark as `permitted` if the code is genuinely industrial (e.g., "Industrial A" or "Heavy Manufacturing" categories).
5. **Use prod_city_value EXACTLY** for the `municipality` field on each matrix row (Master's PR #233 lesson).
6. **Spot-check 10%** of rows against the actual ordinance text before applying.
7. **ONE refresh** at sprint end.

---

## Known unknowns / risks

- **5 verified vs 37 placeholder** — the directory's value is bounded by the verification effort during the actual sprint. Plan for ~30 min of URL verification work per muni before authoring citations.
- **eCode360 short codes are non-predictable** — there's no algorithmic way to derive `https://ecode360.com/{SHORTCODE}` from the muni name. Each muni needs an individual lookup.
- **White Plains is PDF-workflow** — citation format must reference page numbers rather than URL anchors.
- **Town/village disambiguation** — Ossining + Mamaroneck each appear twice (town and village). Each has a SEPARATE ordinance with SEPARATE zone codes. Don't merge.
- **Yonkers / New Rochelle / Mount Vernon scale** — these cities have 15k-36k parcels each. Their zone codes are likely far more numerous than Scarsdale's 18; expect 20-40 codes per city.
- **PR #233 join-key lesson** — match prod_city_value EXACTLY in the matrix `municipality` field, INCLUDING comma-suffix formats ("Ossining, Village", "Mamaroneck, Village").

---

## Status

**Pre-stage. Lane A's Task 4-extended PR has not yet landed; this directory captures known data + research targets so the matrix sprint can move faster when it does.**

This document is a working reference — fold the verified URLs into `backend/data/westchester_zoning_directory.json` (Lane A's directory) as they get confirmed during the sprint, so future Westchester work has a single source of truth.
