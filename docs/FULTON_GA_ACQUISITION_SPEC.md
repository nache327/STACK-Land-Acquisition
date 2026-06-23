# Fulton GA Acquisition Spec

Date: 2026-06-23

Purpose: read-only acquisition spec for a possible Lane A ingestion/backfill sprint covering Fulton County, GA, with emphasis on the 58-list wealth pockets Sandy Springs and Buckhead.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Fulton County GIS Tax Parcels** |
| Parcel source URL | `https://services1.arcgis.com/AQDHTHDrZzfsFsB5/arcgis/rest/services/Tax_Parcels/FeatureServer/0` |
| Parcel source class | **SINGLE-COUNTY-PORTAL** |
| Verified class | **Class A/B hybrid, PARTIAL verified** |
| GA state / DOR parcel layer | **NO VIABLE CLASS A FOUND**. Georgia DOR points users to county tax office sites; no statewide DOR parcel FeatureServer was found in this probe. |
| Class C embedded parcel zoning | **NO**. Fulton parcel rows carry assessor/tax fields (`TaxDist`, `LUCode`, `ClassCode`, `NbrHood`), not municipal zoning district codes. |
| Class A separate zoning layer | **PARTIAL**. Sandy Springs and Atlanta publish machine-readable zoning polygon layers. Fulton County publishes only a small unincorporated zoning layer and should not be used for Sandy Springs or Buckhead. |
| Sandy Springs coverage | **YES, strong city-level source**. Sandy Springs zoning layer has 27,711 rows with nonblank `Zoning` / `ZoningDistrict`, parcel IDs, addresses, and Municode links. |
| Buckhead coverage | **YES, but only as Atlanta sub-neighborhood filter**. Buckhead is not a separate municipality. Use Atlanta city zoning, then constrain to an approved Buckhead neighborhood geometry set. |
| Buckhead prefilter requirement | **MANDATORY**. Treat Atlanta city as the Class B candidate and apply a sub-neighborhood spatial filter for Buckhead, analogous to the Maricopa AZ Scottsdale city-boundary prefilter discipline. |
| Lane A effort estimate | **3-5 days** for Sandy Springs proof plus Buckhead-filtered Atlanta proof; **1-2+ weeks** for broader Fulton operationalization. |
| Expected operational outcome | **Two-center proof-then-scale**, not first-sprint countywide operational. |
| Recommended dispatch | **MEDIUM/HIGH**. Fulton is viable, but less clean than King/Maricopa because the parcel source has no city field and Buckhead requires an explicit neighborhood interpretation. |

## Current Prod State

Prior diagnostic `docs/PHASE4_5_STRUCTURAL_DIAGNOSTIC.md` reported Fulton County, GA as registered but ingestion-blocked:

- Jurisdiction: `Fulton County, GA`, `bb9e5176-c1e8-4221-9f2e-b27c34545f98`.
- Admin coverage was stale at `parcel_count=0`, while parcel search returned `372,723`.
- Sampled prod parcels had `city=null` and `zoning_code=null`.
- `/api/jurisdictions/{id}/cities` returned `[]`.

Live source probe on 2026-06-23 found 373,004 rows in the current Fulton parcel source. This matches the prior prod parcel-search scale closely enough to treat Fulton as parcels-loaded but zoning/city-unbound.

## Probe Target Summary

| Probe target | Live result | Source class rating |
|---|---|---|
| GA State GIS / Department of Revenue parcel layer | DOR property-records page provides county tax-office links; no live statewide parcel FeatureServer found. GIO/Data Hub search did not surface a usable statewide parcel service. | **Not viable Class A for this sprint** |
| Fulton County GIS parcel layer | `Tax_Parcels/FeatureServer/0`, 373,004 polygon rows. | **Canonical parcel source; Class A parcel substrate** |
| Fulton County GIS zoning layer | `Zoning/FeatureServer/0`, 35 polygon rows, unincorporated-only extent. | **Class A only for unincorporated Fulton; not target source** |
| City of Sandy Springs GIS | `General_Reference/FeatureServer/127`, 27,711 polygon rows with parcel IDs and zoning codes. | **Strong city-level Class A source candidate** |
| City of Atlanta GIS zoning | `ZoningHosted/FeatureServer/0`, 2,404 zoning polygons. | **Class A city zoning source candidate; Class B ordinance binding likely needed** |
| Atlanta neighborhood boundary | `AdministrativeArea/GeopoliticalArea/MapServer/1`, 248 official neighborhood polygons. | **Required Buckhead spatial filter substrate** |

## State / DOR Parcel Probe

Primary public sources checked:

- Georgia DOR property records page: `https://dor.georgia.gov/property-records-online`
- Georgia Geospatial Information Office data hub: `https://data-hub.gio.georgia.gov/`
- ArcGIS Hub/search probes for statewide Georgia parcel services.

The DOR page says it provides links to county tax offices and that county Boards of Tax Assessors / Tax Commissioners are responsible for property valuation and ad valorem tax collection. That is a directory posture, not a statewide parcel FeatureServer.

Verdict: **do not build a Georgia statewide parcel adapter from this probe**. Fulton County's own parcel FeatureServer is the practical canonical source for this sprint.

## Canonical Parcel Source

Recommended source: Fulton County GIS Tax Parcels.

- Open data item: `https://gisdata.fultoncountyga.gov/datasets/fulcogis::tax-parcels/about`
- ArcGIS item: `https://www.arcgis.com/home/item.html?id=e581a072dca9442e884d3682bff03484`
- Live layer: `https://services1.arcgis.com/AQDHTHDrZzfsFsB5/arcgis/rest/services/Tax_Parcels/FeatureServer/0`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Tax Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Georgia West StatePlane, `wkid=102667`, `latestWkid=2240` |
| Max record count | 1,000 |
| Parcel count | 373,004 |
| Full parcel bbox, WGS84 | `[-84.8561109, 33.5014387, -84.0979549, 34.1868448]` |

Observed fields include:

`ParcelID`, `TaxYear`, `Address`, address component fields, `Owner`, owner address fields, `TaxDist`, `LUCode`, `ClassCode`, `ExCode`, `LivUnits`, `LandAcres`, `NbrHood`, subdivision fields, `FeatureID`, and geometry fields.

Class C gate result: **FAIL**. `TaxDist`, `LUCode`, `ClassCode`, and `NbrHood` are assessor/tax/neighborhood fields, not municipal zoning district codes.

Sample 50-feature probe:

| Source | Filter | Sample size | Key nonblank fields in sample | First rows |
|---|---|---:|---|---|
| Fulton tax parcels | `1=1` | 50 | `ParcelID`, `TaxYear`, `Address`, `TaxDist`, `LUCode`, `ClassCode`, `LandAcres`, `NbrHood`: 50/50 | `07 410001590187`, `0 GULLATT RD`, `LUCode=100`, `ClassCode=R4`; `07 410001590039`, `0 GULLATT RD`, `LUCode=100`, `ClassCode=R5`; `07 410001590195`, `0 GULLATT RD`, `LUCode=100`, `ClassCode=A5`; `07 410001590104`, `9265 GULLATT RD`, `LUCode=101`, `ClassCode=R4`; `07 410001590112`, `9260 GULLATT RD`, `LUCode=101`, `ClassCode=R3` |

Implementation note: because this layer has no reliable municipality/city field, target-city parcel cohorts should be built by spatial prefilter, not by parcel attribute equality.

## Fulton County Zoning Layer

Public sources:

- Fulton open data page: `https://gisdata.fultoncountyga.gov/maps/4bef7661a5b04a7c854cd4e3ebfc0deb/about`
- Current live FeatureServer mirror: `https://services1.arcgis.com/AQDHTHDrZzfsFsB5/arcgis/rest/services/Zoning/FeatureServer/0`
- Older item URL from the open data page, currently stale/not found in REST probe: `https://gismaps.fultoncountyga.gov/arcgispub/rest/services/OpenData/Planning_ZoningCurrent/MapServer`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Current Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Georgia West StatePlane, `wkid=102667`, `latestWkid=2240` |
| Count | 35 |
| Bbox, WGS84 | `[-84.5386910, 33.7653766, -84.5071424, 33.7870079]` |

Fields include `CaseID`, `ZClass`, `EffDate`, and `ZClassDesc`.

Sample 35-feature full-layer probe:

| Source | Filter | Sample size | Key nonblank fields in sample | First rows |
|---|---|---:|---|---|
| Fulton unincorporated zoning | `1=1` | 35 | `ZClass`, `ZClassDesc`: 35/35; `EffDate`: 34/35 | `M-2`, Heavy Industrial; `M-2`, Heavy Industrial, `CaseID=1966Z -0055`; repeated `M-2` heavy industrial rows in the first five |

Verdict: **not useful for Sandy Springs or Buckhead proof**. It is a small unincorporated Fulton source. Keep it as a later county-expansion source only.

## Sandy Springs Zoning

Public sources:

- Sandy Springs GIS page: `https://www.sandyspringsga.gov/gis-mapping/`
- Sandy Springs open data portal: `https://data-coss.opendata.arcgis.com/`
- Sandy Springs general reference service: `https://gis2.sandyspringsga.gov/arcgis/rest/services/OpenData/General_Reference/FeatureServer`
- Zoning layer: `https://gis2.sandyspringsga.gov/arcgis/rest/services/OpenData/General_Reference/FeatureServer/127`
- City limit layer for spatial parcel prefilter: `https://gis2.sandyspringsga.gov/arcgis/rest/services/OpenData/General_Reference/FeatureServer/107`
- Sandy Springs Development Code: `https://library.municode.com/ga/sandy_springs/codes/development_code`

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning (amended 4-17-2018)` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Georgia West StatePlane, `wkid=102667`, `latestWkid=2240` |
| Count | 27,711 |
| Zoning bbox, WGS84 | `[-84.4468039, 33.8768688, -84.2583865, 34.0100952]` |
| City limit layer count | 1 |

Fields include `ParcelID`, `Address`, `Zoning`, `ZoningDistrict`, setback fields, `municode`, and `LotCoverage_Pct`.

Top observed zoning district counts:

| Zoning district | Count |
|---|---:|
| `RD-18` | 6,821 |
| `RT-3` | 3,920 |
| `RM-3` | 3,810 |
| `RD-27` | 3,337 |
| `RE-2` | 1,832 |
| `RE-1` | 1,754 |
| `RM-3/8` | 1,018 |
| `RD-12` | 851 |

Sample 50-feature probe:

| Source | Filter | Sample size | Key nonblank fields in sample | First rows |
|---|---|---:|---|---|
| Sandy Springs zoning | `1=1` | 50 | `ParcelID`, `Address`, `Zoning`, `ZoningDistrict`, `municode`: 50/50; `LotCoverage_Pct`: 49/50 | `17 0177  LL1216`, `4710 NORTHSIDE DR`, `RE-2`; `17 013400010317`, `608 CHESTNUT OAK CT`, `RD-27`; `17 013400010309`, `602 CHESTNUT OAK CT`, `RD-27`; `17 0073  LL0825`, `940 GLENGATE PL`, `RD-7.5`; `17 0073  LL0890`, `540 GLENGATE COVE`, `RD-7.5` |

Sandy Springs verdict: **strong city-level Class A candidate**. The layer is parcel-like enough to backfill by `ParcelID` after ID normalization, and polygon geometry can support a spatial fallback. Use city limit layer 107 as the Sandy Springs parcel prefilter against Fulton tax parcels before claiming target-city coverage.

## Atlanta / Buckhead Zoning

Public sources:

- Atlanta Maps and GIS page: `https://www.atlantaga.gov/government/departments/city-planning/maps-and-gis`
- Atlanta zoning FeatureServer: `https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/ZoningHosted/FeatureServer/0`
- Atlanta open data hub: `https://dpcd-coaplangis.opendata.arcgis.com/search`
- Atlanta city code / zoning ordinance: `https://library.municode.com/ga/atlanta/codes/code_of_ordinances`

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning District` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Georgia West StatePlane, `wkid=103028`, `latestWkid=6447` |
| Count | 2,404 |
| Zoning bbox, WGS84 | `[-84.5515895, 33.6475154, -84.2894814, 33.8870158]` |

Fields include `ZONECLASS`, `SPI`, `SUBAREA`, `STATUS`, case fields, and geometry fields. `ZONEDESC` was blank in the 50-row sample, so matrix authoring must bind `ZONECLASS` / overlay codes back to Atlanta Part 16 rather than relying on feature descriptions.

Top observed zone-class counts:

| Zone class | Count |
|---|---:|
| `C-1` | 184 |
| `PD-H` | 155 |
| `RG-3` | 138 |
| `C-1-C` | 119 |
| `RG-2` | 117 |
| `I-1` | 117 |
| `RG-3-C` | 100 |
| `R-4` | 85 |

Sample 50-feature probe:

| Source | Filter | Sample size | Key nonblank fields in sample | First rows |
|---|---|---:|---|---|
| Atlanta zoning | `1=1` | 50 | `ZONECLASS`, `SPI`, `SUBAREA`, `STATUS`: 50/50; `ZONEDESC`: 0/50 | `RG-3`; `HC-20A SA5`; `HC-20A SA1`; `HC-20A SA4`; `HC-20A SA5` |

Atlanta verdict: **viable city zoning source, but Buckhead is not a municipality**. Do not register or treat Buckhead as a city. Use Atlanta as the zoning authority and apply a neighborhood spatial filter to limit the proof cohort.

## Buckhead Neighborhood Filter Requirement

Public boundary source:

- Official neighborhoods open data item: `https://dpcd-coaplangis.opendata.arcgis.com/datasets/official-neighborhoods-open-data`
- Live layer: `https://gis.atlantaga.gov/dpcd/rest/services/AdministrativeArea/GeopoliticalArea/MapServer/1`

Live neighborhood probe:

| Check | Result |
|---|---:|
| Layer name | `Neighborhood` |
| Geometry | `esriGeometryPolygon` |
| Count | 248 |
| Full neighborhood bbox, WGS84 | `[-85.3939, 32.8400, -83.5083, 34.6400]` server extent is broad; use feature geometries, not full service extent, for target filtering. |
| Buckhead-name filter count | 4 |
| NPU A+B filter count | 27 |

Buckhead-name filter:

| Official neighborhood | NPU | Acres | Sq mi |
|---|---|---:|---:|
| Buckhead Village | B | 127.21 | 0.20 |
| Buckhead Forest | B | 200.28 | 0.31 |
| North Buckhead | B | 1,707.15 | 2.67 |
| Buckhead Heights | B | 44.28 | 0.07 |

North-side / broader Buckhead candidate filter:

- `NPU IN ('A','B')` returns 27 official neighborhoods, including Paces, Chastain Park, Tuxedo Park, Garden Hills, Peachtree Hills, Lenox, Buckhead Village, Buckhead Forest, North Buckhead, and Buckhead Heights.
- Bbox, WGS84: `[-84.4608655, 33.8122430, -84.3477355, 33.8869475]`.

Required product decision before Lane A backfill:

1. **Narrow Buckhead**: use official neighborhoods with `UPPER(NAME) LIKE '%BUCKHEAD%'`. This is precise but likely under-covers common Buckhead usage.
2. **Broad Buckhead**: use NPU A+B or a curated official-neighborhood list. This better matches north-side Buckhead market language but requires a named list committed in the directory.

Implementation rule: **Atlanta city = Class B candidate, Buckhead = sub-neighborhood spatial filter**. The parcel cohort must be:

```text
Fulton tax parcels
  AND Atlanta city boundary
  AND approved Buckhead neighborhood geometry set
```

Then backfill `zoning_code` from Atlanta `ZoningHosted` polygons. Because Atlanta spans Fulton and DeKalb counties, keep the Fulton parcel source as the county limiter; do not accidentally include DeKalb Atlanta parcels in a Fulton GA proof.

This is analogous to the Maricopa AZ Scottsdale caution: a naive city or postal field is not sufficient. Fulton is stricter because the parcel source has no city field at all.

## Lane A Execution Shape

Recommended staged plan:

1. Treat existing Fulton registration as parcels-loaded but stale coverage. Refresh only after a preview backfill plan is ready.
2. Use Fulton County Tax Parcels as canonical parcel source:
   - `parcel_id`: normalize from `ParcelID` preserving spaces exactly in raw attributes; create comparison-normalized form for joins.
   - address: `Address` plus component fields.
   - source provenance: Fulton County GIS Tax Parcels FeatureServer URL + pull timestamp.
   - source CRS: EPSG:2240 / Georgia West StatePlane.
3. Do **not** classify as Class C. Parcel `TaxDist`, `LUCode`, `ClassCode`, and `NbrHood` are not zoning district codes.
4. Build Sandy Springs proof first:
   - Use Sandy Springs city limit layer 107 to prefilter Fulton parcels.
   - Use Sandy Springs zoning layer 127 for `ZoningDistrict`.
   - Attempt direct normalized `ParcelID` join first; use spatial `ST_Within` as fallback/QA.
   - Author `backend/data/fulton_ga_zoning_directory.json` entry for Sandy Springs Municode Development Code and allowed-use table.
5. Build Buckhead proof second:
   - Use Atlanta zoning layer `ZoningHosted/FeatureServer/0`, `ZONECLASS`.
   - Use Atlanta city boundary plus approved official-neighborhood geometry set.
   - Require product signoff on narrow Buckhead vs broad Buckhead before counting coverage.
   - Author directory entries under authority `City of Atlanta`, subarea `Buckhead`, not a separate municipality.
6. Run strengthened Class A gates in preview before any production write:
   - district bbox covers >=50% of target prefiltered parcel bbox.
   - 1,000-parcel `ST_Within` dry-run >=50% match for Sandy Springs and for the approved Buckhead cohort.
   - raw attributes nonempty for all district rows.
7. Leave Fulton unincorporated zoning out of the target proof. It can be added later for countywide coverage but does not unlock the named wealth pockets.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Fulton source config / parcel field verification | 3-5h |
| Sandy Springs city-boundary prefilter + zoning join dry-run | 5-8h |
| Sandy Springs matrix/directory from Municode allowed-use table | 6-10h |
| Buckhead neighborhood-filter decision + geometry extraction | 3-6h |
| Atlanta zoning ingest + Buckhead spatial backfill dry-run | 6-10h |
| Atlanta/Buckhead matrix from Part 16 zone chapters and overlays | 8-16h |
| Two-center proof total | 3-5 days |
| Broader Fulton operational expansion | 1-2+ weeks minimum |

## Risk Register

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| No embedded parcel zoning | High | Fulton parcels have no zoning district field. | Treat as Class A/B; always use separate zoning layers. |
| No parcel city field | High | Parcel rows do not expose a clean municipality join key. | Build cohorts by city/neighborhood spatial filters. |
| Buckhead is not a municipality | High | Product target is a neighborhood/market area inside Atlanta, not a city. | Store authority as Atlanta and require a Buckhead geometry filter. |
| Buckhead definition ambiguity | High | Name-filter gives 4 neighborhoods; NPU A+B gives 27. | Require explicit narrow/broad selection before coverage claims. |
| Atlanta overlay complexity | Medium/High | `ZONECLASS` includes compound codes like `HC-20A SA5`; descriptions are blank in sampled rows. | Preserve raw code and normalize primary district + overlay tokens separately. |
| Sandy Springs parcel-like zoning layer | Medium | Layer has 27,711 rows and parcel IDs, likely more parcel-like than district-generalized. | Use it because it carries authoritative zone per parcel; dedupe by zone geometry/code during ingest if district count inflates. |
| Stale Fulton open-data URL | Medium | Older Fulton zoning MapServer URL returned service-not-found; current FeatureServer mirror works. | Use current `services1.arcgis.com` FeatureServer for adapters and document stale URL as noncanonical. |
| County-level audit mismatch | Medium | Sandy Springs + Buckhead will not clear full county operational coverage alone. | Scope as two-center proof; plan broader municipal expansion separately. |
| Coordinate systems | Medium | Fulton/Sandy use EPSG:2240; Atlanta zoning uses EPSG:6447; neighborhood layer uses Web Mercator. | Reproject to WGS84/PostGIS geometry during ingest; preserve source SRID. |
| API pagination | Medium | Fulton parcel max record count is 1,000. | Use objectId batching / existing ArcGIS pagination. |

## Recommendation

Fulton GA is viable for a Lane A proof, but should be dispatched with explicit target boundaries:

- **Sandy Springs**: straightforward city-level proof using Sandy Springs zoning + city limit.
- **Buckhead**: Atlanta zoning proof with a separately approved Buckhead official-neighborhood geometry set.

Do not route Fulton as a countywide zoning sprint first. The practical first ticket is:

```text
Fulton parcels + Sandy Springs city proof + Buckhead/Atlanta neighborhood-filtered proof
```

That unlocks the two named Phase 5 wealth-pocket centers without pretending that Buckhead is a municipality or that Fulton County zoning solves incorporated-city zoning.
