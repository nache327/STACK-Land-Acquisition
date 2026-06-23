# Mecklenburg NC Acquisition Spec

Date: 2026-06-23

Purpose: read-only acquisition spec for a possible Lane A ingestion sprint covering Mecklenburg County, NC, with emphasis on the 58-list wealth pocket **South Charlotte**. South Charlotte is a sub-neighborhood / wealth-band inside the City of Charlotte, itself inside Mecklenburg County, so this must follow the Buckhead-style spatial-filter pattern rather than a countywide or whole-city operational claim.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **NC OneMap NC1Map Parcels, polygons layer** |
| Parcel source URL | `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1` |
| Parcel source class | **SINGLE-STATE-AGGREGATOR** |
| County/POLARIS corroboration | **YES**. Mecklenburg County `GIS/MAT/MapServer/1` exposes `Tax Parcels`, matching Charlotte-hosted `CountyData/Parcels/MapServer/0` count. |
| Verified class | **Class A/B hybrid, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. NC OneMap carries assessor/tax use fields such as `parusecode` / `parusedesc`, not zoning district codes. |
| Class A separate zoning layer | **YES, preview-gated**. City of Charlotte publishes live zoning polygons with local `ZoneDes` and `ZoneClass` fields. |
| South Charlotte spatial filter | **REQUIRED**. Do not use `scity='CHARLOTTE'` as the target; it returns the whole city. Use the uploaded 58-pocket polygon or a derived South Charlotte AOI before any backfill / re-jurisdictioning. |
| Verified via Lane A strengthened gates | **PARTIAL**. Live fields, counts, 50-feature samples, and rough AOI overlap pass. Required 1,000-parcel `ST_Within` dry-run remains a preview gate. |
| Lane A effort estimate | **2-4 days** for South-Charlotte-only proof using existing per-muni / wealth-pocket pattern; **1-2+ weeks** for broader Charlotte or Mecklenburg operationalization. |
| Expected operational outcome | **Wealth-pocket proof**, not countywide operational. `scity='CHARLOTTE'` is about 330k NC OneMap rows; South Charlotte must be carved spatially. |
| Recommended dispatch | **HIGH** if Phase 5 South is being opened. Mecklenburg has public parcels, public zoning, and a clear sub-city spatial filter requirement. |

## Current Prod State

Per `docs/TARGET_MARKETS.md`, Mecklenburg NC / South Charlotte is Phase 5 and currently `partial · 0%`.

Treat Mecklenburg as **not operational for this target** until South Charlotte parcels are spatially filtered, zoning is backfilled, and matrix coverage clears the normal gates.

## Probe Summary

Live probes on 2026-06-23:

| Source | URL | Count / sample | Verdict |
|---|---|---:|---|
| NC OneMap parcels | `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1` | Mecklenburg `stcntyfips='37119'`: 442,287; `scity='CHARLOTTE'`: 330,185; 50-row sample pulled | Best canonical parcel adapter. Rich assessor/address/value fields, no zoning. |
| Mecklenburg County POLARIS/MAT parcels | `https://edmsgis.mecklenburgcountync.gov/server/rest/services/GIS/MAT/MapServer/1` | 395,625; 50-row sample pulled | Authoritative county parcel geometry / ID corroboration. Thin attributes. |
| Charlotte-hosted county parcels | `https://gis.charlottenc.gov/arcgis/rest/services/CountyData/Parcels/MapServer/0` | 395,625; 50-row sample pulled | Same lightweight parcel schema as county MAT, useful fallback but not canonical. |
| City of Charlotte zoning | `https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/0` | 5,664 zones; 5,664 nonblank `ZoneDes`; 5,661 nonblank `ZoneDes` + `ZoneClass`; 50-row sample pulled | Strong Class A zoning polygon candidate for Charlotte / South Charlotte. |

Rough South Charlotte preview envelope used only for scale sanity:

`[-80.93, 35.02, -80.74, 35.20]` in WGS84.

| Source | Rough AOI intersect count |
|---|---:|
| NC OneMap Mecklenburg parcels | 123,486 |
| Mecklenburg POLARIS/MAT parcels | 104,926 |
| Charlotte zoning polygons | 1,575 |

This rough envelope is **not** the production filter. It only proves source overlap in the expected part of the city. The production run must use the actual 58-pocket South Charlotte polygon or an approved derived AOI.

## Canonical Parcel Source

Recommended source: NC OneMap `NC1Map_Parcels`, polygons layer.

- NC OneMap parcels page: `https://www.nconemap.gov/pages/parcels`
- FeatureServer: `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer`
- Polygon layer: `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1`
- Mecklenburg filter: `stcntyfips = '37119'`
- Charlotte city filter for preview only: `stcntyfips = '37119' AND scity = 'CHARLOTTE'`

Why NC OneMap over county direct: the county/POLARIS layer is official and should be kept as a corroborating geometry source, but it is thin: `map_book`, `map_page`, `map_block`, `lot_num`, `nc_pin`, `pid`, `parcel_type`, `condo_town_flag`, `legal_from`, `gisacres`, geometry. NC OneMap keeps the county geometry while adding standardized site address, city, owner, assessed value, county FIPS, and source-agent fields.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels (polys)` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | North Carolina State Plane, `wkid=102719`, `latestWkid=2264` |
| Max record count | 5,000 |
| Mecklenburg parcel count | 442,287 |
| Charlotte `scity` count | 330,185 |
| Mecklenburg bbox, WGS84 | `[-81.0567415, 35.0021791, -80.5501131, 35.5116451]` |
| Charlotte `scity` bbox, WGS84 | `[-81.0398787, 35.0105230, -80.6348874, 35.4966176]` |

Observed NC OneMap fields include:

`parno`, `altparno`, `ownname`, `improvval`, `landval`, `parval`, `mailadd`, `mcity`, `siteadd`, `scity`, `szip`, `gisacres`, `parusecode`, `parusedesc`, `parvaltype`, `cntyname`, `cntyfips`, `stcntyfips`, `sourceagnt`, and geometry fields.

Class C gate result: **FAIL**. `parusecode` / `parusedesc` are tax parcel use classifications, not zoning district codes.

50-feature Mecklenburg sample summary:

| Check | Result |
|---|---|
| Sample size | 50 rows |
| Source agent | `Mecklenburg County Assessor` on sampled rows |
| City values in sample | Charlotte 43, unincorporated 5, Cornelius 1, Pineville 1 |
| Top tax-use values in sample | `R300 CONDOMINIUM` 29; `R100 SINGLE FAMILY RESIDENTIAL` 9; `A500 MULTI FAMILY` 6 |
| Zoning-like field found | **No** |

Sample NC OneMap rows:

| Parcel | Address | City | Use code | Use description | Parcel value |
|---|---|---|---|---|---:|
| `17103426` | `1000 E WOODLAWN RD, 203 CHARLOTTE NC` | CHARLOTTE | `R300` | CONDOMINIUM | 260,653 |
| `17103458` | `1000 E WOODLAWN RD, 312 CHARLOTTE NC` | CHARLOTTE | `R300` | CONDOMINIUM | 276,968 |
| `17103483` | `1000 E WOODLAWN RD, 415 CHARLOTTE NC` | CHARLOTTE | `R300` | CONDOMINIUM | 437,421 |
| `00507430` | `19862 DEER VALLEY DR CORNELIUS NC` | CORNELIUS | `R300` | CONDOMINIUM | 219,159 |
| `06911302` | `CELIA AV CHARLOTTE NC` | CHARLOTTE | `R100` | SINGLE FAMILY RESIDENTIAL | 15,900 |

Implementation notes:

- Use `parno` as the primary APN candidate and preserve `altparno` / `nparno` where present.
- Normalize `scity` carefully. It is useful for city preview, but **not sufficient** for South Charlotte.
- Preserve `sourceagnt` and `transfdate` in raw provenance.
- The Mecklenburg count is higher than the county MAT count, likely because NC OneMap includes standardized tax/condo parcel representation. Preview should compare unique `parno` / `pid` behavior before production.

## Mecklenburg County POLARIS / MAT Source

Mecklenburg GIS describes POLARIS as the county's property ownership and land records information system and notes that it includes zoning overlays and many mapping overlays. The public REST service backing the relevant parcel geometry is:

- County GIS page: `https://gis.mecknc.gov/`
- REST service: `https://edmsgis.mecklenburgcountync.gov/server/rest/services/GIS/MAT/MapServer`
- Tax Parcels layer: `https://edmsgis.mecklenburgcountync.gov/server/rest/services/GIS/MAT/MapServer/1`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Tax Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | North Carolina State Plane, `wkid=102719`, `latestWkid=2264` |
| Max record count | 2,000 |
| Parcel count | 395,625 |
| County MAT bbox, WGS84 | `[-81.0692571, 34.9986972, -80.5462797, 35.5198154]` |

Observed fields:

`objectid`, `map_book`, `map_page`, `map_block`, `lot_num`, `nc_pin`, `condo_town_flag`, `parcel_type`, `pid`, `legal_from`, `gisacres`, and geometry.

50-feature sample summary:

| Check | Result |
|---|---|
| Sample size | 50 rows |
| Parcel type in sample | all 50 rows `parcel_type=0` |
| Core identifiers | `nc_pin`, `pid`, map book/page/block/lot |
| Address / value fields | Not present in this layer |
| Zoning-like field found | **No** |

Sample county rows:

| Object ID | NC PIN | PID | Map ref | Acres |
|---:|---|---|---|---:|
| 1 | `3499068735` | `19930105` | `199-30-1-05` | 3.2420 |
| 2 | `3497090263` | `21731124` | `217-31-1-24` | 2.7135 |
| 3 | `3499525162` | `21730257` | `217-30-2-57` | 0.2289 |
| 4 | `3498647874` | `21726314` | `217-26-3-14` | 0.4451 |
| 5 | `3488897173` | `21719248` | `217-19-2-48` | 1.0000 |

POLARIS verdict: **strong corroborating parcel source, not a Class C source**. It is thinner than NC OneMap for the product because it lacks site address, city, owner/value fields, and zoning, but it is useful for ID/geometry cross-checks.

## Charlotte-Hosted County Parcel Fallback

Charlotte also hosts a `CountyData/Parcels` service:

- Service: `https://gis.charlottenc.gov/arcgis/rest/services/CountyData/Parcels/MapServer`
- Layer: `https://gis.charlottenc.gov/arcgis/rest/services/CountyData/Parcels/MapServer/0`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Max record count | 3,000 |
| Parcel count | 395,625 |

The 50-feature sample has the same lightweight identifiers as county MAT: `MAP_BOOK`, `MAP_PAGE`, `MAP_BLOCK`, `LOT_NUM`, `NC_PIN`, `PID`, `PARCEL_TYPE`, `CONDO_TOWN_FLAG`, and `Legal_From`.

Fallback verdict: useful if the Mecklenburg endpoint is unstable, but not preferred over NC OneMap for the first adapter because it lacks the normalized address/value/city fields.

## Zoning Source Audit

South Charlotte is inside the City of Charlotte. Countywide or unincorporated Mecklenburg zoning should not be treated as a single source-of-record for this target. The immediate zoning source is the City of Charlotte planning zoning service:

- ArcGIS item: `https://www.arcgis.com/home/item.html?id=7bb03f3b73cb4da0a3fd5ed805182d86`
- Service: `https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer`
- Zoning layer: `https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/0`
- Item info: `https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/info/iteminfo`

The service item describes the layer as current zoning designations including monthly zoning changes. The REST service tags include Charlotte, Mecklenburg County, planning, zoning districts, regulatory, development, conditional, and by-right.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | North Carolina State Plane, `wkid=102719`, `latestWkid=2264` |
| Max record count | 2,000 |
| Zoning polygon count | 5,664 |
| Nonblank `ZoneDes` count | 5,664 |
| Nonblank `ZoneDes` + `ZoneClass` count | 5,661 |
| Zoning bbox, WGS84 | `[-81.0663113, 34.9991000, -80.5949663, 35.4024500]` |

Observed fields:

`OBJECTID`, `ZonePetition`, `ZoneDes`, `SPA`, `Overlay`, `RezoneDate`, `ZoneClass`, `Hyperlink`, and geometry fields.

50-feature citywide zoning sample summary:

| Check | Result |
|---|---|
| Sample size | 50 rows |
| Top `ZoneDes` values in sample | `MUDD-O` 4; `I-2(CD)` 3; `MUDD(CD)` 3; `N1-B` 3; `NS` 3; `OFC` 3 |
| Top `ZoneClass` values in sample | BUSINESS 9; NEIGHBORHOOD 1 8; MIXED USE 7; MULTI-FAMILY 4; OFFICE 4 |
| Petition links | Present on some conditional / petitioned zones |
| Zoning-like field found | **Yes: `ZoneDes` should be the zone code candidate** |

Sample citywide zoning rows:

| Object ID | Zone | Class | Petition | Overlay | SPA |
|---:|---|---|---|---|---|
| 387162 | `INST(CD)` | INSTITUTIONAL | `2004-024` | none | no |
| 387163 | `OFC` | OFFICE | blank | none | no |
| 387164 | `I-2(CD)` | GENERAL INDUSTRIAL | `2023-030` | none | no |
| 387165 | `B-1(CD)` | BUSINESS | `1977-037` | none | no |
| 387166 | `N2-A(CD)` | NEIGHBORHOOD 2 | `2024-004` | none | no |
| 387167 | `MUDD(CD)` | MIXED USE | `2019-008` | none | no |

Rough South Charlotte AOI 50-feature zoning sample:

| Check | Result |
|---|---|
| Sample size | 50 rows |
| Top AOI `ZoneDes` values in sample | `INST(CD)` 4; `UR-2(CD)` 4; `NS` 3; `CG` 2; `ML-1` 2; `OFC` 2; `TOD-NC` 2 |
| AOI zoning intersect count | 1,575 polygons |

Charlotte zoning verdict: **strong Class A zoning polygon source for the South Charlotte proof**, with Class B directory work still needed for ordinance/matrix citations. It is not countywide; it should be used only after filtering target parcels to the South Charlotte AOI.

## South Charlotte Spatial Filter Requirement

This is the most important implementation constraint.

`scity='CHARLOTTE'` is too broad:

- NC OneMap `scity='CHARLOTTE'` count: 330,185 rows.
- Charlotte `scity` bbox, WGS84: `[-81.0398787, 35.0105230, -80.6348874, 35.4966176]`.
- The 58-list target is **South Charlotte**, not all Charlotte.

The correct operational shape should be:

1. Register a South Charlotte wealth-pocket / per-muni-style jurisdiction only after selecting the actual AOI.
2. Use the uploaded 58-pocket polygon when available. If unavailable, derive an explicit South Charlotte polygon from the approved business definition and save it as source provenance.
3. Pull parcels from NC OneMap with county filter `stcntyfips='37119'`, then spatially clip to the South Charlotte AOI.
4. Pull Charlotte zoning polygons from `PLN/Zoning/MapServer/0`, then spatially clip to the same AOI plus a small buffer for boundary-crossing districts.
5. Run strengthened Class A gates:
   - zoning bbox covers >=50% of South Charlotte parcel bbox
   - 1,000-parcel `ST_Within` dry-run >=50% match for target parcels
   - inspect misses near AOI boundary and conditional zoning polygons
6. Populate parcel `zoning_code` from `ZoneDes`.
7. Build a Charlotte zoning directory/matrix seed keyed by `(South Charlotte, ZoneDes)` or `(Charlotte, ZoneDes)` depending on how the jurisdiction is registered.

Do **not** claim Mecklenburg countywide operational readiness from a South Charlotte proof. This is the same structural lesson as large-county wealth-pocket work in King WA and Maricopa AZ.

## Lane A Execution Shape

Recommended staged plan:

1. Stage NC OneMap parcel adapter for Mecklenburg with `stcntyfips='37119'`.
2. Preserve key parcel fields:
   - APN: `parno`
   - alternate IDs: `altparno`, `nparno` if present
   - municipality/postal city: `scity`
   - address: `siteadd`, `sunit`, split address fields where useful
   - assessed value: `parval`, `landval`, `improvval`
   - land/tax use only: `parusecode`, `parusedesc`
   - source provenance: `sourceagnt`, `transfdate`, NC OneMap URL
3. Cross-check a sample against county/POLARIS `pid` / `nc_pin` before production. Do not require exact row-count parity because NC OneMap and MAT appear to model parcel/condo rows differently.
4. Load / derive the South Charlotte AOI.
5. Spatially clip parcels to South Charlotte. Treat this clipped set as the operational target.
6. Ingest Charlotte zoning polygons from `PLN/Zoning/MapServer/0` and use `ZoneDes` as the zone-code candidate.
7. Run strengthened Class A preview gates before any production backfill:
   - South Charlotte parcel bbox vs zoning bbox
   - 1,000-parcel `ST_Within` dry-run
   - sample bound parcels by `ZoneDes`
8. Author `backend/data/mecklenburg_nc_zoning_directory.json` or a Charlotte/South-Charlotte-specific directory after preview confirms the zone-code universe.
9. Keep full Mecklenburg, Huntersville, Cornelius, Pineville, Matthews, Mint Hill, and unincorporated zoning as later scale work.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| NC OneMap parcel adapter reuse / field map | 4-8h |
| Mecklenburg county/POLARIS sample cross-check | 1-2h |
| South Charlotte AOI acquisition / derivation | 2-4h if KMZ polygon is available; longer if it must be redrawn |
| Charlotte zoning pull + target AOI preview gates | 4-8h |
| South Charlotte directory/matrix seed | 1-2 days |
| South-Charlotte-only proof end to end | 2-4 days |
| Full Charlotte or Mecklenburg operationalization | 1-2+ weeks |

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| South Charlotte is not a source field | Whole-city `scity='CHARLOTTE'` would dilute the target and fail the wealth-pocket intent | Require KMZ/approved AOI polygon before operational backfill. |
| NC OneMap count differs from county MAT | Duplicate / condo modeling or feature representation differences could affect parcel parity | Compare unique `parno`, `pid`, and sample geometries during preview. |
| Parcel source has no embedded zoning | Prevents Class C path | Treat `parusecode` and `parusedesc` as tax/use only. Use Charlotte zoning polygons. |
| Charlotte zoning is city-scoped | Does not solve countywide Mecklenburg | Limit proof to South Charlotte / city Charlotte. Source other municipalities separately later. |
| Conditional zoning / petition suffixes | Matrix code universe may be larger than base zoning | Preserve full `ZoneDes`, `ZonePetition`, `SPA`, `Overlay`, and `Hyperlink`; decide during matrix sprint whether to normalize suffixes. |
| AOI boundary effects | Spatial clip can drop zoning polygons or parcels crossing the target boundary | Clip zoning with buffer for staging; evaluate parcel centroids for final `ST_Within` assignment. |
| Multiple parcel services | Wrong canonical source could lose values or city fields | Use NC OneMap as canonical; keep POLARIS/MAT as geometry and ID corroboration. |

## Verdict

Mecklenburg is **not blocked at source acquisition**. NC OneMap provides a viable statewide parcel source with Mecklenburg/Charlotte filters and assessment fields, Mecklenburg POLARIS/MAT provides authoritative parcel-geometry corroboration, and City of Charlotte publishes live zoning polygons with local zone codes.

The sprint is **not** a Class C field-mapping sprint. Parcel fields expose tax/use codes, not zoning. The viable path is **Class A/B hybrid**: NC OneMap parcels clipped to the South Charlotte wealth-pocket polygon, then Charlotte zoning polygons spatially backfilled via `ZoneDes`, followed by a Charlotte/South-Charlotte matrix directory.

Recommended next action: run a South Charlotte preview ingest once the actual target polygon is available. If the KMZ/AOI is not available to Lane A, stop before production work; the whole-city `CHARLOTTE` filter is too broad to be a truthful operational target.
