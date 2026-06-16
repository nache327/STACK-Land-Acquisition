# Maricopa County, AZ - Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-16
**Purpose:** Pre-stage citation sources for the Maricopa AZ matrix sprint after Lane A lands the Maricopa parcel adapter and municipal zoning backfills. Target municipalities are Scottsdale and Paradise Valley from the 57-list, plus Carefree, Cave Creek, and Fountain Hills as adjacent northeast Valley wealth-band candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's Maricopa ingest output lands.** `prod_city_value` values below are predictions from Maricopa County parcel `PropertyCity`; verify exact case and formatting against prod after ingest before authoring matrix rows.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| Direct 57-list polygon coverage | **YES**: Scottsdale + Paradise Valley |
| Bergen-pattern fit | 1 YES / 4 PARTIAL / 0 NO |
| Zoning-layer availability | 2 verified live municipal zoning layers / 1 parcel-only GIS app / 2 PDF-code workflows / 0 no-public-source |
| Scottsdale preflight flag | **Carry forward.** Raw `PropertyCity='SCOTTSDALE'` bbox failed the 50% primitive in `docs/MARICOPA_AZ_ACQUISITION_SPEC.md`; needs city-boundary or city-parcel prefilter before Class A backfill. |
| Paradise Valley preflight note | **Simpler Class A path.** Town zoning bbox passed against `PropertyCity='PARADISE VALLEY'`; 464 rows / 427 nonblank `ZONECLASS` rows. |
| Expected matrix sprint hours at 5-10 min/code | 13-26h raw authoring |
| Expected total with source friction | 18-34h |
| Recommended proof scope | Paradise Valley + Scottsdale first: both direct 57-list polygons; Paradise Valley for spatial simplicity, Scottsdale for ordinance-table quality |
| Recommended add-on scope | Fountain Hills, Cave Creek, Carefree after the 57-list proof |

**Recommendation:** Stage Maricopa as a **single-county parcel adapter plus per-muni zoning sources**, not a Class C sprint. Scottsdale has the best ordinance-side matrix fit but needs a city-boundary prefilter before spatial backfill. Paradise Valley has the cleaner spatial preflight and should be the first technical proof if Lane A wants a lower-risk Class A path.

**Class A/C gate note:** Maricopa parcels do **not** carry embedded municipal zoning. Do not treat `PropertyUseCode`, `PropertyUseDescription`, `TaxingDistrictCode`, legal class, or `PropertyCity` as zoning. Use municipal zoning layers where verified: Scottsdale `full_zoning` from `OpenData/MapServer/24`, Paradise Valley `ZONECLASS` from `Planning_and_Zoning/MapServer/7`. Cave Creek's public app exposes a parcel-only layer, not zoning. Carefree and Fountain Hills were not verified as public zoning FeatureServer sources in this pass.

---

## Live source probes used

- Maricopa parcel source: `https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Parcel_Data_View/FeatureServer/0`
- Maricopa acquisition spec baseline: `docs/MARICOPA_AZ_ACQUISITION_SPEC.md`
- Scottsdale zoning resources: `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning`
- Scottsdale Municode zoning ordinance: `https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR`
- Scottsdale zoning layer: `https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/24`
- Paradise Valley GIS portal: `https://www.paradisevalleyaz.gov/699/Public-GIS-Maps-Portal`
- Paradise Valley zoning layer: `https://gis.paradisevalleyaz.gov/arcgis/rest/services/Community_Development/Planning_and_Zoning/MapServer/7`
- Paradise Valley town code: `https://www.paradisevalleyaz.gov/281/Town-Code`
- Paradise Valley zoning map: `https://www.paradisevalleyaz.gov/DocumentCenter/View/277/Zoning-Map`
- Carefree zoning documents: `https://www.carefree.org/page/zoning-documents`
- Carefree American Legal code: `https://codelibrary.amlegal.com/codes/carefree/latest/carefree_az/0-0-0-1`
- Cave Creek planning/zoning: `https://www.cavecreekaz.gov/165/Planning-Zoning`
- Cave Creek ordinances/guidelines: `https://www.cavecreekaz.gov/336/Ordinances-Guidelines`
- Cave Creek zoning and land use map app: `https://azmag.maps.arcgis.com/apps/instant/basic/index.html?appid=d3d24fe809704b5190b8efffbcb51252`
- Cave Creek parcel-only FeatureServer exposed by that app: `https://services1.arcgis.com/MdyCMZnX1raZ7TS3/arcgis/rest/services/Parcels_01012025_CCOnly/FeatureServer/0`
- Fountain Hills planning/zoning: `https://www.fountainhillsaz.gov/220/Planning-Zoning`
- Fountain Hills planning maps: `https://www.fountainhillsaz.gov/221/Planning-Applications-Information`
- Fountain Hills zoning ordinance: `https://fountainhills.town.codes/ZO`

Predicted city values and source coverage:

| Display name | Predicted prod_city_value | Parcel evidence | Zoning source status |
|---|---|---|---|
| Scottsdale | `SCOTTSDALE` | 150,207 rows from accepted spec | Live zoning layer, but raw county-city bbox fails; prefilter required |
| Paradise Valley | `PARADISE VALLEY` | 10,071 rows from accepted spec | Live zoning layer; bbox primitive passes |
| Carefree | `CAREFREE` | Maricopa sample rows confirmed; count probe timed out in this pass | American Legal/PDF-code workflow; no live zoning layer verified |
| Cave Creek | `CAVE CREEK` | Cave Creek app parcel layer has 4,348 rows; county count probe timed out | Public app is parcel-only; ordinance/PDF-map workflow for zoning |
| Fountain Hills | `FOUNTAIN HILLS` | Maricopa sample rows confirmed; count probe timed out in this pass | Town Codes + zoning-map PDF workflow; no live zoning layer verified |

Layer/code availability:

| Muni | Zoning layer status | Verified code field | Distinct code estimate |
|---|---|---|---:|
| Scottsdale | Live MapServer, prefilter required | `full_zoning`; optional `comparable_zoning` | High, overlay-heavy; raw layer has 1,937 polygons |
| Paradise Valley | Live MapServer | `ZONECLASS` | Small; accepted spec saw 427 nonblank rows |
| Carefree | No live layer verified; American Legal + zoning documents | N/A | ~8-12 |
| Cave Creek | Public parcel-only FeatureServer; zoning map/app + chapter PDFs | N/A | ~8-12 |
| Fountain Hills | No live layer verified; Town Codes + zoning-map PDF | N/A | ~20-30 |

---

## How to use this directory

1. After Lane A lands Maricopa parcels, re-pull actual uncovered `(city, zoning_code)` pairs for the staged munis.
2. Use `PropertyCity` only as a predicted municipality key. Scottsdale already showed postal-city/bbox noise, so Lane A should add city-boundary or city-parcel prefiltering before backfill.
3. Do not classify Maricopa as Class C. Parcel use/tax/legal fields are not zoning.
4. If Lane A backfills from Scottsdale's layer, preserve raw `full_zoning` and separately derive a normalized base district only if needed for matrix grouping.
5. If Lane A backfills from Paradise Valley's layer, filter blank `ZONECLASS` rows and preserve `ZONECLASS` as the matrix key unless a cleaner normalized code is deliberately introduced.
6. For Carefree, Cave Creek, and Fountain Hills, do not assume a municipal GIS map carries zoning until a live layer with zoning fields passes preview gates.

---

## Scottsdale

| Field | Value |
|---|---|
| Display name | Scottsdale, AZ |
| Predicted prod_city_value | `SCOTTSDALE` |
| Maricopa parcel coverage | YES: 150,207 rows in accepted spec |
| Canonical ordinance URL | `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning` |
| Municode ordinance | `https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR` |
| Live zoning layer | `https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/24` |
| Verified code fields | `full_zoning`; `comparable_zoning` sparse/optional |
| Zoning section anchors | Article XI Land Use Tables; Table 11.201.A land use table; district regulations in Scottsdale Basic Zoning Ordinance |
| Bergen-pattern fit | **YES** |
| Estimated sprint scope | ~40-70 raw/overlay codes; 6-10h after city-boundary-filtered zone codes are populated |

Scottsdale is the best ordinance-side Maricopa target. The city page explicitly links XI Land Use Tables, and the prior diagnostic identified Table 11.201.A as the core use-table citation pattern. The risk is not citation availability; it is source geometry scope. The accepted acquisition spec found that raw county `PropertyCity='SCOTTSDALE'` parcels have a much wider bbox than city zoning polygons, likely because of postal-city noise.

Sample live zoning rows and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R1-18 PCD ESL` | Live `full_zoning` value; base district `R1-18` with overlays | Cite Article XI for uses by base district plus overlay/district regulations for `PCD`/`ESL`; do not collapse without preserving raw. |
| `C-1` | Live `full_zoning` value | Cite Table 11.201.A and commercial district regulations. |
| `C-2` | Live `full_zoning` value | Cite Table 11.201.A; storage/industrial-adjacent uses need explicit read. |
| `C-O` | Live `full_zoning` value | Cite Table 11.201.A and office district regulations. |
| `S-R (C)` | Live `full_zoning` value | Cite special/resort district provisions plus Article XI; use-level read required. |

Sprint note: Scottsdale should be part of the first Maricopa proof because it is a direct 57-list target, but Lane A should not run spatial backfill on raw `PropertyCity='SCOTTSDALE'` without a city-boundary prefilter.

---

## Paradise Valley

| Field | Value |
|---|---|
| Display name | Paradise Valley, AZ |
| Predicted prod_city_value | `PARADISE VALLEY` |
| Maricopa parcel coverage | YES: 10,071 rows in accepted spec |
| Canonical ordinance URL | `https://www.paradisevalleyaz.gov/281/Town-Code` |
| Municode source | `https://library.municode.com/az/paradise_valley/codes/town_code` |
| Zoning map PDF | `https://www.paradisevalleyaz.gov/DocumentCenter/View/277/Zoning-Map` |
| Live zoning layer | `https://gis.paradisevalleyaz.gov/arcgis/rest/services/Community_Development/Planning_and_Zoning/MapServer/7` |
| Verified code field | `ZONECLASS` |
| Zoning section anchors | Appendix A Zoning Ordinance; residential district sections for R-43/R-35/R-18; Article 10 height/area regulations; SUP/resort provisions where applicable |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~8-15 codes; 2-4h after zone codes are populated |

Paradise Valley is the simpler spatial proof. The town zoning layer bbox nearly matches the county `PropertyCity='PARADISE VALLEY'` parcel bbox, and the accepted spec found 464 total zoning rows with 427 nonblank `ZONECLASS` values. The ordinance side is more narrative and estate-residential than Scottsdale's table workflow.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-43` | Paradise Valley zoning ordinance / map references | Cite Appendix A residential district section and Article 10 area/height rules. |
| `R-35` | Municode ordinance history and residential district sections | Same residential district pattern. |
| `R-18` | Article 2 definitions / residential district text | Same residential district pattern; verify suffixes like `R-18A` if present. |
| `OSP-Open Space Reserve` | Live `ZONECLASS` value from accepted spec | Cite map/layer plus open-space district provisions. |
| `Public School` | Live `ZONECLASS` value from accepted spec | Cite zoning map/layer and public/institutional provisions. |

Sprint note: Paradise Valley should be the first Class A backfill proof if Lane A wants a clean bbox gate. Matrix authoring is small but less Bergen-like than Scottsdale.

---

## Carefree

| Field | Value |
|---|---|
| Display name | Carefree, AZ |
| Predicted prod_city_value | `CAREFREE` |
| Maricopa parcel coverage | YES by sample rows; count not captured before timeout |
| Canonical ordinance URL | `https://www.carefree.org/page/zoning-documents` |
| American Legal code | `https://codelibrary.amlegal.com/codes/carefree/latest/carefree_az/0-0-0-1` |
| Zoning map source | `https://www.carefree.org/documents/departments/planning-%26-zoning/zoning-maps/21964167` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 16 Zoning; Article IV Zoning District Boundaries; Section 5.01 Uses Permitted In Each Zoning District |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~8-12 codes; 2-4h including PDF/source friction |

Carefree is ordinance-accessible but not a live-layer proof in this pass. American Legal exposes district and permitted-use sections, and the town page links zoning documents/maps. Lane A still needs a zoning geometry source or map extraction path before matrix work can bind to parcels.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R1-70` | Article IV district-boundary list / Carefree zoning ordinance | Cite Article IV for district establishment plus Section 5.01 permitted uses. |
| `R1-35` | Carefree zoning ordinance and PDF references | Same residential district + Section 5.01 pattern. |
| `R1-18` | Carefree zoning ordinance and PDF references | Same residential district + Section 5.01 pattern. |
| `GO` | Article IV Garden Office district | Cite Article IV and Section 5.01; office/commercial use-level read required. |
| `C` | Article IV Commercial district | Cite Article IV and Section 5.01; commercial use-level read required. |

Sprint note: Carefree should wait until Lane A finds source geometry. Citation authoring is manageable after codes exist.

---

## Cave Creek

| Field | Value |
|---|---|
| Display name | Cave Creek, AZ |
| Predicted prod_city_value | `CAVE CREEK` |
| Parcel coverage | Cave Creek public app parcel layer has 4,348 rows; Maricopa count probe timed out |
| Canonical ordinance URL | `https://www.cavecreekaz.gov/336/Ordinances-Guidelines` |
| Planning/zoning page | `https://www.cavecreekaz.gov/165/Planning-Zoning` |
| Zoning map/app | `https://azmag.maps.arcgis.com/apps/instant/basic/index.html?appid=d3d24fe809704b5190b8efffbcb51252` |
| Public app FeatureServer | `https://services1.arcgis.com/MdyCMZnX1raZ7TS3/arcgis/rest/services/Parcels_01012025_CCOnly/FeatureServer/0` |
| Verified zoning field | **NO**. The app layer is parcel-only: fields include `APN`, address, `City`, `PUC`, deed/subdivision fields, and geometry, but no zoning district field. |
| Zoning section anchors | Chapter 2 Residential Zones; Chapter 3 Commercial Zones; Chapter 4 Open Space Zones; Appendix C Zoning Map; Appendix F Tables |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~8-12 codes; 3-5h including PDF/map extraction friction |

Cave Creek has strong official chapter PDFs and a public map app, but the app's exposed FeatureServer is not a zoning layer. It is a useful parcel/geometry source, not a Class C or Class A zoning source by itself.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `DR-190` | Chapter 2 residential zone family / zoning map references | Cite Chapter 2 Residential Zones and Appendix C map. |
| `DR-89` | Chapter 2 and zoning-map amendment references | Same residential district pattern. |
| `DR-70` | Chapter 2 residential zone family | Same residential district pattern. |
| `DR-43` | Chapter 2 residential zone family | Same residential district pattern. |
| `CB` | Zoning map amendment table / commercial buffer references | Cite Chapter 3 Commercial Zones and Appendix C. |
| `GC` | Commercial zone family | Cite Chapter 3; use-level read required. |

Sprint note: Cave Creek should not be treated as a live zoning-layer add-on. It needs zoning-map extraction or a hidden zoning service before matrix rows matter.

---

## Fountain Hills

| Field | Value |
|---|---|
| Display name | Fountain Hills, AZ |
| Predicted prod_city_value | `FOUNTAIN HILLS` |
| Maricopa parcel coverage | YES by sample rows; count not captured before timeout |
| Canonical ordinance URL | `https://fountainhills.town.codes/ZO` |
| Planning/zoning page | `https://www.fountainhillsaz.gov/220/Planning-Zoning` |
| Zoning map PDF | `https://www.fountainhillsaz.gov/DocumentCenter/View/4339/Zoning-Map-PDF` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 2 Establishment of Zoning Districts and Boundaries; Open Space districts; Single-Family Residential districts; Multifamily districts; Commercial districts; Industrial districts; Lodging/Town Center districts |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~20-30 codes; 4-7h including map/PDF source friction |

Fountain Hills has the strongest online code platform among the three add-ons because `town.codes` exposes structured zoning chapters. No live public zoning FeatureServer was verified in this pass. The town planning page links a zoning map PDF and other planning maps.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R1-35` | Town Codes single-family residential district list | Cite Zoning Ordinance single-family residential district chapter and zoning map. |
| `R1-18` | Town Codes single-family residential district list | Same residential district pattern. |
| `R1-10` | Town Codes single-family residential district list | Same residential district pattern. |
| `C-1` | Town Codes commercial district list | Cite commercial district chapter; use-level read required. |
| `C-2` | Town Codes commercial district list | Same commercial district pattern. |
| `IND-1` | Town Codes industrial district list | Cite industrial district chapter; likely relevant for industrial/storage-like uses, but do not bulk-class. |

Sprint note: Fountain Hills is citation-friendly but source-friction heavy. It should follow Scottsdale/Paradise Valley and probably after Cave Creek only if Lane A finds a better map extraction path.

---

## Recommended Maricopa sprint sequence

1. **Paradise Valley** - direct 57-list polygon and cleanest Class A spatial preflight. Expected 2-4h matrix after zoning ingest.
2. **Scottsdale** - direct 57-list polygon and best land-use table source, but requires city-boundary/prefilter work before backfill. Expected 6-10h matrix.
3. **Fountain Hills** - structured Town Codes, larger add-on footprint, but no live zoning layer verified. Expected 4-7h after source extraction.
4. **Cave Creek** - official chapter PDFs and map app, but exposed app layer is parcel-only. Expected 3-5h after source extraction.
5. **Carefree** - smaller add-on with American Legal code and zoning documents. Expected 2-4h after source extraction.

Expected target-muni matrix backlog: **18-34h including source friction**, or **13-26h raw authoring** after clean `(city, zoning_code)` values are available.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Scottsdale raw `PropertyCity` bbox fails | Backfill could miss/overbind parcels | Use actual city boundary or city-parcel prefilter before Class A dry-run. |
| Parcel source has no embedded zoning | No Class C path | Use municipal zoning geometry or map extraction per muni. |
| Scottsdale `full_zoning` includes overlays and suffixes | Matrix rows could miss if normalized too aggressively | Preserve raw `full_zoning`; derive base district only as a secondary key if needed. |
| Paradise Valley has blank `ZONECLASS` rows | Blank zoning codes could be backfilled | Filter blanks and track unmatched polygons in QA. |
| Cave Creek app is parcel-only | Easy false Class C/Class A claim | Treat `PUC` as assessor/use code, not zoning; find zoning geometry separately. |
| Carefree/Fountain Hills source layer not verified | Source friction before matrix sprint | Keep as PDF/code workflows until Lane A finds live zoning fields. |

---

## Directory shape recommendation

Maricopa's directory should key each municipal source by predicted `PropertyCity` and exact municipal zoning-code field where a live layer exists:

```json
{
  "county": "Maricopa",
  "state": "AZ",
  "municipalities": {
    "PARADISE VALLEY": {
      "display_name": "Paradise Valley",
      "parcel_filter_field": "PropertyCity",
      "source_type": "arcgis_mapserver",
      "zoning_layer_url": "https://gis.paradisevalleyaz.gov/arcgis/rest/services/Community_Development/Planning_and_Zoning/MapServer/7",
      "zone_code_field": "ZONECLASS",
      "ordinance_url": "https://www.paradisevalleyaz.gov/281/Town-Code"
    },
    "SCOTTSDALE": {
      "display_name": "Scottsdale",
      "parcel_filter_field": "PropertyCity",
      "source_type": "arcgis_mapserver_requires_city_boundary_prefilter",
      "zoning_layer_url": "https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/24",
      "zone_code_field": "full_zoning",
      "normalized_zone_field_candidate": "comparable_zoning",
      "ordinance_url": "https://www.scottsdaleaz.gov/codes-and-ordinances/zoning",
      "notes": "Raw PropertyCity='SCOTTSDALE' bbox failed accepted-spec primitive; do not production-backfill without boundary/prefilter."
    },
    "CAVE CREEK": {
      "display_name": "Cave Creek",
      "parcel_filter_field": "PropertyCity",
      "source_type": "parcel_app_plus_pdf_zoning",
      "parcel_app_url": "https://services1.arcgis.com/MdyCMZnX1raZ7TS3/arcgis/rest/services/Parcels_01012025_CCOnly/FeatureServer/0",
      "zoning_map_url": "https://azmag.maps.arcgis.com/apps/instant/basic/index.html?appid=d3d24fe809704b5190b8efffbcb51252",
      "zone_code_field": null,
      "notes": "Public app layer is parcel-only; no zoning field verified."
    },
    "FOUNTAIN HILLS": {
      "display_name": "Fountain Hills",
      "parcel_filter_field": "PropertyCity",
      "source_type": "town_codes_plus_pdf_map",
      "zoning_map_url": "https://www.fountainhillsaz.gov/DocumentCenter/View/4339/Zoning-Map-PDF",
      "ordinance_url": "https://fountainhills.town.codes/ZO",
      "zone_code_field": null,
      "notes": "No public zoning FeatureServer verified in pre-stage."
    },
    "CAREFREE": {
      "display_name": "Carefree",
      "parcel_filter_field": "PropertyCity",
      "source_type": "american_legal_plus_pdf_map",
      "zoning_map_url": "https://www.carefree.org/documents/departments/planning-%26-zoning/zoning-maps/21964167",
      "ordinance_url": "https://codelibrary.amlegal.com/codes/carefree/latest/carefree_az/0-0-0-1",
      "zone_code_field": null,
      "notes": "No public zoning FeatureServer verified in pre-stage."
    }
  }
}
```

This directory should not include matrix rows. It is only the acquisition/citation map that lets Lane A populate parcel `zoning_code` and lets orchestrator author matrix rows after ingest.
