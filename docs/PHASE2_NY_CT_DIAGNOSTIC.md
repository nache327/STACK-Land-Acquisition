# Phase-2 NY/CT Diagnostic

Date: 2026-06-11

Question: can the NJ matrix-completion sprint pattern, roughly 3-4 hours per county, work for Westchester NY, Nassau NY, and Fairfield CT, or do they need structural work first?

Short answer: **NO for all three as immediate NJ-style matrix sprints.** The ordinances are mostly online, and some municipalities have use-table-like material, but prod parcel data does not currently expose populated `zoning_code` values for any sampled municipality. Nassau and Fairfield also do not expose `city` values through `/api/jurisdictions/{id}/cities`, so there is no stable `(municipality, zone_code)` matrix join key yet.

The NJ/Bergen pattern depends on two things being true before matrix authoring starts:

1. A per-municipality source directory exists, e.g. `backend/data/bergen_zoning_directory.json` with `muni_code`, `muni_name`, `in_njsea_zoning`, `map_url`, `ordinance_url`, and `website_url`.
2. Prod parcels already carry usable municipality and zone-code values so matrix rows can join back to parcels.

For these three Phase-2 counties, the ordinance side is only partly sprintable and the parcel join-key side is not ready.

## Westchester County, NY

Verdict: **NO for immediate 3-4h NJ sprint.** Ordinances are online for the sampled towns, but the structure is mixed and prod parcel `zoning_code` is null in all sampled rows. Westchester is the closest to sprintable after prereq work because `city` is populated.

Estimated structural prereq: **12-20 hours** to build a Westchester directory, identify zoning map/district sources per municipality, populate parcel zone codes, and verify city-name normalization. Matrix sprint hours after that: likely **5-8 hours** for the sampled high-value towns, not 3-4h for the whole county, because several codes are narrative district articles rather than clean use tables.

| Municipality | Ordinance source | Structure vs NJ pattern | Zone code scope | Prod parcel probe |
|---|---|---|---|---|
| Scarsdale | eCode360 Chapter 310, `https://ecode360.com/6439798`; Article II use restrictions at `https://ecode360.com/6439862` | **Different.** District-by-district narrative. Example: Residence C incorporates Residence A uses; Business A/C sections list allowed uses by prose, not one matrix table. | Village-level: examples include Residence A/C, Business A/C, Village Center Retail/Office, PUD. | City filter works. `city=Scarsdale`, total `5,929`; sampled APNs `55500120.01.1`, `55500121.01.2`, `55500123.01.1A2` all `zoning_code=null`. |
| Rye | eCode360 Chapter 197, `https://ecode360.com/6977013`; Article IV says uses are regulated by Article VIII Table of Regulations, `https://ecode360.com/6977098`; Article VIII at `https://ecode360.com/6977440` | **Partial NJ-like.** It has a table/schedule concept, but it is rendered as cumulative district text, e.g. RT uses permitted in R-6, RA-1 uses permitted in RT. | City-level: examples include R-6, RT, RA-1 through RA-6, B districts. | City filter works. `city=Rye`, total `4,948`; sampled APNs `551400153-9-1-32`, `551400153-5-3-72-1X`, `551400153-5-3-72` all `zoning_code=null`. |
| Bronxville | eCode360 Chapter 310, `https://ecode360.com/9450363` | **Different.** Article III is district-use-and-bulk sections, e.g. one-family residence districts, multiple residence districts, Central Business A, Service Business B. Not a county/common use matrix. | Village-level: examples include AAA, AA, A, B, C, D, Central Business A, Service Business B. | City filter works. `city=Bronxville`, total `1,723`; sampled APNs `5524016./1/1.1`, `5524016./1/1`, `5524017.J/1/1` all `zoning_code=null`. |
| White Plains | City page points to official zoning ordinance PDF, `https://www.cityofwhiteplains.com/120/White-Plains-Zoning-Ordinance` | **Different / PDF workflow.** City-hosted ordinance, not eCode table. Page explicitly directs permitted-use questions to Planning Department. | City-level. | City filter works. `city=White Plains`, total `13,965`; sampled APNs `551700120.20-17-1`, `551700126.70-1-1`, `551700121.17-2-2` all `zoning_code=null`. |
| Mount Kisco | eCode360 Chapter 110, `https://ecode360.com/10863078`; district regulations at `https://ecode360.com/10863108` | **Different.** Long district-by-district article. Example districts include PD, CD, RS-12, CB-1, GR, RDX, ML; each district has its own permitted/special permit use prose. | Town/Village-level. | City filter works. `city=Mount Kisco`, total `2,805`; sampled APNs `55560169.71-3-1`, `55560180.66-1-1`, `55560180.62-1-1` all `zoning_code=null`. |

Westchester equivalent directory shape needed:

```json
{
  "muni_name": "Scarsdale",
  "muni_type": "village",
  "county": "Westchester",
  "state": "NY",
  "prod_city_value": "Scarsdale",
  "ordinance_url": "https://ecode360.com/6439798",
  "ordinance_platform": "ecode360",
  "use_structure": "district_narrative",
  "zoning_map_url": "...",
  "zoning_district_source_url": null,
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Nassau County, NY

Verdict: **NO.** Nassau needs structural work before any NJ-style sprint. Sampled ordinances are online, but the county record lacks exposed `city` drilldown and sampled parcels are `zoning_code=null`. Nassau also has nested municipal authority: some samples are incorporated villages with their own eCode chapters, while Manhasset is mostly under Town of North Hempstead zoning.

Estimated structural prereq: **18-30 hours** to build a Nassau municipality authority map, resolve village/town jurisdiction boundaries, populate `city` or another municipality key, locate zoning maps/district data, and then backfill parcel zone codes. Matrix sprint after prereq: **PARTIAL**, likely 6-10 hours for the sampled set because Garden City/Roslyn/Great Neck/North Hempstead are narrative district articles and Long Beach is PDF.

Prod API baseline: `/api/jurisdictions/{nassau_id}/cities` returns `[]`. County-level slim search total is `420,577`; sampled largest row had `zoning_code=null`.

| Municipality | Ordinance source | Structure vs NJ pattern | Zone code scope | Prod parcel probe |
|---|---|---|---|---|
| Garden City | eCode360 Chapter 200, `https://ecode360.com/9148416`; Article V schedule at `https://ecode360.com/9148500` | **Different / partial.** Article V adopts a schedule, but use rules are still long district sections. Example: R-40/R-20/R-12/R-8/R-6 uses listed in §200-16, with "any use not permitted hereinabove shall be prohibited." | Village-level: examples include R-40, R-20, R-12, R-8, R-6, CO, C, I. | Text search `Garden City`: total `127`; sampled `100 GARDEN CITY PLAZA` APNs all `city=null`, `zoning_code=null`. Bbox probe: total `19,576`; sampled APNs `28201133.-C-517`, `28201134.-550-102`, `28208944.-F-147` all `city=null`, `zoning_code=null`. |
| Roslyn | eCode360 Chapter 470, `https://ecode360.com/13790062`; Roslyn maps page `https://www.roslynny.gov/home/pages/maps-roslyn` | **Different.** District-by-district sections, not one use matrix. eCode TOC lists R-1, R-2, R-3, R-4, R-MF, R-WD, R-C, C-V, C-N, C-H, WMU, OSR, overlays. | Village-level. | Text search `Roslyn`: total `317`; sampled `ROSLYN RD` / `ROSLYN EXPRESSWAY PLZ` rows all `city=null`, `zoning_code=null`. Bbox probe: total `7,028`; sampled APNs `2822896.-53-1077`, `28224520.-M-9`, `2822076.-53-218` all `city=null`, `zoning_code=null`. |
| Manhasset | Town of North Hempstead Chapter 70, `https://ecode360.com/9299439`; zoning maps page `https://www.northhempsteadny.gov/departments/buildings/zoning_maps.php` | **Different.** Town code is article-per-district. Example: Business A District §70-125 lists permitted uses in prose; Industrial A / Modified Planned Industrial Park likewise list permitted and conditional uses by section. | Town-level for unincorporated Manhasset areas, with adjacent village overlays possible. | Text search `Manhasset`: total `170`; sampled APNs `2822171.-154-16`, `2822171.-178-37`, `2822893.-237-9` all `city=null`, `zoning_code=null`. Bbox probe: total `9,460`; sampled APNs `2822896.-53-1077`, `2822193.-E-9`, `2822076.-53-218` all `city=null`, `zoning_code=null`. |
| Great Neck | Village of Great Neck eCode360 Chapter 575, `https://ecode360.com/29392297`; Business A example `https://ecode360.com/6308339`; zoning maps page `https://www.greatneckvillage.org/government/zoning_maps/index.php` | **Different.** District articles list permitted/conditional uses. Example: Business A §575-129 lists ground/upper-level uses in prose. Great Neck also has multiple related villages, so "Great Neck" is not one authority. | Village-level, but "Great Neck" area spans several villages. | Text search `Great Neck`: total `229`; sampled APNs `2822132.-233-7`, `2822892.-284-800`, `2822892.-51-209` all `city=null`, `zoning_code=null`. Bbox probe: total `13,212`; sampled APNs `2822193.-E-9`, `2822171.-197-1`, `2822293.-E-486` all `city=null`, `zoning_code=null`. |
| Long Beach | City code page `https://www.longbeachny.gov/index.asp?DE=46CE5630-0337-4BAF-9880-017D43D760BB&SEC=1A40DC3F-AB22-4EF5-8107-35B30A446295`; current code PDF `https://www.longbeachny.gov/vertical/sites/%7BC3C1054A-3D3A-41B3-8896-814D00B86D2A%7D/uploads/Code_of_Ord_Sup_86b%281%29.pdf` | **Different / PDF workflow.** Current code is a 1,050-page PDF, current as of April 7, 2026 on the city page and codified through Ord. No. 3102/2025 / LL III/2025 inside the PDF. | City-level. | Text search `Long Beach`: total `1,051`; sampled rows all `city=null`, `zoning_code=null`. Bbox probe: total `13,370`; sampled APNs `28202341.-J-3`, `28208941.-K-2`, `28208943.-H-100` all `city=null`, `zoning_code=null`. |

Nassau equivalent directory shape needed:

```json
{
  "place_name": "Manhasset",
  "authority_name": "Town of North Hempstead",
  "authority_type": "town_or_village",
  "county": "Nassau",
  "state": "NY",
  "prod_city_value": null,
  "municipality_boundary_source_url": "...",
  "ordinance_url": "https://ecode360.com/9299439",
  "ordinance_platform": "ecode360",
  "use_structure": "district_narrative",
  "zoning_map_url": "https://www.northhempsteadny.gov/departments/buildings/zoning_maps.php",
  "zoning_district_source_url": null,
  "zone_code_scope": "municipal_or_town_subarea",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Fairfield County, CT

Verdict: **NO.** Fairfield County needs structural prereq work first. Connecticut zoning authority is municipal, not county-level: CGS Chapter 124 authorizes each city, town, or borough zoning commission to regulate within that municipality (`https://cga.ct.gov/2026/sup/chap_124.htm`), and Connecticut counties have existed only as geographic regions without independent county government since 1960 (`https://www.cga.ct.gov/2015/rpt/2015-R-0274.htm`). The sampled ordinances are online, but prod Fairfield parcels expose neither `city` nor `zoning_code` in sampled rows.

Estimated structural prereq: **18-28 hours** to build a CT town directory, map CT CAMA parcel town identity into `city` or a joinable municipality key, locate municipal zoning-map/district sources, and populate parcel zone codes. Matrix sprint after prereq: **PARTIAL**, likely 6-12 hours for sampled towns because Westport/New Canaan/Stamford have table-like material while Greenwich/Darien are section/PDF workflows.

Prod API baseline: `/api/jurisdictions/{fairfield_id}/cities` returns `[]`. County-level slim search total is `261,652`; sampled largest row had `zoning_code=null`.

| Municipality | Ordinance source | Structure vs NJ pattern | Zone code scope | Prod parcel probe |
|---|---|---|---|---|
| Greenwich | Town building-zone regulations page `https://www.greenwichct.gov/442/Building-Zone-Regulations`; Municode `https://library.municode.com/ct/greenwich` | **Different / sectioned.** Regulations list use groups and per-zone sections: §6-100 Use Groups for Business Zones, §6-103 LBR, §6-104 LB, §6-105 GB, §6-106 GBO, §6-107 WB, §6-108 BEX-50, etc. | Town-level. | Text search `Greenwich`: total `209`; sampled rows all `city=null`, `zoning_code=null`. Bbox probe: total `15,335`; sampled APNs `33620-11-4509`, `33620-10-4019`, `33620-10-1529` all `city=null`, `zoning_code=null`. |
| Westport | EncodePlus regulations `https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx`; town page says current version last revised April 12, 2024 at `https://www.westportct.gov/government/departments-a-z/planning-and-zoning-department/zoning-and-subdivision-regulations` | **Partial NJ-like.** EncodePlus exposes searchable regs and permitted-use sections/tables, but it is not a county-standard table. | Town-level. | Text search `Westport`: total `275`, but address-search is not reliable as a town filter. Bbox probe: total `14,020`; sampled APNs `000000`, `83500-F05001000`, `83500-C04001000` all `city=null`, `zoning_code=null`. |
| Darien | Town regulations PDF page `https://www.darienct.gov/301/Zoning-Regulations-Map` | **Different / PDF workflow.** Town page links the zoning regulations PDF, says it was amended effective May 10, 2026 through Amendment 104, and separately links the zoning map. | Town-level. | Text search `Darien`: total `12`, address-search only. Bbox probe: total `7,102`; sampled APNs `18850-36-123-00`, `18850-07-066-00`, `18850-05-040-00` all `city=null`, `zoning_code=null`. |
| New Canaan | Town zoning regulations page `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regulations.php`; update page with existing/proposed use-table PDFs `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regs_update_2025.php` | **Partial NJ-like.** Current regulations are PDF, and 2026 update materials include "Existing Use Table Residence Zones" and proposed use-table documents, but these are not yet a county-standard matrix source. | Town-level. | Text search `New Canaan`: total `121`; sampled rows all `city=null`, `zoning_code=null`. Bbox probe: total `9,621`; sampled APNs `124-23-1`, `30/51/121`, `33/34/55` all `city=null`, `zoning_code=null`. |
| Stamford | City zoning regulations page `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations` | **Partial NJ-like.** City page lists zoning regulations as of May 31, 2026, including Section 4 - Use Regulations and Standards, Section 5 - Districts and District Regulations, and appendices. Still city-specific, not county-level. | City-level. | Text search `Stamford`: total `119`; sampled rows all `city=null`, `zoning_code=null`. Bbox probe: total `35,535`; sampled APNs `18850-07-066-00`, `30/51/121`, `33/34/55` all `city=null`, `zoning_code=null`. |

Fairfield equivalent directory shape needed:

```json
{
  "town_name": "Greenwich",
  "county": "Fairfield",
  "state": "CT",
  "ct_cama_town_value": "...",
  "prod_city_value": null,
  "ordinance_url": "https://www.greenwichct.gov/442/Building-Zone-Regulations",
  "ordinance_platform": "town_site_or_municode",
  "use_structure": "sectioned_zone_regulations",
  "zoning_map_url": "...",
  "zoning_district_source_url": null,
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Bottom Line

Do **not** dispatch three NJ-style matrix sprints yet. The expected one-day path is blocked by missing parcel join keys, not just by ordinance discovery.

Recommended attack order if Master wants to unlock Phase 2:

1. **Westchester first**: it already has `city` values, so the smallest structural path is likely building `westchester_zoning_directory.json`, finding zoning district sources/maps, and backfilling `zoning_code`.
2. **Nassau second**: solve municipal authority and city-boundary normalization before matrix work. The town/village nesting makes it riskier than Westchester.
3. **Fairfield third**: solve CT CAMA town identity and municipal zoning-source discovery first. The ordinance side is manageable, but the county has no zoning authority and the current prod county record has no town join key.

Escalation recommendation: hold all three matrix sprints until a structural prereq ticket is accepted. The first concrete deliverable should be a Westchester directory plus one proof municipality where prod parcels have `(city, zoning_code)` populated and a zone matrix row joins correctly.
