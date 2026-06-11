# King WA Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering King County, WA, with emphasis on the 57-list wealth pockets Bellevue and Mercer Island.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Washington State Current Parcels / Washington State Parcels Project** |
| Parcel source URL | `https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0` |
| Parcel source class | **SINGLE-STATE-AGGREGATOR** |
| Verified class | **Class A/B hybrid, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. Parcel rows carry DOR/county land-use fields, not zoning district codes. |
| Class A separate zoning layer | **PARTIAL**. Washington Commerce's statewide Zoning Atlas covers Bellevue and Mercer Island with local `ZoneID`, `ZoneName`, generalized use fields, and code reference URLs. Bellevue and Mercer Island also publish city zoning FeatureServers. Bbox primitive passes for both target cities; production `ST_Within` dry-run cannot run until parcels are staged. |
| Verified via Lane A strengthened gates | **PARTIAL**. Live field samples and bbox checks pass. Required 1,000-parcel `ST_Within` dry-run remains a preview gate. |
| Lane A effort estimate | **3-5 days** for statewide parcel adapter + Bellevue/Mercer Island zoning proof; **1-2+ weeks** for broader King County operationalization. |
| Expected operational outcome | **Two-city proof-then-scale**, not first-sprint countywide operational. Bellevue + Mercer Island are about 40,665 of 635,192 King parcel rows, roughly 6.4%. |
| Bellevue coverage | **YES**. State parcel count 33,217; Bellevue city zoning layer count 1,009; WAZA Bellevue zones count 991. |
| Mercer Island coverage | **YES**. State parcel count 7,448; Mercer Island city zoning layer count 82; WAZA Mercer Island zones count 48. |
| Multi-county carry | **YES**. State parcel source covers WA statewide; live Puget Sound counts include King 635,192, Pierce 339,590, Snohomish 318,594, and Kitsap 139,602 parcels. |
| Recommended dispatch | **HIGH**. This should be considered above Maricopa on adapter ROI because the parcel source is statewide and the Zoning Atlas is also statewide. Immediate 57-list impact is still two polygons. |

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `King` match.
- `/api/admin/coverage`: no `King` row.

King remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Recommended source: Washington State Current Parcels, hosted by WaTech / Washington State Geospatial Open Data Portal.

- Statewide map/item: `https://geo.wa.gov/maps/2b603a599a0842a3b2284c04c8927f35`
- ArcGIS item: `https://www.arcgis.com/home/item.html?id=2b603a599a0842a3b2284c04c8927f35`
- Live parcel layer: `https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0`
- King County direct parcel layer fallback: `https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0`
- King County open data page: `https://gis-kingcounty.opendata.arcgis.com/datasets/kingcounty::parcel/about`
- King County GIS catalog metadata: `https://www5.kingcounty.gov/sdc?Layer=PARCEL_AREA`

Why statewide over King County direct: King County's direct parcel layer is authoritative and simple, but it exposes only `PIN`, `MAJOR`, `MINOR`, and geometry. Washington Current Parcels adds normalized address/city, statewide land-use fields, value fields, and a data link while preserving geometry. It also becomes a reusable WA adapter rather than a single-county adapter.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels_2026` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Washington State Plane North, `wkid=2927` |
| Max record count | 2,000 |
| Statewide parcel count | 3,321,859 |
| King parcel count | 635,192 |
| Full statewide bbox | `xmin=576751.6303`, `ymin=83504.0720`, `xmax=2550619.1205`, `ymax=1355594.7489` |

Observed parcel fields include:

`FIPS_NR`, `COUNTY_NM`, `PARCEL_ID_NR`, `ORIG_PARCEL_ID`, `SITUS_ADDRESS`, `SUB_ADDRESS`, `SITUS_CITY_NM`, `SITUS_ZIP_NR`, `LANDUSE_CD`, `ORIG_LANDUSE_CD`, `VALUE_LAND`, `VALUE_BLDG`, `DATA_LINK`, and geometry fields.

Class C gate result: **FAIL**. `LANDUSE_CD` and `ORIG_LANDUSE_CD` are DOR/county land-use classifications, not zoning district codes.

Implementation note: despite the field alias "County Name", live rows use numeric county values such as `COUNTY_NM='33'` for King. Do not assume literal county names in the adapter filter.

## Multi-County Carry

The Washington statewide parcel layer is the stronger multi-county unlock. Live Puget Sound counts:

| County | State parcel filter | Live count |
|---|---|---:|
| King | `COUNTY_NM='33'` | 635,192 |
| Pierce | `COUNTY_NM='53'` | 339,590 |
| Snohomish | `COUNTY_NM='61'` | 318,594 |
| Kitsap | `COUNTY_NM='35'` | 139,602 |

PSRC/Sound Transit regional fallback:

- Service: `https://rtamaps2.soundtransit.org/arcgis/rest/services/RegionalParcels_MIL1/MapServer`
- Layers: King `0`, Pierce `1`, Snohomish `2`
- King count: 637,237

The regional service is useful as corroboration but is not the preferred adapter target. It is thinner than the statewide source, with parcel number plus geometry only, and it does not expose Kitsap in the probed service. The statewide source is the canonical choice.

## Target Parcel Coverage

Bellevue live query:

- Query: `COUNTY_NM='33' AND SITUS_CITY_NM='BELLEVUE'`
- Count: 33,217
- Parcel bbox, WGS84: `[-122.2511546, 47.5284504, -122.0843964, 47.6617612]`

Sample Bellevue parcel rows:

| County | Parcel ID | Original parcel ID | Address | City | DOR land use | County land use |
|---|---|---|---|---|---:|---|
| `33` | `033-9888000060` | `9888000060` | `17102 SE COUGAR MOUNTAIN DR` | BELLEVUE | 11 | `33-2` |
| `33` | `033-9888000050` | `9888000050` | `17100 SE COUGAR MOUNTAIN DR` | BELLEVUE | 11 | `33-2` |
| `33` | `033-9888000040` | `9888000040` | `17109 SE COUGAR MOUNTAIN DR` | BELLEVUE | 11 | `33-2` |
| `33` | `033-9888000030` | `9888000030` | `17116 SE COUGAR MOUNTAIN DR` | BELLEVUE | 11 | `33-2` |
| `33` | `033-9810500000` | `9810500000` | `11330 NE 36TH PL` | BELLEVUE | 14 | `33-20` |

Mercer Island live query:

- Query: `COUNTY_NM='33' AND SITUS_CITY_NM='MERCER ISLAND'`
- Count: 7,448
- Parcel bbox, WGS84: `[-122.2547522, 47.5240329, -122.1999567, 47.5966780]`

Sample Mercer Island parcel rows:

| County | Parcel ID | Original parcel ID | Address | City | DOR land use | County land use |
|---|---|---|---|---|---:|---|
| `33` | `033-9845500040` | `9845500040` | `4495 E MERCER WAY` | MERCER ISLAND | 11 | `33-2` |
| `33` | `033-9845500030` | `9845500030` | `4501 E MERCER WAY` | MERCER ISLAND | 11 | `33-2` |
| `33` | `033-9845500020` | `9845500020` | `4505 E MERCER WAY` | MERCER ISLAND | 11 | `33-2` |
| `33` | `033-9845500010` | `9845500010` | `4507 E MERCER WAY` | MERCER ISLAND | 11 | `33-2` |
| `33` | `033-9365700386` | `9365700386` | `4341 ISLAND CREST WAY` | MERCER ISLAND | 11 | `33-2` |

Conclusion: both 57-list centers are covered by the canonical statewide parcel source. They are not local parcel patchworks.

## Zoning Source Audit

King County's DPER / county zoning concepts should not be treated as a unified city zoning system. Bellevue and Mercer Island are incorporated cities with city-level zoning. County zoning layers may be useful for unincorporated King County later, but they do not solve the 57-list target cities.

### Washington State Zoning Atlas

Primary Class A candidate:

- State map/item: `https://geo.wa.gov/maps/743c0f2e1c1b4a438452c4d40ff53d74`
- ArcGIS item: `https://www.arcgis.com/home/item.html?id=743c0f2e1c1b4a438452c4d40ff53d74`
- FeatureServer: `https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer`
- Zones layer: `https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer/0`

The Washington State Zoning Atlas is hosted by the Department of Commerce and describes itself as a centralized spatial zoning database for Washington's 39 counties and 281 cities. It exposes local zone IDs plus generalized land-use categories, development standards, and reference URLs.

Live WAZA probe:

| Check | Bellevue | Mercer Island |
|---|---:|---:|
| Count | 991 | 48 |
| Parcel bbox, WGS84 | `[-122.2511546, 47.5284504, -122.0843964, 47.6617612]` | `[-122.2547522, 47.5240329, -122.1999567, 47.5966780]` |
| WAZA zoning bbox, WGS84 | `[-122.2227950, 47.5349652, -122.0872055, 47.6607355]` | `[-122.2545065, 47.5244374, -122.2015861, 47.5960370]` |
| Bbox primitive | **Passes**. Roughly 80% rectangular overlap against raw Bellevue situs-city parcel bbox. | **Passes**. Nearly full overlap against Mercer Island parcel bbox. |

Fields include `Jurisdiction`, `COUNTYNAME`, `ZoneID`, `ZoneName`, `WAZAZoneGeneral`, `WAZAZoneSpecific`, many `Use*` columns, `Dim*` / `Den*` standards, `Info`, and `ReferenceURL`.

Sample WAZA rows:

| Jurisdiction | Zone ID | Zone name | General | Specific | Residential use | Reference URL |
|---|---|---|---|---|---|---|
| Bellevue | `R-10` | Multifamily Residential R-10 | LIR | MHR2 | P | `https://bellevue.municipal.codes/LUC/20.20.010` |
| Bellevue | `PO` | Proffessional Office | COM | COMOFFI | P | `https://bellevue.municipal.codes/LUC/20.20.010` |
| Bellevue | `R-20` | Multifamily Residential R-20 | LIR | MHR3-4 | P | `https://bellevue.municipal.codes/LUC/20.20.010` |
| Bellevue | `GC` | General Comercial | COM | COMOFFI | C | `https://bellevue.municipal.codes/LUC/20.20.010` |
| Mercer Island | `R-15` | Residential, 15,000 sq ft lot | LIR | SR1-5 | P | Municode Title 19.02 |
| Mercer Island | `R-9.6` | Residential, 9,600 sq ft lot | LIR | SR1-5 | P | Municode Title 19.02 |
| Mercer Island | `R-8.4` | Residential, 8,400 sq ft lot | LIR | SR5-12 | P | Municode Title 19.02 |

WAZA verdict: **best first Class A candidate, preview-gated**. It is statewide, has local code-like `ZoneID`, carries ordinance URLs, and passes the bbox primitive for both target cities. The required 1,000-parcel `ST_Within` dry-run must still run in preview before production backfill.

### Bellevue City Zoning

Public sources:

- Bellevue GIS data page: `https://bellevuewa.gov/city-government/departments/ITD/maps-gis/gis-data`
- Bellevue Open Data zoning page: `https://data.bellevuewa.gov/datasets/cobgis::zoning`
- Bellevue zoning FeatureServer: `https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/Zoning/FeatureServer`
- Bellevue zoning layer: `https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/Zoning/FeatureServer/7`
- Bellevue Land Use Code: `https://bellevue.municipal.codes/LUC`
- Land Use Districts: `https://bellevue.municipal.codes/LUC/20.10`
- Land Use Charts / tables: `https://bellevue.municipal.codes/LUC/Tables`

Live city zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Washington State Plane North, `wkid=103180`, `latestWkid=6597` |
| Count | 1,009 |
| Nonblank `Zoning` count | 1,009 |
| City zoning bbox, WGS84 | `[-122.2238857, 47.5339000, -122.0849914, 47.6616000]` |
| Bellevue parcel bbox, WGS84 | `[-122.2511546, 47.5284504, -122.0843964, 47.6617612]` |
| Bbox primitive | **Passes**. The city zoning layer covers roughly 80% of the raw Bellevue situs-city parcel bbox. The western raw parcel extent likely includes postal/situs edge noise. |

Fields include `Zoning`, `ZoningDescription`, `ZoningAlias`, `ZoningAliasDescription`, `ZONING_PreCodeAmendment2017`, `ORDNUM`, `ORDBOTH`, and edit metadata.

Sample city zoning rows:

| Zoning | Description | Pre-2017 code | Ordinance |
|---|---|---|---|
| `LDR-2` | Middle Housing | `R-10` | `ORD.4448` |
| `PO` | Professional Office | `PO` | `ORD.2781` |
| `MDR-1` | Middle Housing | `R-20` | `ORD.1200` |
| `MDR-2` | Middle Housing | `R-30` | `ORD.2644` |
| `MU-H` | Mixed Use Highrise | `GC` | blank / newer amendment |
| `SR-4` | Middle Housing | `R-5` | `ORD.4794` |

Bellevue verdict: **strong city-level Class A fallback plus Class B directory support**. WAZA should be tried first for statewide consistency; Bellevue's own layer is the source-of-record fallback if WAZA's preview join underperforms or if current code naming is needed. Bellevue's code is online and has land-use charts/tables, but it is not a single Bergen-style countywide table.

### Mercer Island City Zoning

Public sources:

- Mercer Island planning FeatureServer: `https://services3.arcgis.com/bJ3kuL5CJAvqKrUn/arcgis/rest/services/Mercer_Island_Planning_Layers/FeatureServer`
- Mercer Island zoning layer: `https://services3.arcgis.com/bJ3kuL5CJAvqKrUn/arcgis/rest/services/Mercer_Island_Planning_Layers/FeatureServer/2`
- Mercer Island web map item found by ArcGIS search: `https://www.arcgis.com/home/item.html?id=e61b22542f8f47dcaee6d30a477d59ec`
- Mercer Island Title 19 Unified Land Development Code: `https://library.municode.com/wa/mercer_island/codes/city_code?nodeId=CICOOR_TIT19UNLADECO`

Live city zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Washington State Plane North, `wkid=2926` |
| Count | 82 |
| City zoning bbox, WGS84 | `[-122.2546988, 47.5241145, -122.2002049, 47.5965640]` |
| Mercer Island parcel bbox, WGS84 | `[-122.2547522, 47.5240329, -122.1999567, 47.5966780]` |
| Bbox primitive | **Passes**. City zoning bbox effectively matches Mercer Island parcel bbox. |

Fields include `ZONING`, `ZoningDescription`, `ACRES`, and geometry fields.

Sample city zoning rows:

| Zoning | Description |
|---|---|
| `R-15` | Residential, minimum 15,000 sq ft lot, Unified Land Development Code 19.02 |
| `R-9.6` | Residential, minimum 9,600 sq ft lot, Unified Land Development Code 19.02 |
| `R-8.4` | Residential, minimum 8,400 sq ft lot, Unified Land Development Code 19.02 |
| `MF-2` | Multi-Family, max density 38 units/acre, Unified Land Development Code 19.03 |
| `TC` | Town Center, Unified Land Development Code 19.11 |
| `B` | Business, Unified Land Development Code 19.04.050 |

Mercer Island verdict: **strong city-level Class A fallback plus Class B directory support**. WAZA and city layer both pass bbox. City layer has fewer polygons and clearer local descriptions; WAZA has stronger statewide standardization and code URLs.

## Lane A Execution Shape

Recommended staged plan:

1. Register King County in preview.
2. Ingest King parcels from Washington Current Parcels with filter `COUNTY_NM='33'`.
3. Normalize parcel identity:
   - `parcel_id`: `ORIG_PARCEL_ID` or `PARCEL_ID_NR` after confirming existing ID conventions
   - alternate IDs: keep both `PARCEL_ID_NR` and `ORIG_PARCEL_ID`
   - municipality/subjurisdiction: `SITUS_CITY_NM`
   - source provenance: Washington Current Parcels FeatureServer URL + pull timestamp
   - source CRS: EPSG:2927
4. Do **not** classify as Class C. `LANDUSE_CD` and `ORIG_LANDUSE_CD` are land-use/tax fields.
5. For Bellevue + Mercer Island proof, stage zoning from WAZA `Zones` layer first:
   - Bellevue: `Jurisdiction='Bellevue'`
   - Mercer Island: `Jurisdiction='Mercer Island'`
6. Run strengthened Class A gates before production backfill:
   - district bbox covers >=50% of target-city parcel bbox
   - 1,000-parcel `ST_Within` dry-run >=50% match for each target city
7. If WAZA underperforms, retry with city source-of-record layers:
   - Bellevue city zoning: `Zoning/FeatureServer/7`
   - Mercer Island city zoning: `Mercer_Island_Planning_Layers/FeatureServer/2`
8. Author `backend/data/king_wa_zoning_directory.json` for Bellevue + Mercer Island proof only, using WAZA `ReferenceURL` values plus Bellevue/Mercer code links.
9. Treat Seattle, Redmond, Kirkland, unincorporated DPER zoning, and full King County operationalization as later scale work.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Washington statewide parcel adapter for King | 6-10h |
| Reuse adapter for Pierce/Snohomish/Kitsap/other WA counties | +2-4h after King succeeds |
| WAZA zoning pull + target-city preview gates | 4-8h |
| Bellevue city zoning fallback validation | 2-4h |
| Mercer Island city zoning fallback validation | 2-4h |
| Bellevue + Mercer Island directory/matrix seed | 1-2 days |
| Two-city proof end to end | 3-5 days |
| Full King County operationalization | 1-2+ weeks |

Expected coverage after only Bellevue + Mercer Island:

- Bellevue parcels: 33,217
- Mercer Island parcels: 7,448
- Combined: 40,665
- King total: 635,192
- Countywide fraction: about 6.4%

This is a two-polygon proof and a statewide adapter unlock, not a first-sprint countywide operational flip.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| State parcel field aliases are misleading | Adapter filters can silently miss King | Use live value `COUNTY_NM='33'`; verify counts against King direct parcels. |
| No embedded zoning in parcel source | Prevents Class C path | Treat `LANDUSE_CD` / `ORIG_LANDUSE_CD` as land use only. |
| WAZA is a normalized atlas, not necessarily municipal source of record | Potential code freshness / simplification drift | Use WAZA for first standardized preview; fall back to Bellevue and Mercer Island city FeatureServers if necessary. |
| Bellevue raw situs-city parcel bbox is wider than city zoning bbox | Postal/situs edge noise can depress bbox/ST_Within metrics | Gate per target city and inspect misses; consider city boundary or city zoning-source fallback. |
| Multiple coordinate systems | Transform risk: parcel EPSG:2927, WAZA Web Mercator, Bellevue EPSG:103180/6597, Mercer EPSG:2926 | Keep CRS in run log and rely on existing geometry transform path. |
| ArcGIS pagination | Large statewide source requires paging | Use existing paginated ArcGIS adapter pattern. |
| County DPER zoning confusion | Wrong zoning system for Bellevue/Mercer Island | Keep zoning scoped to incorporated city / WAZA jurisdictions. |
| Multi-county carry can be overstated | WA adapter does not automatically make Pierce/Snohomish/Kitsap operational | Flag as parcel-source carry; each county still needs zoning-source gates and target municipalities. |

## Verdict

King is **not blocked at parcel acquisition**. The strongest source is not just King County GIS; it is Washington's statewide Current Parcels layer, which gives Lane A a reusable statewide adapter and cleaner target-city filters than King County's bare `PIN`/geometry layer.

King is **a stronger Class A candidate than prior scoping indicated** because Washington Commerce's statewide Zoning Atlas covers Bellevue and Mercer Island with local zone IDs and code reference URLs, and both target cities also publish public city zoning FeatureServers. The classification remains **PARTIAL verified** until Lane A runs the required preview `ST_Within` gates.

Recommended next action: move King above Maricopa if Master is prioritizing adapter ROI. It has the same two-polygon immediate footprint as Maricopa, but the parcel source is statewide and the zoning-atlas candidate is also statewide.
