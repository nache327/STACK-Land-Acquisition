# Oakland MI Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Oakland County, MI, with emphasis on the 57-list wealth pockets Birmingham and Bloomfield Hills.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Oakland County Access Oakland / OC Tax Parcels (Public)** |
| Parcel source URL | `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1` |
| Parcel source class | **SINGLE-COUNTY-PORTAL** |
| Verified class | **Class A/B hybrid, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. County parcel rows carry tax jurisdiction, assessing class, address, and value fields, not zoning district codes. |
| Class A separate zoning layer | **PARTIAL**. Birmingham and Bloomfield Hills both have live zoning geometry with district/code fields and bbox coverage. Bloomfield Hills is parcel-like and carries `PIN` + `Zoning`; Birmingham is polygon zoning with `district` + ordinance links. Production `ST_Within` dry-run cannot run until Oakland parcels are staged. |
| Verified via Lane A strengthened gates | **PARTIAL**. Live field samples and bbox primitives pass for the two target municipalities. Required 1,000-parcel `ST_Within` dry-run remains a preview gate. |
| Lane A effort estimate | **3-5 days** for county parcel adapter + Birmingham/Bloomfield Hills proof; **1-2+ weeks** for broader Oakland operationalization. |
| Expected operational outcome | **Two-city proof-then-scale**, not first-sprint countywide operational. Birmingham + Bloomfield Hills are about 11,619 of 490,590 Oakland parcel rows, roughly 2.4%. |
| Birmingham coverage | **YES**. County parcel count 9,786 by tax jurisdiction; city zoning layer count 400 with district/standards fields. |
| Bloomfield Hills coverage | **YES**. County parcel count 1,833 by tax jurisdiction; city zoning layer count 1,853 with nonblank `Zoning` and `PIN`. |
| Detroit-metro multi-county carry | **NO verified SEMCOG parcel carry**. SEMCOG has regional open-data layers, but no current authoritative parcel service for Oakland + Wayne + Macomb was verified in the time box. |
| Recommended dispatch | **MEDIUM-HIGH**. Better than Allegheny because it has two target cities and live zoning sources, but below Hennepin/King because it does not produce a verified multi-county adapter unlock. |

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `Oakland` match.
- `/api/admin/coverage`: no `Oakland` row.

Oakland remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Recommended source: Oakland County Access Oakland open parcel layer.

- County GIS maps/data page: `https://www.oakgov.com/government/information-technology/enterprise-gis/maps-data`
- Access Oakland property search: `https://accessoakland-oakgov.opendata.arcgis.com/search?tags=property`
- ArcGIS item: `https://www.arcgis.com/home/item.html?id=e2910cc3a8f84549ab7f0f8e8f99817b`
- Live parcel layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Oakland terms referenced by item metadata: `https://www.oakgov.com/open-data-terms`

The item description says the layer is a spatial representation of tax parcels and that `KeyPIN` is the unique parcel identification number used to link the tax parcel to parcel attributes maintained in Oakland County land records.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Tax Parcel Plus` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Max record count | 2,000 |
| Oakland parcel count | 490,590 |
| County bbox, WGS84 | `[-83.6943413, 42.4260971, -83.0744139, 42.8936067]` |

Observed parcel fields include:

`KEYPIN`, `REVISIONDATE`, `CVTTAXCODE`, `CVTTAXDESCRIPTION`, `PIN`, `CLASSCODE`, `NAME1`, `NAME2`, `SITEADDRESS`, `SITECITY`, `SITEZIP5`, `ASSESSEDVALUE`, `TAXABLEVALUE`, `NUM_BEDS`, `NUM_BATHS`, `STRUCTURE_DESC`, and geometry fields.

Class C gate result: **FAIL**. `CLASSCODE` is an assessing/classification value and `CVTTAX*` is tax jurisdiction. Neither is a municipal zoning district code.

## Multi-County Carry

No verified SEMCOG parcel carry.

Sources checked:

- SEMCOG data/maps page: `https://www.semcog.org/data-maps/`
- ArcGIS search for SEMCOG parcel services
- SEMCOG-hosted open data results such as `Land Use 2020`, `Building Points`, and `Building Footprints`
- Third-party-looking item `2019_parcel_data_SEMCOG`: `https://services7.arcgis.com/bXqgWVEWtpVS1ia3/arcgis/rest/services/2019_parcel_data_SEMCOG/FeatureServer`
- Michigan tax parcels page: `https://www.michigan.gov/dtmb/services/maps/mgf-data-hub/boundaries-and-mgf/tax-parcels`

Findings:

- SEMCOG publishes useful regional planning layers, but no current authoritative parcel layer covering Oakland + Wayne + Macomb was verified.
- The `2019_parcel_data_SEMCOG` item is not owned by SEMCOG, has a tiny extent, and is not suitable as a regional parcel adapter source.
- Michigan's tax-parcel page says the statewide MGF parcel layer is internal and public parcel layers are on individual county websites, sometimes with fees.

Conclusion: **do not move Oakland above Hennepin/King on multi-county ROI**. Oakland is a strong single-county source, not a Detroit-metro regional adapter unlock.

## Target Parcel Coverage

Use `CVTTAXDESCRIPTION`, not `SITECITY`, for target municipality filtering. `SITECITY='BLOOMFIELD HILLS'` includes postal-city parcels outside the City of Bloomfield Hills.

Birmingham live query:

- Query: `UPPER(CVTTAXDESCRIPTION)='CITY OF BIRMINGHAM'`
- Count: 9,786
- Parcel bbox, WGS84: `[-83.2505626, 42.5303877, -83.1849290, 42.5667137]`

Sample Birmingham parcel rows:

| KEYPIN | Tax code | Tax jurisdiction | PIN | Class | Address | Site city | Structure |
|---|---|---|---|---|---|---|---|
| `2031502004` | `08` | CITY OF BIRMINGHAM | `2031502004` | 402 | blank | blank | blank |
| `2031456028` | `08` | CITY OF BIRMINGHAM | `2031456028` | 401 | `1755 E MELTON RD` | BIRMINGHAM | blank |
| `2031456027` | `08` | CITY OF BIRMINGHAM | `2031456027` | 401 | `2200 DUNSTABLE RD` | BIRMINGHAM | Colonial/2Sty |
| `2031456026` | `08` | CITY OF BIRMINGHAM | `2031456026` | 402 | `1775 E MELTON RD` | BIRMINGHAM | blank |
| `2031456024` | `08` | CITY OF BIRMINGHAM | `2031456024` | 401 | `1699 HANLEY CT` | BIRMINGHAM | Colonial/2Sty |

Bloomfield Hills live query:

- Query: `UPPER(CVTTAXDESCRIPTION)='CITY OF BLOOMFIELD HILLS'`
- Count: 1,833
- Parcel bbox, WGS84: `[-83.2663229, 42.5589851, -83.2247159, 42.5973384]`

Sample Bloomfield Hills parcel rows:

| KEYPIN | Tax code | Tax jurisdiction | PIN | Class | Address | Site city | Structure |
|---|---|---|---|---|---|---|---|
| `1923476003` | `12` | CITY OF BLOOMFIELD HILLS | `1923476003` | 402 | `1390 QUARTON RD` | BLOOMFIELD HILLS | blank |
| `1923476002` | `12` | CITY OF BLOOMFIELD HILLS | `1923476002` | 201 | `37357 WOODWARD AVE` | BLOOMFIELD HILLS | blank |
| `1923476001` | `12` | CITY OF BLOOMFIELD HILLS | `1923476001` | 401 | `340 CHESTERFIELD RD` | BLOOMFIELD HILLS | Colonial/2Sty |
| `1923451020` | `12` | CITY OF BLOOMFIELD HILLS | `1923451020` | 401 | `300 CHESTERFIELD RD` | BLOOMFIELD HILLS | Colonial/2Sty |
| `1923451019` | `12` | CITY OF BLOOMFIELD HILLS | `1923451019` | 401 | `290 CHESTERFIELD RD` | BLOOMFIELD HILLS | Colonial/2Sty |

Conclusion: both 57-list centers are covered by the canonical county parcel source. They are not local parcel-source patchworks.

## Zoning Source Audit

Oakland County does not provide a countywide zoning system for Birmingham and Bloomfield Hills. Zoning is municipal. Both target municipalities publish ordinance sources online, and both have live zoning geometry after deeper probing.

### Birmingham

Public sources:

- City codes/ordinances page: `https://www.bhamgov.org/about_birmingham/city_government/codes___ordinances.php`
- enCodePlus zoning ordinance: `https://online.encodeplus.com/regs/birmingham-mi/index.aspx`
- enCodePlus Chapter 126 example: `https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx?secid=317`
- enCodePlus Appendix A Land Use Matrix: `https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx?secid=660`
- Zoning map PDF: `https://cms7files1.revize.com/birmingham/Document_Center/About%20Birmingham/Codes%20%26%20Ordinances/Zoning%20Map%20-%20August%202021.pdf`
- Online city GIS map: `http://maps.bhamgov.org/apps/gisviewer/`
- Live city zoning layer: `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0`

The city page links to the zoning ordinance, zoning map PDF, and online city map. The online GIS `config.js` exposes the `Zoning/MapServer` service.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NAD 1983 StatePlane Michigan South Intl Feet, WKT only |
| Count | 400 |
| Nonblank `district` count | 400 |
| City zoning bbox, WGS84 | `[-83.2505657, 42.5302272, -83.1849203, 42.5667137]` |
| Birmingham parcel bbox, WGS84 | `[-83.2505626, 42.5303877, -83.1849290, 42.5667137]` |
| Bbox primitive | **Passes**. City zoning bbox effectively matches Birmingham tax-jurisdiction parcel bbox. |

Fields include `district`, `descript`, and `standards`. `standards` links directly into the zoning ordinance PDF by district page.

Sample distinct city zoning rows:

| District | Description | Standards link |
|---|---|---|
| `R1` | Single Family Residential | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=16` |
| `R2` | Single Family Residential | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=18` |
| `R4` | Two Family Residential | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=22` |
| `R8` | Multiple Family Residential | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=30` |
| `B-1` | Neighborhood Business / Office | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=38` |
| `B-2` | General Business | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=41` |
| `MX` | Mixed Use | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=50` |
| `TZ-1` | Transitional Zone | `http://maps.bhamgov.org/docs/ZONING_ORDINANCE.pdf#page=52` |

Birmingham acquisition verdict: **strong city-level Class A candidate plus strong Class B directory support**. The zoning layer is district polygons, not parcel rows, so Lane A should run the strengthened spatial gates in preview before backfill. The matrix side is unusually good because enCodePlus exposes an Appendix A Land Use Matrix.

False-positive note: ArcGIS item `d3c975d87d4a491ca167b2ecf61f33be` / `services2.arcgis.com/Z4oonA9tfgNvnlIk/.../Birmingham_Zoning` is **not** the Michigan target. Its extent resolves to Alabama. Do not use it.

### Bloomfield Hills

Public sources:

- City maps page: `https://www.bloomfieldhills.gov/149/Maps`
- Zoning map PDF: `https://www.bloomfieldhills.gov/DocumentCenter/View/30/Zoning-Map-PDF`
- Zoning ordinance page: `https://www.bloomfieldhills.gov/241/Zoning-Ordinance`
- Municode / code link from city page: `http://www.municode.com/resources/gateway.aspx?productid=10301`
- Bloomfield Hills zoning FeatureServer: `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0`

The city maps page links a zoning map PDF, and the zoning ordinance page states the zoning ordinance text is in the City Code. The FeatureServer is not linked directly from the city page in the probed HTML, but it is public and matches the city parcel bbox.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning_BloomfieldHills` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Michigan South StatePlane, `wkid=2253` |
| Count | 1,853 |
| Nonblank `Zoning` count | 1,853 |
| City zoning bbox, WGS84 | `[-83.2663227, 42.5589850, -83.2247157, 42.5973383]` |
| Bloomfield Hills parcel bbox, WGS84 | `[-83.2663229, 42.5589851, -83.2247159, 42.5973384]` |
| Bbox primitive | **Passes**. Zoning bbox effectively matches Bloomfield Hills tax-jurisdiction parcel bbox. |

Fields include `CVTTAXCODE`, `CVTTAXDESC`, `PIN`, `SITEADDRES`, `SITECITY`, `STRUCTURE_`, and `Zoning`.

Sample direct zoning rows:

| PIN | Tax code | Tax jurisdiction | Address | Site city | Zoning |
|---|---|---|---|---|---|
| `1914127030` | `12` | CITY OF BLOOMFIELD HILLS | `167 E LONG LAKE RD` | BLOOMFIELD HILLS | `B-1` |
| `1914127031` | `12` | CITY OF BLOOMFIELD HILLS | `169 E LONG LAKE RD` | BLOOMFIELD HILLS | `B-1` |
| `1914127032` | `12` | CITY OF BLOOMFIELD HILLS | `173 E LONG LAKE RD` | BLOOMFIELD HILLS | `B-1` |
| `1923476002` | `12` | CITY OF BLOOMFIELD HILLS | `37357 WOODWARD AVE` | BLOOMFIELD HILLS | `I-1` |
| `1923476003` | `12` | CITY OF BLOOMFIELD HILLS | `1390 QUARTON RD` | BLOOMFIELD HILLS | `I-1` |

Distinct zoning examples include `A-1`, `A-2`, `A-3`, `A-3-1`, `A-4`, `A-6`, `B-1`, `C-1`, `I-1`, `O-1`, `O-2`, `P-1`, and `RR`.

Bloomfield Hills acquisition verdict: **best proof city**. This is a direct parcel-like zoning source with `PIN` + `Zoning`, so Lane A can attempt direct attribute join from Oakland `PIN` to city `PIN`, with spatial backfill as fallback. Preview should include a direct join-rate gate in addition to the standard bbox and `ST_Within` gates.

## Lane A Execution Shape

Recommended staged plan:

1. Register Oakland County in preview.
2. Ingest Oakland parcels from `EnterpriseOpenParcelDataMapService/MapServer/1`.
3. Normalize parcel identity:
   - `parcel_id`: `KEYPIN` or `PIN` after confirming existing conventions
   - alternate IDs: keep both `KEYPIN` and `PIN`
   - municipality/subjurisdiction: `CVTTAXDESCRIPTION`
   - postal city: `SITECITY`
   - source provenance: Access Oakland item/layer URL + pull timestamp
   - source CRS: Web Mercator from county layer
4. Do **not** classify as Class C. `CLASSCODE` and `CVTTAX*` are not zoning.
5. For first proof, prioritize Bloomfield Hills:
   - pull `Zoning_BloomfieldHills/FeatureServer/0`
   - attempt direct `PIN` -> `PIN` zoning-code join
   - require sampled join-rate gate before production write
6. For Birmingham proof:
   - pull `maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0`
   - run spatial backfill preview with target filter `CVTTAXDESCRIPTION='CITY OF BIRMINGHAM'`
7. Run Lane A strengthened gates before production backfill:
   - district bbox covers >=50% of target-city parcel bbox
   - 1,000-parcel `ST_Within` dry-run >=50% for spatial sources
   - direct `PIN` join-rate gate for Bloomfield Hills
8. Author `backend/data/oakland_mi_zoning_directory.json` for Birmingham + Bloomfield Hills proof only.
9. Treat full Oakland operationalization as later scale work across many city/township zoning systems.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Oakland parcel adapter | 6-10h |
| Bloomfield Hills direct zoning join + preview gates | 4-8h |
| Birmingham zoning pull + preview spatial gates | 4-8h |
| Birmingham + Bloomfield Hills directory/matrix seed | 1-2 days |
| Two-city proof end to end | 3-5 days |
| Full Oakland operationalization | 1-2+ weeks |

Expected coverage after only Birmingham + Bloomfield Hills:

- Birmingham parcels: 9,786
- Bloomfield Hills parcels: 1,833
- Combined: 11,619
- Oakland total: 490,590
- Countywide fraction: about 2.4%

This is a two-polygon proof with good city zoning sources, not a first-sprint countywide operational flip.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| SEMCOG carry unverified | No 3-county Detroit adapter bump | Keep Oakland scoped as single-county until an authoritative SEMCOG parcel layer is found. |
| Michigan statewide parcel layer is internal | No state-aggregator path | Use Oakland County direct source; do not wait for state open data. |
| County parcel rows have no zoning | Prevents Class C path | Use municipal zoning layers and directory/matrix work. |
| Postal city over-selects Bloomfield Hills | Inflated target parcels and failed gates | Filter by `CVTTAXDESCRIPTION`, not `SITECITY`. |
| Birmingham city zoning service exposes WKT-only StatePlane CRS | Transform and ingest risk | Record CRS, test preview transform, and compare bbox before backfill. |
| Bloomfield Hills source ownership is not clearly city-owned in ArcGIS item metadata | Provenance caveat | Cross-check with city zoning map PDF and ordinance; prefer direct join only after preview samples match Oakland `PIN`. |
| Small countywide fraction | First proof will not make Oakland operational | Scope as proof-then-scale and avoid promising countywide gate clearance. |
| Multiple municipal zoning styles | Matrix/directory scale work is per-muni | Start with Birmingham/Bloomfield Hills; scale city-by-city later. |

## Verdict

Oakland is **not blocked at parcel acquisition**. Oakland County's official open parcel layer is directly queryable, current enough for a preview sprint, and covers both Birmingham and Bloomfield Hills.

Oakland is **not a SEMCOG multi-county unlock** based on the live probes. It should not move above Hennepin or King on adapter ROI. It is, however, stronger than the earlier source-scoping summary because both target municipalities now have live zoning geometry: Bloomfield Hills has a parcel-like `PIN` + `Zoning` layer, and Birmingham has city zoning polygons with ordinance links plus an enCodePlus land-use matrix.

Recommended next action: keep Oakland below King/Hennepin and around Maricopa in the queue. If Master prioritizes fastest proof quality, run **Bloomfield Hills first**, then Birmingham. If Master prioritizes two-polygon footprint, run both as a single Oakland preview-gated proof.

Next unscoped spec pick: **Cook IL**. It is the better next diagnostic than Miami-Dade because it can test whether any Illinois parcel/zoning adapter shape extends from the already-ingested DuPage work into Cook/North Shore.
