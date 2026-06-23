# Wake NC Acquisition Spec

Date: 2026-06-23

Purpose: read-only acquisition spec for a possible Lane A ingestion sprint covering Wake County, NC, with emphasis on the Phase 5 wealth-pocket centers Cary and North Raleigh.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **NC OneMap NC1Map Parcels, Parcels (polys)** |
| Parcel source URL | `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1` |
| Parcel source class | **SINGLE-STATE-AGGREGATOR** |
| Verified class | **Class A parcel source, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. Parcel rows carry tax parcel use fields (`parusecode`, `parusedesc`), not zoning district codes. |
| Separate zoning source | **YES**. Wake iMAPS publishes a `Planning/Zoning` service with separate Raleigh and Cary zoning layers. Cary also publishes its own `LandUse/Zoning` FeatureServer. |
| Target-center shape | **Cary = incorporated town**; **North Raleigh = neighborhood/subarea within Raleigh city**, not a separate municipality or zoning authority. |
| Verified via Lane A strengthened gates | **PARTIAL**. Live counts, field checks, bbox extents, and 50-row samples pass. Required parcel-to-zoning `ST_Within` dry-run remains a preview gate. |
| Lane A effort estimate | **3-5 days** for Wake parcel adapter + Cary/Raleigh zoning proof; **1-2+ weeks** for broader Wake multi-municipality operationalization. |
| Expected operational outcome | **Two-center proof-then-scale**, not first-sprint countywide operational. Cary + Raleigh situs-city parcels are 196,283 of 435,381 Wake NC OneMap parcels, roughly 45.1%; North Raleigh itself requires a market subarea cut inside Raleigh. |
| Cary coverage | **YES**. NC OneMap Cary situs parcels count 57,182; Wake iMAPS Cary zoning count 2,736; Town of Cary zoning count 2,829. |
| Raleigh / North Raleigh coverage | **YES for Raleigh city zoning**. NC OneMap Raleigh situs parcels count 139,101; Wake iMAPS Raleigh zoning count 3,561. No single official `North Raleigh` polygon was found in the Raleigh Neighborhood Registry; the registry has many smaller neighborhood polygons. |
| Multi-county carry | **YES for parcels**. NC OneMap covers all NC counties; live Mecklenburg count is 442,287 using the same layer and filters. Wake + Mecklenburg should share the same statewide parcel adapter if Mecklenburg's Class A parcel path is confirmed. |
| Recommended dispatch | **HIGH** for Phase 5. Wake has a statewide parcel adapter candidate and clean zoning polygon sources for both named centers. |

## Current Prod State

Prior prod diagnostics in `docs/PHASE4_5_STRUCTURAL_DIAGNOSTIC.md` classified Wake as **INGESTION-BLOCKED**:

- Registered as `Wake County, NC` with `jurisdiction_id=b05b7317-b412-492c-a56c-433d447d17bf`.
- Parcel search returned about 435k rows, but admin coverage was stale/out-of-sync at `parcel_count=0`.
- Sampled parcel rows had `city=null` and `zoning_code=null`.
- `/api/jurisdictions/{id}/cities` returned `[]`.
- Operational blocker: no parcel zoning codes and no city drilldown.

This spec does not change prod data. It identifies the likely upstream sources needed to backfill municipality and zoning join keys.

## Canonical Parcel Source

Recommended source: NC OneMap `NC1Map_Parcels`, polygon layer.

- NC OneMap parcel page: `https://www.nconemap.gov/pages/parcels`
- Dataset page: `https://www.nconemap.gov/datasets/nconemap::north-carolina-parcels-polygons/about`
- FeatureServer: `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer`
- Polygon layer: `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1`
- Wake iMAPS parcel fallback: `https://maps.raleighnc.gov/arcgis/rest/services/Property/Property/FeatureServer/0`

Why NC OneMap over Wake-only parcels: Wake iMAPS is authoritative and has richer Wake-specific jurisdiction fields, but NC OneMap is a statewide normalized parcel layer. It gives Lane A one adapter for Wake and Mecklenburg rather than separate county-specific parcel adapters.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels (polys)` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NC StatePlane feet, `wkid=102719`, `latestWkid=2264` |
| Max record count | 5,000 |
| Statewide parcel count | 5,938,640 |
| Wake parcel count | 435,381 |
| Mecklenburg parcel count | 442,287 |
| Wake bbox, WGS84 | `[-78.9950726, 35.5194636, -78.2533728, 36.0765226]` |

Observed fields include:

`parno`, `altparno`, `ownname`, `siteadd`, `scity`, `cntyname`, `cntyfips`, `sourceagnt`, `gisacres`, `parusecode`, `parusedesc`, `improvval`, `landval`, `parval`, `transfdate`, and geometry fields.

Class C gate result: **FAIL**. `parusecode` and `parusedesc` are tax parcel use fields, not zoning district codes. Wake needs separate zoning polygons and a spatial backfill.

Implementation note: use live county fields `cntyname='Wake'` or `cntyfips='183'`. Do not assume a `COUNTY` field.

## Multi-County Carry

NC OneMap is the strongest parcel-source unlock for North Carolina Phase 5 work.

| County | Filter | Live count |
|---|---|---:|
| Wake | `cntyname='Wake'` or `cntyfips='183'` | 435,381 |
| Mecklenburg | `cntyname='Mecklenburg'` or `cntyfips='119'` | 442,287 |

Source-path coordination: if the Mecklenburg spec confirms NC OneMap as Class A for parcels, both Mecklenburg and Wake should reference the same upstream adapter:

```text
https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1
```

The carry is parcel-only. Charlotte/Mecklenburg and Wake still need separate zoning-source gates because zoning authority is municipal/local.

## Target Parcel Coverage

Cary live query:

- Query: `cntyname='Wake' AND scity='CARY'`
- Count: 57,182

Sample Cary parcel rows from a 50-feature sample:

| Parcel | Alt parcel | Address | City | Tax use | Source |
|---|---|---|---|---|---|
| `0765045120` | `0210739` | `100 MONTAUK POINT PL` | CARY | `RHS` / `R` | Wake County Assessor |
| `0723263673` | `0524003` | `1105 SPARKLING LAKE DR` | CARY | `HOA` / `I` | Wake County Assessor |
| `0723260869` | `0524007` | `1401 SPARKLING LAKE DR` | CARY | `HOA` / `I` | Wake County Assessor |
| `0723169366` | `0524008` | `1432 SPARKLING LAKE DR` | CARY | `HOA` / `I` | Wake County Assessor |
| `0723175358` | `0524054` | `10017 SECLUDED GARDEN DR` | CARY | `VAC` / `V` | Wake County Assessor |

Raleigh live query:

- Query: `cntyname='Wake' AND scity='RALEIGH'`
- Count: 139,101

Sample Raleigh parcel rows from a 50-feature sample:

| Parcel | Alt parcel | Address | City | Tax use | Source |
|---|---|---|---|---|---|
| `1713072013` | `0007442` | `420 HAYWOOD ST` | RALEIGH | `RHS` / `R` | Wake County Assessor |
| `0794582681` | `0043121` | `1401 DIXIE TRL` | RALEIGH | `RHS` / `R` | Wake County Assessor |
| `0773865199` | `0060690` | `632 S LAKESIDE DR` | RALEIGH | `RHS` / `R` | Wake County Assessor |
| `1736820978` | `0149114` | `6201 RIVER LANDINGS DR` | RALEIGH | `RHS` / `R` | Wake County Assessor |
| `1748324840` | `0515172` | `2680 PRINCESS TREE DR` | RALEIGH | `RHS` / `R` | Wake County Assessor |

Conclusion: both named centers are covered at the parcel layer, but North Raleigh must be scoped as a Raleigh subarea after Raleigh city zoning is joined. It should not become a separate product jurisdiction.

## Zoning Source Audit

Wake County is not a single zoning-code jurisdiction. Cary is an incorporated town with its own Land Development Ordinance and zoning map. North Raleigh lies within Raleigh city, so Raleigh UDO and Raleigh zoning control.

### Wake County iMAPS

Primary zoning source candidate:

- Wake/Raleigh services root: `https://maps.raleighnc.gov/arcgis/rest/services`
- iMAPS zoning service: `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer`
- Raleigh zoning layer: `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/0`
- Cary zoning layer: `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/3`
- Wake iMAPS property fallback: `https://maps.raleighnc.gov/arcgis/rest/services/Property/Property/FeatureServer/0`
- Jurisdiction boundaries: `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Jurisdictions/MapServer`

Service description: `Map service displaying zoning for municipalities in Wake County.`

Wake iMAPS property probe:

| Check | Result |
|---|---:|
| Layer name | `Property` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NC StatePlane feet, `wkid=102719`, `latestWkid=2264` |
| Count | 440,053 |
| Cary `CITY_DECODE` count | 57,186 |
| Raleigh `CITY_DECODE` count | 139,405 |

Property fields include `PIN_NUM`, `REID`, `SITE_ADDRESS`, `CITY_DECODE`, `PLANNING_JURISDICTION`, `TYPE_USE_DECODE`, `LAND_CLASS_DECODE`, and assessed value fields. This is a strong county parcel fallback and a useful field-map reference, but no zoning code field was observed on parcel rows.

Sample Wake iMAPS property rows from a 50-feature sample:

| PIN | REID | Address | City | Planning jurisdiction | Type/use |
|---|---|---|---|---|---|
| `0695327712` | `0448960` | `7712 BILL LOVE RD` | blank | `WC` | `SINGLFAM` |
| `0695320153` | `0022383` | `7716 BILL LOVE RD` | blank | `WC` | blank |
| `1713072013` | `0007442` | `420 HAYWOOD ST` | RALEIGH | `RA` | `SINGLFAM` |
| `0765045120` | `0210739` | `100 MONTAUK POINT PL` | CARY | `CA` | `SINGLFAM` |
| `0794582681` | `0043121` | `1401 DIXIE TRL` | RALEIGH | `RA` | `SINGLFAM` |

Wake iMAPS zoning verdict: **strong Class A zoning aggregator for target municipalities, preview-gated**. It publishes Raleigh and Cary layers under one service and should be the first zoning pull for a two-center proof.

Wake iMAPS Cary zoning layer probe:

| Check | Result |
|---|---:|
| Layer URL | `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/3` |
| Count | 2,736 |
| Zone-code field | `CLASS` |
| Bbox, WGS84 | `[-78.9496291, 35.6443267, -78.7289807, 35.8969729]` |

The 50-feature Cary sample returned `CLASS` values such as `CT`, `CT-C`, and `GC`. Top observed `CLASS` values by polygon count include `PDDMajor`, `R12`, `R40`, `R8CU`, `TRCU`, `R20`, `R8`, `R/R`, `ORD`, `TC`, `R12CU`, `OICU`, `OI`, `GC`, and `GCCU`.

### Raleigh Zoning

Primary source:

- City item: `https://www.arcgis.com/home/item.html?id=6e03606265fc42f89e6be2f16b227f26`
- Layer URL: `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/0`
- Raleigh zoning page: `https://raleighnc.gov/planning/services/zoning-map`
- Raleigh UDO use table: `https://udo.raleighnc.gov/sec-614-allowed-principal-use-table`

Live Raleigh zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Raleigh Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NC StatePlane feet, `wkid=102719`, `latestWkid=2264` |
| Count | 3,561 |
| Bbox, WGS84 | `[-78.8193989, 35.7062128, -78.4698896, 35.9716498]` |

Fields include `ZONE_TYPE`, `ZONE_TYPE_DECODE`, `HEIGHT`, `FRONTAGE`, `FRONTAGE_DECODE`, `CONDITIONAL`, `ZONING`, `ZONE_CASE`, `ORDINANCE`, `PLAN_NAME`, and `COND_LINK`.

Sample Raleigh zoning rows from a 50-feature sample:

| Zoning | Type | Height | Frontage | Conditional | Case | Ordinance |
|---|---|---:|---|---|---|---|
| `OX-3-CU` | Office Mixed Use | 3 | blank | `-CU` | `Z-22-1993` | `217ZC329` |
| `IX-3` | Industrial Mixed Use | 3 | blank | blank | `Z-27B-2014` | `523ZC721` |
| `R-10` | Residential-10 | blank | blank | blank | blank | blank |
| `IX-3-PK` | Industrial Mixed Use | 3 | Parkway | blank | `Z-27B-2014` | `523ZC721` |
| `MH` | Manufactured Housing | blank | blank | blank | `Z-56-1982` | `003ZC109` |

Top observed zoning codes by polygon count include `R-4`, `R-10`, `R-6`, `R-10-CU`, `OX-3-CU`, `R-6-CU`, `CM`, `OX-3`, `RX-3`, `RX-3-CU`, `IX-3`, and `CX-3`.

Raleigh verdict: **strong city-level Class A zoning source plus Class B directory support**. It has local zone codes that match the Raleigh UDO use table shape. Use it for North Raleigh because North Raleigh is inside Raleigh's municipal zoning authority.

### North Raleigh Boundary Probe

Boundary candidate:

- Raleigh Neighborhood Registry item: `https://www.arcgis.com/home/item.html?id=b3914e45ea414414bfa7bc5d6b6d21d4`
- FeatureServer: `https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Raleigh_Neighborhood_Registry/FeatureServer/0`
- City page: `https://raleighnc.gov/community/services/raleigh-neighborhood-registry`

Live Neighborhood Registry probe:

| Check | Result |
|---|---:|
| Layer name | `Neighborhoods` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 413 |
| `UPPER(Name) LIKE '%NORTH%'` count | 16 |
| `District='Northeast'` count | 272 |
| Northeast bbox, WGS84 | `[-78.8165351, 35.6605354, -78.5039794, 35.9706247]` |

Sample `Name LIKE '%North%'` rows:

| Name | District | Homes |
|---|---|---:|
| North Hills Neighborhood Association | Northeast | 1,291 |
| North Bend Townhomes HOA | Northeast | 163 |
| North Ridge Condominium HOA | Northeast | 118 |
| North Ridge Villas HOA | Northeast | 357 |
| Northclift Neighbors NA | Northeast | 539 |
| Summerfield North NA | Northeast | 321 |
| Northshore Neighborhood Association | Northeast | 115 |
| North Ridge Road Neighborhood Alliance | Northeast | 573 |
| 5401 North | Northeast | 300 |

North Raleigh verdict: **no single official North Raleigh polygon found**. The registry is useful for subarea QA or wealth-pocket clipping, but it is a neighborhood-organization registry, not a zoning authority boundary. Production ingestion should join all Raleigh parcels against Raleigh zoning first. A later market-filter step can clip to a supplied KMZ wealth-pocket polygon, the `District='Northeast'` registry subset, or a documented road-based proxy such as north of Millbrook Road if Master approves that proxy.

### Town of Cary GIS

Preferred Cary municipal source-of-record:

- Town maps page: `https://www.carync.gov/projects-initiatives/maps`
- Town GIS data portal: `https://data-carync.opendata.arcgis.com/`
- Town zoning FeatureServer: `https://maps-apis.carync.gov/server/rest/services/LandUse/Zoning/FeatureServer`
- Base zoning layer: `https://maps-apis.carync.gov/server/rest/services/LandUse/Zoning/FeatureServer/11`
- Cary LDO page: `https://www.carync.gov/business-development/developing-in-cary/development-regulations/land-development-ordinance`
- Cary permitted uses/setbacks page: `https://www.carync.gov/business-development/developing-in-cary/development-guidelines/permitted-uses-setbacks`

Live Town of Cary zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning District` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NC StatePlane feet, `wkid=102719`, `latestWkid=2264` |
| Count | 2,829 |
| Bbox, WGS84 | `[-78.9537969, 35.6443754, -78.7294475, 35.8968751]` |

Fields include `ZONECLASS`, `ZONEDESC`, `BASEELEV`, `HEIGHT`, `LASTUPDATE`, `COMMENTS`, editor metadata, and geometry fields.

Sample Town of Cary zoning rows from a 50-feature sample:

| Zone class | Description | Height | Comments |
|---|---|---:|---|
| `MXD` | blank | 34.31981276 | blank |
| `GC` | blank | 5.72711450 | blank |
| `GC` | blank | 7.64663176 | blank |
| `GC` | blank | 1.21283948 | blank |
| `GC` | blank | 2.03410343 | blank |

Top observed zone classes by polygon count include `PDDMajor`, `R12`, `R40`, `TRCU`, `R8CU`, `R8`, `R20`, `R/R`, `TC`, `R12CU`, `ORD`, `OICU`, `OI`, `GC`, `GCCU`, `MXD`, `PDDMinor`, `TR`, `RMF`, and `ORDCU`.

Cary verdict: **strong per-municipality Class B zoning source, source-of-record fallback/override**. Wake iMAPS already carries Cary zoning under the countywide zoning service, but Cary's own FeatureServer has slightly more polygons and clearer local ownership. Use Cary's own layer if Wake iMAPS and Town of Cary disagree.

## Lane A Execution Shape

Recommended staged plan:

1. Register/refresh Wake County in preview only.
2. Ingest Wake parcels from NC OneMap with filter `cntyname='Wake'` or `cntyfips='183'`.
3. Normalize parcel identity:
   - `parcel_id`: `parno`
   - alternate IDs: keep `altparno` and `nparno` when present
   - municipality/subjurisdiction: `scity`
   - source provenance: NC OneMap FeatureServer URL + pull timestamp
   - source CRS: EPSG:2264 via `latestWkid=2264`
4. Do **not** classify as Class C. `parusecode` and `parusedesc` are tax/land-use fields.
5. For two-center proof, stage zoning:
   - Raleigh: Wake iMAPS `Planning/Zoning/MapServer/0`, zone key `ZONING`
   - Cary: Town of Cary `LandUse/Zoning/FeatureServer/11`, zone key `ZONECLASS`
   - Keep Wake iMAPS Cary `Planning/Zoning/MapServer/3`, key `CLASS`, as corroboration/fallback.
6. Run strengthened Class A gates before production backfill:
   - zoning bbox covers >=50% of target parcel bbox
   - 1,000-parcel `ST_Within` dry-run >=50% match for Cary
   - 1,000-parcel `ST_Within` dry-run >=50% match for Raleigh
   - sample misses around city edges and blank `scity` parcels
7. Treat North Raleigh as a subarea after Raleigh city zoning is joined:
   - preferred: supplied wealth-pocket KMZ polygon
   - fallback QA: Raleigh Neighborhood Registry polygons with approved names/districts
   - do not create a `North Raleigh` municipality.
8. Author a Wake zoning directory scoped to Cary + Raleigh only:
   - Raleigh ordinance platform: Raleigh UDO, allowed principal use table
   - Cary ordinance platform: Cary LDO/use table
   - matrix join key should include municipality plus zone code, because `GC`, `MXD`, and residential codes can collide across municipalities.
9. Treat Apex, Wake Forest, Holly Springs, Garner, unincorporated Wake, and countywide operationalization as later scale work.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| NC OneMap statewide parcel adapter for Wake | 6-10h |
| Reuse adapter for Mecklenburg/other NC counties | +2-4h after Wake succeeds |
| Wake iMAPS Raleigh zoning pull + preview gates | 3-5h |
| Town of Cary zoning pull + preview gates | 3-5h |
| North Raleigh market-subarea clipping decision | 2-4h if wealth KMZ is available; longer if proxy must be adjudicated |
| Cary + Raleigh directory/matrix seed | 1-2 days |
| Two-center proof end to end | 3-5 days |
| Full Wake County operationalization | 1-2+ weeks |

Expected coverage after Cary + all Raleigh city parcels:

- Cary parcels: 57,182
- Raleigh parcels: 139,101
- Combined: 196,283
- Wake total: 435,381
- Countywide fraction: about 45.1%

The actual Phase 5 footprint is smaller because North Raleigh is a wealth-pocket subarea inside Raleigh rather than all Raleigh.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| NC OneMap parcel fields are not zoning fields | False Class C path | Treat `parusecode` / `parusedesc` as tax use only; require zoning polygons. |
| Existing prod Wake parcels have null `city` | City drilldown remains broken if only prod rows are reused | Reingest or backfill municipality from `scity` / Wake iMAPS `CITY_DECODE`. |
| Multiple parcel counts differ slightly across sources | Confusing QA baselines | Use NC OneMap as canonical adapter count; use Wake iMAPS as corroboration. |
| Cary zoning duplicated in Wake iMAPS and Town GIS | Inconsistent polygon count or freshness | Prefer Town of Cary source-of-record for Cary; keep Wake layer as fallback. |
| North Raleigh is not an incorporated place | Wrong jurisdiction/matrix split | Use Raleigh zoning authority; only subclip for market/wealth-pocket analysis. |
| Raleigh Neighborhood Registry is not a complete official `North Raleigh` boundary | Bad market clipping | Prefer supplied KMZ wealth polygon; otherwise require Master approval of proxy. |
| CRS differences | Geometry join errors | Normalize NC StatePlane EPSG:2264 and Web Mercator neighborhood registry before joins. |
| Zone-code collisions across municipalities | Matrix rows can misclassify | Use `(municipality, zone_code)` as the matrix key. |

## Verdict

Wake is **not blocked at parcel acquisition**. The strongest parcel source is NC OneMap's statewide parcel polygon FeatureServer, which should also be considered for Mecklenburg and future NC counties.

Wake is also **not blocked at target-center zoning acquisition**. Raleigh and Cary both have public zoning polygon layers, and Wake iMAPS conveniently publishes both under one municipal zoning service. Cary's own FeatureServer is the better source-of-record fallback for Cary.

Recommended next action: run a preview Wake adapter proof using NC OneMap parcels plus Raleigh and Cary zoning polygons. Do not model North Raleigh as a separate municipality; model it as a Raleigh market subarea after Raleigh zoning is operational.
