# Tier 4 Matrix Sprint Readiness

Date: 2026-06-15

Purpose: read-only readiness forecast for matrix-authoring work that will remain after Tier 2 multi-county parcel/zoning carry sources land. Scope covers Washington Current Parcels/WAZA carry counties, MetroGIS Twin Cities carry counties, and the speculative SEMCOG Detroit-metro carry.

## Executive Summary

The Tier 2 carries create real adapter leverage, but they do **not** make the downstream matrix queue cheap if Master wants countywide operational coverage.

- **Verified carry backlog, excluding speculative SEMCOG:** about **1,320 estimated unique/local zone codes**, or **110-220 matrix authoring hours** at Bergen's 5-10 min/code rate.
- **Including speculative Wayne + Macomb:** about **1,800 estimated codes**, or **150-300 hours**.
- **Current prod state:** none of the WA/MN/MI carry counties below are registered as their target county in prod today. A `Washington` query only matched existing Washington County, UT rows, not Washington County, MN.
- **Matrix match forecast:** **0% for all carry counties immediately after ingest/backfill**, because no county-specific matrix/directory exists for these jurisdictions today.
- **Recommended sequencing:** use a **roundtable smallest-first / target-muni-first** strategy, not NJ-style biggest-first county sweeps. Start with Kitsap WA or Scott/Carver MN if testing full-county matrix operations; start with top customer-value municipalities if the goal is post-adapter proof velocity.

Bottom line: Tier 4 is a matrix backlog, not a data-source mystery. Washington has the strongest post-ingest matrix substrate because WAZA already exposes local zone IDs and reference URLs. Minnesota is heavier because MetroGIS is parcel-only and zoning remains municipal. SEMCOG should stay out of Tier 4 until a real authoritative parcel carry is found.

## Bottom-Line Table

| County | Carry source | Est. codes | Est. sprint hours | Bergen-pattern fit | On 57-list direct |
|---|---|---:|---:|---|---|
| Pierce WA | Washington Current Parcels + WAZA | 258 exact WAZA `ZoneID`s | 22-43h | **PARTIAL** - WAZA helps, municipal ordinances mixed | No |
| Snohomish WA | Washington Current Parcels + WAZA | 232 exact WAZA `ZoneID`s | 19-39h | **PARTIAL** - WAZA helps, municipal ordinances mixed | No |
| Kitsap WA | Washington Current Parcels + WAZA | 112 exact WAZA `ZoneID`s | 9-19h | **PARTIAL/YES** - smallest WA county, WAZA + city codes | No |
| Ramsey MN | MetroGIS parcels | ~120 | 10-20h | **PARTIAL** - St. Paul/Roseville/Shoreview municipal mix | No |
| Anoka MN | MetroGIS parcels | ~110 | 9-18h | **PARTIAL** - many municipal codes, no regional zoning atlas | No |
| Carver MN | MetroGIS parcels | ~90 | 8-15h | **PARTIAL/YES** - smaller CTU set, many ordinances online | No |
| Dakota MN | MetroGIS parcels | ~160 | 13-27h | **PARTIAL** - large suburban patchwork | No |
| Scott MN | MetroGIS parcels | ~90 | 8-15h | **PARTIAL/YES** - smaller CTU set | No |
| Washington MN | MetroGIS parcels | ~150 | 13-25h | **PARTIAL** - many small cities/townships | No |
| Wayne MI | SEMCOG, **unverified** | ~300 speculative | 25-50h | **PARTIAL/NO until source verified** | No |
| Macomb MI | SEMCOG, **unverified** | ~180 speculative | 15-30h | **PARTIAL/NO until source verified** | No |

## Shared Method Notes

Prod API source: `GET https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions` and `GET /api/admin/coverage`, probed 2026-06-15.

Matrix coverage forecast:

- If a county is not registered, `parcel_count`, `parcel_zoning_code_coverage_pct`, `operational_readiness`, `blocking_gaps`, and `matrix_zone_count` are absent.
- Since no jurisdiction-specific directory/matrix exists for these counties in repo or prod, expected post-ingest `matrix_zone_match_pct` is **0%** until a matrix sprint lands.
- Code count estimates use exact WAZA distinct `ZoneID` counts for WA counties, MetroGIS parcel/CTU structure plus peer-county municipal patterns for MN, and conservative metro complexity estimates for speculative MI.

Lane A gate note: this document does **not** reclassify any county as ready for backfill. It assumes Tier 2 adapter/backfill work separately passes Lane A's bbox and `ST_Within` gates.

## Washington Carry Counties

Carry source: Washington Current Parcels, `https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0`.

Zoning source candidate: Washington State Zoning Atlas / WAZA, `https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer/0`.

### Pierce County, WA

Prod state:

| Field | Value |
|---|---|
| Registered in prod? | No `Pierce` jurisdiction row found. |
| Admin coverage | No `Pierce` row found. |
| parcel_count / zoning coverage / matrix count | Absent. |
| operational_readiness / blocking_gaps | Absent. |

Post-Tier-2 forecast:

- Parcel source live count from Washington Current Parcels: **339,590** for `COUNTY_NM='53'`.
- WAZA live probe: **19,116** zone polygons and **258** distinct `ZoneID` values where `COUNTYNAME='Pierce'`.
- Expected post-ingest `matrix_zone_match_pct`: **0%** until a Pierce matrix/directory exists.

Matrix sprint estimate:

- **258 codes x 5-10 min/code = 22-43h.**
- Representative citation sources: Tacoma Municode Title 13 zoning (`https://library.municode.com/wa/tacoma/codes/municipal_code?nodeId=TIT13LADERECO_CH13.06ZO`), Pierce County development regulations (`https://www.piercecountywa.gov/961/Development-Regulations`), Lakewood municipal zoning (`https://www.codepublishing.com/WA/Lakewood/`).
- Bergen-pattern fit: **PARTIAL**. WAZA gives code labels and reference URLs, but Pierce is a multi-city county; full-county matrix authoring is large.
- 57-list impact: not directly on the 57-list. Value is Puget Sound breadth after King.

### Snohomish County, WA

Prod state:

| Field | Value |
|---|---|
| Registered in prod? | No `Snohomish` jurisdiction row found. |
| Admin coverage | No `Snohomish` row found. |
| parcel_count / zoning coverage / matrix count | Absent. |
| operational_readiness / blocking_gaps | Absent. |

Post-Tier-2 forecast:

- Parcel source live count: **318,594** for `COUNTY_NM='61'`.
- WAZA live probe: **34,705** zone polygons and **232** distinct `ZoneID` values where `COUNTYNAME='Snohomish'`.
- Expected post-ingest `matrix_zone_match_pct`: **0%** until a Snohomish matrix/directory exists.

Matrix sprint estimate:

- **232 codes x 5-10 min/code = 19-39h.**
- Representative citation sources: Everett zoning code (`https://www.codepublishing.com/WA/Everett/`), Edmonds Community Development Code (`https://www.codepublishing.com/WA/Edmonds/`), Mukilteo municipal zoning (`https://www.codepublishing.com/WA/Mukilteo/`).
- Bergen-pattern fit: **PARTIAL**. Ordinances are online, but the county is a mixed municipal patchwork.
- 57-list impact: not directly on the 57-list. Adjacent value is north-Seattle metro breadth.

### Kitsap County, WA

Prod state:

| Field | Value |
|---|---|
| Registered in prod? | No `Kitsap` jurisdiction row found. |
| Admin coverage | No `Kitsap` row found. |
| parcel_count / zoning coverage / matrix count | Absent. |
| operational_readiness / blocking_gaps | Absent. |

Post-Tier-2 forecast:

- Parcel source live count: **139,602** for `COUNTY_NM='35'`.
- WAZA live probe: **15,606** zone polygons and **112** distinct `ZoneID` values where `COUNTYNAME='Kitsap'`.
- Expected post-ingest `matrix_zone_match_pct`: **0%** until a Kitsap matrix/directory exists.

Matrix sprint estimate:

- **112 codes x 5-10 min/code = 9-19h.**
- Representative citation sources: Bainbridge Island Municode Title 18 zoning (`https://library.municode.com/wa/bainbridge_island/codes/municipal_code?nodeId=TIT18ZO`), Bremerton zoning code (`https://www.codepublishing.com/WA/Bremerton/`), Poulsbo zoning code (`https://www.codepublishing.com/WA/Poulsbo/`).
- Bergen-pattern fit: **PARTIAL/YES**. Smaller than Pierce/Snohomish and WAZA gives a usable starting directory shape.
- 57-list impact: not directly on the 57-list. Adjacent value is Puget Sound coverage breadth.

WA sequencing recommendation: **Kitsap first** if Master wants a full-county Tier 4 proof. Pierce and Snohomish should be target-municipality roundtables first because countywide authoring is too large for a single quick sprint.

## Minnesota MetroGIS Carry Counties

Carry source: MetroGIS Regional Parcel Dataset, `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer`.

Confirmed carry list from `docs/HENNEPIN_MN_ACQUISITION_SPEC.md`: Anoka, Carver, Dakota, Hennepin, Ramsey, Scott, and Washington County, MN. Hennepin itself is already specced separately; this document covers Ramsey plus the five other non-Hennepin carry counties.

Important: MetroGIS is a parcel source, not a zoning atlas. These counties need municipal zoning acquisition before matrix work has real `zone_code` values to classify.

### Ramsey County, MN

Prod state:

| Field | Value |
|---|---|
| Registered in prod? | No `Ramsey` county jurisdiction row found. |
| Admin coverage | No `Ramsey` county row found. |
| parcel_count / zoning coverage / matrix count | Absent. |
| operational_readiness / blocking_gaps | Absent. |

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 4: **171,888**.
- Largest CTUs by parcel count: Saint Paul 84,950; Maplewood 13,967; Roseville 13,097; Shoreview 10,779; White Bear Lake 8,910.
- Estimated unique/local zoning codes after municipal zoning acquisition: **~120**.
- Expected post-ingest `matrix_zone_match_pct`: **0%** until Ramsey matrix/directory exists.

Matrix sprint estimate:

- **~120 codes x 5-10 min/code = 10-20h.**
- Representative citation sources: Saint Paul zoning code (`https://library.municode.com/mn/st._paul/codes/code_of_ordinances?nodeId=PTIILECO_TITVIIIZOCO`), Roseville Title 10 zoning (`https://library.municode.com/mn/roseville/codes/code_of_ordinances?nodeId=TIT10ZOCO`), Shoreview zoning (`https://www.shoreviewmn.gov/government/departments/community-development/zoning`).
- Bergen-pattern fit: **PARTIAL**. Major-city ordinances are online, but St. Paul alone is a substantial code system.
- 57-list impact: not directly on the 57-list. Strong adjacent value if Twin Cities coverage is strategic.

### Anoka County, MN

Prod state: no `Anoka` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 0: **139,680**.
- Largest CTUs: Blaine 26,302; Coon Rapids 22,583; Andover 12,339; Ramsey 11,503; Fridley 9,917.
- Estimated unique/local zoning codes: **~110**.
- Expected post-ingest `matrix_zone_match_pct`: **0%**.

Matrix sprint estimate:

- **~110 codes x 5-10 min/code = 9-18h.**
- Representative citation sources: Blaine city code zoning (`https://library.municode.com/mn/blaine/codes/code_of_ordinances`), Coon Rapids zoning (`https://library.municode.com/mn/coon_rapids/codes/code_of_ordinances`), Anoka city code (`https://library.municode.com/mn/anoka/codes/code_of_ordinances`).
- Bergen-pattern fit: **PARTIAL**. Mostly online, but municipal patchwork.
- 57-list impact: not directly on the 57-list.

### Carver County, MN

Prod state: no `Carver` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 1: **47,135**.
- Largest CTUs: Chanhassen 10,833; Chaska 10,437; Waconia 5,658; Victoria 5,229; Carver 2,790.
- Estimated unique/local zoning codes: **~90**.
- Expected post-ingest `matrix_zone_match_pct`: **0%**.

Matrix sprint estimate:

- **~90 codes x 5-10 min/code = 8-15h.**
- Representative citation sources: Chanhassen zoning (`https://library.municode.com/mn/chanhassen/codes/code_of_ordinances`), Chaska zoning (`https://library.municode.com/mn/chaska/codes/code_of_ordinances`), Victoria city code (`https://library.municode.com/mn/victoria/codes/code_of_ordinances`).
- Bergen-pattern fit: **PARTIAL/YES**. Smaller county and many ordinances are online.
- 57-list impact: not directly on the 57-list.

### Dakota County, MN

Prod state: no `Dakota` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 2: **153,152**.
- Largest CTUs: Lakeville 26,088; Eagan 20,299; Burnsville 16,568; Apple Valley 16,019; Inver Grove Heights 11,000.
- Estimated unique/local zoning codes: **~160**.
- Expected post-ingest `matrix_zone_match_pct`: **0%**.

Matrix sprint estimate:

- **~160 codes x 5-10 min/code = 13-27h.**
- Representative citation sources: Eagan zoning (`https://library.municode.com/mn/eagan/codes/code_of_ordinances`), Lakeville zoning (`https://library.municode.com/mn/lakeville/codes/code_of_ordinances`), Apple Valley zoning (`https://library.municode.com/mn/apple_valley/codes/code_of_ordinances`).
- Bergen-pattern fit: **PARTIAL**. Large suburban patchwork.
- 57-list impact: not directly on the 57-list.

### Scott County, MN

Prod state: no `Scott` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 5: **60,840**.
- Largest CTUs: Shakopee 15,869; Savage 11,689; Prior Lake 11,667; Belle Plaine 3,070; Jordan 2,443.
- Estimated unique/local zoning codes: **~90**.
- Expected post-ingest `matrix_zone_match_pct`: **0%**.

Matrix sprint estimate:

- **~90 codes x 5-10 min/code = 8-15h.**
- Representative citation sources: Shakopee zoning (`https://library.municode.com/mn/shakopee/codes/code_of_ordinances`), Savage zoning (`https://library.municode.com/mn/savage/codes/code_of_ordinances`), Prior Lake city code (`https://library.municode.com/mn/prior_lake/codes/code_of_ordinances`).
- Bergen-pattern fit: **PARTIAL/YES**. Smaller than Ramsey/Dakota/Washington MN and likely a good MN proof county.
- 57-list impact: not directly on the 57-list.

### Washington County, MN

Prod state:

| Field | Value |
|---|---|
| Registered in prod? | No Washington County, MN row found. |
| Admin coverage | Querying `Washington` returned Washington County, UT operational/partial rows; those are not this county. |
| parcel_count / zoning coverage / matrix count | Absent for Washington County, MN. |
| operational_readiness / blocking_gaps | Absent for Washington County, MN. |

Post-Tier-2 forecast:

- MetroGIS parcel count, layer 6: **118,000**.
- Largest CTUs: Woodbury 29,433; Cottage Grove 16,494; Oakdale 11,055; Forest Lake 8,958; Stillwater 8,622; Hugo 7,757; Lake Elmo 6,107.
- Estimated unique/local zoning codes: **~150**.
- Expected post-ingest `matrix_zone_match_pct`: **0%**.

Matrix sprint estimate:

- **~150 codes x 5-10 min/code = 13-25h.**
- Representative citation sources: Woodbury zoning code (`https://library.municode.com/mn/woodbury/codes/code_of_ordinances?nodeId=PTII_CH24ZO`), Stillwater city code (`https://library.municode.com/mn/stillwater/codes/code_of_ordinances`), Lake Elmo city code (`https://library.municode.com/mn/lake_elmo/codes/code_of_ordinances`).
- Bergen-pattern fit: **PARTIAL**. Many small cities/townships; ordinances are online but not uniform.
- 57-list impact: not directly on the 57-list.

MN sequencing recommendation: **Scott or Carver first** for a manageable MetroGIS matrix proof; Ramsey only if St. Paul metro breadth is strategically valuable. Dakota and Washington MN should be target-muni roundtables before countywide authoring.

## Speculative Detroit-Metro SEMCOG Carry

Oakland PR #239 found **no verified authoritative SEMCOG parcel carry**. Wayne and Macomb are included only because the dispatch asked for them if SEMCOG holds. Current recommendation: **do not dispatch Tier 4 matrix work for Wayne/Macomb until parcel/zoning acquisition is re-opened and a real carry source passes Lane A source gates.**

### Wayne County, MI

Prod state: no `Wayne` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- Carry source: **unverified**. SEMCOG did not prove out as a current authoritative parcel source.
- If a future Wayne source populates zoning codes at >=70%, expected `matrix_zone_match_pct`: **0%** until Wayne matrix/directory exists.
- Estimated unique/local zoning codes if Detroit + inner-ring suburbs are included: **~300**.

Matrix sprint estimate:

- **~300 codes x 5-10 min/code = 25-50h.**
- Representative citation sources: Detroit zoning (`https://library.municode.com/mi/detroit/codes/code_of_ordinances?nodeId=PTIIICICO_CH50ZO`), Grosse Pointe zoning (`https://library.municode.com/mi/grosse_pointe/codes/code_of_ordinances?nodeId=PTIICOOR_CH90ZO`), Northville zoning resources (`https://www.ci.northville.mi.us/services/building___planning___zoning`).
- Bergen-pattern fit: **PARTIAL/NO until source verified**. Detroit alone is too large for quick Bergen-style authoring.
- 57-list impact: not directly on the 57-list.

### Macomb County, MI

Prod state: no `Macomb` jurisdiction row or admin coverage row found.

Post-Tier-2 forecast:

- Carry source: **unverified**. SEMCOG did not prove out as a current authoritative parcel source.
- If a future Macomb source populates zoning codes at >=70%, expected `matrix_zone_match_pct`: **0%** until Macomb matrix/directory exists.
- Estimated unique/local zoning codes: **~180**.

Matrix sprint estimate:

- **~180 codes x 5-10 min/code = 15-30h.**
- Representative citation sources: Warren zoning code (`https://library.municode.com/mi/warren/codes/code_of_ordinances`), Sterling Heights zoning (`https://library.municode.com/mi/sterling_heights/codes/code_of_ordinances`), Macomb Township zoning (`https://library.municode.com/mi/macomb_township/codes/code_of_ordinances?nodeId=PTIICOOR_CH26ZO`).
- Bergen-pattern fit: **PARTIAL/NO until source verified**. Likely municipal patchwork, but source gates need to reopen first.
- 57-list impact: not directly on the 57-list.

MI sequencing recommendation: **do not queue Wayne/Macomb Tier 4 matrix sprints yet**. Oakland remains the Detroit-metro proof target; Wayne/Macomb need acquisition scoping before matrix readiness is actionable.

## Recommended Tier 4 Dispatch Queue

1. **Kitsap WA** - smallest exact WAZA code count among WA carry counties; best full-county WA matrix proof.
2. **Scott MN or Carver MN** - smallest MetroGIS matrix proof candidates; good way to validate MN municipal-directory workflow.
3. **Ramsey MN target-muni roundtable** - St. Paul first if customer value justifies complexity.
4. **Pierce/Snohomish WA target-muni roundtables** - avoid full-county authoring until WAZA directory tooling is ready.
5. **Dakota/Washington MN target-muni roundtables** - larger MN suburban patchworks.
6. **Wayne/Macomb MI** - hold until SEMCOG or another parcel/zoning source is actually verified.

Do not start with biggest-first full-county authoring. These carry counties are breadth unlocks, and the efficient way to exploit them is to author high-value municipalities first while building reusable directory patterns.
