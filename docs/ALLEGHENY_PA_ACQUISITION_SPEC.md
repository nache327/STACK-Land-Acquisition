# Allegheny PA Acquisition Spec

Date: 2026-06-11

Purpose: read-only acquisition spec for a possible Lane A not-loaded ingestion sprint covering Allegheny County, PA, with emphasis on the 57-list wealth pocket Fox Chapel.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **Allegheny County / WPRDC Parcel Boundaries** |
| Parcel source URL | `https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0` |
| Parcel source class | **SINGLE-COUNTY-PORTAL** |
| Verified class | **Class B / PARTIAL** |
| Class C embedded parcel zoning | **NO**. Parcel fields do not carry zoning. |
| Class A separate zoning layer | **NO verified countywide municipal zoning layer found in time box**. |
| Lane A effort estimate | **2-4 days** for Fox Chapel proof; **1+ weeks** if manual zoning-map conversion is required. |
| Expected operational outcome | **Fox Chapel proof only**, not full county operational on first sprint. |
| Fox Chapel coverage | **YES for parcels; PARTIAL for zoning**. County parcels identify Fox Chapel by `MUNICODE=868`; borough zoning is online but machine-readable zoning polygons were not found. |
| Recommended dispatch | **Good fallback / fastest one-polygon proof**, behind Maricopa if Master wants a two-polygon queue item. |

## Current Prod State

Production probes on 2026-06-11:

- `/api/jurisdictions`: no `Allegheny` match.
- `/api/admin/coverage`: no `Allegheny` row.

Allegheny remains `NOT-LOADED-NEEDS-INGEST`.

## Canonical Parcel Source

Primary source: Allegheny County parcel boundaries through the county GIS/WPRDC stack.

- WPRDC dataset page: `https://data.wprdc.org/dataset/allegheny-county-parcel-boundaries1`
- ArcGIS item: `https://www.arcgis.com/home/item.html?id=ebc3eb6a71dc4a60839b6eb80fa176aa`
- Live REST layer: `https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0`
- PASDA parcel catalog is a useful fallback, but WPRDC/Allegheny is the canonical source because WPRDC says it is harvested from Allegheny County GIS.

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Parcel` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Pennsylvania State Plane South, `wkid=102729`, `latestWkid=2272` |
| Max record count | 1,000 |
| Total parcel count | 580,039 |
| Full parcel bbox, WGS84 | `[-80.366078, 40.195260, -79.690669, 40.675466]` |

Observed parcel fields:

`OBJECTID`, `PIN`, `MAPBLOCKLOT`, `MUNICODE`, `CALCACREAGE`, `NOTES`, `PSEUDONO`, `MODIFIEDBY`, `MODIFIEDON`, `CREATEDBY`, `CREATEDON`, `COMMENTS`, `GlobalID`, geometry fields.

Class C gate result: **FAIL**. There is no parcel-level `zoning`, `zone`, `zn`, or district-code field. The layer is parcel geometry + parcel identity/municipality metadata only.

## Fox Chapel Parcel Coverage

Allegheny municipal boundaries are available through a separate public FeatureServer:

- Municipal boundaries service: `https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services/AlleghenyCountyMunicipalBoundaries/FeatureServer/0`

Fox Chapel municipality row:

| Field | Value |
|---|---|
| `NAME` | `FOX CHAPEL` |
| `TYPE` | `BOROUGH` |
| `LABEL` | `Fox Chapel Borough` |
| `FIPS` | 27120 |
| `MUNICODE` | `868` |
| `ACRES` | 5,025.40039062 |
| `SQMI` | 7.85218763 |

County parcel query:

- Query: `MUNICODE=868`
- Count: 2,179
- Fox Chapel parcel bbox, WGS84: `[-79.915271, 40.491778, -79.855270, 40.552093]`

Sample Fox Chapel parcel rows:

| PIN | Map/block/lot | Muni code | Calculated acreage |
|---|---|---:|---:|
| `0170K00018000000` | `170-K-18` | 868 | null |
| `0439E00340000000` | `439-E-340` | 868 | null |
| `0359P00020000000` | `359-P-20` | 868 | 3.72 |
| `0525B00010000000` | `525-B-10` | 868 | null |
| `0224B00140000000` | `224-B-140` | 868 | null |

Conclusion: Fox Chapel parcels are covered in the canonical county parcel source. They are not a per-borough parcel patchwork.

## Zoning Source Assessment

### Countywide / Aggregator Zoning

No usable countywide municipal zoning FeatureServer was found in the time box.

The Allegheny county open-data REST folder exposes the `OPENDATA/Parcels` service and `Address_Points_Test1`; it did not expose a zoning service. ArcGIS search found county municipal boundaries but no public Allegheny/Fox Chapel zoning FeatureServer suitable for Class A spatial backfill.

Class A result: **not verified**. The required district-bbox and `ST_Within` dry-run gates cannot be attempted because no machine-readable Fox Chapel zoning polygon source was found.

### Fox Chapel Borough Zoning

Public sources:

- Fox Chapel zoning chapter / eCode360 entry: `https://ecode360.com/31904910`
- Fox Chapel district classifications page: `https://www.fox-chapel.pa.us/185/Classifications`
- Fox Chapel zoning map route: `https://www.fox-chapel.pa.us/302/Zoning-Map-PDF` redirects toward `DocumentCenter/View/117/Zoning-Map-PDF`

Fox Chapel structure from the prior structural diagnostic remains valid: it is a small borough-level zoning system with a small number of districts, mostly residential/open-space/institutional. It is not a Bergen-style rich use-table sprint, but it is operationally small enough to author manually after parcel load.

Class B result: **YES, but manual/PDF-heavy**. Ordinance and map are online, but no clean zoning polygon FeatureServer was found.

## Lane A Execution Shape

Recommended staged plan:

1. Register Allegheny County in preview.
2. Ingest parcels from `OPENDATA/Parcels/MapServer/0`.
3. Normalize parcel identity:
   - `parcel_id`: `PIN`
   - alternate ID: `MAPBLOCKLOT`
   - subjurisdiction key: `MUNICODE`
   - municipality lookup: join `MUNICODE=868` to Fox Chapel from the public municipal-boundary layer.
4. Do **not** attempt Class C; no parcel zoning field exists.
5. For proof, scope to Fox Chapel:
   - filter parcels by `MUNICODE=868`
   - acquire/digitize borough zoning map or manually assign if a source is found outside this time box
   - author `backend/data/allegheny_pa_zoning_directory.json` for Fox Chapel only
6. If Master wants a full-county jurisdiction, hold operational claims until many municipalities have zoning maps/directories.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Parcel adapter/source config for Allegheny MapServer | 4-8h |
| Preview parcel ingest and QA | 3-5h |
| Municipal-code lookup wiring from Allegheny municipal boundaries | 1-2h |
| Fox Chapel zoning map acquisition/digitization | 4-12h |
| Fox Chapel directory authoring | 4-8h |
| Fox Chapel proof total | 2-4 days |
| Full county operational expansion | Multi-week municipality-by-municipality effort |

## Expected Coverage and Audit Outcome

Parcel load alone creates roughly 580,039 Allegheny parcels but no zoning code. It will not clear audit gates.

Fox Chapel has 2,179 parcel rows, about 0.38% of the county parcel layer. A Fox Chapel-only proof is useful for the 57-list polygon but cannot make the whole county operational under a county-level audit.

If the system supports borough-level jurisdiction registration, Fox Chapel is a plausible fast proof. If the system requires county-level jurisdiction readiness, Allegheny is **not** a first-sprint operational flip.

## Risk Register

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| No embedded zoning | High | Parcel layer has no zoning code field. | Treat as Class B/manual zoning after parcel ingest. |
| No public zoning FeatureServer found | High | Fox Chapel ordinance/map are online, but machine-readable zoning polygons were not found. | Expect PDF/manual conversion unless Lane A discovers a hidden source. |
| County-level audit mismatch | High | Fox Chapel is only 2,179 of 580,039 parcels. | Scope as borough proof or defer county operational claim. |
| Coordinate system | Medium | Parcel and municipal layers use PA State Plane South `wkid=2272`. | Reproject to WGS84/PostGIS geometry during ingest; preserve source SRID. |
| API pagination | Medium | Parcel MapServer max record count is 1,000. | Use objectId batching or standard ArcGIS pagination. |
| Zoning-map route drift | Medium | The Fox Chapel zoning-map route redirects to a DocumentCenter URL that returned inconsistently during curl probe. | Use browser/manual download in Lane A prep; attach archived source path in provenance. |
| Ordinance structure | Low | Fox Chapel is simple but not a Bergen-style use table. | Manual directory is acceptable for proof because district count is small. |

## Recommendation

Keep Allegheny PA queued as the fastest **one-polygon** backup proof, not as the primary next multi-polygon target.

If Contra Costa or Maricopa stalls on preview spatial gates, Allegheny is a reasonable fallback only if Master accepts a Fox Chapel borough proof with manual zoning acquisition. If Master requires whole-county operational status, pivot away from Allegheny and use a stronger city-zoning source target instead.
