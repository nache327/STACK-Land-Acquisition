# Fox Chapel PA vendor recovery probe

Date: 2026-06-23
Scope: read-only diagnostic only. No ingest, no parcel join, no code changes.

## Verdict

**VIABLE.**

The stale ZoningHub-configured service is still dead, but a separate public FeatureServer under the Borough of Fox Chapel ArcGIS owner (`FoxChapelAC`) exposes live zoning polygons:

`https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer/0`

Class rating: **HIGH Path A / Class A candidate**.

Expected fire effort: **45-90 minutes** for a focused Fox Chapel Path A ingest, assuming normal bbox and `ST_Within` preview gates pass. The layer has 72 polygon features, `esriGeometryPolygon`, code field `ZONECLASS`, and the expected five Fox Chapel classes: `A`, `B`, `C`, `D`, `I-O`.

## Best source found

| Field | Value |
| --- | --- |
| Source owner | `FoxChapelAC` |
| ArcGIS item | `bc38d9d6d63b497382dd8da18a692024` |
| Service | `https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer` |
| Layer | `.../FeatureServer/0` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | `102729`, latest `2272` |
| Display/code field | `ZONECLASS` |
| Secondary fields | `ZONEDESC`, `SOURCE`, edit-tracking fields |
| Feature count | 72 |
| Distinct classes | `A`, `B`, `C`, `D`, `I-O` |
| Item extent | `[-79.91580087145336, 40.491147782382754]` to `[-79.85406219882834, 40.55242680644854]` |
| Source/vintage hints | Item created `1453761634000`; modified `1649932626000`; layer edit metadata updated on current read; source field sample is `zoning.shp` |

HTTP/status/sample:

- `GET https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer?f=json`
- HTTP transport status: `200`
- Content sample: `"serviceDescription":"Zoning District"`, `"capabilities":"Create,Delete,Query,Update,Editing,Extract,Sync,ChangeTracking"`, one polygon layer named `"Zoning District"`.

- `GET https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer/0?f=json`
- HTTP transport status: `200`
- Content sample: `"displayField":"ZONECLASS"`, `"geometryType":"esriGeometryPolygon"`, unique-value renderer on `ZONECLASS` with values `A`, `B`, `C`, `D`, `I-O`.

- `GET .../FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json&resultRecordCount=20`
- HTTP transport status: `200`
- Content sample: fields include `ZONECLASS` alias `Zoning Classification`; sample features include `{"OBJECTID":1,"ZONECLASS":"I-O","SOURCE":"zoning.shp"}` and `{"OBJECTID":2,"ZONECLASS":"C","SOURCE":"zoning.shp"}`.

- `GET .../FeatureServer/0/query?where=1%3D1&outStatistics=[count OBJECTID]&f=json`
- HTTP transport status: `200`
- Content sample: `{"feature_count":72}`.

- `GET .../FeatureServer/0/query?where=1%3D1&groupByFieldsForStatistics=ZONECLASS&outStatistics=[count OBJECTID]&orderByFields=ZONECLASS&f=json`
- HTTP transport status: `200`
- Content sample: `A=16`, `B=11`, `C=10`, `D=5`, `I-O=30`.

Recommended next gates before any ingest:

1. Use this live layer as the zoning district source.
2. Run bbox coverage against Fox Chapel parcel bbox / `MUNICODE=868`.
3. Run full or sampled `ST_Within` preview gate against `city='Fox Chapel Borough'`.
4. Spot-check current borough PDF/eCode map against the five class codes and obvious large districts, because the ArcGIS item appears created in 2016 and modified in 2022 even though the service responded with fresh read headers.

## Paths probed

### 1. ZoningHub stale config

`https://fo2332.zoninghub.com/`

- HTTP transport status: `200`
- Content sample: Vite shell with `/assets/index-CDW8Qb2H.js` and `/assets/index-BArCU2LR.css`; title `ZoningHub`.

`https://fo2332.zoninghub.com/api/accounts/info`

- HTTP transport status: `200`
- Content sample: `{"id":85,"name":"Borough of Fox Chapel","domain":"FO2332","state":"Pennsylvania","status":"Closed","isArcGis":true}`.

`https://fo2332.zoninghub.com/api/map/layers`

- HTTP transport status: `200`
- Content sample: Base Zoning layer id `224` with link `https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0`, renderer field `ZONECLASS`; Parcel layer id `370`; Municipal Boundary layer id `78`.

`https://fo2332.zoninghub.com/api/map/layers/224`

- HTTP transport status: `200`
- Content sample: `"type":"Base Zoning"`, `"link":"https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0"`, `"field":"ZONECLASS"`, classes `A`, `B`, `C`, `D`, `I-O`.

`https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0?f=json`

- HTTP transport status: `200`
- ArcGIS payload status: `{"error":{"code":400,"message":"Invalid URL","details":["Invalid URL"]}}`

`https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json&resultRecordCount=5`

- HTTP transport status: `200`
- ArcGIS payload status: `{"error":{"code":400,"message":"Invalid URL","details":["Invalid URL"]}}`

ZoningHub conclusion: stale config confirmed. Not the viable path.

### 2. Borough official site

`https://www.fox-chapel.pa.us/181/Building-Zoning`

- HTTP transport status: `200`
- Content sample: Building and Zoning Office description, Zoning District Map link, contact block for Dan Moretti, Zoning Administrator, 401 Fox Chapel Rd, phone `412-850-5023`.

`https://www.fox-chapel.pa.us/185/Classifications`

- HTTP transport status: `200`
- Content sample: borough divided into five districts: Class `"A"` Residence District, Class `"B"` Residence District, Class `"C"` Residence District, Class `"D"` Residence District, Institutional/Open Space District `(I-O)`.

`https://www.fox-chapel.pa.us/201/Forms-Applications`

- HTTP transport status: `200`
- Content sample: Building and Zoning tab includes `MapLink: Visual Zoning Service` pointing to `https://fo2332.zoninghub.com/`.

`https://www.fox-chapel.pa.us/302/Zoning-Map-PDF`

- HTTP transport status: `302` to `/DocumentCenter/View/117/Zoning-Map-PDF`, then `200`
- Content sample: `application/pdf`, `content-disposition: inline;filename=Zoning%20Map.pdf`, size `1067219` bytes.

`https://www.fox-chapel.pa.us/362/Maps`

- HTTP transport status: `200`
- Content sample: map list includes `Fox Chapel Trails Map (PDF)`, `Map of the Borough of Fox Chapel (PDF)`, and `Zoning Map (PDF)` at `/DocumentCenter/View/117/Zoning-Map-PDF`.

`https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf`

- HTTP transport status: `200`
- Content sample: `application/pdf`, `FO2332-400b Zoning District Map.pdf`, size `463731` bytes.

Official-site conclusion: **PIVOT fallback remains available** via PDF/manual tooling, but it is no longer the best path because the borough ArcGIS FeatureServer is live.

### 3. Allegheny County / WPRDC / PASDA

`https://gisdata.alleghenycounty.us/arcgis/rest/services?f=pjson`

- HTTP transport status: `200`
- Content sample: folders include `Accela`, `ACWebsite`, `Addressing`, `EGIS`, `LandRecords`, `OPENDATA`, etc.; root services only list `SampleWorldCities`.

`https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA?f=pjson`

- HTTP transport status: `200`
- Content sample: OPENDATA folder lists `OPENDATA/Address_Points_Test1` and `OPENDATA/Parcels`; no zoning service in that folder.

WPRDC package search:

- `zoning Allegheny`: HTTP `200`, top results were county block areas, county boundary, cemeteries, parcel boundaries, bridges, landmarks, municipal parks, council districts, hydrology, golf courses.
- `planning Allegheny`: HTTP `200`, top results included parcel boundaries, bridges, public buildings, map index, `Allegheny County Land Use Areas`, soils, roads.
- `land use Allegheny`: HTTP `200`, found `Allegheny County Land Use Areas` and `Allegheny County Municipal Land Use Ordinances`, but not a county zoning polygon layer.

ArcGIS public search:

- `title:zoning AND owner:AlleghenyCounty`: HTTP `200`, total `0`.
- `zoning AND owner:AlleghenyCounty`: HTTP `200`, total `0`.
- `zoning AND orgid:vdNDkVykv9vEWFX4`: HTTP `200`, returned noisy county services such as voting district labels, council districts, police zones, trails, street centerlines, municipal boundaries, and opportunity zones, not Fox Chapel zoning.

County conclusion: no county-level zoning layer verified. County sources remain parcel/municipal-boundary/land-use context only.

### 4. Wayback Machine

`https://web.archive.org/cdx?url=fo2332.zoninghub.com/*&output=json&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200&collapse=digest&limit=100`

- HTTP transport status: `301` then `200`
- Content sample: captures for `https://fo2332.zoninghub.com/`, `contact.aspx`, CSS assets, and highlight/procedure pages from 2022, 2024, and 2025.

`https://web.archive.org/cdx?url=https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer*&output=json&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200&collapse=digest&limit=50`

- HTTP transport status: `301` then `200`
- Content sample: `[]`

Wayback conclusion: no archived stale FeatureServer response found. The useful recovery path came from the `FoxChapelAC` ArcGIS owner inventory, not Wayback.

### 5. Other vendor recovery angles

ArcGIS owner inventory:

`https://www.arcgis.com/sharing/rest/search?q=owner%3AFoxChapelAC&f=json&num=100`

- HTTP transport status: `200`
- Content sample: owner `FoxChapelAC` results include `Address Pnts Parcel 2022`, `Park Land`, `FoxChapel_Boundary`, `Land Trust`, `Parcels 2022`, `Parcel Developments`, `Landslide Risk`, `Land Movement`, and **`Zoning District`** at `https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer`.

`https://www.arcgis.com/sharing/rest/search?q=FO2332_Zoning&f=json&num=20`

- HTTP transport status: `200`
- Content sample: total `0`.

`https://www.arcgis.com/sharing/rest/search?q=owner%3AZoningHub%20Fox%20Chapel&f=json&num=20`

- HTTP transport status: `200`
- Content sample: total `0`.

`https://www.arcgis.com/sharing/rest/search?q=Fox%20Chapel%20zoning&f=json&num=20`

- HTTP transport status: `200`
- Content sample: total `2`, both non-usable for zoning ingest: a CMU StoryMap and an unrelated/test `Urban Design Database`.

`https://services9.arcgis.com/Guv5jJnoQM8GFnGs/arcgis/rest/services/OFC/FeatureServer`

- HTTP transport status: `200`
- Content sample: live `O'Hara Fox Chapel` service with layers `FoxChapel` and `OHara`; fields are municipal-boundary fields such as `NAME`, `TYPE`, `LABEL`, `MUNICODE`, not zoning.

Vendor-domain probes:

- `https://gis-allegheny.com/`: DNS resolution failure.
- `https://www.gis-allegheny.com/`: DNS resolution failure.
- `https://connectexplorer.com/`: HTTP `200`, effective URL `https://expireddomains.com/domain/connectexplorer.com?...`; expired-domain content.
- `https://pictometry.com/` and `https://www.pictometry.com/`: HTTP `200`, effective URL `https://www.eagleview.com/product/eagleview-cloud/government/`; no Fox Chapel zoning source found.
- `https://www.tylertech.com/`: HTTP `200`, generic Tyler site; no Fox Chapel zoning source found.
- `https://www.opengov.com/`: HTTP `200`, generic OpenGov site; no Fox Chapel zoning source found.
- `https://www.digitalgovernment.com/`: HTTP `403` Cloudflare challenge.
- `https://dg.cc/`: TLS failure in curl.

Web search samples:

- Search `Fox Chapel zoning FeatureServer ZONECLASS`: surfaced borough classifications, ZoningHub, Fox Chapel maps/building pages, eCode360, Zoneomics/Regrid commercial pages, Allegheny GIS page, and unrelated results.
- Search `site:connectexplorer.com "Fox Chapel"`, `site:pictometry.com "Fox Chapel" "zoning"`, `site:opengov.com "Fox Chapel" "zoning"`, `site:gis-allegheny.com "Fox Chapel" "zoning"`: no usable Fox Chapel zoning source found.
- Search `Fox Chapel CivicPlus/Granicus/Municode/MapLink`: surfaced borough CivicPlus pages, eCode360/MapLink references, and unrelated records.

Other-vendor conclusion: no Pictometry/ConnectExplorer/Tyler/OpenGov/DG/GIS-Allegheny recovery path found. The working recovery angle is the borough's own ArcGIS account.

## Final recommendation

Use the `FoxChapelAC` `Zoning_District` FeatureServer as the recovery path and promote Fox Chapel from LOW/PDF fallback to a Class A candidate.

Minimum implementation notes for the next, non-diagnostic agent:

- Source URL: `https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer/0`
- Code field: `ZONECLASS`
- Optional name/description field: `ZONEDESC` exists but was null in samples; derive labels from ordinance/PDF/eCode if needed.
- Expected classes: `A`, `B`, `C`, `D`, `I-O`
- Expected feature count: 72
- Expected fire effort: 45-90 minutes including preview gates and citation spot-check.
