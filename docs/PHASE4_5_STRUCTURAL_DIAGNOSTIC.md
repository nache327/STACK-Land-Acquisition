# Phase 4/5 Structural Diagnostic

Date: 2026-06-11

Scope: Plymouth MA, Cook IL, Fulton GA, Mecklenburg NC, Wake NC, Douglas CO, and Arapahoe CO. Norfolk MA, Middlesex MA, and DuPage IL are intentionally skipped because other lanes are diagnosing them.

Question: for the remaining target-map partial/not-loaded counties, is the Bergen/NJ matrix pattern available, is the county ingestion-blocked, or is some other structural prerequisite needed?

## Bottom-Line Classification

| County | Prod state | Classification | Next action |
|---|---:|---|---|
| Plymouth County, MA | Not registered in `/api/jurisdictions`; no `/api/admin/coverage` row found. | **NOT-LOADED-NEEDS-INGEST** | Add jurisdiction + full parcel pipeline first. Ordinance samples suggest MA town-level use tables are available after ingest. |
| Cook County, IL | Registered, but `parcel_count=0`; `operational_readiness=not_loaded`; gaps: `no_parcels`, `no_zone_use_matrix`, `no_zoning_polygons`, `missing_bbox`. | **NOT-LOADED-NEEDS-INGEST** | Fix/load parcel ingest before any matrix work. |
| Fulton County, GA | Registered and parcel search returns `372,723`, but admin coverage snapshot is stale/out-of-sync at `parcel_count=0`; sampled parcels have `city=null`, `zoning_code=null`; `/cities=[]`. | **INGESTION-BLOCKED** | Backfill parcel municipality + zoning codes; then matrix sprint likely works for Sandy Springs and parts of Atlanta/South Fulton. |
| Mecklenburg County, NC | Registered; no admin coverage row in current payload; parcel search returns `395,263`; sampled parcels have `city=null`, `zoning_code=null`; `/cities=[]`. | **INGESTION-BLOCKED** | Backfill municipality + zoning codes from local zoning/GIS sources. Charlotte UDO is table-friendly after join keys exist. |
| Wake County, NC | Registered and parcel search returns `435,434`, but admin coverage snapshot is stale/out-of-sync at `parcel_count=0`; sampled parcels have `city=null`, `zoning_code=null`; `/cities=[]`. | **INGESTION-BLOCKED** | Backfill town/city + zoning codes. Raleigh/Cary/Apex use tables are sprintable after ingestion. |
| Douglas County, CO | Registered; no admin coverage row in current payload; parcel search returns `152,441`; sampled parcels have `city=null`, `zoning_code=null`; `/cities=[]`. | **INGESTION-BLOCKED** | Backfill zoning codes and distinguish unincorporated Douglas PDs from municipal codes. Highlands Ranch PD adds a structural wrinkle, but current blocker is still missing parcel zone codes. |
| Arapahoe County, CO | Registered; no admin coverage row in current payload; parcel search returns `231,430`; sampled parcels have `city=null`, `zoning_code=null`; `/cities=[]`. | **INGESTION-BLOCKED** | Backfill municipal/unincorporated jurisdiction + parcel zoning codes before matrix. Cherry Hills/Greenwood/Englewood are use-table-friendly once keyed. |

## Prod-State Notes

Admin coverage source: `GET https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage`.

Public jurisdiction and parcel source: `GET /api/jurisdictions`, `GET /api/jurisdictions/{id}/cities`, and `POST /api/parcels/search`.

Key inconsistency: Fulton and Wake have stale admin coverage rows reporting zero parcels, but current parcel search returns loaded parcels. Treat admin `blocking_gaps` as stale for those two; the operational product blocker is missing parcel zone codes, not absence of parcels.

## Plymouth County, MA

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Plymouth County` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Unknown / absent. |
| parcel_zoning_code_coverage_pct | Unknown / absent. |
| zoning_district_count | Unknown / absent. |
| operational_readiness | Absent from prod; effectively not loaded. |
| blocking_gaps | Jurisdiction not registered, no parcels, no zoning/matrix state. |

Representative ordinance samples:

| Municipality | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Hingham | Town application/regulations page links `Hingham Zoning By-law (PDF)`: `https://www.hingham-ma.gov/168/Application-Forms-Regulations`. Section III-A is the Schedule of Uses. | **MATRIX-SPRINTABLE after ingest.** Schedule-of-uses table with allowed/special/prohibited coding; PDF workflow. | Town-level zoning districts. |
| Plymouth | Town zoning maps/documents page: `https://www.plymouth-ma.gov/488/Zoning-Maps-Planning-Documents`; bylaw PDF `https://www.plymouth-ma.gov/DocumentCenter/View/7334/Zoning-Bylaw-10-2024-PDF`. Article V §205-1 says allowed uses are shown in the Use Table and unlisted uses are prohibited. | **MATRIX-SPRINTABLE after ingest.** Explicit use table keyed by town districts. | Town-level zoning districts. |
| Cohasset | eCode360 Chapter 300: `https://ecode360.com/31605802`; Article 4 use regulations `https://ecode360.com/31605934`; Table of Use Regulations PDF `https://www.cohassetma.gov/DocumentCenter/View/6230/Table-of-Use-Regulations`. | **MATRIX-SPRINTABLE after ingest.** Table of Principal Uses / Use Regulations with yes/special-permit/no columns. | Town-level zoning districts. |
| Duxbury | Town zoning bylaws page `https://www.town.duxbury.ma.us/zoning-board-appeals/pages/zoning-bylaws`; zoning bylaw PDF `https://www.town.duxbury.ma.us/planning-department/files/zoning-bylaw-approved-through-2020`. | **PARTIAL.** PDF is district-by-district narrative for business districts, e.g. Neighborhood Business Light/1/2 use sections, rather than one clean global matrix. | Town-level zoning districts. |

Directory shape needed after ingest:

```json
{
  "town_name": "Hingham",
  "county": "Plymouth",
  "state": "MA",
  "ordinance_url": "https://www.hingham-ma.gov/168/Application-Forms-Regulations",
  "ordinance_platform": "town_pdf",
  "use_structure": "schedule_of_uses_pdf",
  "zoning_map_url": "https://www.hingham-ma.gov/1016/Land-Use-and-Development",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "jurisdiction_absent"
}
```

## Cook County, IL

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `1726fc6f-9927-413e-b20e-936ab438de10` |
| Registered? | Yes, `Cook County, IL`. |
| parcel_count | Coverage row: `0`; parcel search total: `0`. |
| parcel_zoning_code_coverage_pct | `0.0` |
| zoning_district_count | `0` |
| operational_readiness | `not_loaded` |
| blocking_gaps | `no_parcels`, `no_zone_use_matrix`, `no_zoning_polygons`, `missing_bbox` |

Representative ordinance samples:

| Municipality / sub-jurisdiction | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Winnetka | American Legal Title 17 Zoning: `https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873`; commercial use table referenced at §17.46.010. | **MATRIX-SPRINTABLE after ingest.** Local code has district-specific use tables, including commercial Table of Uses. | Village-level zoning districts. |
| Wilmette | Village zoning page `https://www.wilmette.gov/206/Zoning-Ordinance-Zoning-Map`; Municode Appendix A / Chapter 30 starts at `https://library.municode.com/IL/Wilmette/codes/Code_of_Ordinances?nodeId=COOR_APXAZOOR_ART30-1TIPUAP_S30-1.3PU`. | **MATRIX-SPRINTABLE after ingest.** Appendix A zoning ordinance; use permissions are local-zone keyed. | Village-level zoning districts. |
| Glencoe | Code/PDF source `https://cityofglencoe.org/wp-content/uploads/2024/02/Glencoe-Zoning-Ordinance-2023.pdf`; examples include Table 5.5 for uses permitted in R-1. | **MATRIX-SPRINTABLE after ingest.** Tables by district rather than county-wide table, but extractable. | Village-level zoning districts. |
| Unincorporated Cook | Cook County zoning administration page `https://www.cookcountyil.gov/service/zoning-ordinance-administration`; unincorporated zoning districts ArcGIS layer `https://hub-cookcountyil.opendata.arcgis.com/datasets/cookcountyil::unincorporated-zoning-districts/explore`. | **STRUCTURAL SUBSET.** County zoning applies only to unincorporated parcels; most target north-shore places are municipal. | County-level only for unincorporated areas; municipal elsewhere. |

Directory shape needed after ingest:

```json
{
  "place_name": "Winnetka",
  "authority_name": "Village of Winnetka",
  "county": "Cook",
  "state": "IL",
  "ordinance_url": "https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873",
  "ordinance_platform": "american_legal",
  "use_structure": "district_use_table",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "no_parcels"
}
```

## Fulton County, GA

Verdict: **INGESTION-BLOCKED.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `bb9e5176-c1e8-4221-9f2e-b27c34545f98` |
| Registered? | Yes, `Fulton County, GA`. |
| parcel_count | Admin coverage row says `0` but is stale; parcel search total returns `372,723`. |
| parcel_zoning_code_coverage_pct | Admin says `0.0`; sampled parcel rows have `zoning_code=null`. |
| zoning_district_count | Admin coverage row says `0`. |
| operational_readiness | Admin says `not_loaded`, but current parcel search shows parcels loaded. Treat as stale coverage; operationally partial/parcels-only. |
| blocking_gaps | Stale admin gaps: `no_parcels`, `no_zone_use_matrix`, `no_zoning_polygons`, `missing_bbox`; current blocker: no parcel zoning codes and no city drilldown. |
| city drilldown | `/api/jurisdictions/{id}/cities` returns `[]`. |
| parcel sample | Largest rows include APNs `08 220000980067`, `08 340001530032`, `08 350001650102`; all `city=null`, `zoning_code=null`. |

Representative ordinance samples:

| Municipality / sub-jurisdiction | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Sandy Springs | Municode Development Code `https://library.municode.com/ga/sandy_springs/codes/development_code`; city page `https://www.sandyspringsga.gov/sandy-springs-development-code/` says Division 7.2 is the Allowed Use Table. | **MATRIX-SPRINTABLE after ingestion.** Explicit allowed-use table across district types. | City-level zoning districts. |
| Atlanta / Buckhead | Municode city code `https://library.municode.com/ga/atlanta/codes/code_of_ordinances`; city ordinance page `https://www.atlantaga.gov/government/departments/city-planning/ordinances-regulations`. | **PARTIAL.** Atlanta Part 16 is chapter-by-zone and overlay-heavy; usable but not one county table. | City-level zoning districts and overlays. |
| Unincorporated Fulton | Fulton zoning resolution page `https://www.fultoncountyga.gov/inside-fulton-county/fulton-county-departments/public-works/planning-zoning-and-permitting/zoning-resolution`; articles are PDF by topic/district. | **PARTIAL / STRUCTURAL SUBSET.** Applies only to unincorporated Fulton; district articles are narrative, not a clean global use matrix. | County-level only for unincorporated areas. |
| Milton / Johns Creek | Milton UDC `https://library.municode.com/ga/milton/codes/unified_development_code`; Johns Creek Appendix A zoning `https://www.municode.com/library/ga/johns_creek/codes/code_of_ordinances?nodeId=PTIICOOR_APXAZO`. | **PARTIAL.** Milton has UDC use tables; Johns Creek inherits/extends Fulton-style zoning with local amendments and town-center use tables. | City-level zoning districts. |

Directory shape needed:

```json
{
  "place_name": "Sandy Springs",
  "authority_name": "City of Sandy Springs",
  "county": "Fulton",
  "state": "GA",
  "prod_city_value": null,
  "ordinance_url": "https://library.municode.com/ga/sandy_springs/codes/development_code",
  "ordinance_platform": "municode",
  "use_structure": "allowed_use_table",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Mecklenburg County, NC

Verdict: **INGESTION-BLOCKED.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `ae7276c5-6655-4e8f-93e4-273787afd968` |
| Registered? | Yes, `Mecklenburg County, NC`. |
| parcel_count | No admin coverage row found; parcel search total returns `395,263`. |
| parcel_zoning_code_coverage_pct | Unknown in coverage; sampled parcel rows have `zoning_code=null`. |
| zoning_district_count | No admin coverage row found. |
| operational_readiness | No admin coverage row found; product state is parcels loaded but zoning unbound. |
| blocking_gaps | No admin row; current blocker: no parcel zoning codes and no city drilldown. |
| city drilldown | `/api/jurisdictions/{id}/cities` returns `[]`. |
| parcel sample | Largest rows include APNs `00125N01`, `00127N01`, `00119N01`; all `city=null`, `zoning_code=null`. |

Representative ordinance samples:

| Municipality | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Charlotte / South Charlotte | Charlotte zoning page `https://www.charlottenc.gov/Growth-and-Development/Planning-and-Development/Zoning/Zoning-Ordinance`; UDO Article 15 `https://charlotteudo.org/articles/part-vii-uses/article-15-uses`. | **MATRIX-SPRINTABLE after ingestion.** Article 15.2 says Table 15-1 Use Matrix identifies permitted, temporary, and accessory uses by zoning district. | City-level zoning districts. |
| Matthews | UDO page `https://www.matthewsnc.gov/pview.aspx?id=20754`; full UDO PDF `https://matthewsnc.municipalone.com/files/documents/FullUDODocument1318125052031524PM.pdf`. | **PARTIAL.** UDO is online but PDF-heavy; Chapter 5/use districts are extractable but less direct than Charlotte UDO. | Town-level zoning districts. |
| Huntersville / Cornelius / Davidson subarea | Mecklenburg Code Info page `https://code.mecknc.gov/customer-tools/circ` points users to the proper zoning jurisdiction links for each municipality. | **STRUCTURAL SUBSET.** County product jurisdiction spans many zoning authorities; a municipal authority map is required. | Municipal zoning jurisdictions, not one county zoning code. |

Directory shape needed:

```json
{
  "place_name": "Charlotte",
  "authority_name": "City of Charlotte",
  "county": "Mecklenburg",
  "state": "NC",
  "prod_city_value": null,
  "ordinance_url": "https://charlotteudo.org/articles/part-vii-uses/article-15-uses",
  "ordinance_platform": "charlotte_udo",
  "use_structure": "global_use_matrix",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Wake County, NC

Verdict: **INGESTION-BLOCKED.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `b05b7317-b412-492c-a56c-433d447d17bf` |
| Registered? | Yes, `Wake County, NC`. |
| parcel_count | Admin coverage row says `0` but is stale; parcel search total returns `435,434`. |
| parcel_zoning_code_coverage_pct | Admin says `0.0`; sampled parcel rows have `zoning_code=null`. |
| zoning_district_count | Admin coverage row says `0`. |
| operational_readiness | Admin says `not_loaded`, but current parcel search shows parcels loaded. Treat as stale coverage; operationally parcels-only. |
| blocking_gaps | Stale admin gaps: `no_parcels`, `no_zone_use_matrix`, `no_zoning_polygons`, `missing_bbox`; current blocker: no parcel zoning codes and no city drilldown. |
| city drilldown | `/api/jurisdictions/{id}/cities` returns `[]`. |
| parcel sample | Largest rows include APNs `1802015192`, `0618420089`, `0776365198`; all `city=null`, `zoning_code=null`. |

Representative ordinance samples:

| Municipality | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Cary | Town page `https://www.carync.gov/business-development/developing-in-cary/development-guidelines/permitted-uses-setbacks`; LDO page `https://www.carync.gov/business-development/developing-in-cary/development-regulations/land-development-ordinance`; full LDO PDF `https://files.amlegal.com/pdffiles/Cary_pdf/Entire_LDO.pdf`. | **MATRIX-SPRINTABLE after ingestion.** Cary explicitly directs users to permitted-use tables and setbacks by zoning. | Town-level zoning districts. |
| Raleigh / North Raleigh | Raleigh UDO §6.1.4 Allowed Principal Use Table `https://udo.raleighnc.gov/sec-614-allowed-principal-use-table`; §6.1.3 key `https://udo.raleighnc.gov/sec-613-key-use-table`. | **MATRIX-SPRINTABLE after ingestion.** Explicit use table with P/L/S coding; snippet includes Self-Service Storage row. | City-level zoning districts. |
| Apex | UDO page `https://www.apexnc.org/233/Unified-Development-Ordinance`; Article 4.2 Use Table PDF `https://www.apexnc.org/DocumentCenter/View/549`. | **MATRIX-SPRINTABLE after ingestion.** UDO exposes a use table by district. | Town-level zoning districts. |
| Wake Forest | UDO page `https://www.wakeforestnc.gov/planning/unified-development-ordinance`; zoning page says permitted uses are in §2.3.3: `https://www.wakeforestnc.gov/planning/zoning`. | **MATRIX-SPRINTABLE after ingestion.** Permitted Use Table exists, but source is town-specific. | Town-level zoning districts. |

Directory shape needed:

```json
{
  "place_name": "Raleigh",
  "authority_name": "City of Raleigh",
  "county": "Wake",
  "state": "NC",
  "prod_city_value": null,
  "ordinance_url": "https://udo.raleighnc.gov/sec-614-allowed-principal-use-table",
  "ordinance_platform": "raleigh_udo",
  "use_structure": "allowed_principal_use_table",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Douglas County, CO

Verdict: **INGESTION-BLOCKED.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `ec296fd0-d042-4fbb-aea7-6bf7242a6c45` |
| Registered? | Yes, `Douglas County, CO`. |
| parcel_count | No admin coverage row found; parcel search total returns `152,441`. |
| parcel_zoning_code_coverage_pct | Unknown in coverage; sampled parcel rows have `zoning_code=null`. |
| zoning_district_count | No admin coverage row found. |
| operational_readiness | No admin coverage row found; product state is parcels loaded but zoning unbound. |
| blocking_gaps | No admin row; current blocker: no parcel zoning codes and no city drilldown. |
| city drilldown | `/api/jurisdictions/{id}/cities` returns `[]`. |
| parcel sample | Largest rows include APNs `261123000001`, `276722100001`, `276515100002`; all `city=null`, `zoning_code=null`. |

Representative ordinance samples:

| Municipality / sub-jurisdiction | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Unincorporated Douglas | Douglas zoning page `https://www.douglasco.gov/planning/development-review-regulations/zoning/`; zoning resolution page `https://www.douglasco.gov/planning/development-review-regulations/zoning/development-zoning-compliance/`. | **PARTIAL.** County zoning resolution is online; uses include allowed/special-review sections, but many target areas are planned developments rather than simple districts. | County-level for unincorporated parcels. |
| Highlands Ranch | Planned Development guides page `https://www.douglasco.gov/planning/development-review-regulations/zoning/zoning-planned-developments/`; Highlands Ranch PD summary `https://www.douglasco.gov/documents/highlands-ranch-pd-summary.pdf`. | **STRUCTURAL WRINKLE.** PD guide governs land uses and development standards for Highlands Ranch rather than a simple ordinance use table. | Planned development / planning-area scope. |
| Castle Pines | City zoning page `https://www.castlepinesco.gov/city-services/city-departments/community-development/land-use-zoning/zoning/`; ordinance viewer `https://online.encodeplus.com/regs/castlepines-co/doc-viewer.aspx`. | **PARTIAL.** EncodePlus code has principal uses / special review sections, but municipal and PD boundaries must be separated. | City-level zoning districts. |
| Castle Rock / Lone Tree | Castle Rock ordinances often use tables for specific districts; Lone Tree has municipal zoning separate from county. | **PARTIAL.** Need municipal authority map and zone-source discovery. | Municipal zoning districts. |

Directory shape needed:

```json
{
  "place_name": "Highlands Ranch",
  "authority_name": "Douglas County",
  "county": "Douglas",
  "state": "CO",
  "prod_city_value": null,
  "ordinance_url": "https://www.douglasco.gov/documents/highlands-ranch-pd-summary.pdf",
  "ordinance_platform": "county_pdf_pd_guide",
  "use_structure": "planned_development_guide",
  "zoning_map_url": "...",
  "zone_code_scope": "planned_development",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Arapahoe County, CO

Verdict: **INGESTION-BLOCKED.**

Current prod state:

| Field | Value |
|---|---|
| jurisdiction_id | `5c4b612c-a5a7-47dc-af9f-b955d97c3d4e` |
| Registered? | Yes, `Arapahoe County, CO`. |
| parcel_count | No admin coverage row found; parcel search total returns `231,430`. |
| parcel_zoning_code_coverage_pct | Unknown in coverage; sampled parcel rows have `zoning_code=null`. |
| zoning_district_count | No admin coverage row found. |
| operational_readiness | No admin coverage row found; product state is parcels loaded but zoning unbound. |
| blocking_gaps | No admin row; current blocker: no parcel zoning codes and no city drilldown. |
| city drilldown | `/api/jurisdictions/{id}/cities` returns `[]`. |
| parcel sample | Largest rows include APNs `034831029`, `031565537`, `031583128`; all `city=null`, `zoning_code=null`. |

Representative ordinance samples:

| Municipality / sub-jurisdiction | Ordinance source | Pattern fit | Zone-code scope |
|---|---|---|---|
| Unincorporated Arapahoe | County zoning page `https://www.arapahoeco.gov/your_county/county_departments/public_works_and_development/divisions/zoning/index.php`; LDC PDF `https://files.arapahoeco.gov/Public%20Works_Development/zoning/Land%20Development%20Code/Arapahoe%20County%20LDC%20Rev%2009-12-2023%20FINAL%20VERSION%20WITH%20BOOKMARKS.pdf`. | **PARTIAL.** County LDC is online and references the official Arapahoe County Zoning Map, but only applies outside municipal zoning authority. | County-level for unincorporated parcels. |
| Cherry Hills Village | Municode `https://library.municode.com/co/cherry_hills_village`; zoning division page `https://www.cherryhillsvillage.com/382/Planning-Zoning-Division`; ordinance packet example has Table 16-2-120 Land Use by Zoning District `https://www.cherryhillsvillage.com/Archive.aspx?ADID=1307`. | **MATRIX-SPRINTABLE after ingestion.** Explicit land-use-by-zoning-district table. | City-level zoning districts. |
| Greenwood Village | Municode `https://library.municode.com/co/greenwood_village`; adopted codes page `https://www.greenwoodvillage.com/2501/Adopted-Codes-Manuals`. | **MATRIX-SPRINTABLE after ingestion.** Land Development Code is municipal; use and district rules are city-level. | City-level zoning districts. |
| Englewood | Zoning page `https://www.englewoodco.gov/government/city-departments/community-development/zoning`; UDC Chapter 4 PDF `https://englewoodgov.civicweb.net/document/152672/` says Table 16-4-2 identifies permitted and conditional uses. | **MATRIX-SPRINTABLE after ingestion.** Explicit use table by district. | City-level zoning districts. |

Directory shape needed:

```json
{
  "place_name": "Cherry Hills Village",
  "authority_name": "City of Cherry Hills Village",
  "county": "Arapahoe",
  "state": "CO",
  "prod_city_value": null,
  "ordinance_url": "https://library.municode.com/co/cherry_hills_village",
  "ordinance_platform": "municode",
  "use_structure": "land_use_by_zoning_district_table",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "null_in_sample"
}
```

## Recommendation

Do not dispatch matrix sprints for this batch yet.

1. **Load first:** Plymouth and Cook need full jurisdiction/parcel ingest before any Bergen-pattern test is meaningful.
2. **Backfill join keys first:** Fulton, Mecklenburg, Wake, Douglas, and Arapahoe have parcels but no exposed municipality or parcel `zoning_code` join key in sampled responses.
3. **Best first ingestion-blocked target:** Wake County. Raleigh, Cary, Apex, and Wake Forest have explicit use tables, so once municipality + zone codes are populated, the ordinance side should be the cleanest sprint.
4. **Highest structural caution:** Douglas County. Highlands Ranch is a planned development guide, so even after zone-code ingestion, directory records need `zone_code_scope=planned_development` for some target areas.
