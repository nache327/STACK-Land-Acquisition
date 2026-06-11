# Hennepin MN Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Hennepin County, MN, with emphasis on the 57-list wealth pockets Edina and Wayzata.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **MetroGIS Regional Parcel Dataset / Parcels_2025** |
| Parcel source URL | `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/3` |
| Parcel source class | **REGIONAL-AGGREGATOR**. This is a seven-county Twin Cities parcel source, equivalent in adapter leverage to a state-aggregator sprint. |
| Verified class | **Class B with Edina-specific Class A/attribute-join primitive, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. MetroGIS parcel rows carry assessor use fields such as `USECLASS1`, not zoning district codes. |
| Class A separate zoning layer | **PARTIAL**. Edina has a live city zoning service with `PID` + `Zoning` values and bbox coverage matching Edina parcels. Wayzata did not surface a public FeatureServer during the time box; it publishes a zoning map PDF and Municode ordinance. |
| Verified via Lane A strengthened gates | **PARTIAL**. Edina passes live field sample and bbox primitive. The required 1,000-parcel `ST_Within` dry-run still must run in preview because Hennepin is not loaded in prod. |
| Lane A effort estimate | **2-4 days** for MetroGIS parcel adapter + Edina/Wayzata proof; **1-2+ weeks** for broader Hennepin operationalization. |
| Expected operational outcome | **Proof-then-scale**, not first-sprint county operational. Edina + Wayzata are about 23,348 of 445,965 Hennepin parcel rows, roughly 5.2%. |
| Edina coverage | **YES**. MetroGIS parcel count 21,372; Edina city zoning layer count 20,976 with nonblank `Zoning`. |
| Wayzata coverage | **PARTIAL**. MetroGIS parcel count 1,976; ordinance and zoning map are online, but no public machine-readable zoning layer found in the time box. |
| Ramsey carry | **YES for parcel source**. Same MetroGIS service exposes Ramsey County layer 4 with 171,888 parcels. Zoning still remains city-by-city. |
| Recommended dispatch | **HIGH as a regional parcel-adapter sprint; MEDIUM for immediate 57-list operational ROI**. MetroGIS should move up if Master values the Ramsey/seven-county carry, but Hennepin still needs municipal zoning work before operational readiness. |

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `Hennepin` match.
- `/api/admin/coverage`: no `Hennepin` row.

Hennepin remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Recommended source: MetroGIS Regional Parcel Dataset, current `Parcels_2025` FeatureServer.

- Service root: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer`
- Hennepin layer: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/3`
- Ramsey carry layer: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/4`
- Minnesota Geospatial Commons dataset page: `https://gisdata.mn.gov/dataset/us-mn-state-metrogis-plan-regional-parcels`
- MetroGIS parcel data page: `https://metrogis.org/how-do-i-get/parcel-data/`
- Hennepin direct open-data page checked as source-of-record fallback: `https://gis-hennepin.hub.arcgis.com/datasets/county-parcels/explore`

Why MetroGIS over Hennepin direct: it is one standardized REST source covering all seven Twin Cities metro parcel layers, so Lane A gets Hennepin plus Ramsey/Anoka/Carver/Dakota/Scott/Washington adapter reuse from the same source shape.

Live REST probe:

| Check | Result |
|---|---:|
| Service layers | Anoka `0`, Carver `1`, Dakota `2`, Hennepin `3`, Ramsey `4`, Scott `5`, Washington `6` |
| Hennepin layer name | `Hennepin County Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | UTM Zone 15N, `wkid=26915` |
| Max record count | 2,000 |
| Hennepin parcel count | 445,965 |
| Ramsey parcel count | 171,888 |
| Hennepin full bbox | `xmin=439356.3565`, `ymin=4959189.9023`, `xmax=485985.4777`, `ymax=5010370.5636` |

Observed Hennepin fields include:

`COUNTY_PIN`, `STATE_PIN`, `PIN`, `CTU_NAME`, `CTU_ID_TXT`, `POSTCOMM`, `CO_CODE`, `CO_NAME`, address fields, owner/tax fields, `USECLASS1`, `USECLASS2`, `USECLASS3`, `USECLASS4`, `DWELL_TYPE`, `HOME_STYLE`, and geometry fields.

Class C gate result: **FAIL**. The parcel source carries assessor use classes, not municipal zoning district codes. Do not treat `USECLASS1` values such as `Residential`, `Vacant Land - Residential`, `Commercial`, or `Townhouse` as zoning.

## Target Parcel Coverage

Edina live query:

- Query: `UPPER(CTU_NAME)='EDINA'`
- Count: 21,372
- Parcel bbox, WGS84: `[-93.4015415, 44.8600721, -93.3187749, 44.9305876]`

Sample Edina parcel rows:

| COUNTY_PIN | STATE_PIN | CTU | Post community | Assessor use | PIN |
|---|---|---|---|---|---|
| `0411621210001` | `27053-0411621210001` | Edina | EDINA | Residential | `053-0411621210001` |
| `0411621210003` | `27053-0411621210003` | Edina | EDINA | Vacant Land - Residential | `053-0411621210003` |
| `0411621210014` | `27053-0411621210014` | Edina | EDINA | Residential | `053-0411621210014` |
| `0411621210018` | `27053-0411621210018` | Edina | EDINA | Residential | `053-0411621210018` |
| `0411621210019` | `27053-0411621210019` | Edina | EDINA | Residential | `053-0411621210019` |

Wayzata live query:

- Query: `UPPER(CTU_NAME)='WAYZATA'`
- Count: 1,976
- Parcel bbox, WGS84: `[-93.5481203, 44.9507315, -93.4767310, 44.9819733]`

Sample Wayzata parcel rows:

| COUNTY_PIN | STATE_PIN | CTU | Post community | Assessor use | PIN |
|---|---|---|---|---|---|
| `0111723110018` | `27053-0111723110018` | Wayzata | WAYZATA | Residential | `053-0111723110018` |
| `0111723110021` | `27053-0111723110021` | Wayzata | WAYZATA | Residential | `053-0111723110021` |
| `0111723120001` | `27053-0111723120001` | Wayzata | WAYZATA | Commercial | `053-0111723120001` |
| `0111723140001` | `27053-0111723140001` | Wayzata | WAYZATA | Residential | `053-0111723140001` |
| `0111723140028` | `27053-0111723140028` | Wayzata | WAYZATA | Townhouse | `053-0111723140028` |

Conclusion: both 57-list centers are covered by the canonical MetroGIS parcel source. They are not parcel-source patchworks.

## Zoning Source Audit

There is no countywide Hennepin zoning FeatureServer suitable for a one-shot Class A backfill. Zoning is municipal.

### Edina

Public sources:

- Edina quick links page: `https://www.edinamn.gov/QuickLinks.aspx?CID=140`
- Interactive zoning map: `https://edinagis.maps.arcgis.com/apps/instant/sidebar/index.html?appid=3f886aaedbb847f5b9a1854120902a64`
- Zoning ordinance: `https://library.municode.com/mn/edina/codes/code_of_ordinances?nodeId=SPBLADERE_CH36ZO`
- Live zoning map service: `https://utility.arcgis.com/usrsvcs/servers/6aeef36d107a4ff9aa765ad8d0baadfb/rest/services/Planning/Zoning/MapServer`
- District/parcel layer: `https://utility.arcgis.com/usrsvcs/servers/6aeef36d107a4ff9aa765ad8d0baadfb/rest/services/Planning/Zoning/MapServer/2`

Edina's public page links directly to the interactive zoning map and the Municode zoning ordinance. The ArcGIS web map resolves to the `Planning/Zoning` MapServer.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Districts` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 20,976 |
| Nonblank `Zoning` count | 20,976 |
| Zoning bbox, WGS84 | `[-93.4015459, 44.8600461, -93.3187032, 44.9305903]` |
| Edina parcel bbox, WGS84 | `[-93.4015415, 44.8600721, -93.3187749, 44.9305876]` |
| Bbox primitive | **Passes**. Zoning bbox effectively matches the Edina parcel bbox. |

Fields include `PID`, `CITY`, `ZIP`, `Zoning`, `LandUse`, and `GuidePlan`.

Live Edina zoning samples joined by `PID` to MetroGIS `COUNTY_PIN`:

| PID | Zoning | Land use | City | ZIP |
|---|---|---|---|---|
| `0411621210001` | `R-1` | Single Family Detached | EDINA | 55439 |
| `0411621210003` | `R-1` | Major Highway | EDINA | 00000 |
| `0411621210014` | `R-1` | Single Family Detached | EDINA | 55439 |
| `0411621210018` | `R-1` | Single Family Detached | EDINA | 55439 |
| `0411621210019` | `R-1` | Single Family Detached | EDINA | 55439 |

Distinct zoning examples from the live layer include `R-1`, `R-2`, `RMD`, `PUD`, `PID`, `PCD-1`, `POD-1`, `MDD-4`, and `APD`.

Edina acquisition verdict: **strong proof candidate**. This is better than a generic spatial-only Class A source because it carries parcel identifier `PID` plus `Zoning`. Lane A can preview either:

1. direct attribute join from MetroGIS `COUNTY_PIN` to Edina `PID`, or
2. spatial backfill from Edina polygons after the required `ST_Within` dry-run.

The first option should be less risky because it avoids nearest/spatial boundary ambiguity for Edina.

Ordinance structure: **Class B support required for matrix/directory**. Edina's Municode zoning is online, but it is not a single Bergen-style all-district use table. It uses district sections such as principal uses and dimensional standards by district. Directory authoring should therefore be scoped as municipal/manual, even though zoning-code population can be automated for Edina.

### Wayzata

Public sources:

- Planning page: `https://www.wayzata.org/236/Planning`
- City code / zoning ordinance: `https://library.municode.com/mn/wayzata/codes/code_of_ordinances`
- Part IX zoning use table section found by search: `https://library.municode.com/mn/wayzata/codes/code_of_ordinances?nodeId=CD_ORD_PTIXZO_CH937ZODIUSTAPEST_937.03PEUSRE`
- Updated zoning map PDF: `https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025`

Wayzata's planning page says zoning information is in Part IX of the City Code and links to a zoning map updated March 2025. The PDF map lists zone codes including `C-1`, `C-1A`, `C-1B`, `C-2`, `C-3`, `C-3A`, `C-4`, `C-4A`, `C-4B`, `INS`, `P`, `PUD`, `R-1`, `R-1A`, `R-2`, `R-2A`, `R-3`, `R-3A`, `R-4`, `R-4A`, and `R-5`.

The Municode search result for Chapter 937 indicates a permitted-use table: `937.03` says the table specifies permitted, conditional, interim, and accessory uses. This is closer to the Bergen pattern than Edina's district-by-district structure.

Live ArcGIS search result: **no Wayzata-owned public zoning FeatureServer found in the time box**. The available source appears to be city ordinance + PDF map. This makes Wayzata a Class B/PDF-map acquisition unless Lane A finds an unpublished REST endpoint behind a city GIS tool later.

Wayzata acquisition verdict: **manual Class B for proof**. Parcels are cleanly available from MetroGIS, and the ordinance/map are online, but zoning-code population is not automatically solved from the sources found here.

## Ramsey Carry

MetroGIS is a real multi-county parcel-source carry:

| County layer | Layer id | Live count |
|---|---:|---:|
| Hennepin County Parcels | 3 | 445,965 |
| Ramsey County Parcels | 4 | 171,888 |

The same service also exposes Anoka, Carver, Dakota, Scott, and Washington parcel layers. That makes the parcel adapter reusable beyond Hennepin.

Important caveat: this is a parcel-source carry only. It does not solve zoning for Ramsey or the other metro counties. St. Paul/Ramsey zoning appears to use separate city/county services and must be scoped independently if Ramsey enters the 57-list.

## Lane A Execution Shape

Recommended staged plan:

1. Register Hennepin County in preview.
2. Ingest Hennepin parcels from MetroGIS `Parcels_2025/FeatureServer/3`.
3. Normalize parcel identity:
   - `parcel_id`: `COUNTY_PIN`
   - alternate IDs: `STATE_PIN`, `PIN`
   - municipality/subjurisdiction: `CTU_NAME`
   - source provenance: MetroGIS Regional Parcel Dataset URL + pull timestamp
   - source CRS: EPSG:26915
4. Do **not** classify as Class C. `USECLASS*` values are assessor classes.
5. For Edina proof:
   - pull `Planning/Zoning/MapServer/2`
   - populate zoning by direct `COUNTY_PIN` -> `PID` join if preview sample confirms broad match rate
   - otherwise use spatial backfill after strengthened Class A pre-flight
6. For Wayzata proof:
   - treat as Class B/PDF-map unless a machine-readable city layer is found
   - use MetroGIS parcels clipped by `CTU_NAME='Wayzata'`
   - manually derive or acquire zoning polygons/codes from the March 2025 zoning map if Master approves this scope
7. Run Lane A gates before any production backfill:
   - district/parcel bbox coverage >=50%
   - 1,000-parcel `ST_Within` dry-run >=50% for any spatial source
   - for Edina direct join, add a `COUNTY_PIN` -> `PID` sampled join-rate gate
8. Author `backend/data/hennepin_mn_zoning_directory.json` for Edina + Wayzata proof only.
9. Treat full Hennepin operationalization as a later scale sprint across many municipalities; do not block the proof on Minneapolis/suburban countywide coverage.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| MetroGIS parcel adapter for Hennepin | 6-10h |
| Reuse adapter for Ramsey/other MetroGIS counties | +2-4h after Hennepin succeeds |
| Edina zoning pull + preview direct join/spatial gate | 4-8h |
| Edina directory/matrix seed | 4-8h |
| Wayzata zoning-code acquisition from ordinance/PDF map | 1-2 days |
| Wayzata directory/matrix seed | 4-8h |
| Edina + Wayzata proof end to end | 2-4 days |
| Full Hennepin operationalization | 1-2+ weeks |

Expected coverage after only Edina + Wayzata:

- Edina parcels: 21,372
- Wayzata parcels: 1,976
- Combined: 23,348
- Hennepin total: 445,965
- Countywide fraction: about 5.2%

This is enough for a wealth-pocket proof, not enough to clear Hennepin county operational gates.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| MetroGIS parcels have no zoning fields | Prevents Class C path | Treat `USECLASS*` as assessor-only; use municipal zoning sources. |
| MetroGIS is standardized regional compilation, not direct zoning authority | Vintage/edge differences possible | Keep source provenance and compare against Hennepin direct parcel hub if anomalies appear. |
| EPSG:26915 source CRS | Ingest/backfill transform risk | Reproject through existing ingestion path; record CRS in run log. |
| ArcGIS max record count 2,000 | Requires pagination | Use existing paginated ArcGIS adapter pattern. |
| Edina zoning layer is parcel-like, not pure district polygons | Spatial backfill may duplicate parcel geometry semantics | Prefer direct `COUNTY_PIN` -> `PID` join after preview join-rate check. |
| Wayzata has no machine-readable zoning layer found | Slower proof and possible manual map digitization | Start with Edina as the proof city; add Wayzata only if Master approves Class B/PDF effort. |
| Edina/Wayzata are a small share of county parcels | First sprint will not make Hennepin operational | Scope as proof-then-scale and avoid promising countywide readiness. |
| Ramsey carry can be overstated | Parcel adapter reuse does not solve zoning | Flag Ramsey as parcel-source carry only; require separate zoning-source diagnostic before claiming operational unlock. |

## Verdict

Hennepin is **not blocked at parcel acquisition**. MetroGIS is a strong regional parcel source and should be treated as a high-leverage adapter target, especially because it carries Ramsey and five other Twin Cities metro counties.

Hennepin is **not a clean countywide Class A or Class C sprint**. The parcel source has no zoning code. Edina has a strong city-specific zoning source with direct `PID` + `Zoning` values and bbox coverage, while Wayzata appears to require Class B ordinance/PDF-map work.

Recommended next action: approve a **MetroGIS + Edina proof sprint** if Master wants the regional parcel-adapter unlock next. Add Wayzata as a second proof municipality only with the expectation that it is manual Class B, not a live FeatureServer backfill.
