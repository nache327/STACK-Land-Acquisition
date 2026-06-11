# Contra Costa CA Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Contra Costa County, CA, with emphasis on the 57-list wealth pockets Lafayette and Walnut Creek.

## Bottom Line

- Canonical parcel source: **Contra Costa County CCMAP Assessment Parcels**, `https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0`
- Parcel source class: **SINGLE-COUNTY-PORTAL**
- Zoning source class: **Class A/B hybrid, PARTIAL verified**
  - Class C parcel-embedded zoning: **NO**. County parcel fields do not carry zoning.
  - Class A primitive: **PARTIAL**. California Statewide Zoning North covers Contra Costa, Lafayette, and Walnut Creek with local `Code` values and passes bbox coverage, but the required 1,000-parcel `ST_Within` dry-run cannot run until parcels are staged because Contra Costa is not loaded in prod.
  - Class B support: **YES** for Walnut Creek; **PARTIAL** for Lafayette.
- Verified via Lane A strengthened gates: **PARTIAL**
- Effort estimate for Lane A ingest:
  - Parcel adapter only: **6-10h**
  - Parcel + CA statewide zoning preview/backfill validation: **1.5-2.5 days**
  - Operational two-city proof with Lafayette + Walnut Creek directory: **3-5 days**
  - Full county operational coverage: **1-2+ weeks**, because matrix/directory coverage must span many city-level zoning systems if zoning is populated countywide.
- Expected operational outcome: **proof-then-scale**, not guaranteed first-sprint full county operational.
- 57-list wealth pockets covered by canonical parcel source: **YES**. County parcel layer has 11,088 Lafayette parcels and 34,949 Walnut Creek parcels.
- Recommended dispatch: **YES, but scope Lane A as a preview-gated proof**. Do not promise county operational readiness until the statewide-zoning `ST_Within` gate and matrix coverage strategy are resolved.

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `Contra Costa` match.
- `/api/admin/coverage`: no `Contra Costa` row.

Contra Costa remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Contra Costa County's official property page says the Assessor's Parcel shapefile and other data are updated monthly and free to download, and points users to the county GIS download site:

- County maps/property page: `https://www.contracosta.ca.gov/552/Maps-Property-Information`
- County GIS page: `https://www.contracosta.ca.gov/1818/GIS`
- CCMAP parcel app root: `https://gis.cccounty.us/`
- Live parcel REST layer: `https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Assessment Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Max record count | 2,000 |
| Total parcel count | 387,835 |
| Full parcel bbox, WGS84 | `[-122.438957, 37.711766, -121.532927, 38.101578]` |

Observed parcel fields:

`OBJECTID`, `APN`, `APN_CHECK`, `TRA`, address components, `USE_CODE`, `Description`, `ACREAGE`, assessed-value fields, `parcel_dashes`, `s_city`, `assr_url`, geometry fields.

Class C gate result: **FAIL**. There is no parcel-level `zoning`, `zone`, `zn`, or district-code field. `USE_CODE` / `Description` are assessor land-use values, not zoning district codes.

## Parcel Row Samples

Lafayette live query:

- Query: `UPPER(s_city)='LAFAYETTE'`
- Count: 11,088

Sample rows:

| APN | Dashed APN | City | Address | Use code | Description |
|---|---|---|---|---:|---|
| `249100012` | `249-100-012` | `LAFAYETTE` | `CAMELLIA LN - LAFAYETTE` | 17 | Vacant, 1 site |
| `249100011` | `249-100-011` | `LAFAYETTE` | `131 CAMELLIA LN - LAFAYETTE` | 11 | Single Family, 1 residence |
| `249090003` | `249-090-003` | `LAFAYETTE` | `CAMELLIA LN - LAFAYETTE` | 18 | Vacant, 2 or more sites |
| `249110011` | `249-110-011` | `LAFAYETTE` | `23 CAMELLIA LN - LAFAYETTE` | 62 | Rural, 1 acre up to 10 acres |
| `249110005` | `249-110-005` | `LAFAYETTE` | `110 CAMELLIA LN - LAFAYETTE` | 11 | Single Family, 1 residence |

Walnut Creek live query:

- Query: `UPPER(s_city)='WALNUT CREEK'`
- Count: 34,949

Sample rows:

| APN | Dashed APN | City | Address | Use code | Description |
|---|---|---|---|---:|---|
| `185190006` | `185-190-006` | `WALNUT CREEK` | `OLYMPIC BLVD - WALNUT CREEK` | 79 | Government-owned |
| `190030075` | `190-030-075` | `WALNUT CREEK` | `NO ADDRESS - WALNUT CREEK` | 87 | Common Area parcels in PUDs |
| `190110062` | `190-110-062` | `WALNUT CREEK` | `2925 PTARMIGAN DR - WALNUT CREEK` | 29 | Condominiums and Cooperatives |
| `190110063` | `190-110-063` | `WALNUT CREEK` | `2941 PTARMIGAN DR - WALNUT CREEK` | 29 | Condominiums and Cooperatives |
| `190110064` | `190-110-064` | `WALNUT CREEK` | `2941 PTARMIGAN DR - WALNUT CREEK` | 29 | Condominiums and Cooperatives |

Conclusion: Lafayette and Walnut Creek parcels are in the county source. They are not city-only parcel patchworks.

## County Zoning Layer

Contra Costa publishes a zoning FeatureServer:

- Service: `https://ccmap.cccounty.us/arcgis/rest/services/_Authoritative/Zoning/FeatureServer`
- Layer: `PLA_DCD_Zoning`, id `39`
- Layer URL: `https://ccmap.cccounty.us/arcgis/rest/services/_Authoritative/Zoning/FeatureServer/39`

Service metadata states this layer shows zoning for **unincorporated areas of Contra Costa County**. The county property/zoning page also says CCMAP zoning and general plan information is available for unincorporated County areas only.

Live REST probe:

| Check | Result |
|---|---:|
| Count | 1,259 |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| County zoning bbox, WGS84 | `[-122.441208, 37.718513, -121.534354, 38.104493]` |

Fields include `ZONING`, `OVERLAY`, `ZONE_OVER`, `Zoning_Text`, `Overlay_Text`, `Zoning_Standard`, and `URL`.

Sample zoning rows:

| Zoning | Overlay | Zone over | Text | URL |
|---|---|---|---|---|
| `A-2` | `-BS` | `A-2, -BS` | General Agricultural | Municode Title 8 link |
| `A-2` | `-BS -SG` | `A-2, -BS -SG` | General Agricultural | Municode Title 8 link |
| `A-2` | `-FH` | `A-2, -FH` | General Agricultural | Municode Title 8 link |

Class A result for county layer: **not sufficient for the 57-list cities**. It is useful for unincorporated Contra Costa, but Lafayette and Walnut Creek require city zoning.

## California Statewide Zoning North

The stronger Class A candidate is California Statewide Zoning North:

- FeatureServer: `https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_North/FeatureServer`
- Layer: `CaliforniaZoning10_17_24_north`, id `1`
- Layer URL: `https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_North/FeatureServer/1`

Service metadata says zoning data was collected from 535 of California's 539 jurisdictions. The layer fields include `County`, `Jurisdiction`, `Code`, `Description`, `Classkey`, `Source`, `Date`, `Version`, and standardized class fields.

Live Contra Costa probe:

| Check | Result |
|---|---:|
| `County='CCO'` count | 9,934 |
| Distinct CCO jurisdictions returned | Antioch, Brentwood, CCO, Clayton, Concord, Danville, El Cerrito, Hercules, Lafayette, Martinez, Moraga, Oakley, Orinda, Pinole, Pittsburg, Pleasant Hill, Richmond, San Pablo, San Ramon, Walnut Creek |
| CCO zoning bbox, WGS84 | `[-122.441208, 37.718513, -121.534354, 38.100936]` |
| County parcel bbox, WGS84 | `[-122.438957, 37.711766, -121.532927, 38.101578]` |
| Bbox coverage primitive | Passes; zoning bbox covers effectively the county parcel bbox width and >98% of its height. |

Target-city probe:

| Jurisdiction | Count | Sample codes | Source/date |
|---|---:|---|---|
| Lafayette | 401 | `A-2`, `APO`, `C` | `Direct`, `2021 q4` |
| Walnut Creek | 929 | `AS` | `REST`, `2022 q1` |

Target-city bbox check:

| Layer set | Bbox WGS84 |
|---|---|
| Lafayette + Walnut Creek parcels | `[-122.167502, 37.833795, -121.937380, 37.961406]` |
| Lafayette + Walnut Creek statewide zoning | `[-122.165216, 37.842502, -121.980620, 37.946326]` |

The target-city statewide zoning bbox covers roughly 65% of the target-city parcel bbox by simple rectangular overlap, above the 50% bbox primitive.

Class A result for statewide layer: **PARTIAL**. The bbox gate passes and local code-like values exist, but Contra Costa has no production parcels, so the required 1,000-parcel `ST_Within` dry-run must happen in a preview/staging ingest before any production backfill.

## Walnut Creek City Zoning

Walnut Creek has the best city-level source.

Public pages:

- Zoning page: `https://www.walnutcreekca.gov/government/community-development-department/zoning`
- Zoning web map page: `https://www.walnutcreekca.gov/government/community-development-department/zoning/maps/zoning-web-map`
- Web app item: `https://walnutcreek.maps.arcgis.com/apps/webappviewer/index.html?id=8b9686d49d8543198932925a819f9699`
- Web map item behind app: `eb81b56e98094292acc4706d2506f249`
- Municipal code: `https://ecode360.com/WA4684`

The Walnut Creek web page says the map can be used to look up zoning for a property, and that the zoning field tells the zoning district code. It also says the ordinance link field includes a link to the municipal code that applies to the property.

Live ArcGIS layers behind the Walnut Creek web map:

- Zoning parcel layer: `https://services2.arcgis.com/AhHMUmDoudKVXiUl/arcgis/rest/services/ZoningDistrict/FeatureServer/0`
- Zoning district layer: `https://services2.arcgis.com/AhHMUmDoudKVXiUl/arcgis/rest/services/Zoning_Districts/FeatureServer/0`
- Supplemental planning layer set: `https://services2.arcgis.com/AhHMUmDoudKVXiUl/arcgis/rest/services/Zoning_Web_Map_WFL1/FeatureServer`

Walnut Creek `ZoningDistrict/FeatureServer/0` fields include `ZONECLASS`, `ZONEDESC`, `Within`, `SP`, `SP_full`, `SP_title`, `URL`, `APN`, `Address`, and `Add_City`.

Sample parcel-zoning rows:

| APN | Zone class | Zone description | Within | Address |
|---|---|---|---|---|
| `134243029` | `R85` | Single Family Residential District 8,500 | Walnut Creek | 20 PRIMROSE CT |
| `134243004` | `R85` | Single Family Residential District 8,500 | Walnut Creek | 631 WINTERGREEN LN |
| `134243005` | `R85` | Single Family Residential District 8,500 | Walnut Creek | 641 WINTERGREEN LN |
| `134243026` | `R85` | Single Family Residential District 8,500 | Walnut Creek | 3260 PRIMROSE LN |
| `138320002` | `UNINC` / `HPD` | blank | Outside / Planning Area | blank |

Walnut Creek `Zoning_Districts/FeatureServer/0` sample district rows:

| Zone class | Label | Description | URL |
|---|---|---|---|
| `R20` | `R-20` | Single Family Residential District 20,000 | blank |
| `AS-CM` | `AS-CM` | Auto Sales & Custom Manufacturing | CodePublishing/eCode legacy URL |
| `PD` | `PD 1609` | Planned Development 1609 | PDF ordinance link |
| `PD` | `PD 1612` | Planned Development 1612 | PDF ordinance link |

Walnut Creek acquisition verdict: **sprintable Class B support and Class A candidate**. The city provides parcel-zoning rows with APNs and zoning codes. Lane A can either join county parcel APNs to the city zoning-parcel APNs or use city zoning polygons/spatial backfill after preview.

## Lafayette City Zoning

Lafayette has public zoning materials but a weaker machine-readable source.

Public pages:

- Map room: `https://www.lovelafayette.org/city-hall/maps`
- Zoning regulations and handouts: `https://www.lovelafayette.org/city-hall/city-departments/planning-building/zoning-regulations-handouts`
- Zoning regulation PDFs: `https://www.lovelafayette.org/city-hall/city-departments/planning-building/zoning-regulations-handouts/download-zoning-regulations`
- Municipal code: `https://library.municode.com/ca/lafayette`
- Lafayette Title 6 / Planning & Land Use is referenced by city pages as the zoning code.

City evidence:

- The Map Room says Community View is a hosted GIS with property lines, aerial photos, zoning, flood zones, and street information.
- The Zoning Regulations page says users can obtain zoning using Community View by typing a property address, and links to the zoning map.
- The zoning regulation page exposes district handout PDFs and a land-use activity classification table, including `APO`, `C`, `C-60`, `C-1`, `C-1-60`, `R-6`, `R-10`, `R-12`, `R-15`, `R-20`, `R-40`, `R-65`, `RB`, `RB-60`, `R-100`, `SRB`, and `SRB-60`.
- A document listing includes `Zoning Map - Updated 2024-12-16`.

Machine-readable result:

- Quick probe did not find a public Lafayette ArcGIS FeatureServer equivalent.
- Community View is hosted by Digital Map Products at `https://maps.digitalmapcentral.com/production/VECommunityView/cities/lafayette/index.aspx`, not a straightforward public ArcGIS REST layer.
- California Statewide Zoning North has Lafayette rows with `Code` and `Description`, e.g. `A-2`, `APO`, and `C`, so it is the best Lafayette machine-readable zoning candidate.

Lafayette acquisition verdict: **partial**. Use CA Statewide Zoning North as the first machine-readable source if the preview `ST_Within` gate passes; otherwise Lafayette becomes manual/Class B from zoning map PDF + Community View + Municode.

## Lane A Execution Shape

Recommended staged plan:

1. Register Contra Costa County jurisdiction in preview.
2. Ingest county parcels from `Assessment_Parcels_ArcPro/MapServer/0`.
3. Normalize parcel identity:
   - `parcel_id`: `APN` or `parcel_dashes`
   - address: `full_address_display`
   - municipality/subjurisdiction: `s_city`
   - source provenance: county CCMAP URL + pull timestamp
4. Ingest California Statewide Zoning North filtered to `County='CCO'` into zoning districts in preview.
5. Run strengthened Class A pre-flight before backfill:
   - district bbox covers >=50% of parcel bbox: source probe passes.
   - 1,000-parcel `ST_Within` dry-run >=50% match: **still required in preview**.
6. If preview passes, backfill parcel `zoning_code` from statewide zoning `Code`, preserving `Jurisdiction` as subjurisdiction/provenance.
7. For proof, author `backend/data/contra_costa_ca_zoning_directory.json` for Lafayette and Walnut Creek only.
8. If Master wants county operational instead of two-city proof, broaden directory coverage before claiming operational readiness.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Parcel adapter / source config for CCMAP MapServer | 6-10h |
| Preview parcel ingest and QA | 3-5h |
| CA Statewide Zoning North ingest filtered to `County='CCO'` | 3-5h |
| Strengthened Class A pre-flight and spatial dry-run | 2-4h |
| Walnut Creek directory from city GIS + eCode360 | 4-6h |
| Lafayette directory from statewide zoning + city handouts/Municode | 6-10h |
| Two-city proof sprint total | 3-5 days |
| Full county operational directory expansion | 1-2+ weeks |

## Expected Coverage and Audit Outcome

Parcel load alone creates roughly 387,835 Contra Costa parcels but no zoning code. It will not clear audit gates.

If Statewide Zoning North passes the preview `ST_Within` gate and Lane A backfills all `County='CCO'` polygons, parcel zoning-code coverage could plausibly clear the 70% general gate and maybe the 80% parcel-source-zoned exception gate. The bbox primitive supports that hypothesis, but it is not verified until staging.

If Lane A only populates Lafayette and Walnut Creek, the two cities represent 46,037 parcel rows, about 11.9% of the county parcel source. That is enough for a useful 57-list proof but not enough for whole-county operational readiness.

Matrix risk is the gating issue: if statewide zoning populates codes for all Contra Costa jurisdictions but the directory only covers Lafayette and Walnut Creek, matrix match will be low across all zoned parcels. Full county operational status likely requires a broader directory strategy across the 20 distinct `CCO` jurisdictions returned by the statewide zoning layer.

## Risk Register

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| No embedded parcel zoning | High | County parcel layer has assessor land-use fields but no zoning code. | Treat as Class A/B, not Class C. |
| `ST_Within` not yet verified | High | Contra Costa is not loaded in prod, so the required dry-run cannot run yet. | Use preview branch/staging ingest before production backfill. |
| Matrix coverage mismatch | High | Full county zoning backfill may create many city-specific codes; a two-city directory will not bind all codes. | Decide proof-only vs full-county operational before sprint. |
| Lafayette machine-readable source weak | Medium | No clean Lafayette public FeatureServer found in the time box. | Use Statewide Zoning North first; fallback to PDF/Community View manual acquisition. |
| Walnut Creek source vintage | Medium | Web app title references June 2020; state layer reports Walnut Creek source date `2022 q1`; another Walnut Creek planning layer says current as of September 2025 but is dissolved/general-plan oriented. | Preserve source date in provenance and verify a sample against city map before production. |
| Coordinate systems | Medium | County sources use Web Mercator in REST; downloadable county GIS may use California State Plane or local projection. | Standardize to WGS84/PostGIS geometry on ingest; keep source SRID metadata. |
| API limits/pagination | Medium | Parcel MapServer max record count is 2,000; 387,835 rows require pagination. | Use existing ArcGIS pagination patterns; prefer objectId batching. |
| County zoning is unincorporated-only | Medium | The county zoning layer is not sufficient for Lafayette/Walnut Creek. | Use Statewide Zoning North and city-specific sources. |
| Legacy URL drift | Low | Some Walnut Creek zoning district `URL` values point to legacy CodePublishing paths. | Normalize to current `https://ecode360.com/WA4684` where possible. |

## Recommendation

Keep Contra Costa as the next best not-loaded candidate, but dispatch it as **preview-gated proof-then-scale**, not as a guaranteed first-sprint operational flip.

The best Lane A ticket is:

- County parcel ingest from CCMAP.
- Preview-only Statewide Zoning North spatial backfill for `County='CCO'`.
- Directory proof for Walnut Creek and Lafayette.
- Audit refresh only after the `ST_Within` gate and matrix coverage strategy are explicit.

If the statewide zoning `ST_Within` gate fails or Lafayette cannot be bound without manual work, pivot to **Allegheny County, PA** for the fastest one-polygon proof, with **Maricopa County, AZ** as the higher-value follow-up.
