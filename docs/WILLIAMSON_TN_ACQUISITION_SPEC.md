# Williamson TN Acquisition Spec

Date: 2026-06-23

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Williamson County, TN, with emphasis on the 58-list wealth pockets Brentwood and Franklin.

## Bottom Line

| Field | Verdict |
|---|---|
| 58-list polygon targets | **Brentwood** and **Franklin** per `docs/TARGET_MARKETS.md` Phase 5. |
| Canonical parcel source | **Williamson County hosted Parcels FeatureServer** |
| Parcel source URL | `https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/Parcels/FeatureServer/0` |
| Parcel source class | **SINGLE-COUNTY-PORTAL** |
| Tennessee statewide parcel source | **Not viable for Williamson**. Tennessee Property Boundaries Public Use explicitly excludes Williamson because Williamson runs its own CAMA system. |
| Class C embedded parcel zoning | **NO**. County parcel rows have parcel, address, owner, value, and coded `CITY` fields but no zoning-like district field. |
| Separate zoning source | **YES, per-municipality**. Brentwood and Franklin both publish queryable zoning polygon layers with local zoning-code fields. |
| County zoning source | **Support only**. Williamson County `Zones` appears to be county/unincorporated zoning; distinct values include rural/hamlet/village codes and no Brentwood/Franklin labels. |
| Recommended fire path | **County parcels first, then per-muni zoning for Brentwood + Franklin**. Do not wait for statewide TN parcels. |
| Expected operational lift | **1-2 polygons** after preview `ST_Within` verification and directory/matrix work. |
| HALT criteria | Halt if county parcel paging fails, if municipal zoning endpoints stop returning public JSON, or if preview spatial join gives <50% target-city parcel match for both Brentwood and Franklin. |

## Current Prod State

`docs/TARGET_MARKETS.md` lists Williamson, TN in Phase 5 with Brentwood and Franklin as centers and status `not_loaded / 0%`.

No ingestion or production writes were performed in this research pass.

## Source Classification Framework

Using `docs/INGESTION_PIPELINE_PLAN.md`:

- Williamson is **not Class C** because neither the Tennessee statewide source nor Williamson County parcels provide an embedded parcel zoning code for this county.
- Williamson is closest to **Class B/D hybrid**:
  - County parcel source is directly queryable and complete enough for parcels.
  - Zoning must be acquired from separate county/municipal zoning polygon services.
  - Target-city proof is per-municipality, not a single statewide zoning backfill.

## Tennessee Statewide Parcel Probe

Candidate checked:

- Tennessee Property Boundaries Public Use item: `https://www.arcgis.com/home/item.html?id=e356f1a241844d6f9025f2fa4e977df3`
- FeatureServer: `https://services1.arcgis.com/YuVBSS7Y1of2Qud1/arcgis/rest/services/Tennessee_Property_Boundaries_Public_Use/FeatureServer`
- State property data page: `https://geodata.tn.gov/pages/property-data~06d5f39ba142402a8daaeec4cc48ae4b`
- Comptroller parcel data page: `https://comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html`

State item metadata says the hosted layer contains real property information for 86 counties and that Chester, Davidson, Hamilton, Hickman, Knox, Montgomery, Rutherford, Shelby, and **Williamson** are not included.

Verdict: **not a Williamson fire path**. This is a useful Tennessee source generally, but Williamson must use county/municipal sources.

Anti-bot status: public ArcGIS item JSON returned without login or token.

## Canonical Parcel Source

Primary source: Williamson County hosted ArcGIS Parcels layer.

- County maps page: `https://www.williamsoncounty-tn.gov/1381/Maps`
- County web map app: `https://www.arcgis.com/apps/webappviewer/index.html?id=70ae32b7255e48cdad65792ffb2bbf2a`
- Web map item behind app: `https://williamsontn.maps.arcgis.com/sharing/rest/content/items/e87f5b25ec5c48619a72347f3d25735f/data?f=json`
- Live parcel layer: `https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/Parcels/FeatureServer/0`

The county maps page describes online maps for zoning districts and parcel-level planning information. The public Web AppBuilder config exposes the parcel layer in search sources for address, owner, and parcel ID.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Max record count | 2,000 |
| Total parcel count | 107,201 |
| Full layer bbox | `xmin=-9709037.2185`, `ymin=4258392.6228`, `xmax=-9640047.3791`, `ymax=4308340.2230` |

Observed parcel fields include:

`PIN`, `PARCEL_ID`, `COUNTY`, `CITY`, `ADDRESS`, `OWNER_1`, `OWNER_2`, owner address fields, deed fields, assessed/market value fields, acreage fields, and geometry fields.

Sample 50 parcel-quality probe:

| Check | Result |
|---|---:|
| Rows returned | 50 |
| Zoning-like fields present | 0 |
| Non-null zoning-code sample rate | 0% |
| `CITY` field form | coded values such as `000`, `086`, `263967`, `263264`, `701` |

Sample parcel rows:

| PIN / parcel ID | City code | Address |
|---|---|---|
| `007P A 00600 00007007I` | `000` | `1190 GRAFTON DR` |
| `007P A 00700 00007007I` | `000` | `1194 GRAFTON DR` |
| `007P A 00800 00007007P` | `000` | `1198 GRAFTON DR` |
| `007    00200 00007007` | `000` | `6460 EDINBURGH DR` |
| `007P A 00900 00007007I` | `000` | `1110 STONEBRIDGE PARK DR` |

City-code distribution confirms `CITY` is not a ready human-readable municipality field:

| CITY value | Count |
|---|---:|
| `000` | 28,610 |
| `263967` | 18,214 |
| `086` | 17,551 |
| `263264` | 13,695 |
| `701` | 12,637 |
| `535` | 6,424 |
| `255` | 5,163 |
| `718` | 4,432 |

Class C gate result: **FAIL**. There is no parcel-level zoning district field. Use parcel geometry plus municipal boundary/spatial filtering, not raw `CITY` string matching, for Brentwood and Franklin proof.

Anti-bot status: public FeatureServer query returned JSON without login, token, browser cookies, or captcha.

## Boundary Sources

Williamson County publishes both incorporated areas and urban growth boundaries:

- Incorporated areas: `https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/CountyMap_gdb/FeatureServer/2`
- 2025 Urban Growth Boundaries: `https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/2025_Urban_Growth_Boundaries/FeatureServer/0`

Live boundary checks:

| Source | Brentwood | Franklin | Notes |
|---|---:|---:|---|
| Incorporated areas | present | present | Query returns `NAME='BRENTWOOD'` and multiple `NAME='FRANKLIN'` polygons. |
| 2025 UGB | present | present | Query returns `Brentwood UGB` and `Franklin UGB`. |

Implementation note: use incorporated-area geometry to partition target-city parcels. UGB polygons are useful for planning-edge QA, but should not replace incorporated municipal boundaries when backfilling city zoning.

## Williamson County Zoning

Public pages:

- County maps page: `https://www.williamsoncounty-tn.gov/1381/Maps`
- Official zoning map page: `https://www.williamsoncounty-tn.gov/1387/Official-Zoning-Map`
- County web map item: `https://williamsontn.maps.arcgis.com/sharing/rest/content/items/e87f5b25ec5c48619a72347f3d25735f/data?f=json`
- Current county zones layer: `https://services8.arcgis.com/hkhKI6Qq7rjvBjZU/arcgis/rest/services/CountyMap_gdb/FeatureServer/15`
- Archived/reference county zones: `CountyMap_gdb/FeatureServer/21` (`Zones 2013`) and `CountyMap_gdb/FeatureServer/20` (`Zones 1988`)

The official zoning map page states the web zoning map is for reference and does not replace the official regulations maintained by the Williamson County Planning Department.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Zones` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 333 |
| Named zoning-code field | `ZONES` |
| Label field | `LABEL` |
| Sample rows | 50 |
| Non-null `ZONES` sample rate | 50/50, **100%** |

Sample county zoning rows:

| ZONES | LABEL |
|---|---|
| `College Grove Village` | `College Grove Village` |
| `GVC 1` | `GVC 1` |
| `GVC 2` | `GVC 2` |
| `GVC 3` | `GVC 3` |
| `GVC 4` | `GVC 4` |
| `H - Hamlet` | `H` |
| `Leiper's Fork Village` | `Leiper's Fork Village` |
| `RD- 1 - Rural Development - 1` | `RD- 1` |
| `RP- 1 - Rural Preservation - 1` | `RP- 1` |
| `SIC - Suburban Infill and Conservation` | `SIC` |

Target-city relevance check:

- Query for `Brentwood` or `Franklin` in `ZONES`/`LABEL`: **0 rows**.
- Distinct values are county/rural/village-style zones, not Brentwood or Franklin municipal zoning.

Verdict: **county zoning is not sufficient for the 58-list centers**. Keep it as an unincorporated edge source and as a boundary QA companion. Do not use it to classify parcels inside Brentwood or Franklin.

Anti-bot status: public FeatureServer query returned JSON without login, token, browser cookies, or captcha.

## Brentwood Zoning

Public sources:

- City GIS page: `https://www.brentwoodtn.gov/Departments/Information-Technology/GIS`
- City planning maps page: `https://www.brentwoodtn.gov/Departments/Planning-and-Codes/Planning-Section/Maps`
- ArcGIS web map item: `https://www.arcgis.com/home/item.html?id=f3d7154232ae4fd7b2f3ee89c64e3c1f`
- Web map data endpoint: `https://www.arcgis.com/sharing/rest/content/items/f3d7154232ae4fd7b2f3ee89c64e3c1f/data?f=json`
- Brentwood parcels layer: `https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/LandRecords/MapServer/2`
- Brentwood zoning layer: `https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/9`
- Brentwood city-limit layer: `https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/2`
- Brentwood UGB layer: `https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/3`

The Brentwood planning maps page states that the zoning map is maintained by GIS and links to the City of Brentwood Zoning Map.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Tennessee State Plane, `wkid=102736`, `latestWkid=2274` |
| Count | 1,046 |
| Named zoning-code field | `Zoning` |
| Ordinance field | `Ord_Number` |
| Sample rows | 50 |
| Non-null `Zoning` sample rate | 50/50, **100%** |

Sample zoning rows:

| Zoning | Ordinance | Rule ID |
|---|---|---:|
| `AR` | blank | 1 |
| `AR` | blank | 1 |
| `AR` | blank | 1 |
| `AR` | blank | 1 |
| `AR` | blank | 1 |

Observed renderer/domain labels include:

`AR - Agricultural/Res. Estate`, `R1 - Large Lot Residential`, `R2 - Suburban Residential`, `OSRD - Open Space Residential`, `C1 - Commercial Office`, `C2 - Commercial Retail`, `C3 - Commercial Service/Warehouse`, `C4 - Town Center`, and `SI*` service-institution classes.

Brentwood parcel layer probe:

| Check | Result |
|---|---:|
| Brentwood city parcel count | 17,533 |
| Zoning-like parcel fields present in sample | 0 |
| Parcel sample zoning-code rate | 0% |

Sample Brentwood parcel rows:

| Parcel ID | City code | Address |
|---|---|---|
| `030H G 02700 00015030B` | `086` | `BATHWICK DR` |
| `030F B 00600 00016030F` | `086` | `7052 N LAKE DR` |
| `030A A 00700 00015030A` | `086` | `9400 DOVE FIELD CT` |
| `011L B 01900 00015011L` | `086` | `6532 CLOVERBROOK DR` |
| `012M A 06100 00015012L` | `086` | `504 POINTER PL` |

Brentwood verdict: **strong Class B municipal zoning source and Class A preview candidate**. Zoning is polygonal, queryable, and code-like. Use `Zoning` as the raw zone code. Use city-limit geometry, not county `CITY` strings alone, for target parcel partitioning.

Anti-bot status: public ArcGIS REST returned JSON without login or token.

## Franklin Zoning

Public sources:

- City GIS page: `https://www.franklintn.gov/government/departments-a-j/information-technology/geographical-information-systems-gis`
- ArcGIS web map item: `https://www.arcgis.com/home/item.html?id=bc05de053f9348ee90c3b0225df6746c`
- Web map data endpoint: `https://www.arcgis.com/sharing/rest/content/items/bc05de053f9348ee90c3b0225df6746c/data?f=json`
- Franklin public services root: `https://publicmaps.franklintn.gov/arcgis/rest/services`
- Franklin zoning layer: `https://publicmaps.franklintn.gov/arcgis/rest/services/Maps/ZoningWebMercator/MapServer/9`
- Web-map host variant, slower from this environment: `https://eoc.franklin-gov.com/arcgis/rest/services/Maps/ZoningWebMercator/MapServer/9`

The City GIS page says Franklin provides GIS data to the public, including shapefiles, DWG, PDFs, and static maps. The ArcGIS web map identifies `Zoning Districts` as `Maps/ZoningWebMercator/MapServer/9`.

Live zoning probe against `publicmaps.franklintn.gov`:

| Check | Result |
|---|---:|
| Layer name | `Zoning Districts` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 24,168 |
| Max record count | 100,000 |
| Named zoning-code field | `ZONECLASS` |
| Description field | `ZONEDESC` |
| Ordinance/source link field | `WEBLINK` |
| Sample rows | 50 |
| Non-null `ZONECLASS` sample rate | 50/50, **100%** |

Sample zoning rows:

| ZONECLASS | ZONEDESC | WEBLINK |
|---|---|---|
| `AG` | Agriculture | Franklin Zoning Ordinance flippingbook |
| `AG` | Agriculture | Franklin Zoning Ordinance flippingbook |
| `AG` | Agriculture | Franklin Zoning Ordinance flippingbook |
| `AG` | Agriculture | Franklin Zoning Ordinance flippingbook |
| `ER` | ER Estate Residential | Franklin Zoning Ordinance flippingbook |
| `ER` | ER Estate Residential | Franklin Zoning Ordinance flippingbook |

Distinct sample of zone classes/counts:

| Zone class | Description | Count |
|---|---|---:|
| `AG` | Agriculture | 31 |
| `ER` | ER Estate Residential | 124 |
| `CC` | Central Commercial District | 185 |
| `CI` | Civic and Institutional District | 198 |
| `DD` | Downtown District | 112 |
| `GO` | General Office District | 54 |
| `LI` | Light Industrial District | 337 |
| `PD` | Planned District | 14,831 |

Host reliability note:

- `publicmaps.franklintn.gov` returned count, metadata, and sample queries quickly.
- `eoc.franklin-gov.com`, which appears in the web map item, timed out or returned no parseable JSON from this environment for equivalent direct layer requests.

Franklin verdict: **strong Class B municipal zoning source and Class A preview candidate** using `publicmaps.franklintn.gov`. Use `ZONECLASS` as the raw zone code and preserve `ZONEDESC`, `DEFINITION`, and `WEBLINK` for directory/matrix authoring.

Anti-bot status: publicmaps REST returned JSON without login, token, browser cookies, or captcha. Avoid the slower `eoc.franklin-gov.com` host in automated pulls unless retested.

## Target Parcel Coverage Strategy

Do not rely on Tennessee statewide parcels or human-readable parcel city strings for Williamson.

Recommended target-city parcel partition:

1. Ingest Williamson County parcels from `Parcels/FeatureServer/0`.
2. Ingest county incorporated-area polygons from `CountyMap_gdb/FeatureServer/2`.
3. Use incorporated-area polygons for Brentwood and Franklin to select target-city parcels.
4. Use UGB polygons only as QA/planning context.
5. Ingest municipal zoning:
   - Brentwood: `AdministrativeAreas/MapServer/9`, field `Zoning`.
   - Franklin: `ZoningWebMercator/MapServer/9`, field `ZONECLASS`.
6. Run preview `ST_Within` centroid backfill for parcels inside each city boundary.

Expected target scale from live probes:

| Target | Direct local parcel signal | Zoning polygons |
|---|---:|---:|
| Brentwood | 17,533 parcels in Brentwood city parcel layer | 1,046 |
| Franklin | county parcel source plus city boundary required | 24,168 |

The county parcel source has enough rows for both targets, but Franklin's direct parcel service was not mirrored at the quick publicmaps path tested. That is not a blocker because the canonical county parcels plus county incorporated-area boundary can supply the Franklin parcel base.

## Lane A Execution Shape

Recommended staged plan:

1. Register Williamson County in preview only.
2. Ingest county parcels from Williamson County `Parcels/FeatureServer/0`.
3. Normalize parcel identity:
   - `parcel_id`: `PIN` or `PARCEL_ID`
   - alternate IDs: preserve both `PIN` and `PARCEL_ID`
   - address: `ADDRESS`
   - coded municipality: preserve raw `CITY`, but do not treat it as human-readable
   - source provenance: Williamson County hosted FeatureServer URL + pull timestamp
4. Ingest county incorporated areas from `CountyMap_gdb/FeatureServer/2`.
5. Filter target parcels spatially to Brentwood and Franklin incorporated boundaries.
6. Ingest zoning districts in preview:
   - Brentwood zoning: `https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/9`, raw code field `Zoning`
   - Franklin zoning: `https://publicmaps.franklintn.gov/arcgis/rest/services/Maps/ZoningWebMercator/MapServer/9`, raw code field `ZONECLASS`
7. Run strengthened Class A gates before production backfill:
   - district bbox covers >=50% of target-city parcel bbox
   - 1,000-parcel `ST_Within` dry-run >=50% match for each target city
8. Backfill parcel `zoning_code` from municipal zoning polygons only after preview gates pass.
9. Author `backend/data/williamson_tn_zoning_directory.json` for Brentwood + Franklin proof only.
10. Keep county `Zones` as unincorporated support, not as Brentwood/Franklin source of record.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| County parcel adapter/source config | 4-8h |
| County boundary source config and target-city spatial filter | 3-5h |
| Brentwood zoning ingest + preview backfill | 4-6h |
| Franklin zoning ingest + preview backfill | 4-6h |
| Strengthened Class A dry-run and QA | 2-4h |
| Brentwood directory/matrix from city zoning/code | 4-8h |
| Franklin directory/matrix from zoning ordinance links | 6-10h |
| Two-city proof total | 3-5 days |
| Full county operational expansion | 1-2+ weeks, because municipal zoning sources beyond Brentwood/Franklin would need separate discovery. |

## Expected Operational Lift

Williamson parcel load alone creates roughly 107k parcels but no zoning code. It will not clear audit gates.

Brentwood + Franklin are viable first proof targets. If the preview `ST_Within` gate passes for both, expected immediate lift is **1-2 Phase 5 polygons**:

- Brentwood: likely first because both city parcels and city zoning are directly queryable on the same Brentwood ArcGIS host.
- Franklin: likely viable, but use `publicmaps.franklintn.gov` rather than the slower `eoc.franklin-gov.com` host for automation.

If audit remains county-level only, two municipalities may still leave Williamson partial until broader municipal coverage is added. If the product can recognize city-level operational polygons, Brentwood and Franklin can be counted as a meaningful 58-list proof.

## Risk Register

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| Tennessee statewide excludes Williamson | High | The state parcel layer excludes Williamson, so a statewide TN adapter will not load this county. | Use Williamson County hosted parcels. |
| No embedded parcel zoning | High | County and Brentwood parcel samples have no zoning-like field. | Treat as separate zoning polygon ingestion, not Class C. |
| Parcel `CITY` is coded | Medium | County sample values are codes such as `000` and `086`. | Use incorporated boundary spatial filters; preserve raw codes only as source attributes. |
| County zoning is unincorporated-style | Medium | County `Zones` distinct values do not include Brentwood/Franklin municipal zones. | Use county zoning only for unincorporated QA or later expansion. |
| Franklin host split | Medium | Web map references `eoc.franklin-gov.com`, which timed out from this environment; `publicmaps.franklintn.gov` works. | Use publicmaps endpoint and retest before automation. |
| Franklin `PD` broad code | Medium | Many Franklin polygons have `ZONECLASS='PD'`; district specifics may live in `ZONEDESC`, `DEFINITION`, or ordinance records. | Preserve full raw attributes and decide matrix granularity during directory authoring. |
| Municipal boundary duplicates | Low/Medium | County incorporated-area query returns multiple Franklin polygons. | Union city-boundary geometries by `NAME` before spatial filtering. |
| CRS differences | Low/Medium | County and Franklin sources use Web Mercator; Brentwood uses Tennessee State Plane. | Reproject during staging; preserve source SRID in provenance. |

## HALT Criteria

Halt and report instead of ingesting if any of the following occurs:

1. Williamson County parcel FeatureServer stops allowing public paged queries or object-ID batching.
2. Brentwood `AdministrativeAreas/MapServer/9` or Franklin `publicmaps` `ZoningWebMercator/MapServer/9` stops returning public JSON.
3. Brentwood or Franklin zoning-code sample quality drops below 70% non-null in a fresh 50-row probe.
4. Incorporated-area boundary source cannot be unioned into usable Brentwood/Franklin polygons.
5. Preview spatial join matches <50% of target-city parcel centroids for both Brentwood and Franklin.
6. Directory/matrix authoring cannot distinguish Franklin `PD` districts well enough to satisfy audit truthfulness gates.

## Recommendation

Dispatch Williamson TN as a **per-municipality proof sprint**, not a statewide Tennessee adapter sprint.

The best Lane A ticket is:

- County parcels from Williamson County hosted `Parcels/FeatureServer/0`.
- Incorporated city-boundary partition for Brentwood and Franklin.
- Brentwood zoning from city `Zoning` field.
- Franklin zoning from city `ZONECLASS` field on the `publicmaps` host.

Expected outcome is **1-2 operational Phase 5 polygons** after preview gates, with Brentwood slightly lower risk than Franklin.
