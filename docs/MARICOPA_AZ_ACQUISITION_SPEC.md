# Maricopa AZ Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Maricopa County, AZ, with emphasis on the 57-list wealth pockets Scottsdale and Paradise Valley.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Maricopa County Assessor / Maricopa County GIS Parcel Data View** |
| Parcel source URL | `https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Parcel_Data_View/FeatureServer/0` |
| Parcel source class | **SINGLE-COUNTY-PORTAL** |
| Verified class | **Class A/B hybrid, PARTIAL verified** |
| Class C embedded parcel zoning | **NO**. Parcel rows include assessor use/tax/legal-class fields, not zoning district codes. |
| Class A separate zoning layer | **PARTIAL**. Both cities publish zoning polygon layers. Paradise Valley passes the bbox primitive; Scottsdale does **not** pass when compared naively to county `PropertyCity='SCOTTSDALE'` parcel extent, likely because of postal-city noise. Production `ST_Within` dry-run cannot run until parcels are staged because Maricopa is not loaded. |
| Lane A effort estimate | **3-5 days** for Scottsdale + Paradise Valley proof; **1-2+ weeks** for broader county operationalization. |
| Expected operational outcome | **Two-city proof-then-scale**, not first-sprint full county operational. |
| Scottsdale coverage | **YES**. County parcels: 150,207 rows; city zoning layer: 1,937 polygons. |
| Paradise Valley coverage | **YES**. County parcels: 10,071 rows; town zoning layer: 464 polygons / 427 nonblank zone rows. |
| Recommended dispatch | **Strong next queue item** after Contra Costa; better than Allegheny if Master wants two 57-list polygons. |

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `Maricopa` match.
- `/api/admin/coverage`: no `Maricopa` row.

Maricopa remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Primary source: Maricopa County GIS / Assessor parcel data.

Candidate sources checked:

- Maricopa Assessor shapefile item: `https://www.arcgis.com/home/item.html?id=c937f17330f64e64abd41976fc8bb17f`
- Maricopa County Parcel map service: `https://gis.maricopa.gov/arcgis/rest/services/IndividualService/Parcel/MapServer`
- **Recommended live source:** `https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Parcel_Data_View/FeatureServer/0`

The shapefile item is public and explicitly describes all active parcels in Maricopa County, but the hosted `Parcel_Data_View` FeatureServer is the better adapter target because it is directly queryable and includes parcel geometry plus rich assessor attributes.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `ASR_Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Arizona Central State Plane, `wkid=2868` |
| Max record count | 2,000 |
| Total parcel count | 1,742,671 |
| Full parcel bbox, WGS84 | `[-113.354304, 32.687847, -111.076757, 34.044230]` |

Observed parcel fields include:

`APN`, `APNDash`, `APNDashSplit`, address fields, `PropertyCity`, owner fields, sale/deed fields, subdivision fields, `PropertyUseCode`, `PropertyUseDescription`, `TaxingDistrictCode`, `TaxingDistrictDescription`, legal-class fields, tax fields, lat/long, and geometry fields.

Class C gate result: **FAIL**. `PropertyUseCode`, `PropertyUseDescription`, `TaxingDistrictCode`, and legal-class fields are assessor/tax fields, not municipal zoning district codes.

## Target Parcel Coverage

Scottsdale county parcel query:

- Query: `UPPER(PropertyCity)='SCOTTSDALE'`
- Count: 150,207
- Parcel bbox, WGS84: `[-111.994941, 33.376245, -111.466830, 33.964735]`

Sample Scottsdale rows:

| APN | APN dashed | Address | Use code | Use description | Tax district |
|---|---|---|---|---|---|
| `13031006D` | `130-31-006D` | null | `9780` | Municipal miscellaneous improved property | Scottsdale U.S.D. in City of Scottsdale |
| `13032001R` | `130-32-001R` | `3380 N HAYDEN RD` | `2030` | Restaurant fast food | Scottsdale U.S.D. in City of Scottsdale |
| `13001072` | `130-01-072` | `6559 E INDIAN SCHOOL RD` | `9700` | Municipal vacant land | Scottsdale U.S.D. in City of Scottsdale |
| `13003023` | `130-03-023` | `3803 N APACHE WAY` | `0141` | SFR urban subdivided | Scottsdale U.S.D. in City of Scottsdale |
| `13003066` | `130-03-066` | `6617 E 1ST ST` | `0131` | SFR urban subdivided | Scottsdale U.S.D. in City of Scottsdale |

Paradise Valley county parcel query:

- Query: `UPPER(PropertyCity)='PARADISE VALLEY'`
- Count: 10,071
- Parcel bbox, WGS84: `[-112.012889, 33.507901, -111.919570, 33.582549]`

Sample Paradise Valley rows:

| APN | APN dashed | Address | Use code | Use description | Tax district |
|---|---|---|---|---|---|
| `16403122` | `164-03-122` | `6600 N 39TH PL` | `0151` | SFR urban subdivided | Creighton S.D. in City of Phoenix |
| `16403123` | `164-03-123` | `6650 N 39TH PL` | `0151` | SFR urban subdivided | Creighton S.D. in City of Phoenix |
| `16403124` | `164-03-124` | `6700 N 39TH PL` | `0161` | SFR urban subdivided | Creighton S.D. in City of Phoenix |
| `16403125` | `164-03-125` | `6750 N 39TH PL` | `0011` | Vacant residential urban subdivided | Creighton S.D. in City of Phoenix |
| `16403146` | `164-03-146` | `3910 E SIERRA VISTA DR` | `0161` | SFR urban subdivided | Creighton S.D. in City of Phoenix |

Conclusion: both 57-list centers are covered in the county parcel source. Paradise Valley is its own incorporated town, but the canonical parcel source still covers it.

## County Zoning Layer

Maricopa County PlanNet publishes a public zoning layer:

- Service: `https://gis.maricopa.gov/arcgis/rest/services/PND/PlanNet/MapServer/11`

Live fields include `ZONE`, `APN`, `JURIS`, and `EDIT_DATE`; sample rows have `JURIS='COUNTY'` and zones such as `C-1` and `AD-3`.

This layer is useful for unincorporated county planning, but it does not solve Scottsdale or Paradise Valley. It should not be used as the target-city Class A source.

## Scottsdale Zoning

Scottsdale is the strongest Maricopa target.

Public sources:

- Scottsdale zoning resources: `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning`
- Scottsdale Basic Zoning Ordinance / Municode: `https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR`
- Scottsdale Article XI Land Use Tables link appears on the city zoning resources page.
- Scottsdale zoning FeatureService item: `https://www.arcgis.com/home/item.html?id=b79779cd29be4786906835daa7f4c748`
- Live zoning layer: `https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/24`

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Arizona Central State Plane, `wkid=2868` |
| Count | 1,937 |
| Zoning bbox, WGS84 | `[-111.960916, 33.447629, -111.756064, 33.900477]` |
| Parcel bbox, WGS84 | `[-111.994941, 33.376245, -111.466830, 33.964735]` |
| Bbox primitive | **Does not pass against raw `PropertyCity='SCOTTSDALE'` parcels**. Rectangular overlap is roughly 30% of the postal-city parcel bbox. This likely reflects `PropertyCity` noise outside city limits, so Lane A must use an actual Scottsdale city-boundary filter or the city parcel/zoning source before claiming Class A. |

Fields:

- `comparable_zoning`
- `full_zoning`

Sample rows:

| Comparable zoning | Full zoning |
|---|---|
| `R1-18` | `R1-18 PCD ESL` |
| blank | `D/OC-2 DO` |
| blank | `D/RCO-2 PBD DO` |
| blank | `C-2` |
| blank | `R1-7 ESL` |
| blank | `C-O` |
| blank | `S-R (C)` |
| blank | `R1-7 PRD` |

Scottsdale verdict: **Class B sprintable; Class A not yet verified**. The city zoning layer is machine-readable and the ordinance has zone-code-indexed land-use tables. Use `full_zoning` as the source code after preview, with a normalization strategy for overlays/suffixes. Do not run county-parcel spatial backfill from raw `PropertyCity='SCOTTSDALE'` without a city-boundary prefilter.

## Paradise Valley Zoning

Paradise Valley is separately incorporated and has its own public GIS.

Public sources:

- Town GIS portal: `https://www.paradisevalleyaz.gov/699/Public-GIS-Maps-Portal`
- Public Town Information Experience app: `https://experience.arcgis.com/experience/98b86f113846439ab57944442d11fd23`
- Public Viewer web map item: `cb5fafde86154d459467937679279a25`
- Live zoning layer: `https://gis.paradisevalleyaz.gov/arcgis/rest/services/Community_Development/Planning_and_Zoning/MapServer/7`
- Town code page: `https://www.paradisevalleyaz.gov/281/Town-Code`
- Zoning map PDF from prior diagnostic: `https://www.paradisevalleyaz.gov/DocumentCenter/View/277/Zoning-Map`

The town GIS page says the Town Information Map Application includes topics such as zoning, future land use, SUP properties, and public facilities. The Experience app resolves to the `Planning_and_Zoning` MapServer, where layer 7 is `Zoning`.

Live zoning probe:

| Check | Result |
|---|---:|
| Layer name | `Zoning` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Arizona Central State Plane, `wkid=2868` |
| Total zoning rows | 464 |
| Nonblank `ZONECLASS` rows | 427 |
| Zoning bbox, WGS84 | `[-112.012889, 33.509322, -111.917152, 33.582538]` |
| Parcel bbox, WGS84 | `[-112.012889, 33.507901, -111.919570, 33.582549]` |
| Bbox primitive | Passes; zoning bbox overlaps nearly all Paradise Valley parcel bbox. |

Fields:

- `ZONECLASS`
- `GlobalID`
- edit metadata

Sample nonblank rows:

| Zone class |
|---|
| `OSP-Open Space Reserve` |
| `Public School` |
| `R-10` |

Paradise Valley verdict: **Class A source candidate; Class B directory may be manual/narrative**. The zoning geometry is machine-readable and the bbox primitive passes, but the ordinance structure is simpler and more narrative than Scottsdale's land-use tables.

## Lane A Execution Shape

Recommended staged plan:

1. Register Maricopa County in preview.
2. Ingest county parcels from `Parcel_Data_View/FeatureServer/0`.
3. Normalize parcel identity:
   - `parcel_id`: `APN`
   - alternate ID: `APNDash` / `APNDashSplit`
   - address: `PropertyFullStreetAddress`
   - municipality/subjurisdiction: `PropertyCity`
   - source provenance: Maricopa Assessor/County GIS URL + pull timestamp
4. Do **not** classify as Class C; parcel rows do not carry zoning.
5. Ingest target-city zoning layers in preview:
   - Scottsdale: `OpenData/MapServer/24`, `full_zoning`
   - Paradise Valley: `Planning_and_Zoning/MapServer/7`, `ZONECLASS`
6. Run strengthened Class A pre-flight before backfill:
   - district bbox covers >=50% of parcel bbox: source probe passes for Paradise Valley; Scottsdale fails against raw `PropertyCity='SCOTTSDALE'` and needs a city-boundary or city-parcel prefilter before retrying.
   - 1,000-parcel `ST_Within` dry-run >=50% match: **still required in preview**.
7. If preview passes, backfill target-city parcel `zoning_code` from city zoning polygons.
8. Author `backend/data/maricopa_az_zoning_directory.json` for Scottsdale + Paradise Valley proof only.
9. If Master wants full county operational, expand to Phoenix/Tempe/Chandler/Gilbert/etc. later; do not make first proof wait for full county.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Parcel adapter/source config for Maricopa FeatureServer | 6-10h |
| Preview parcel ingest and QA | 4-8h |
| Scottsdale zoning ingest + city-boundary/prefilter validation | 5-8h |
| Paradise Valley zoning ingest + preview spatial backfill | 3-5h |
| Strengthened Class A pre-flight and dry-run | 2-4h |
| Scottsdale directory from Municode Article XI | 6-10h |
| Paradise Valley directory from town code/map | 4-8h |
| Two-city proof total | 3-5 days |
| Full county operational expansion | 1-2+ weeks minimum |

## Expected Coverage and Audit Outcome

Parcel load alone creates roughly 1.74M Maricopa parcels but no zoning code. It will not clear audit gates.

Scottsdale + Paradise Valley together represent 160,278 parcel rows, about 9.2% of the county parcel source. That is enough for a meaningful 57-list proof but not enough for whole-county operational readiness.

If the product can register city-level jurisdictions, Scottsdale and Paradise Valley can be proof targets. If audit remains county-level only, Maricopa will remain partial until more large incorporated jurisdictions are added and matrix coverage is broadened.

## Risk Register

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| No embedded parcel zoning | High | County parcel layer has assessor use/tax fields only. | Treat as Class A/B, not Class C. |
| County-level audit mismatch | High | Scottsdale + Paradise Valley are only 9.2% of county parcels. | Scope as two-city proof or plan broad municipal expansion. |
| Scottsdale bbox mismatch | High | County parcels with `PropertyCity='SCOTTSDALE'` extend well beyond the city zoning bbox, failing the bbox primitive against the raw county-city field. | Use actual city boundary/spatial match or city parcel source in preview; expect postal-city noise in `PropertyCity`. |
| Paradise Valley blank zone rows | Medium | 37 of 464 town zoning rows have blank `ZONECLASS`. | Filter blanks and preserve unmatched polygons in QA. |
| Zoning-code normalization | Medium | Scottsdale `full_zoning` contains overlays/suffixes like `R1-18 PCD ESL`; Paradise Valley `ZONECLASS` includes descriptive labels. | Keep raw source code plus normalized primary district code. |
| Coordinate systems | Medium | County and city sources use Arizona Central State Plane `wkid=2868`; some county map services use Web Mercator. | Reproject to WGS84/PostGIS geometry during ingest; preserve source SRID. |
| API pagination | Medium | County parcel FeatureServer max record count is 2,000; 1.74M rows require robust paging. | Use objectId batching / existing ArcGIS pagination. |
| Ordinance structure | Low/Medium | Scottsdale has Article XI land-use tables; Paradise Valley is more narrative/estate-residential. | Author Scottsdale first; keep Paradise Valley directory tighter and manual if needed. |

## Recommendation

Keep Maricopa AZ as the stronger next queue item after Contra Costa if Master wants a two-polygon proof.

The best Lane A ticket is:

- County parcel ingest from Maricopa `Parcel_Data_View`.
- Preview-only spatial backfill for Paradise Valley and a city-boundary-filtered Scottsdale subset.
- Directory proof for Scottsdale first, Paradise Valley second.
- No full-county operational claim until city-level registration or broader municipal zoning coverage is resolved.

If both city spatial gates fail, pivot to **Allegheny County, PA** for a smaller Fox Chapel proof, or to **Hennepin MN / Oakland MI** for the next single-county source-scoping queue.
