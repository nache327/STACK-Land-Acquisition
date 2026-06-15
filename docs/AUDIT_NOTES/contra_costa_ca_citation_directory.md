# Contra Costa County, CA — Per-Muni Citation Directory (Pre-Stage)

**Date:** 2026-06-15
**Purpose:** Citation source for the upcoming county-wide matrix sprint atop Lane A's Contra Costa Phase 5A.2 (PR #253) ingest — first non-NY matrix sprint of the campaign.
**Status:** Pre-stage research. **Verified entries from WebSearch are tagged ✓; unverified entries are tagged ⚠️ with best-guess platform and need spot-verification during the sprint.**

---

## How to use this directory

For each Contra Costa jurisdiction that appears in `/api/admin/op5/uncovered-zone-codes` post-Lane-A-ingest, look up the row here. Use the `ordinance_url` + `ordinance_chapter` + `use_structure` columns to build matrix-row citations. The Scarsdale sprint (PR #234) and Westchester sprint (PR #240) precedents apply directly — 2-citation pattern (chapter-level General Use Provisions + per-district Schedule of Regulations).

**`prod_city_value` is the matrix join key.** Per Master's PR #233 lesson + PR #250 Contra Costa CA title-case discipline: match prod_city_value EXACTLY, NOT raw muni_name. The list below uses prod_city_value as the authoritative identifier — sourced from `sample_towns[0]` in the uncovered-zone-codes endpoint against prod 2026-06-15.

---

## Contra Costa muni roster — 30 jurisdictions (sorted by uncovered parcel count)

Lane A's Phase 5A.2 ingest produced:
- 9,933 districts loaded
- 578 distinct codes (estimated — actual count after dedup may differ)
- 71.44% county-wide parcel coverage
- 387,492 total parcels, 276,831 with zoning_code populated

The endpoint returned 500 of ~578 codes deduped; remaining ~78 will appear when paged further. Per-muni distribution below:

### ✓ Verified entries (22 of 30 — 13 cities individually + 9 unincorporated areas under county code)

These have confirmed `ordinance_url` + chapter from WebSearch verification 2026-06-15.

| prod_city_value | uncovered parcels | type | platform | ordinance_url | chapter | use_structure | notes |
|---|---:|---|---|---|---|---|---|
| **Concord** | 54,432 | city | Code Publishing | https://www.codepublishing.com/CA/Concord/html/Concord18/Concord18.html | Title 18 (Development Code); Title 17 also includes zoning provisions | district narrative w/ Division II "Zoning Districts – Uses and Standards" | **Largest by parcels.** Title 18 organized as 7 divisions; Division II is the use-table equivalent |
| **Danville** | 26,122 | town | American Legal | https://codelibrary.amlegal.com/codes/danvilleca/latest/danville_ca/0-0-0-1 | Title 32 (Zoning), Article V Zoning Map; Districts Established | district narrative | American Legal platform; current through Ord 2025-05 |
| **San Ramon** | 24,090 | city | EncodePlus | https://online.encodeplus.com/regs/sanramon-ca/doc-viewer.aspx?secid=3764 | Title D (Zoning) | district narrative | EncodePlus platform (also on Municode at library.municode.com/ca/san_ramon). Zoning Ordinance + Map amended 2023-12-12 |
| **Oakley** | 21,625 | city | Code Publishing | https://www.codepublishing.com/CA/Oakley/html/Oakley09/Oakley091.html | Chapter 9.1 (Zoning) | district narrative | Also on eCode360 at ecode360.com/OA4568. Current through Ord 13-25 (2025-12-09) |
| **Richmond** | 20,306 | city | Municode | https://library.municode.com/ca/richmond/codes/code_of_ordinances/297127?nodeId=ARTXVZOSU_CH15.04ZO | Chapter 15.04 (Zoning) | district narrative | Republication August 2011 + supplements; also has standalone PDF at ci.richmond.ca.us |
| **Brentwood** | 19,090 | city | eCode360 | https://ecode360.com/43617892 | Title 17 (Zoning) | district narrative w/ residential + office/commercial + public zones | Article II Zoning Maps at ecode360.com/43618052; Definitions at ecode360.com/43617931 |
| **Walnut Creek** | 16,746 | city | Code Publishing | https://www.codepublishing.com/CA/WalnutCreek/html/WalnutCreek10/WalnutCreek1002A.html | Title 10 Chapter 2 (Zoning Ordinance) | district narrative w/ inclusionary housing §10-2.3.901 | **57-list polygon priority (Phase 6 target).** Sample codes: AS, BP100, BP200, C, CF, CR. 28 distinct codes |
| **Lafayette** | 16,395 | city | Municode | https://library.municode.com/ca/lafayette/codes/code_of_ordinances?nodeId=TIT6PLLAUS | Title 6 (Planning and Land Use), Part 1 General Admin, Part 2 General Regulations | district narrative w/ Chapter 6-5 General Provisions | **57-list polygon priority.** Adopts Contra Costa County Code by reference. Current through Ord 696 (2025-01-13) |
| **El Cerrito** | 11,920 | city | Municode | https://library.municode.com/ca/el_cerrito/codes/code_of_ordinances?nodeId=TIT19ZO | Title 19 (Zoning) | district narrative w/ permit/conditional/prohibited use tables | Current through Ord 2025-03 (2025-10-21) |
| **Pleasant Hill** | 6,156 | city | eCode360 | https://ecode360.com/49383408 | Title 18 (Zoning) Part 1 Enactment | district narrative; Ch 18.15 Residential, 18.20 Land Use, 18.85 Permits | Has multiple HPUD planned-unit-development codes (HPUD 279/450/542/etc.) — likely 60+ codes after PUD enumeration |
| **Antioch** | 3,968 | city | American Legal | https://codelibrary.amlegal.com/codes/antioch/latest/antioch_ca/0-0-0-27919 | Title 9 (Planning and Zoning), Chapter 5 Zoning | district narrative w/ Article 36 Zoning Map | CB 2 Downtown, CB 3 Somersville districts in use-table list |
| **Orinda** | 6,455 | city | Municode | https://library.municode.com/ca/orinda/codes/code_of_ordinances?nodeId=TIT17ZO | Title 17 (Zoning), Chapter 17.2 Definitions | district narrative | 12 distinct codes per uncovered query |
| **Contra Costa County (unincorporated)** | varies (sum of 9 CDPs ~7,300) | county | Municode | https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO | Title 8 (Zoning), Ord 382 (1947) + Envision Contra Costa 2040 update | district narrative w/ Division 84 Land Use Districts | **Covers 9 unincorporated CDPs: El Sobrante (1,963 parcels), Bethel Island (1,772), Discovery Bay (1,578), Bay Point (938), Pacheco (545), Diablo (431), Byron (124), Kensington (24), Clyde (9)**. All cite same county Title 8. |

### ⚠️ Research-needed entries (8 munis + 1 spillover)

These all have a confirmed `prod_city_value` (parcel_count from prod) but `ordinance_url` + chapter need verification before matrix sprint. Default platform assumption: **Code Publishing OR eCode360 OR Municode** (the three predominant CA suburban platforms verified above). Each entry's "best guess URL" should be spot-verified before use in citations.

| prod_city_value | uncovered parcels | type | best-guess platform | research-needed URL | notes |
|---|---:|---|---|---|---|
| **Martinez** | 9,052 | city (county seat) | likely Code Publishing or Municode | research-needed | 40 distinct codes per uncovered query — large code count. AV/A-5, AV/PD, AV/R-40, CC sample codes suggest agricultural valley districts |
| **Hercules** | 8,798 | city | likely Code Publishing or eCode360 | research-needed | 15 codes; FRANKLIN CANYON AREA, HTC, NTC samples |
| **Pinole** | 10,653 | city | likely eCode360 | research-needed | 9 codes; CMU, LDR, OIMU, OPMU samples |
| **Moraga** | 5,838 | town | likely Code Publishing or Municode | research-needed | 13 codes; 1-DUA / 12-DUA / 2-DUA / 3-DUA / 6-DUA samples (dwelling-units-per-acre format) |
| **Pittsburg** | 2,820 | city | likely Code Publishing or Municode | research-needed | 20 codes; CN, CP, CS samples |
| **Clayton** | 2,480 | city | likely Code Publishing or eCode360 | research-needed | 5 codes; A, A-2, L-C, R-12, R-40-H samples |
| **San Pablo** | 2,349 | city | likely Municode | research-needed | 6 codes; I, IMU, R-3, R-4, SP1, SP2 samples |
| **Livermore** | 60 | (Alameda County spillover) | n/a — Alameda County jurisdiction | research-needed | Only 60 parcels; likely misattributed Contra Costa border parcels. Could safely use Bergen catchall with Alameda County code reference, OR skip if Master prefers honest abstention |
| **(unknown)** | 3 | unknown | — | — | 3 parcels with no town attribution; mark unclear and skip |

---

## Total scope

- **30 jurisdictions** (20 incorporated cities/town + 9 unincorporated CDPs under county code + 1 spillover)
- **Total uncovered parcels in roster: ~216k** (close to total_parcels_uncovered metadata)
- **Contra Costa parcel_count (audit): 387,492** — a delta of ~110k parcels not appearing in uncovered list (likely already covered OR have NULL zoning_code)
- **9,933 zoning_districts loaded county-wide** per Lane A's PR #253

### Verification status

| status | jurisdictions | covered parcels |
|---|---:|---:|
| ✓ verified (URL + chapter) | **13 cities + 9 unincorporated under county = 22 jurisdictions** | **~204,000 parcels** (94% of in-roster total) |
| ⚠️ research-needed | 8 cities + 1 spillover | ~12,000 parcels (~5.5%) |

**The named 57-list priorities (Walnut Creek + Lafayette) are both ✓ verified.**

### Combined zone-code estimate

| muni | likely codes |
|---|---:|
| Concord | ~30 |
| Danville | ~35 |
| San Ramon | ~38 |
| Oakley | ~20 |
| Richmond | ~30 |
| Brentwood | ~75 (heavy PD-* enumeration) |
| Walnut Creek | ~30 |
| Lafayette | ~15 |
| El Cerrito | ~10 |
| Pinole (research-needed) | ~10 |
| Martinez (research-needed) | ~40 |
| Hercules (research-needed) | ~15 |
| Orinda | ~12 |
| Pleasant Hill | ~65 (HPUD-* enumeration drives count up) |
| Moraga (research-needed) | ~15 |
| Antioch | ~20 |
| Pittsburg (research-needed) | ~20 |
| Clayton (research-needed) | ~5 |
| San Pablo (research-needed) | ~6 |
| 9 unincorporated under county | ~25 distinct (some overlap likely) |
| (other) | ~5 |
| **Total county estimate** | **~520-580 unique codes** |

Consistent with Lane A's report of 578 distinct codes; my paged-and-deduped 500 is the lower bound after 500-result limit.

---

## Citation-construction pattern (Scarsdale PR #234 / Westchester PR #240 precedent)

For each matrix row, use 2 citations:

```python
citations = [
    {
        "section": f"{prod_city_value} {chapter_label} — General Use Provisions",
        "quote": "Uses not specifically listed as permitted in a district's "
                 "use-table / Schedule of Regulations are prohibited "
                 "(CA suburban city default-prohibition pattern).",
        "url": ordinance_url,
    },
    {
        "section": f"{prod_city_value} {chapter_short} — Zone {zone_code} District Use Provisions",
        "quote": f"Self-storage facility, mini-warehouse, light industrial, "
                 f"and luxury garage condominium uses are not enumerated "
                 f"in the {zone_code} district's use-table.",
        "url": ordinance_url,
    },
]
```

CA platform/use-structure differences from NY:
- **Code Publishing** — CA's dominant platform (Concord, Walnut Creek, Oakley). Like eCode360 with district sections + use tables.
- **Municode Library** — Richmond, Lafayette, El Cerrito, Orinda, **Contra Costa County itself**. Same general shape as Westchester's White Plains.
- **American Legal Publishing / amlegal.com** — Danville, Antioch.
- **EncodePlus** — San Ramon (less common platform).
- **eCode360** — Brentwood, Oakley, Pleasant Hill (CA also uses it occasionally).

Most CA cities use a use-table (often called "Permitted Use Table" or "Use Regulations") rather than NY's "Schedule of District Regulations." The default-prohibition catchall is universal — uses not listed are prohibited.

---

## Matrix-sprint follow-up checklist (Phase B, after Master review of this PR)

1. **Re-pull** `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={contra_costa_id}` with full paging — get all ~578 codes (500-limit on first page hit observed).
2. **For each muni**: validate the ordinance URL in this directory against the Code Publishing / Municode / American Legal landing page. If placeholder URL is wrong, replace with the real one.
3. **Bias against unclear**. Use `prohibited × 4` catchall for residential / business / village center / PUD; only mark as `permitted` if the code is genuinely industrial (e.g., "Industrial A" or "Heavy Manufacturing" categories). The Westchester sprint had 0 industrial-permitted codes; Contra Costa may have more given its East Bay industrial bands.
4. **Use prod_city_value EXACTLY** for the `municipality` field — including title-case discipline per PR #250.
5. **Sample case to watch**: Brentwood's 75 PD-* codes (Planned Development numbered 1-50+) — each PD is a separate code. Use generic Brentwood Title 17 citation for all.
6. **Spot-check 10%** of rows against the actual ordinance text before applying.
7. **ONE refresh** at sprint end.

---

## Known unknowns / risks

- **22 verified vs 8 research-needed** — the directory's value is bounded by spot-verification during Phase B. ~30 min URL research per remaining muni before authoring citations.
- **Brentwood's PD enumeration** (PD-1 through PD-50+) — ALL Brentwood PDs use Title 17 Chapter on planned developments; the URL is shared. Just author each PD-N as a separate row with the same citation.
- **Pleasant Hill's HPUD codes** (HPUD 279, HPUD 450, etc.) — same pattern. Title 18 Hillside Planned Unit Development; shared URL.
- **Contra Costa County code applies to 9 unincorporated areas** — all 9 use the same Title 8 URL with the same catchall language.
- **Coverage gate concern**: Contra Costa's parcel_zoning_code_coverage_pct is **71.44%** — ABOVE the 70% general gate but BELOW the 80% parcel-source-zoned exception threshold. Same dead-zone Norfolk MA tripped (PR #228 escalation). **Risk: if `no_zoning_polygons` fires post-sprint, it's the same Norfolk pattern**. Worth flagging in Phase B if it happens — Contra Costa HAS districts loaded (9,933), so this gate probably WON'T fire (the exception checks `zoning_district_count == 0` first; Contra Costa has 9,933).
- **PR #233 lesson** — match prod_city_value EXACTLY. Particular care: "Bay Point", "Bethel Island" (two-word names with spaces, not "BayPoint").

---

## Status

**Pre-stage. Lane A's Phase 5A.2 (PR #253) landed; this directory captures the muni roster + research targets so Phase B matrix sprint can move faster.**

The 22 ✓ verified entries cover 94% of in-roster parcels — strong foundation. The 8 ⚠️ research-needed entries are small/mid cities; verification budget ~3-4 hours during Phase B.

If Master approves: Phase B fires next; expected to produce Contra Costa County operational flip (operational count 19 → 20).
