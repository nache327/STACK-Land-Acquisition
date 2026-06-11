# Phase 6 Structural Diagnostic

Date: 2026-06-11

Scope: Maricopa AZ, King WA, Multnomah OR, Clackamas OR, Hennepin MN, Oakland MI, Allegheny PA, Summit UT / Park City, Contra Costa CA, and Miami-Dade FL.

Question: for the final Phase 6 Western/outlier target markets in `docs/TARGET_MARKETS.md`, are they Bergen/NJ-style matrix sprints, ingestion-blocked, not loaded, polygon-blocked, or structurally different?

Short answer: **9 of 10 requested county targets are not loaded in prod.** The exception is **Park City, UT**, which is registered as a city-scoped jurisdiction in Summit County, has 6,651 parcels, 99.8% parcel `zoning_code` coverage, 124 zoning districts, and no admin blocking gaps. Park City is the only Phase 6 quick-win candidate, but it is not proof that the full Summit County / Promontory corridor is covered.

## Bottom-Line Classification

Prod sources checked:

- `GET https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions`
- `GET https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage`
- `POST https://capable-serenity-production-0d1a.up.railway.app/api/parcels/search` for the one registered Summit/Park City match

| County / target | Prod state | Classification | Next action |
|---|---|---|---|
| Maricopa County, AZ | No `Maricopa` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register county/city pipeline from Maricopa parcels plus Scottsdale/Paradise Valley zoning sources. |
| King County, WA | No `King` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register and ingest King County parcels, then join municipal zoning for Bellevue/Mercer Island. |
| Multnomah County, OR | No `Multnomah` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register and ingest Multnomah/Metro tax lots if Portland-area Lake Oswego spillover is needed. |
| Clackamas County, OR | No `Clackamas` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register and ingest Clackamas tax lots; this is the primary Lake Oswego county source. |
| Hennepin County, MN | No `Hennepin` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register county parcels and municipal zoning directories for Edina/Wayzata. |
| Oakland County, MI | No `Oakland` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register county parcel/GIS source and municipal zoning for Birmingham/Bloomfield Hills. |
| Allegheny County, PA | No `Allegheny` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register WPRDC/Allegheny parcel boundaries and Fox Chapel/O'Hara municipal zoning. |
| Summit County, UT / Park City | `Park City, UT` registered; `parcel_count=6651`; `parcel_zoning_code_coverage_pct=99.8`; `zoning_district_count=124`; `operational_readiness=operational`; no blocking gaps. | **MATRIX-SPRINTABLE** | Quick-win candidate for Park City/Deer Valley city corridor. Confirm Promontory/unincorporated Summit separately before claiming full Summit coverage. |
| Contra Costa County, CA | No `Contra Costa` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register county parcel source and municipal zoning for Lafayette/Walnut Creek. |
| Miami-Dade County, FL | No `Miami-Dade` jurisdiction match; no admin coverage row. | **NOT-LOADED-NEEDS-INGEST** | Register Miami-Dade parcel source and Pinecrest zoning. |

Phase 6 class counts for the 10 requested rows:

| Classification | Count |
|---|---:|
| NOT-LOADED-NEEDS-INGEST | 9 |
| INGESTION-BLOCKED | 0 |
| MATRIX-SPRINTABLE | 1 |
| POLYGON-BLOCKED | 0 |
| STRUCTURAL-OTHER | 0 |

Note on target counting: `docs/TARGET_MARKETS.md` treats Multnomah/Clackamas as a Lake Oswego split and Salt Lake/Summit as a Park City corridor caveat. This doc classifies the 10 county rows requested here. Polygon counts still need the authoritative KMZ mapping because `TARGET_MARKETS.md` already notes a 57/58 reconciliation issue.

## Maricopa County, AZ

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Maricopa` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: county parcel/GIS ingest plus municipal zoning joins. Maricopa County publishes GIS data through its open data portal (`https://data-maricopa.opendata.arcgis.com/`) and a public parcel viewer (`https://maps.mcassessor.maricopa.gov/`). The Maricopa open-data parcel dataset is explicitly described as active parcels within Maricopa County: `https://data-maricopa.opendata.arcgis.com/datasets/c937f17330f64e64abd41976fc8bb17f`.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Scottsdale | County parcels from Maricopa GIS / Assessor; city zoning lookup also needed. | Scottsdale zoning resources: `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning`; city page lists "XI Land Use Tables." | **MATRIX-SPRINTABLE after ingest.** Scottsdale is close to the Bergen pattern because Article XI is a zone-code-indexed land-use table, including Table 11.201.A for commercial/industrial/parking uses. | City-level zoning districts. |
| Paradise Valley | County parcels from Maricopa; town zoning map/official code needed. | Town code page: `https://www.paradisevalleyaz.gov/281/Town-Code`; zoning map: `https://www.paradisevalleyaz.gov/DocumentCenter/View/277/Zoning-Map`. | **PARTIAL after ingest.** Mostly estate-residential/special-use district rules, more narrative than Scottsdale's global use table. | Town-level zoning districts. |

Directory shape after ingest:

```json
{
  "place_name": "Scottsdale",
  "authority_name": "City of Scottsdale",
  "county": "Maricopa",
  "state": "AZ",
  "parcel_source_url": "https://data-maricopa.opendata.arcgis.com/datasets/c937f17330f64e64abd41976fc8bb17f",
  "ordinance_url": "https://www.scottsdaleaz.gov/codes-and-ordinances/zoning",
  "ordinance_platform": "city_site",
  "use_structure": "article_xi_land_use_tables",
  "zoning_map_url": "...",
  "zone_code_scope": "municipal",
  "parcel_zone_code_status": "jurisdiction_absent"
}
```

## King County, WA

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `King` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: King County parcel/GIS ingest plus city zoning joins. King County publishes GIS data through the King County GIS Open Data hub (`https://gis-kingcounty.opendata.arcgis.com/`) and iMap (`https://kingcounty.gov/en/dept/kcit/data-information-services/gis-center/maps-apps/imap`).

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Bellevue | King County parcels plus Bellevue land-use district/zoning map. | Bellevue Land Use Code: `https://bellevue.municipal.codes/LUC`; Land Use Code tables page: `https://bellevue.municipal.codes/LUC/Tables`; Downtown Land Use Charts example: `https://bellevue.municipal.codes/LUC/20.25A.050`. | **MATRIX-SPRINTABLE after ingest.** Bellevue has land-use charts keyed by district, but there are district/overlay-specific chart sections rather than one county table. | City-level land-use/zoning districts. |
| Mercer Island | King County parcels plus Mercer Island zoning map. | Municode Title 19 Unified Land Development Code: `https://library.municode.com/wa/mercer_island/codes/city_code?nodeId=TIT19UNLADECO`. | **MATRIX-SPRINTABLE after ingest.** Title 19 is local and table/section based; extractable once parcel zone codes exist. | City-level zoning districts. |

## Multnomah County, OR

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Multnomah` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Multnomah taxlot/parcel ingest if the target polygon includes Multnomah-side Portland-area parcels. Multnomah County GIS is at `https://multco.us/info/geographic-information-system-gis`; its ArcGIS open-data search includes tax parcels from Assessment, Recording and Taxation: `https://gis-multco.opendata.arcgis.com/search?tags=parcels`. PortlandMaps also documents weekly taxlot parcels inside Portland and Metro updates outside Portland: `https://www.portlandmaps.com/metadata/index.cfm?LayerID=52065&action=DisplayLayer`.

Representative samples:

| Municipality / area | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Portland west/southwest spillover | Multnomah taxlots / PortlandMaps. | Portland zoning code Title 33: `https://www.portland.gov/code/33`. | **PARTIAL after ingest.** Title 33 is use-category and base-zone driven, but Portland has overlays and plan districts; not a clean Bergen-style county matrix. | City-level base zones and overlays. |
| Lake Oswego area note | Lake Oswego is primarily a Clackamas ingest problem; Multnomah may only matter for edge cases. | Lake Oswego zoning page: `https://www.ci.oswego.or.us/planning/zoning`; code source: `https://ecode360.com/45996060`. | **MATRIX-SPRINTABLE after Clackamas/Lake Oswego ingest.** The city page points to LOC 50.03.002 Use Table, but parcel source should be chosen by county side. | City-level zoning districts across county boundary where applicable. |

## Clackamas County, OR

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Clackamas` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Clackamas County parcel/taxlot ingest plus Lake Oswego municipal zoning. Clackamas GIS publishes CMap (`https://www.clackamas.us/cmap`) and a data portal (`https://www.clackamas.us/gis/data-portal`), with data offered as shapefiles.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Lake Oswego | Clackamas CMap / taxlot data plus city zoning. | City zoning page: `https://www.ci.oswego.or.us/planning/zoning`; eCode360 Chapter 50 Community Development Code: `https://ecode360.com/45996060`; LOC 50.03 Use Regulations and Conditions: `https://ecode360.com/43075916`. | **MATRIX-SPRINTABLE after ingest.** LOC 50.03.002 includes residential and commercial/mixed-use/industrial/special-purpose use tables listing uses as allowed, conditional, or prohibited by base zone. | City-level zoning districts. |
| West Linn / adjacent Clackamas wealth pockets | Clackamas CMap; municipal zoning maps/codes. | West Linn points users to Clackamas CMap for property lookup: `https://westlinnoregon.gov/maps/clackamas-county-gis-cmap`. | **PARTIAL after ingest.** Municipal code lookup needed per city; not county-level. | City-level zoning districts. |

## Hennepin County, MN

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Hennepin` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Hennepin County parcels plus municipal zoning. Hennepin GIS publishes an open-data hub (`https://gis-hennepin.hub.arcgis.com/`) and identifies county parcels as a popular open dataset. ArcGIS Hub describes the county parcel dataset as polygons for individual taxed and tax-exempt parcels: `https://hub.arcgis.com/maps/hennepin::county-parcels`.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Edina | Hennepin county parcels plus Edina zoning map. | Municode Edina code: `https://library.municode.com/mn/edina`; Chapter 36 Zoning is the active zoning chapter. | **PARTIAL after ingest.** Online, but older municipal-code structure with district rules/PUDs rather than a simple Bergen-style table. | City-level zoning districts. |
| Wayzata | Hennepin county parcels plus Wayzata zoning map. | Municode Wayzata code: `https://library.municode.com/mn/wayzata/codes/code_of_ordinances`; Chapter 901 Zoning. | **PARTIAL after ingest.** District-by-district municipal code, extractable but not one county-wide matrix. | City-level zoning districts. |

## Oakland County, MI

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Oakland` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Oakland County parcel/GIS ingest plus municipal zoning. Oakland County GIS maps/data page points to Access Oakland open data (`https://www.oakgov.com/government/information-technology/enterprise-gis/maps-data`), and the county Property Gateway provides free property information and tax parcel maps with city/village/township availability caveats: `https://www.oakgov.com/government/property-gateway`.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Birmingham | Oakland parcel/GIS source plus city zoning map. | Birmingham zoning ordinance page: `https://www.bhamgov.org/about_birmingham/city_departments/planning_department/zoning_ordinance.php`; Municode Chapter 126 Zoning is also available under Birmingham code. | **PARTIAL after ingest.** Local zoning ordinance with schedules/district articles; extractable but municipal, not county-level. | City-level zoning districts. |
| Bloomfield Hills | Oakland parcel/GIS source plus city zoning map. | Municode Bloomfield Hills Chapter 54 Zoning: `https://library.municode.com/mi/bloomfield_hills/codes/code_of_ordinances?nodeId=COOR_CH54ZO`. | **PARTIAL after ingest.** Mostly residential district rules and local permitted/conditional-use sections. | City-level zoning districts. |

## Allegheny County, PA

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Allegheny` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Allegheny County parcel ingest plus borough/township zoning. WPRDC publishes Allegheny County Parcel Boundaries (`https://data.wprdc.org/dataset/allegheny-county-parcel-boundaries1`) and describes the dataset as individual parcel boundaries with county block and lot number. WPRDC also publishes an Allegheny County Property Viewer (`https://data.wprdc.org/dataset/http-alcogis-maps-arcgis-com-apps-webappviewer-index-html-id-b4b1dbb65b4943538425bb5ae0f8f62b`).

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Fox Chapel | WPRDC parcel boundaries plus borough zoning. | eCode360 Chapter 400 Zoning: `https://ecode360.com/31904910`; borough district classifications page: `https://www.fox-chapel.pa.us/185/Classifications`. | **STRUCTURAL-OTHER after ingest for storage matrix.** Simple district structure with five borough zoning districts, heavily residential and not a rich use table; matrix can be authored but not with a Bergen-style table sprint. | Borough-level zoning districts. |
| O'Hara Township / adjacent Fox Chapel area | WPRDC parcels plus township zoning. | O'Hara Township eCode360 entry point: `https://www.ohara.pa.us/administration/pages/township-code-ecode360`. | **PARTIAL after ingest.** Township code/zoning map needed for non-borough parcels around the corridor. | Township-level zoning districts. |

Primary class remains **NOT-LOADED-NEEDS-INGEST** because prod has no jurisdiction/parcels. The ordinance structure is a secondary issue after ingest.

## Summit County, UT / Park City

Verdict: **MATRIX-SPRINTABLE for the registered Park City jurisdiction; not full Summit County coverage.** This is the Phase 6 quick-win candidate.

Current prod state:

| Field | Value |
|---|---|
| Registered? | Yes, `Park City, UT`; no separate `Summit County, UT` county-wide match found. |
| jurisdiction_id | `13b01b39-11cc-46b6-a680-33d68fdf4629` |
| coverage_level | `partial` |
| county | `Summit` in `/api/jurisdictions`; `Summit County` in `/api/admin/coverage`. |
| parcel_count | `6651` |
| parcel_zoning_code_coverage_pct | `99.8` |
| zoning_district_count | `124` |
| matrix_zone_count | `8` |
| operational_readiness | `operational` |
| blocking_gaps | `[]` |
| city drilldown | `/cities` returns `Park City` with `6651` parcels. |
| parcel sample | `POST /api/parcels/search` total `6651`; sampled APNs include `PCA-S-98-PCMR-1` with `zoning_code=OS`, `PCA-S-98-C` with `zoning_code=OS`, `SS-87` with `zoning_code=null`, and `SS-57-A-X` with `zoning_code=OS`. |

Matrix/citation caveat: `/api/jurisdictions/13b01b39-11cc-46b6-a680-33d68fdf4629/zones` returns 8 matrix rows (`Comm`, `CT`, `INT`, `LDR`, `MDR`, `OS`, `RCom`, `UOL`), each with `confidence=0.35`, `classification_source=unclear`, and `citation_url=null`. The parcel/zoning-code join is ready; the matrix still needs a citation sprint.

Representative samples:

| Municipality / area | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Park City / Deer Valley city corridor | Already loaded in prod as `Park City, UT`; city parcel zone codes are populated at 99.8%. | Park City Land Management Code Title 15, Chapter 2 district regulations: `https://parkcity.municipalcodeonline.com/book/print?name=15-2.1_Historic_Residential-Low_Density_%28HRL%29_District&type=ordinances`; city PDF examples include Title 15 Chapter 2.6 HCB district: `https://parkcity.gov/home/showdocument?id=231`. | **MATRIX-SPRINTABLE.** Park City uses district-specific allowed/conditional use lists, e.g. LMC 15-2.1-2 "Uses" for HRL and LMC 15-2.6-2 for HCB. It is not a single global Bergen table, but the zone-code population and online code make a citation sprint feasible. | City-level zoning districts. |
| Promontory / unincorporated Summit | Not shown as a separate loaded prod jurisdiction in this probe. | Summit County interactive maps: `https://summitcounty.org/892/Interactive-Maps`; Promontory likely depends on Summit County development agreements / SPA-style approvals, not Park City city zoning. | **UNKNOWN / likely separate ingest.** Do not assume Park City coverage reaches Promontory or all Deer Valley-adjacent unincorporated parcels. | County/unincorporated or special planning area, not Park City city code. |

Recommended Summit action:

1. Treat **Park City, UT** as a near-term matrix/citation sprint candidate.
2. Before using this to claim the full wealth corridor, run a small Promontory/unincorporated Summit parcel-source check and decide whether a separate Summit County ingest is needed.
3. Do not dispatch a full county ingest if the immediate target is only Park City/Deer Valley city parcels; prod already has the join key for that subset.

## Contra Costa County, CA

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Contra Costa` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Contra Costa parcel/GIS ingest plus municipal zoning. Contra Costa maps/property page points to ParcelQuest Lite for APN/property details (`https://www.contracosta.ca.gov/552/Maps-Property-Information`), and the county GIS page is `https://www.contracosta.ca.gov/1818/GIS`. County parcel viewer: `https://experience.arcgis.com/experience/caa59504ea0040cfac8ea0b11393c486`.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Lafayette | County parcel source plus city zoning. | Lafayette municipal code: `https://www.codepublishing.com/CA/Lafayette/`; city planning/zoning page: `https://www.lovelafayette.org/city-hall/city-departments/planning-building/planning/zoning`. | **PARTIAL after ingest.** City-level planning and land-use code, not a county matrix; likely extractable by district. | City-level zoning districts. |
| Walnut Creek | County parcel source plus city zoning web map. | Walnut Creek zoning page: `https://www.walnutcreekca.gov/government/community-development-department/zoning`; zoning web map: `https://www.walnutcreekca.gov/government/community-development-department/zoning/maps/zoning-web-map`; eCode360 Title 10: `https://ecode360.com/WA4684`. | **MATRIX-SPRINTABLE after ingest.** City page points to summary land-use regulation tables and the web map exposes parcel zoning codes. | City-level zoning districts. |

## Miami-Dade County, FL

Verdict: **NOT-LOADED-NEEDS-INGEST.**

Current prod state:

| Field | Value |
|---|---|
| Registered? | No match for `Miami-Dade` or `Miami` in `/api/jurisdictions`. |
| Admin coverage | No matching row in `/api/admin/coverage`. |
| parcel_count | Absent / not loaded. |
| parcel_zoning_code_coverage_pct | Absent / not loaded. |
| zoning_district_count | Absent / not loaded. |
| operational_readiness | Absent from prod. |
| blocking_gaps | Jurisdiction not registered; no parcels or zoning/matrix state. |

Source class needed: Miami-Dade parcel ingest plus municipal zoning. Miami-Dade Open Data Hub is `https://gis-mdc.opendata.arcgis.com/`; the county parcel dataset is `https://gis-mdc.opendata.arcgis.com/datasets/MDC::parcel/about`; county GIS online services note that 650+ GIS datasets are downloadable through the open data hub (`https://www.miamidade.gov/global/service.page?Mduid_service=ser1495571905689513`). Property Appraiser search is `https://www.miamidadepa.gov/pa/real-estate/property-search.page`.

Representative samples:

| Municipality | Parcel / zoning source | Ordinance and map source | Pattern fit | Zone-code scope |
|---|---|---|---|---|
| Pinecrest | Miami-Dade parcel dataset plus village zoning. | Pinecrest Municode search entry for Chapter 30 Land Development Regulations / Article 4 Zoning District Regulations: `https://library.municode.com/search?clientId=10759&contentTypeId=CODES&searchText=PR&stateId=9`; village zoning page: `https://www.pinecrest-fl.gov/Government/Departments/Building-and-Planning/Zoning`. | **PARTIAL after ingest.** Chapter 30 has district regulations by district; not one clean county-level use matrix. | Village-level zoning districts. |
| Coral Gables / adjacent high-value submarket | Miami-Dade parcel dataset plus city zoning. | Coral Gables zoning code: `https://library.municode.com/fl/coral_gables/codes/zoning`. | **MATRIX-SPRINTABLE after ingest.** Local zoning code is online and structured, but city-specific. | City-level zoning districts. |

## 57-LIST COMPLETION SUMMARY

This section reconciles the three structural diagnostic documents now produced in this lane:

- `docs/PHASE2_NY_CT_DIAGNOSTIC.md`
- `docs/PHASE4_5_STRUCTURAL_DIAGNOSTIC.md`
- `docs/PHASE6_STRUCTURAL_DIAGNOSTIC.md`

The counts below are **diagnostic target rows / county-market rows**, not a literal KMZ polygon count. `docs/TARGET_MARKETS.md` explicitly flags a 57-vs-58 count reconciliation issue, and several market rows map to multiple wealth-pocket polygons. Use this as the planning classification for the diagnosed structural backlog; use the KMZ to convert to exact polygon counts.

| Classification | Count across PR #212 + PR #215 + this PR | Rows |
|---|---:|---|
| INGESTION-BLOCKED | 8 | Westchester NY, Nassau NY, Fairfield CT, Fulton GA, Mecklenburg NC, Wake NC, Douglas CO, Arapahoe CO |
| NOT-LOADED-NEEDS-INGEST | 11 | Plymouth MA, Cook IL, Maricopa AZ, King WA, Multnomah OR, Clackamas OR, Hennepin MN, Oakland MI, Allegheny PA, Contra Costa CA, Miami-Dade FL |
| MATRIX-SPRINTABLE | 1 | Park City UT / Summit quick-win subset |
| POLYGON-BLOCKED | 0 | None newly classified by these three diagnostics. |
| STRUCTURAL-OTHER | 0 | None as the primary class; several rows have secondary structural caveats after ingest. |

Whole target-map planning view:

| Bucket | Count / status | Source / note |
|---|---:|---|
| Already operational/live polygons | About 7 | `docs/TARGET_MARKETS.md` scorecard lists Somerset NJ, Fairfax VA, Montgomery MD, Howard MD, Lake IL, Salt Lake City UT, and Allentown PA as live/operational. |
| Diagnosed structural backlog in this lane | 20 county-market rows | The table above: 8 ingestion-blocked, 11 not-loaded, 1 matrix-sprintable quick win. |
| Other in-flight diagnostics skipped by PR #215 | 3 county rows | Norfolk MA, Middlesex MA, and DuPage IL were intentionally skipped because other orchestrator lanes were diagnosing them. |
| Previously known Phase 1 / Phase 2A partials outside this final batch | Open | Bergen/Morris/Monmouth/Hunterdon NJ, Loudoun VA, Montgomery PA, Williamson TN, Jefferson CO, and any other pre-existing partial lanes should be read from their owning docs/PRs rather than reclassified here. |

Operational implication for Master:

1. **Do not schedule Phase 6 county matrix sprints except Park City.** Nine rows need registration + parcel ingest first.
2. **Park City is a plausible quick win.** The join key exists and coverage is 99.8%, but current matrix rows are low-confidence and uncited.
3. **Promontory/Summit remains a caveat.** Park City operationalization does not by itself cover unincorporated Summit County or Promontory-style special planning areas.
