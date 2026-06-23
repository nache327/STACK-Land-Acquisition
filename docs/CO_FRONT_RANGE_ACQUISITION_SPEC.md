# Colorado Front Range Acquisition Spec

Date: 2026-06-23

Purpose: read-only acquisition spec for a possible Lane A bundled ingestion sprint covering the Colorado Front Range trio: Douglas County, Arapahoe County, and Jefferson County, CO, with emphasis on the 58-list wealth pockets Highlands Ranch, Cherry Hills Village, and Golden.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Colorado Public Parcels / Colorado_Public_Parcel_Composite** |
| Parcel source URL | `https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0` |
| Parcel source class | **SINGLE-STATE-AGGREGATOR, PARTIAL verified**. It is the highest-leverage carry source, but query reliability and embedded zoning completeness need a preview probe before production use. |
| DRCOG parcel carry | **NO parcel equivalent found in the time box**. DRCOG has a strong regional catalog, but no MetroGIS-style regional parcel FeatureServer surfaced. |
| County fallback source class | **THREE SINGLE-COUNTY-PORTAL FALLBACKS**. Douglas, Arapahoe, and Jefferson all expose live parcel services. |
| Verified zoning class | **Class A/B hybrid, PARTIAL verified**. County or municipal zoning FeatureServers exist for the three target areas, but no single regional zoning layer solves all three. |
| Class C embedded parcel zoning | **UNVERIFIED / likely weak**. The state parcel schema exposes `zoningCode` and `zoningDesc`, but the three-county nonblank count probe returned `0` and several state attribute queries returned ArcGIS 500 errors. Do not claim Class C until a preview sample proves nonblank coverage. |
| Class A separate zoning layer | **YES as fallback, fragmented**. Douglas county zoning, Arapahoe county zoning, Jefferson county zoning, and Golden city zoning all returned live sample rows. |
| Verified via Lane A strengthened gates | **PARTIAL**. Live field samples and source counts pass for fallback services. Statewide source needs stable pagination and nonblank zoning-code coverage checks; spatial `ST_Within` dry-runs remain preview gates. |
| Lane A effort estimate | **3-5 days** for statewide parcel adapter + three-center zoning proof if state pagination stabilizes; **5-8 days** if using county parcel/zoning fallbacks; **1-2+ weeks** for broader Front Range operationalization. |
| Expected operational outcome | **Three-center proof-then-scale**, not guaranteed first-sprint countywide operational. |
| Direct 58-list lift | **3 polygons**: Highlands Ranch, Cherry Hills Village, Golden. |
| Carry potential | **YES if state parcel adapter works**. The state parcel source should carry to adjacent Colorado counties beyond the trio. DRCOG's region covers the Denver metro, but was not the parcel carrier found here. |
| Recommended dispatch | **YES, preview-gated**. Start with Colorado Public Parcels for adapter leverage; keep county/municipal zoning fallbacks ready because embedded state zoning was not verified. |

## Current Prod State

From `docs/TARGET_MARKETS.md`:

| County | Target center | Status |
|---|---|---|
| Douglas, CO | Highlands Ranch | partial, 0% |
| Arapahoe, CO | Cherry Hills | partial, 0% |
| Jefferson, CO | Golden | not ingested |

No production mutation or ingestion was attempted in this diagnostic.

## Recommended Source Shape

The best first source is the Colorado statewide parcel composite:

- Colorado Geospatial Portal dataset page: `https://geodata.colorado.gov/datasets/colorado-public-parcels/about`
- ArcGIS web map/item: `https://www.arcgis.com/home/item.html?id=21bde4454fe943cb8a54a7b95cf10a77`
- FeatureServer root: `https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer`
- Parcel layer: `https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0`

Why state over county-direct: one adapter should cover Douglas, Arapahoe, Jefferson, and adjacent Colorado counties. County-direct sources are still viable fallbacks, but they create three parcel adapters and still need separate zoning sources.

Live REST metadata probe:

| Check | Result |
|---|---:|
| Layer name | `Colorado_Public_Parcel_Composite` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | WGS84, `wkid=4326` |
| Max record count | 2,000 |
| Full bbox | `xmin=-109.0601683`, `ymin=36.9919733`, `xmax=-102.0466518`, `ymax=41.0032967` |
| Observed Jefferson count | 258,817 via `UPPER(countyName)='JEFFERSON'` |

Observed fields include:

`countyName`, `countyFips`, `parcel_id`, `account`, `situsAdd`, `sitAddCty`, `sitAddZip`, owner/address fields, `legalDesc`, `landSqft`, `landAcres`, `zoningCode`, `zoningDesc`, `landUseCde`, `landUseDsc`, `dateReceived`, and geometry fields.

Class C warning: the presence of `zoningCode` is not enough. A three-county nonblank query against `zoningCode` returned `0`, while other county attribute filters returned ArcGIS `Error performing query operation`. Treat this as a **statewide parcel adapter candidate**, not an embedded-zoning win, until preview confirms nonblank coverage and stable pagination.

State source sample status:

| Requested sample | Result |
|---|---|
| 50 features by county attribute filter | Failed or timed out for Douglas/Arapahoe; Jefferson count worked. |
| 50 features by target-area geometry envelope | Timed out / returned non-JSON in this environment. |
| Metadata sample | Passed: fields and layer shape are visible. |

## DRCOG Regional Probe

Sources checked:

- DRCOG Regional Data Catalog: `https://data.drcog.org/`
- DRCOG data/maps page: `https://drcog.org/data-maps-modeling`
- DRCOG regional catalog page: `https://www.drcog.org/data-maps-modeling/regional-data-catalog`

DRCOG's catalog is a real Denver-region data catalog and says it supports communities with datasets for mobility, land use, demographics, and related planning. It also describes the region as 59 cities, counties, and towns. However, ArcGIS and web searches during this time box did **not** surface a DRCOG parcel FeatureServer comparable to MetroGIS `Parcels_2025`.

DRCOG verdict: **regional context only for this sprint**. Do not block on DRCOG, and do not represent it as the parcel carrier unless a later agent finds a hidden parcel service.

## County Parcel Fallbacks

### Douglas County

Public pages:

- County GIS maps/apps page: `https://www.douglasco.gov/information-technology/gis-maps-apps/`
- DougCo Hub: `https://dcdata-dougco.opendata.arcgis.com/`

Parcel service:

- Service: `https://apps.douglas.co.us/gisod/rest/services/Parcels/MapServer`
- Parcel layer: `https://apps.douglas.co.us/gisod/rest/services/Parcels/MapServer/4`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `PARCELS` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Colorado StatePlane Central feet, `wkid=102654`, `latestWkid=2232` |
| Max record count | 2,000 |
| Count | 158,356 |
| Sample 50 features | **PASS** |

Observed fields include `PARCEL_SPN`, `PARCEL_NAME`, `DEEDED_AREA`, `CALC_AREA`, `LEGAL_DESCR`, `PARCELS_EID`, `PARCEL_TYPE`, `ADDRESS_COUNT`, `LAT`, and `LON`.

Sample rows around Highlands Ranch showed `LEGAL_DESCR` values such as `LOT 320 HIGHLANDS RANCH #112-A` and `LOT 7 HIGHLANDS RANCH #134A 5TH AMD`, confirming target-center coverage in the county parcel source.

Class C gate result: **FAIL** for county parcel fallback. No parcel zoning code field was observed.

### Arapahoe County

Public pages:

- Arapahoe GIS: `https://gis.arapahoegov.com/`
- Arapahoe GIS data download: `https://gis.arapahoegov.com/datadownload/`

The data download page lists `Parcels` and `Zoning` as export layers and says data is updated nightly.

Parcel service:

- Parcel layer: `https://gis.arapahoegov.com/arcgis/rest/services/OpenDataService/FeatureServer/0`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Colorado StatePlane Central feet, `wkid=102654`, `latestWkid=2232` |
| Max record count | 1,000 |
| Count | 232,880 |
| Sample 50 features | **PASS** |

Observed fields include `PARCEL_ID`, `PIN`, `Folio`, `Situs_Address`, `Situs_City_State_Zip`, `Classification`, `PUC_Code`, `PUC`, `City`, `State`, `Zip`, `Coordinate_X`, and `Coordinate_Y`.

Class C gate result: **FAIL** for county parcel fallback. `PUC` is property/assessor use, not zoning.

### Jefferson County

Public pages:

- Jefferson County GIS/mapping page: `https://www.jeffco.us/739/GIS-Mapping`
- Jefferson County maps/data download page: `https://www.jeffco.us/3165/Maps-Data-Download`
- Jefferson County open data: `https://data-jeffersoncounty.opendata.arcgis.com/`
- Jefferson County web maps: `https://gis.jeffco.us/`

Parcel service:

- Service: `https://gisportal.jeffco.us/server2/rest/services/Parcel/FeatureServer`
- Parcel layer: `https://gisportal.jeffco.us/server2/rest/services/Parcel/FeatureServer/20`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcel` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Colorado StatePlane Central feet, `wkid=102654`, `latestWkid=2232` |
| Max record count | 2,000 |
| Count | 258,941 |
| Sample 50 features | **PASS** |

Observed fields include `PIN`, `SPN`, `PARCELID`, `SCH`, `AIN`, situs/mailing address fields, `PRPCTYNAM`, `TAXCLS*`, `STTSTRC`, `STTTYPUSE`, `TOTACR`, `AUMENTUM_PIN`, and geometry fields.

Class C gate result: **FAIL** for county parcel fallback. Tax class and structure-use fields are assessor fields, not zoning district codes.

## Zoning Source Audit

### Douglas / Highlands Ranch

Primary fallback zoning service:

- Landuse service: `https://apps.douglas.co.us/gisod/rest/services/Landuse/MapServer`
- Zoning layer: `https://apps.douglas.co.us/gisod/rest/services/Landuse/MapServer/1`
- CARA zoning subset: `https://apps.douglas.co.us/gisod/rest/services/Landuse/MapServer/2`
- County zoning page: `https://www.douglasco.gov/planning/development-review-regulations/zoning/`

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `ZONING` |
| Geometry | `esriGeometryPolygon` |
| Count | 933 |
| Sample 50 features | **PASS** |
| Key zone fields | `ZONE_TYPE`, `FIRST_DESC`, `PD_Name` |

Sample codes/descriptions included `PD` / Planned Development, `A1` / Agricultural One, and `LI` / Light Industrial.

Highlands Ranch note: Highlands Ranch is a Douglas County CDP, not a separate municipality for this purpose. The county parcel and county zoning services are the likely first fallback path. Because many rows are planned development (`PD`), matrix authoring will need planned-development guide handling rather than only simple district-code rows.

### Arapahoe / Cherry Hills Village

Primary fallback zoning service:

- Arapahoe zoning FeatureServer: `https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/AC_WSS_Arapahoe_County_Zoning/FeatureServer`
- Zoning layer: `https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/AC_WSS_Arapahoe_County_Zoning/FeatureServer/89`
- Arapahoe data download page: `https://gis.arapahoegov.com/datadownload/`
- Cherry Hills Village zoning maps page: `https://www.cherryhillsvillage.com/392/Zoning-District-Maps`

Cherry Hills Village says its maps are informational, points users to the official zoning map PDF, and says Arapahoe County also provides an online mapping service that includes properties in Cherry Hills Village.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Arapahoe_County_Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 1,236 |
| Sample 50 features | **PASS** |
| Key zone fields | `ZONING`, `CASE_NUMBE`, `ACTIVE`, `HYPERLINK`, `Zoning_Doc` |

Sample codes included `RR-A`, `SH PUD`, `A-E`, and `A-1`. Rows carry links to county zoning district PDFs and zoning case documents.

Cherry Hills verdict: **sprintable fallback, but verify municipal authority**. Use Arapahoe parcels + Arapahoe zoning for the first spatial proof, then cross-check Cherry Hills Village official zoning map and code for target-center matrix rows.

### Jefferson / Golden

Jefferson County zoning service:

- Service: `https://gisportal.jeffco.us/server2/rest/services/Zoning/FeatureServer`
- Zoning layer: `https://gisportal.jeffco.us/server2/rest/services/Zoning/FeatureServer/36`

Jefferson County page caveat: the county planning and zoning map is for information based on county land development regulation and zoning resolution; municipal areas require their own city rules.

Live Jefferson zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Colorado StatePlane Central feet, `wkid=102654`, `latestWkid=2232` |
| Count | 3,275 |
| Sample 50 features | **PASS** |
| Key fields | `ZCASE`, `ZCASE2`, `ZCOND`, `ZTYPE`, `ORTHOMAPLABELEDAS` |

Sample codes included `P-D`, `C-1`, and zoning case values such as `05-164079RZ`, `Z93-7`, and `B64-8`.

The REST directory description says the layer is current and changes for unincorporated Jefferson County occur as needed by county Planning and Zoning GIS staff. It also notes municipal Jefferson County is represented with city boundaries in `ZTYPE` rather than full municipal zoning.

Golden city zoning service:

- Golden open-data portal: `https://maps-cityofgolden.opendata.arcgis.com/`
- Golden zoning item: `https://maps-cityofgolden.opendata.arcgis.com/items/0c7b78352deb434694b63453358bf0d3`
- Golden zoning FeatureServer: `https://services1.arcgis.com/FP2GwMAr4SrmXGhq/arcgis/rest/services/Zoning/FeatureServer/0`
- Golden zoning criteria guide: `https://www.cityofgolden.gov/business/land_use_development/zoning_criteria_guide.php`

Live Golden zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Count | 180 |
| Sample 50 features | **PASS** |
| Key zone fields | `Zone_Code`, `Zone_Description`, `Name`, `Ordinance`, `ZoneDefinition` |

Sample Golden codes included `R-1`, `PUD`, `AG`, and `C-2`, with descriptions such as Residential Standard Lot, Planned Unit Development, Agricultural, and General Commercial.

Golden verdict: **strong municipal Class A fallback**. Use Golden's city zoning layer for the Golden center; use Jefferson parcels for geometry/base parcel identity unless state parcels prove cleaner.

## Multi-County Carry Potential

There are two carry levels:

1. **Direct target lift:** 3 wealth-pocket polygons: Highlands Ranch, Cherry Hills Village, Golden.
2. **Adapter carry:** if `Colorado_Public_Parcels` can be paginated reliably, the same adapter should carry to adjacent Colorado counties. Immediate Denver-region carry candidates include Adams, Boulder, Broomfield, Denver, and possibly Weld-side regional pockets if they enter scope.

Important caveat: the statewide parcel source does **not** currently prove statewide zoning readiness. Even if the parcel adapter is statewide, zoning remains:

- embedded `zoningCode` only if preview proves nonblank coverage;
- otherwise county/municipal Class A zoning layers plus matrix/directory authoring.

This is analogous to the Hennepin MetroGIS carry warning: the parcel source can scale faster than operational zoning coverage.

## Lane A Execution Shape

Recommended staged plan:

1. Register or stage the three Colorado jurisdictions in preview only.
2. Try Colorado Public Parcels first:
   - page by county filter or object-id windows;
   - normalize `parcel_id` as primary parcel id;
   - preserve `countyName`, `countyFips`, `sitAddCty`, `zoningCode`, `zoningDesc`, `landUseCde`, `landUseDsc`, and `dateReceived`;
   - log ArcGIS 500/timeouts and fall back quickly if pagination is unstable.
3. Run a state-source embedded-zoning gate:
   - sample at least 1,000 parcels per target county;
   - compute nonblank `zoningCode` and `zoningDesc` coverage;
   - if coverage is below 70%, do **not** use Class C.
4. If state embedded zoning fails, use county parcel fallbacks:
   - Douglas parcels: `PARCEL_SPN`;
   - Arapahoe parcels: `PARCEL_ID` / `PIN`;
   - Jefferson parcels: `PIN` / `PARCELID` / `AIN`.
5. Ingest target zoning layers:
   - Douglas zoning `ZONE_TYPE` / `FIRST_DESC` / `PD_Name`;
   - Arapahoe zoning `ZONING` / case-doc links;
   - Golden city zoning `Zone_Code` / `Zone_Description`;
   - Jefferson county zoning only for unincorporated Jefferson, not as Golden municipal zoning.
6. Run strengthened Class A pre-flight per source:
   - district/parcel bbox coverage >=50%;
   - 1,000-parcel `ST_Within` dry-run >=50%;
   - distinct-zone count and null-rate checks;
   - CRS transform check for StatePlane/Web Mercator/WGS84 mixes.
7. Author a Colorado Front Range zoning directory scoped to the three centers first. Do not attempt countywide matrix coverage in the first proof.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Statewide parcel adapter probe and pagination hardening | 6-10h |
| State embedded-zoning coverage gate | 2-4h |
| Douglas county parcel + zoning fallback proof | 6-10h |
| Arapahoe parcel + zoning + Cherry Hills official-map cross-check | 6-10h |
| Jefferson parcel + Golden city zoning proof | 6-10h |
| Three-center directory/matrix seed | 1-2 days |
| Three-center proof end to end | 3-5 days if state source works; 5-8 days using fallbacks |
| Broader Front Range operationalization | 1-2+ weeks |

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| State parcel queries return ArcGIS 500/timeouts | Blocks statewide adapter or makes ingestion brittle | Use object-id windowing, smaller envelopes, retry/backoff; fall back to county services if unstable. |
| State `zoningCode` is blank for target counties | Prevents Class C shortcut | Treat county/municipal zoning FeatureServers as the real zoning path. |
| County parcels lack zoning fields | No parcel-only operational path | Pair each parcel source with zoning FeatureServer and run spatial backfill. |
| CRS mix across sources | Backfill errors or false bbox failures | Normalize through existing reprojection path; record CRS per source. |
| Golden is municipal, not solved by Jefferson county zoning | Wrong zoning codes for target center | Use Golden city zoning FeatureServer for Golden. |
| Cherry Hills official map is PDF/informational page | Authority mismatch | Use Arapahoe zoning GIS for machine layer, then verify against Cherry Hills official map and code. |
| Douglas planned developments dominate target area | Matrix complexity | Seed PD-specific directory rows and planned-development guide handling. |
| DRCOG carry can be overstated | Mis-scoped regional promise | State explicitly that DRCOG parcel carry was not found; carry is via state parcel source only. |

## Verdict

The Colorado Front Range trio is **not blocked**. There is a credible statewide parcel carrier and strong county/municipal zoning fallback coverage for the three target centers.

The sprint should be scoped as **statewide parcel adapter first, local zoning proof second**. If Colorado Public Parcels can be paginated reliably, expected direct lift is the 3 target polygons plus a reusable Colorado parcel adapter for adjacent counties. If the state source remains unstable or the embedded `zoningCode` fields are blank, the fallback path is still viable but becomes a three-county/municipal Class A sprint rather than a clean statewide Class C unlock.

Recommended next action: approve a **preview-gated CO Front Range proof sprint** for Douglas/Arapahoe/Jefferson. Do not promise full county operational readiness until the preview run proves parcel pagination, zoning-code coverage, and `ST_Within` backfill rates.
