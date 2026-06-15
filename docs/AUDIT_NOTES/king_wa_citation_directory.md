# King County, WA — Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-15
**Purpose:** Pre-stage citation sources for the King WA matrix sprint after Lane A lands the Tier 2 parcel + zoning adapter clone. Target municipalities are Bellevue and Mercer Island from the 57-list, plus Medina, Hunts Point, and Clyde Hill as adjacent high-value Eastside wealth-band candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's King ingest output lands.** `prod_city_value` values below are predictions from Washington Current Parcels `SITUS_CITY_NM`; verify them against prod after ingest before authoring matrix rows.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| WAZA distinct zone-code estimate | 79 |
| Bergen-pattern fit | 2 YES / 3 PARTIAL / 0 NO |
| Expected matrix sprint hours at 5-10 min/code | 7-13h raw authoring |
| Recommended proof scope | Bellevue + Mercer Island first: 65 codes, roughly 5-11h |
| Recommended add-on scope | Medina + Hunts Point + Clyde Hill: 14 codes, roughly 1-3h |

**Recommendation:** Start with Bellevue + Mercer Island because they are the direct 57-list polygons. Add Medina, Hunts Point, and Clyde Hill in the same sprint only if Lane A's WAZA/city-zoning join already exposes their `zoning_code` values cleanly. These three add only ~14 unique WAZA codes, but they need municipal-code spot-checks because WAZA `ReferenceURL` is sparse/null for them.

**Class A/C gate note:** Washington Current Parcels carries parcel geometry and city values, not parcel-level zoning district codes. Do not treat `LANDUSE_CD` or `ORIG_LANDUSE_CD` as embedded zoning. The usable primitive remains Class A: WAZA or city zoning polygons spatially backfilled to parcels, with Lane A's required preview `ST_Within` gate before production.

---

## Live source probes used

- Washington Current Parcels: `https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0`
- Washington State Zoning Atlas / WAZA zones: `https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer/0`
- Bellevue city zoning fallback: `https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/Zoning/FeatureServer/7`

Live parcel counts by `COUNTY_NM='33' AND SITUS_CITY_NM=<city>`:

| Predicted prod_city_value | Raw parcel city | Current Parcels count |
|---|---|---:|
| `BELLEVUE` | `BELLEVUE` | 33,217 |
| `MERCER ISLAND` | `MERCER ISLAND` | 7,448 |
| `MEDINA` | `MEDINA` | 1,186 |
| `HUNTS POINT` | `HUNTS POINT` | 183 |
| `CLYDE HILL` | `CLYDE HILL` | 1,049 |

Live WAZA distinct `ZoneID` estimates:

| Jurisdiction | Distinct WAZA `ZoneID` count | Sample codes |
|---|---:|---|
| Bellevue | 53 | `R-10`, `PO`, `R-20`, `R-30`, `O`, `R-5`, `GC`, `R-2.5` |
| Mercer Island | 12 | `B`, `C-O`, `MF-2`, `MF-2L`, `MF-3`, `PBZ`, `PI`, `R-12`, `R-15`, `R-8.4`, `R-9.6`, `TC` |
| Medina | 6 | `NA`, `Public`, `R-16`, `R-20`, `R-30`, `SR-30` |
| Hunts Point | 4 | `R-20`, `R-20A`, `R-20A P`, `R-40` |
| Clyde Hill | 4 | `B-1`, `G-1`, `R-1`, `S-1` |

---

## How to use this directory

1. After Lane A's King ingest lands, re-pull the actual uncovered zone codes for King County.
2. Match matrix `municipality` to the actual prod `parcels.city` value, not to the display name here. Predicted values are uppercase because that is how Washington Current Parcels publishes `SITUS_CITY_NM`.
3. Prefer WAZA `ZoneID` for the initial matrix key if Lane A backfilled from WAZA. If Lane A falls back to a city layer, use that city layer's district field instead.
4. For Bellevue only, check whether Lane A used WAZA aliases (`R-10`, `R-20`, `GC`) or Bellevue's current city layer (`LDR-2`, `MDR-1`, `MU-H`). The two are crosswalked in the city layer via `ZONING_PreCodeAmendment2017`.
5. Bias against unclear. Residential, park, school, and small-town business districts should default to prohibited for self-storage / mini-warehouse / light industrial / luxury garage condo unless the ordinance explicitly permits the use.

---

## Bellevue

| Field | Value |
|---|---|
| Display name | Bellevue, WA |
| Predicted prod_city_value | `BELLEVUE` |
| Current Parcels coverage | YES: 33,217 rows |
| WAZA coverage | YES: 991 polygons; 53 distinct `ZoneID` values |
| City zoning fallback | YES: Bellevue `Zoning/FeatureServer/7`, 1,009 polygons |
| Canonical ordinance URL | `https://bellevue.municipal.codes/LUC` |
| Zoning section anchors | `LUC 20.10` Land Use Districts; `LUC 20.10.440` permitted uses by zone; `LUC 20.20.010` dimensional requirements |
| Bergen-pattern fit | **PARTIAL** |

Bellevue has usable online tables, but it is not a single Bergen-style countywide table. The Land Use Code uses district charts and separate development-standard sections. WAZA currently exposes several pre-middle-housing-style codes (`R-10`, `R-20`, `GC`), while the Bellevue city layer exposes current codes (`LDR-2`, `MDR-1`, `MU-H`) and a `ZONING_PreCodeAmendment2017` crosswalk.

Sample WAZA rows and citation pattern:

| Sample code | WAZA zone name | WAZA class | Citation pattern |
|---|---|---|---|
| `R-10` | Multifamily Residential R-10 | LIR / MHR2 | Cite `LUC 20.10.440` for permitted uses plus `LUC 20.20.010` for district dimensional chart. |
| `PO` | Professional Office | COM / COMOFFI | Cite `LUC 20.10.440`; office district needs explicit use-table read before any permitted classification. |
| `R-20` | Multifamily Residential R-20 | LIR / MHR3-4 | Same Bellevue chart pattern; likely residential/multifamily, not storage/industrial. |
| `R-5` | Single-Family Residential 5 | LIR / SR1-5 | Same Bellevue chart pattern; residential district. |
| `GC` | General Commercial | COM / COMOFFI | Cite `LUC 20.10.440`; commercial code needs spot-check for storage-like uses. |

Bellevue city-layer crosswalk sample:

| Current city zoning | Description | WAZA / old-code analog |
|---|---|---|
| `LDR-2` | Middle Housing | `R-10` |
| `MDR-1` | Middle Housing | `R-20` |
| `MDR-2` | Middle Housing | `R-30` |
| `MU-H` | Mixed Use Highrise | `GC` |
| `SR-4` | Middle Housing | `R-5` |

Sprint note: if Lane A uses WAZA, matrix rows probably need WAZA `ZoneID`. If Lane A uses Bellevue's city zoning fallback, matrix rows probably need current city `Zoning`. Do not author both until the ingest output is known.

---

## Mercer Island

| Field | Value |
|---|---|
| Display name | Mercer Island, WA |
| Predicted prod_city_value | `MERCER ISLAND` |
| Current Parcels coverage | YES: 7,448 rows |
| WAZA coverage | YES: 48 polygons; 12 distinct `ZoneID` values |
| City zoning fallback | YES: `Mercer_Island_Planning_Layers/FeatureServer/2`, 82 polygons |
| Canonical ordinance URL | `https://library.municode.com/wa/mercer_island/codes/city_code?nodeId=CICOOR_TIT19UNLADECO` |
| Zoning section anchors | Title 19 Unified Land Development Code; Chapter 19.02 Residential; Chapter 19.03 Multi-Family; Chapter 19.04.050 Business; Chapter 19.11 Town Center |
| Bergen-pattern fit | **YES** |

Mercer Island is the cleanest direct 57-list sprint target. WAZA has ordinance URLs for residential zones, and the city zoning layer has clear local `ZONING` values.

Sample WAZA rows and citation pattern:

| Sample code | WAZA zone name | WAZA class | Citation pattern |
|---|---|---|---|
| `R-15` | Residential, minimum 15,000 sq ft lot | LIR / SR1-5 | Cite MICC Title 19.02 residential zones. |
| `R-9.6` | Residential, minimum 9,600 sq ft lot | LIR / SR1-5 | Cite MICC Title 19.02 residential zones. |
| `R-8.4` | Residential, minimum 8,400 sq ft lot | LIR / SR5-12 | Cite MICC Title 19.02 residential zones. |
| `MF-2` | Multi-family, max density 38 units/acre | Residential multifamily | Cite MICC Title 19.03 multi-family zones. |
| `TC` | Town Center | Mixed use / town center | Cite MICC Title 19.11; spot-check uses before classifying. |
| `B` | Business | Commercial | Cite MICC 19.04.050; spot-check uses before classifying. |

Sprint note: the likely first matrix batch is 12 rows. Residential zones can be handled quickly; `TC`, `B`, `C-O`, `PBZ`, and `PI` need individual use checks.

---

## Medina

| Field | Value |
|---|---|
| Display name | Medina, WA |
| Predicted prod_city_value | `MEDINA` |
| Current Parcels coverage | YES: 1,186 rows |
| WAZA coverage | YES: 1,271 polygons; 6 distinct `ZoneID` values |
| Canonical ordinance URL | `https://library.municode.com/wa/medina/codes/code_of_ordinances` |
| Zoning section anchors | Title 16 Unified Development Code; Chapter 16.20 official zoning map / districts; Chapter 16.21.030 use table |
| Zoning map backup | `https://www.medina-wa.gov/sites/default/files/fileattachments/development_services/page/17966/medina_zones_tree_inventory_project_zone_1.pdf` |
| Bergen-pattern fit | **YES** |

Medina is small and highly sprintable once zoning codes are populated. WAZA `ReferenceURL` was null in sampled rows, but the municipal code and city zoning-map PDF expose the necessary zone list. Search-indexed Medina ordinance text shows `Table 16.21.030` as a land-use table across `R-16`, `R-20`, `R-30`, `SR-30`, `NA`, and `Public`.

Sample WAZA rows and citation pattern:

| Sample code | WAZA zone name | WAZA class | Citation pattern |
|---|---|---|---|
| `R-16` | Single Family Residence | LIR / SR1-5 | Cite MMC 16.20 district list + MMC 16.21.030 use table. |
| `R-20` | Single Family Residence | LIR / SR1-5 | Cite MMC 16.20 district list + MMC 16.21.030 use table. |
| `R-30` | Single Family Residence | LIR / SR1-5 | Cite MMC 16.20 district list + MMC 16.21.030 use table. |
| `SR-30` | Suburban Gardening Residential | Low-intensity residential | Cite MMC 16.20 district list + MMC 16.21.030 use table. |
| `Public` | Parks and Public Spaces | OS / OS | Cite zoning map + use table; likely parks/public only. |

Sprint note: expect 6 rows. `NA` may require a specific commercial/auto-service read; do not bulk-class it from residential assumptions.

---

## Hunts Point

| Field | Value |
|---|---|
| Display name | Hunts Point, WA |
| Predicted prod_city_value | `HUNTS POINT` |
| Current Parcels coverage | YES: 183 rows |
| WAZA coverage | YES: 198 polygons; 4 distinct `ZoneID` values |
| Canonical ordinance URL | `https://ecode360.com/HU4811` |
| Zoning section anchors | Title 18 Zoning; Chapter 18.15 zone classifications; Chapter 18.31 R-40; Chapter 18.35 R-20; Chapter 18.37 R-20A; Chapter 18.38 R-20A Flex |
| Zoning map backup | `https://huntspoint-wa.gov/vertical/sites/%7BC1015BB4-DD89-4FBF-BEA2-28483C12923F%7D/uploads/THP_Zoning_Map_2025.pdf` |
| Bergen-pattern fit | **PARTIAL** |

Hunts Point is tiny but not a clean use-table workflow. eCode360 exposes district chapters, with residential districts enumerated by chapter and bulk/accessory standards. The zoning map confirms `R40`, `R20`, and `R20A` variants.

Sample WAZA rows and citation pattern:

| Sample code | WAZA zone name | WAZA class | Citation pattern |
|---|---|---|---|
| `R-40` | Residential 40,000 sq ft lot | LIR / SR1-5 | Cite Chapter 18.31 R-40; residential use/bulk chapter. |
| `R-20` | Residential 20,000 sq ft lot | LIR / SR1-5 | Cite Chapter 18.35 R-20; residential use/bulk chapter. |
| `R-20A` | Residential 12,000 sq ft lot | LIR / SR1-5 | Cite Chapter 18.37 R-20A; residential use/bulk chapter. |
| `R-20A P` | R-20A park/property variant | Low-intensity public/residential | Cite zoning map plus relevant R-20A chapter; verify exact source label after ingest. |

Sprint note: expect only 4 rows, but citations are district-chapter/narrative rather than Bergen-style use table. This is still matrix-sprintable because every code is narrow and residential/public.

---

## Clyde Hill

| Field | Value |
|---|---|
| Display name | Clyde Hill, WA |
| Predicted prod_city_value | `CLYDE HILL` |
| Current Parcels coverage | YES: 1,049 rows |
| WAZA coverage | YES: 1,141 polygons; 4 distinct `ZoneID` values |
| Canonical ordinance URL | `https://ecode360.com/CL4389` |
| City zoning page | `https://clydehill.org/government/departments/building_planning/land_use/zoning.php` |
| Zoning section anchors | CHMC Title 17 Zoning; Chapter 17.12 establishment of districts / zoning map; Chapter 17.16 R-1; Chapter 17.18 G-1; Chapter 17.19 S-1; Chapter 17.28 B-1 |
| Bergen-pattern fit | **PARTIAL** |

Clyde Hill has a clean online code and very few districts, but the code is district-chapter based rather than a single zone-code use table. The city zoning page states that CHMC Chapter 17 governs land use and lists city zoning districts, including `R-1`.

Sample WAZA rows and citation pattern:

| Sample code | WAZA zone name | WAZA class | Citation pattern |
|---|---|---|---|
| `R-1` | Residence District | LIR / SR1-5 | Cite CHMC Chapter 17.16 R-1 residence district. |
| `G-1` | Government District | Public/institutional | Cite CHMC Chapter 17.18 G-1. |
| `S-1` | School District | Public/institutional | Cite CHMC Chapter 17.19 S-1; eCode lists schools, parks, and G-1 uses. |
| `B-1` | Business District | COM / COMRET | Cite CHMC Chapter 17.28 B-1; spot-check before any permitted/commercial classification. |

Sprint note: expect 4 rows. `B-1` is the only code that needs real use-level care; the rest are low-risk residential/public districts.

---

## Recommended King matrix sprint sequence

1. **Mercer Island** — 12 codes, clean Municode, direct 57-list polygon.
2. **Bellevue residential/current-code reconciliation** — confirm WAZA vs Bellevue city-layer code key, then author the high-volume residential/commercial rows.
3. **Bellevue commercial/mixed-use tail** — spot-check `GC`, `O`, `PO`, `MU-H`, business-retail, and downtown/mixed-use codes.
4. **Medina** — 6 codes, table-driven, strong adjacent wealth value.
5. **Hunts Point + Clyde Hill** — 8 combined codes, very small towns; district-chapter citations are enough.

If the sprint budget is tight, stop after Mercer Island + the first Bellevue batch. If Lane A has cleanly populated all five city values from WAZA, the adjacent three towns are cheap enough to include.

---

## Known risks / follow-up checks

- **`prod_city_value` uncertainty:** King is not loaded today, so matrix join keys must be verified from prod after Lane A's adapter writes parcels. Raw source values are uppercase.
- **Bellevue code vintage mismatch:** WAZA sample rows use codes like `R-10` and `GC`; Bellevue's city layer now exposes `LDR-2`, `MDR-1`, `MU-H`, etc. Do not author Bellevue rows until the actual `parcels.zoning_code` values are known.
- **WAZA sparse references for small towns:** Medina, Hunts Point, and Clyde Hill samples had null `ReferenceURL`; use municipal code anchors manually.
- **District narrative for tiny towns:** Hunts Point and Clyde Hill are not Bergen-style use tables, but their code sets are so small that manual district-chapter citations should be fast.
- **Commercial edge cases:** Bellevue `GC`/`O`/`PO`, Mercer Island `B`/`TC`, Medina `NA`, and Clyde Hill `B-1` need explicit use checks.

---

## Status

Pre-stage only. No code, no ingest, no matrix authoring. Use this document as the citation checklist once Lane A's King Tier 2 adapter output is available.
