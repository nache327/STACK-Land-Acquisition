# Ingest Source Scoping - NOT-LOADED Counties

Date: 2026-06-11

Scope: the 11 `NOT-LOADED-NEEDS-INGEST` counties from `docs/PHASE4_5_STRUCTURAL_DIAGNOSTIC.md` and `docs/PHASE6_STRUCTURAL_DIAGNOSTIC.md`: Plymouth MA, Cook IL, Maricopa AZ, King WA, Multnomah OR, Clackamas OR, Hennepin MN, Oakland MI, Allegheny PA, Contra Costa CA, and Miami-Dade FL. Summit UT is intentionally skipped because `Park City, UT` is already operational per the Phase 6 diagnostic.

Question: before Lane A builds ingestion adapters, what is the parcel-source acquisition path for each county, and which sources should Master dispatch first?

## Executive Read

Three conclusions matter for sprint planning after the MassGIS halt in
`docs/OP5_MASSGIS_INGEST_SPRINT.md`:

1. **No remaining non-MA source cleanly unlocks >=3 57-list counties.**
   The best regional leverage is Oregon's PortlandMaps/RLIS taxlot
   source for Multnomah + Clackamas, but that is two counties and one
   Lake Oswego target area. MetroGIS covers seven Twin Cities counties,
   but only Hennepin is in this 57-list batch.
2. **Most Phase 6 rows have good parcel geometry sources.** Maricopa,
   King, Cook, Hennepin, Oakland, Allegheny, Contra Costa, and
   Miami-Dade are not blocked on public parcel geometry. They are
   blocked on registering/loading parcels, then joining city/town zoning.
3. **Zoning is still the long pole.** Live field probes did not verify
   any embedded county parcel `zoning_code` source, and the county-level
   zoning layers found are unincorporated-only or not applicable to the
   target incorporated municipalities. Treat every non-MA row here as
   Class B until a municipality-specific zoning layer proves otherwise.

Source-class legend:

- **SINGLE-STATE-AGGREGATOR**: one state or regional public parcel source covers multiple counties.
- **SINGLE-COUNTY-PORTAL**: one county portal covers this county's parcel geometry.
- **PER-MUNICIPALITY**: parcel geometry itself is fragmented by town/city.
- **BLOCKED**: no usable public parcel source found in the time box.

Zoning-source legend follows Lane A's `docs/INGESTION_PIPELINE_PLAN.md`:

- **Embedded parcel field / Class C-like**: zoning can be mapped during parcel ingest.
- **Separate zoning layer / Class A-like**: zoning polygons exist and need spatial backfill.
- **Per-municipality ordinance/GIS / Class B-like**: per-city/town directory plus adapter required.
- **None online / Class D blocked**: defer.

Polygon impact is an estimate from `docs/TARGET_MARKETS.md` representative centers, not a parsed KMZ count. The KMZ remains authoritative.

## State-Aggregator / Regional Unlocks First

| Source | URL | Counties covered in this target map | Recommendation |
|---|---|---|---|
| MassGIS Property Tax Parcels | `https://www.mass.gov/info-details/massgis-data-property-tax-parcels` and ArcGIS item `https://hub.arcgis.com/maps/b5f19318e90841d4bcf15e97b55851b7` | Plymouth MA plus Middlesex MA and Norfolk MA partial rows | **DEFER.** Parcel source remains useful, but PR #222 found no clean statewide MA zoning source. Operationalization is per-muni/per-region, not a one-shot MA ingest. |
| Oregon ORMAP / PortlandMaps / RLIS regional taxlots | ORMAP `https://ormap.net/`; PortlandMaps metadata `https://www.portlandmaps.com/metadata/index.cfm?LayerID=52065&action=DisplayLayer`; RLIS taxlots `https://rlisdiscovery.oregonmetro.gov/datasets/9d3c396ffad44649bc7451465aa300f0` | Multnomah OR and Clackamas OR; source also includes Washington County OR, not a current 57-list county | **BEST REGIONAL UNLOCK.** One source can cover the Lake Oswego county split if raw access and license are acceptable. |
| MetroGIS / Minnesota Geospatial Commons regional parcels | `https://metrogis.org/how-do-i-get/parcel-data/`; `https://gisdata.mn.gov/dataset/us-mn-state-metrogis-plan-regional-parcels`; live layer `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/3` | Hennepin MN only in the current 57 list; seven Twin Cities metro counties in source | **GOOD SOURCE, LOW TARGET-MAP LEVERAGE.** Use for Hennepin, but it does not unlock other 57-list counties today. |
| Washington State Parcels Project | `https://geo.wa.gov/maps/2b603a599a0842a3b2284c04c8927f35` | King WA only in this 57-list batch | **LOWER THAN KING COUNTY PORTAL.** Use direct King County parcel layer first. |
| Florida Statewide Parcels | `https://geodata.floridagio.gov/datasets/FGIO::florida-statewide-parcels/about` | Miami-Dade FL only in this 57-list batch | **LOWER THAN MIAMI-DADE PORTAL.** County feed is direct and current. |
| PASDA county parcel catalog | `https://www.pasda.psu.edu/uci/SearchResults.aspx?Keyword=parcel` | Allegheny PA plus Montgomery PA partial row | **USEFUL FALLBACK, NOT >=3.** WPRDC/Allegheny county source is still cleaner for this row. |
| California statewide parcel boundary collection | `https://hub.arcgis.com/documents/baaf8251bfb94d3984fb58cb5fd93258` | Contra Costa CA only in this 57-list batch | **LOWER THAN COUNTY SOURCE.** Contra Costa publishes monthly assessor parcel shapefiles directly. |
| Michigan Geographic Framework tax parcels | `https://www.michigan.gov/dtmb/services/maps/mgf-data-hub/boundaries-and-mgf/tax-parcels` | Oakland MI only in this 57-list batch | **NOT A PUBLIC STATE UNLOCK.** Michigan says the statewide parcel layer is internal and public parcel layers live on county websites. |

No non-MA source found in this batch clearly unlocks three or more
57-list counties at once.

## Strengthened-Gate Addendum

Applied Lane A's newer rules from the Montgomery PA and MassGIS halt
loops:

- **No Class A claim without spatial proof.** County zoning layers found
  here are either unincorporated-only (Cook County, Contra Costa County)
  or not enough for incorporated target cities. Because they fail source
  scope before geometry, no bbox / 1,000-parcel `ST_Within` dry-run was
  run and no county is classified as Class A.
- **No Class C claim without live field proof.** Live parcel metadata /
  row probes checked likely candidates and did not verify embedded
  municipal zoning:
  - Cook `Current Parcel`: `Pin10`, `PIN14`, `City`, `Town`, assessment
    fields; no zoning-code field.
  - King `King County parcels`: `MAJOR`, `MINOR`, `PIN`, geometry only.
  - Hennepin MetroGIS `Hennepin County Parcels`: `CTU_NAME`, tax/use and
    valuation fields; no zoning-code field.
  - Oakland `Tax Parcel Plus`: `KEYPIN`, `CVTTAXCODE`, `CLASSCODE`,
    address/value fields; no municipal zoning-code field.
  - Miami-Dade `Parcel_poly`: `PID`, `FOLIO`, `PARCEL_STRAP`, edit fields;
    no zoning-code field.
- **Per-municipality zoning remains the default.** Every operational path
  below needs a directory keyed to the target city/town, with parcel
  ingest first and zoning-map/ordinance adapter second.

## Plymouth County, MA

**Post-PR #222 status:** **DEFER for this non-MA follow-up.** MassGIS
remains the parcel source, but `docs/OP5_MASSGIS_INGEST_SPRINT.md`
accepted the zoning-source halt: no clean statewide MA zoning aggregator
with usable county coverage was found. Plymouth needs parcel
registration plus per-muni/per-region zoning work.

Parcel source: **public statewide parcel layer with reliable geometry.**

Source class: **SINGLE-STATE-AGGREGATOR.**

Primary parcel source:

- MassGIS Property Tax Parcels: `https://www.mass.gov/info-details/massgis-data-property-tax-parcels`
- ArcGIS Hub item: `https://hub.arcgis.com/maps/b5f19318e90841d4bcf15e97b55851b7`
- Massachusetts Interactive Property Map: `https://www.mass.gov/info-details/massachusetts-interactive-property-map`

Source notes:

- MassGIS describes the dataset as standardized assessor parcel boundaries and database information from each community's assessor.
- It covers all 351 Massachusetts cities and towns, so it also helps the 57-list Middlesex MA and Norfolk MA rows.
- This is the cleanest not-loaded parcel acquisition path in the batch.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like.**

- Parcel records should carry town identity from MassGIS, but zoning districts are local.
- Plymouth County zoning after parcel ingest should use a `massachusetts_zoning_directory.json` or per-county equivalent keyed by `town_name`, `prod_city_value`, zoning map/source URL, ordinance URL, and zone-code field.
- Existing structural samples already found Hingham, Plymouth, and Cohasset use-table-style ordinances; Duxbury is more narrative/PDF.
- MAPC/National Zoning Atlas material may help as a research layer, but it is not a substitute for authoritative municipal zoning maps and ordinances.

Effort estimate:

- Parcel ingest only: **1-2 days** to build/verify the MassGIS adapter once, then county-scoped load.
- Operational for Plymouth target polygons: **3-5 days** if Hingham plus one or two adjacent towns provide zoning GIS; **1-2 weeks** if zoning maps are PDF/manual.
- Comparable anchor: easier than Lane A Class B Westchester because the parcel source is statewide and standardized; zoning is still municipal.

57-list polygon impact: **1 estimated polygon** for Hingham/Plymouth County, plus indirect source leverage for Middlesex MA and Norfolk MA.

Priority recommendation: **DEFER / PER-MUNI.** Parcel source is clean,
but operationalization is not a one-shot statewide zoning sprint.

## Cook County, IL

Parcel source: **public county parcel layer with reliable geometry.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel source:

- Cook Central / Cook County GIS: `https://www.cookcountyil.gov/CookCentral`
- Cook Central ArcGIS Hub: `https://hub-cookcountyil.opendata.arcgis.com/`
- Property open data page: `https://hub-cookcountyil.opendata.arcgis.com/pages/property-open-data`
- CookViewer: `https://maps.cookcountyil.gov/cookviewer/`
- Current Parcel REST layer: `https://gis.cookcountyil.gov/traditional/rest/services/cookVwrDynmc/MapServer/44`

Source notes:

- Cook Central is the public GIS portal for authoritative county spatial data.
- CookViewer exposes parcel lookup and unincorporated zoning, but the target North Shore municipalities are incorporated.
- Prod already has a `Cook County, IL` jurisdiction shell, but it has zero parcels and admin gaps `no_parcels`, `no_zone_use_matrix`, `no_zoning_polygons`, and `missing_bbox`.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with a small county-zoning exception.

- Cook County publishes unincorporated zoning districts, e.g. `https://hub-cookcountyil.opendata.arcgis.com/datasets/cookcountyil::unincorporated-zoning-districts/explore` and REST layer `https://gis.cookcountyil.gov/traditional/rest/services/unincZoneRules/FeatureServer/0`.
- BTAA metadata explicitly notes those boundaries are only for unincorporated areas and users should contact municipalities for incorporated zoning.
- Winnetka/Wilmette/Glencoe need municipal zoning code/map adapters, not a county-wide zoning layer.

Effort estimate:

- Parcel load repair: **1-3 days** because county portal and jurisdiction shell already exist.
- Operational for Winnetka/North Shore target: **1-2 weeks** for municipal zoning directory + spatial backfill + matrix citations.
- Comparable anchor: parcel acquisition is easier than Nassau NY; zoning resembles Lane A Class D fallback to per-municipality work.

57-list polygon impact: **1 estimated polygon** for Winnetka/Cook County.

Priority recommendation: **MEDIUM**. Good parcel source, but no multi-county unlock and municipal zoning is still required.

## Maricopa County, AZ

Parcel source: **public county parcel layer with reliable geometry.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel source:

- Maricopa County GIS Open Data: `https://data-maricopa.opendata.arcgis.com/`
- Parcel dataset: `https://data-maricopa.opendata.arcgis.com/datasets/c937f17330f64e64abd41976fc8bb17f`
- Assessor parcel viewer: `https://maps.mcassessor.maricopa.gov/`
- GIS mapping applications: `https://www.maricopa.gov/3942/GIS-Mapping-Applications`

Source notes:

- The open-data parcel dataset is a county-wide parcel shapefile identified by APN.
- The Assessor viewer and County GIS pages are public and actively maintained.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with strong municipal table support for Scottsdale.

- Scottsdale zoning resources are online at `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning` and include Article XI Land Use Tables.
- Paradise Valley has official code and zoning map resources, but the structure is more estate-residential/special-use narrative than Scottsdale's land-use table.
- County PlanNet / unincorporated zoning is not enough for Scottsdale and Paradise Valley.

Effort estimate:

- Parcel ingest: **1-2 days**.
- Operational for Scottsdale/Paradise Valley: **3-6 days** if Scottsdale zoning GIS fields are easy to extract; **1-2 weeks** if Paradise Valley requires PDF/map manual treatment.
- Comparable anchor: easier than NY/CT structural prereqs because APN parcel source is clean; zoning is two-city scoped.

57-list polygon impact: **2 estimated polygons** for Scottsdale and Paradise Valley.

Priority recommendation: **HIGH**. Not a multi-county unlock, but strong parcel source and high-value two-center impact.

## King County, WA

Parcel source: **public county parcel layer with reliable geometry.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel source:

- King County GIS Open Data: `https://gis-kingcounty.opendata.arcgis.com/`
- Parcel layer: `https://gis-kingcounty.opendata.arcgis.com/datasets/kingcounty::parcel/about`
- Parcel REST layer: `https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0`
- Parcel Viewer: `https://gismaps.kingcounty.gov/parcelviewer2/`
- iMap: `https://kingcounty.gov/en/dept/kcit/data-information-services/gis-center/maps-apps/imap`

Source notes:

- King County's open parcel layer represents tax parcels county-wide.
- A Washington statewide parcels project exists at `https://geo.wa.gov/maps/2b603a599a0842a3b2284c04c8927f35`, but it does not unlock another 57-list county in this batch, so the county portal is the recommended source.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with possible separate zoning layers.

- King Parcel Viewer has a King County zoning layer, but that is not sufficient for Bellevue and Mercer Island city zoning.
- Bellevue Land Use Code is online at `https://bellevue.municipal.codes/LUC` with land-use charts/tables.
- Mercer Island Title 19 is online at `https://library.municode.com/wa/mercer_island/codes/city_code?nodeId=TIT19UNLADECO`.
- Expect a municipal zoning layer/directory join, not embedded parcel `zoning_code`.

Effort estimate:

- Parcel ingest: **1-2 days**.
- Operational for Bellevue/Mercer Island: **4-8 days** if city zoning layers are downloadable; **1-2 weeks** if only web maps/code tables are available.
- Comparable anchor: similar to Maricopa, but with more district/overlay complexity.

57-list polygon impact: **2 estimated polygons** for Bellevue and Mercer Island.

Priority recommendation: **MEDIUM**. High-value market, clean parcel source, but no multi-county leverage.

## Multnomah County, OR

Parcel source: **public state/regional taxlot sources; county-specific source also exists.**

Source class: **SINGLE-STATE-AGGREGATOR** for planning purposes, because ORMAP/GEOHub is statewide and PortlandMaps/RLIS is a regional multi-county taxlot source.

Primary parcel sources:

- ORMAP statewide property tax map: `https://ormap.net/`
- Oregon GEOHub parcel viewer page: `https://geohub.oregon.gov/pages/parcel-viewer`
- PortlandMaps taxlots metadata: `https://www.portlandmaps.com/metadata/index.cfm?LayerID=52065&action=DisplayLayer`
- Multnomah County GIS: `https://multco.us/info/geographic-information-system-gis`

Source notes:

- ORMAP is statewide and publicly accessible, but raw taxlot download may still route through counties.
- PortlandMaps taxlots are a practical regional source: the metadata says the layer includes Multnomah, Clackamas, and Washington Counties, with taxlot polygons and county property IDs.
- Lake Oswego is primarily Clackamas, so Multnomah should not be the first Oregon row unless KMZ confirms a Multnomah-side polygon.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like.**

- Portland Title 33 is online, but Lake Oswego zoning is city-level and mostly a Clackamas-side problem.
- No evidence that Multnomah taxlots embed the municipal `zoning_code` needed for Lake Oswego.

Effort estimate:

- Parcel ingest if using PortlandMaps/RLIS regional taxlots: **2-4 days** shared with Clackamas.
- Operational for any Multnomah-side target: **1-2 weeks** depending on which municipality the KMZ actually touches.
- Comparable anchor: regional parcel acquisition is plausible; zoning is still municipal and needs a directory.

57-list polygon impact: **0-1 estimated polygon**. Treat as an edge/overflow county for the Lake Oswego polygon until KMZ proves otherwise.

Priority recommendation: **LOW** independently; **MEDIUM** only as part of a joint Oregon taxlot sprint with Clackamas.

## Clackamas County, OR

Parcel source: **public state/regional taxlot sources plus county GIS.**

Source class: **SINGLE-STATE-AGGREGATOR** for planning purposes, paired with Multnomah through ORMAP/PortlandMaps regional taxlots.

Primary parcel sources:

- ORMAP statewide property tax map: `https://ormap.net/`
- Clackamas GIS: `https://www.clackamas.us/gis`
- Clackamas CMap: `https://www.clackamas.us/cmap`
- PortlandMaps taxlots metadata: `https://www.portlandmaps.com/metadata/index.cfm?LayerID=52065&action=DisplayLayer`

Source notes:

- Clackamas County GIS points users to ORMAP for statewide assessor maps and provides CMap for local property/jurisdiction lookup.
- PortlandMaps taxlots explicitly include Clackamas County and are likely the fastest shared source for the Lake Oswego polygon.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with Lake Oswego table support.

- Lake Oswego zoning page: `https://www.ci.oswego.or.us/planning/zoning`
- Lake Oswego Community Development Code via eCode360: `https://ecode360.com/45996060`
- LOC 50.03 Use Regulations and Conditions: `https://ecode360.com/43075916`
- Lake Oswego has use tables, but zoning district geometry still needs city/county map extraction.

Effort estimate:

- Parcel ingest if paired with Multnomah through PortlandMaps/RLIS: **2-4 days**.
- Operational for Lake Oswego: **4-8 days** if Lake Oswego zoning geometry is available as GIS; **1-2 weeks** if zoning map conversion is manual.
- Comparable anchor: easier parcel source than per-muni patchwork; zoning resembles Lane A Class B.

57-list polygon impact: **1 estimated polygon** for Lake Oswego, primary county.

Priority recommendation: **HIGH** if Lake Oswego is next. Best done with Multnomah as one Oregon regional taxlot sprint.

## Hennepin County, MN

Parcel source: **public regional/state parcel aggregator plus county open data.**

Source class: **SINGLE-STATE-AGGREGATOR.**

Primary parcel sources:

- MetroGIS Regional Parcel Dataset: `https://metrogis.org/how-do-i-get/parcel-data/`
- Minnesota Geospatial Commons dataset: `https://gisdata.mn.gov/dataset/us-mn-state-metrogis-plan-regional-parcels`
- MetroGIS Hennepin parcel REST layer: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/3`
- Hennepin GIS Open Data: `https://gis-hennepin.hub.arcgis.com/pages/open-data`
- Hennepin County Parcels ArcGIS Hub item: `https://hub.arcgis.com/maps/hennepin::county-parcels`

Source notes:

- MetroGIS says the regional parcel dataset compiles tax parcel polygon and point layers from seven Twin Cities metropolitan counties: Anoka, Carver, Dakota, Hennepin, Ramsey, Scott, and Washington.
- Hennepin's own parcel layer contains polygons representing taxed and tax-exempt parcels tracked for taxing purposes.
- Only Hennepin is a current 57-list county, so this is a good source but not a high-leverage target-map unlock.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like.**

- Edina and Wayzata zoning ordinances are online through Municode, but zoning districts are local city layers/codes.
- No evidence that the MetroGIS/Hennepin parcel layer embeds city zoning codes for Edina/Wayzata.

Effort estimate:

- Parcel ingest: **1-3 days** using Hennepin direct or MetroGIS.
- Operational for Edina/Wayzata: **4-8 days** if municipal zoning layers exist; **1-2 weeks** if city map extraction is manual.
- Comparable anchor: similar to King/Maricopa after parcel load; municipal zoning drives the schedule.

57-list polygon impact: **2 estimated polygons** for Edina and Wayzata.

Priority recommendation: **MEDIUM**. Clean parcel source, good market, but one target county.

## Oakland County, MI

Parcel source: **public county parcel/GIS source, with some product/access caveats.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel sources:

- Oakland County GIS maps/data page: `https://www.oakgov.com/government/information-technology/enterprise-gis/maps-data`
- Access Oakland / Open Data: `https://accessoakland-oakgov.opendata.arcgis.com/search?tags=property`
- Public tax parcel REST layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Property Gateway: `https://www.oakgov.com/government/property-gateway`
- Public tax parcels metadata via BTAA: `https://geo.btaa.org/catalog/e2910cc3a8f84549ab7f0f8e8f99817b_1`

Source notes:

- Oakland open data includes a public tax-parcel spatial representation keyed by `KeyPIN`.
- Michigan's state tax-parcel page says the MGF stores a statewide
  parcel layer, but it is internal-only and public parcel layers are
  available on individual county websites. That confirms
  `SINGLE-COUNTY-PORTAL`, not a statewide public unlock.
- Property Gateway provides maps and land/property information, but some reports/products may be fee-based and availability varies by city/village/township.
- The public ArcGIS layer should be tested before relying on Property Gateway exports.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like.**

- Birmingham and Bloomfield Hills zoning are municipal.
- Birmingham zoning ordinance page: `https://www.bhamgov.org/about_birmingham/city_departments/planning_department/zoning_ordinance.php`
- Bloomfield Hills Municode Chapter 54: `https://library.municode.com/mi/bloomfield_hills/codes/code_of_ordinances?nodeId=COOR_CH54ZO`
- No county-wide municipal zoning layer was found in the time box.

Effort estimate:

- Parcel ingest: **2-4 days** because source access should be verified around public vs fee/report products.
- Operational for Birmingham/Bloomfield Hills: **1-2 weeks** for municipal zoning geometry and matrix.
- Comparable anchor: parcel work is probably straightforward after ArcGIS layer validation; zoning is Lane A Class B.

57-list polygon impact: **2 estimated polygons** for Birmingham and Bloomfield Hills.

Priority recommendation: **MEDIUM**.

## Allegheny County, PA

Parcel source: **public county/regional parcel layer with reliable geometry.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel sources:

- WPRDC Allegheny County Parcel Boundaries: `https://data.wprdc.org/dataset/allegheny-county-parcel-boundaries1`
- PASDA authoritative parcel page: `https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=1214`
- Allegheny County Property Viewer dataset: `https://data.wprdc.org/dataset/http-alcogis-maps-arcgis-com-apps-webappviewer-index-html-id-b4b1dbb65b4943538425bb5ae0f8f62b`
- Allegheny County GIS Open Data: `https://openac-alcogis.opendata.arcgis.com/search`

Source notes:

- WPRDC describes the parcel-boundaries dataset as individual parcel boundaries with county block and lot number.
- PASDA exposes REST, WMS, KMZ, GeoJSON, preview, and download options.
- This is one of the easiest parcel-source acquisitions in the batch.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with a narrow/simple matrix.

- Fox Chapel eCode360 Chapter 400 Zoning: `https://ecode360.com/31904910`
- Fox Chapel district classifications: `https://www.fox-chapel.pa.us/185/Classifications`
- Fox Chapel has only five districts listed by the borough, mostly residential/open-space/institutional. This is operationally small, but not a rich Bergen-style use-table sprint.

Effort estimate:

- Parcel ingest: **1-2 days**.
- Operational for Fox Chapel: **3-5 days** if the borough zoning map can be digitized or sourced; **1 week** if manual map conversion is needed.
- Comparable anchor: parcel source is easier than most; zoning scope is small.

57-list polygon impact: **1 estimated polygon** for Fox Chapel.

Priority recommendation: **HIGH** despite one polygon, because parcel source is clean and zoning scope is narrow.

## Contra Costa County, CA

Parcel source: **public county parcel layer with reliable geometry.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel sources:

- Maps & Property Information: `https://www.contracosta.ca.gov/552/Maps-Property-Information`
- Contra Costa GIS: `https://www.contracosta.ca.gov/1818/GIS`
- Contra Costa GIS Hub: `https://contra-costa-gis-cocogis.hub.arcgis.com/`
- Parcel Viewer: `https://experience.arcgis.com/experience/caa59504ea0040cfac8ea0b11393c486`

Source notes:

- The county maps/property page says the Assessor's Parcel shapefile is updated monthly and free to download.
- The parcel viewer supports county-wide parcel/address search.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like**, with good Walnut Creek map support.

- County CCMAP zoning is only for unincorporated county areas: `https://www.contracosta.ca.gov/4843/Property-Zoning-Lookup`.
- Walnut Creek zoning web map exposes parcel zoning codes and ordinance links: `https://www.walnutcreekca.gov/government/community-development-department/zoning/maps/zoning-web-map`.
- Lafayette code is online at `https://www.codepublishing.com/CA/Lafayette/`, but zoning map/GIS extraction must be confirmed.

Effort estimate:

- Parcel ingest: **1-2 days**.
- Operational for Walnut Creek/Lafayette: **4-8 days** if Walnut Creek and Lafayette zoning GIS can be exported; **1-2 weeks** if Lafayette is manual.
- Comparable anchor: county parcel source is clean; zoning is two-city Class B.

57-list polygon impact: **2 estimated polygons** for Lafayette and Walnut Creek.

Priority recommendation: **HIGH** because the county parcel source is strong and Walnut Creek has an explicit zoning web map.

## Miami-Dade County, FL

Parcel source: **public county parcel layer with reliable geometry; statewide fallback exists.**

Source class: **SINGLE-COUNTY-PORTAL.**

Primary parcel sources:

- Miami-Dade Open Data Hub: `https://gis-mdc.opendata.arcgis.com/`
- Miami-Dade parcel dataset: `https://gis-mdc.opendata.arcgis.com/datasets/MDC::parcel/about`
- Parcel polygon REST layer: `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/Parcelpoly_gdb/FeatureServer/0`
- GIS online services: `https://www.miamidade.gov/global/service.page?Mduid_service=ser1495571905689513`
- Property Appraiser search: `https://www.miamidadepa.gov/pa/real-estate/property-search.page`

Source notes:

- Miami-Dade GIS says 650+ public GIS datasets are downloadable through the Open Data Hub.
- The parcel dataset is a polygon feature class of property ownership boundaries, updated weekly per the GDSC metadata mirror.
- Florida statewide parcels exist at `https://geodata.floridagio.gov/datasets/FGIO::florida-statewide-parcels/about`, but the county weekly feed is more direct.

Zoning source class: **Per-municipality ordinance/GIS / Class B-like.**

- Pinecrest zoning is municipal: `https://www.pinecrest-fl.gov/Government/Departments/Building-and-Planning/Zoning`
- Pinecrest Municode search entry for Chapter 30 Land Development Regulations: `https://library.municode.com/search?clientId=10759&contentTypeId=CODES&searchText=PR&stateId=9`
- County parcel geometry does not remove the need for Pinecrest zoning map/ordinance adapter.

Effort estimate:

- Parcel ingest: **1-2 days**.
- Operational for Pinecrest: **3-6 days** if zoning map/GIS is available; **1 week** if only municipal map/code workflow.
- Comparable anchor: clean county parcel source plus one target municipality.

57-list polygon impact: **1 estimated polygon** for Pinecrest.

Priority recommendation: **MEDIUM**. Good source, one polygon, no multi-county leverage.

## Recommended Dispatch Order

1. **Oregon regional taxlot sprint if Lake Oswego matters now.** Confirm
   raw access/licensing for PortlandMaps/RLIS taxlots, then load
   Clackamas first and Multnomah only if the KMZ crosses county lines.
   This is the only remaining source that covers more than one target
   county in this batch.
2. **Fast single-county wins:** Allegheny PA, Contra Costa CA, Maricopa
   AZ, and Miami-Dade FL. Each has a clean county parcel source and a
   small target-municipality zoning scope.
3. **High-value but heavier municipal zoning:** King WA, Hennepin MN, and
   Oakland MI. Parcel sources are good; operationalization depends on
   Bellevue/Mercer Island, Edina/Wayzata, and Birmingham/Bloomfield Hills
   zoning map adapters.
4. **Cook IL after parcel-shell repair decision.** Cook has a useful
   county parcel layer and a jurisdiction shell, but the North Shore
   target remains municipal zoning work. No Illinois statewide source was
   found that also explains DuPage; treat Cook and DuPage as separate
   county-source lanes.
5. **Plymouth MA deferred.** PR #222 / `docs/OP5_MASSGIS_INGEST_SPRINT.md`
   accepted the halt: no clean MA statewide zoning aggregator. Plymouth
   remains per-muni/per-region after parcel registration.

## Bottom-Line Table

| County | Parcel source class | Zoning source class | Effort estimate | Polygons unlocked | Priority recommendation |
|---|---|---|---|---:|---|
| Cook IL | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-3 days parcel repair; 1-2 weeks operational | 1 | MEDIUM |
| Maricopa AZ | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-2 days parcel; 3-6 days to 1-2 weeks operational | 2 | HIGH |
| King WA | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-2 days parcel; 4-8 days to 1-2 weeks operational | 2 | MEDIUM |
| Multnomah OR | SINGLE-STATE-AGGREGATOR | Per-municipality ordinance/GIS / Class B-like | 2-4 days shared parcel; 1-2 weeks if target confirmed | 0-1 | MEDIUM, only paired with Clackamas |
| Clackamas OR | SINGLE-STATE-AGGREGATOR | Per-municipality ordinance/GIS / Class B-like | 2-4 days shared parcel; 4-8 days to 1-2 weeks operational | 1 | HIGH |
| Hennepin MN | SINGLE-STATE-AGGREGATOR | Per-municipality ordinance/GIS / Class B-like | 1-3 days parcel; 4-8 days to 1-2 weeks operational | 2 | MEDIUM |
| Oakland MI | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 2-4 days parcel validation; 1-2 weeks operational | 2 | MEDIUM |
| Allegheny PA | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-2 days parcel; 3-5 days to 1 week operational | 1 | HIGH |
| Contra Costa CA | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-2 days parcel; 4-8 days to 1-2 weeks operational | 2 | HIGH |
| Miami-Dade FL | SINGLE-COUNTY-PORTAL | Per-municipality ordinance/GIS / Class B-like | 1-2 days parcel; 3-6 days to 1 week operational | 1 | MEDIUM |

Active non-MA polygon impact: **14-15 polygons** depending on whether
Multnomah owns a separate Lake Oswego edge polygon. No active non-MA
county is classified Class A or Class C under the strengthened gates.
