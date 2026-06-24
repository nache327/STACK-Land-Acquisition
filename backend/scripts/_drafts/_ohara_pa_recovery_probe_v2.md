# O'Hara PA recovery probe v2

Date: 2026-06-23
Scope: read-only follow-up probe for an O'Hara Township PA zoning-code source after PR #330 blocked O'Hara. No ingest, no database writes, no matrix work.

## Verdict

**HALT for Class B adapter.** No authoritative anonymous zoning polygon source surfaced for O'Hara Township. Do not build `perm_muni_ohara_pa_zoning.py` from the sources found here.

**PIVOT only if Master authorizes PDF/manual tooling.** The official O'Hara zoning map PDF is directly reachable and was exported from ArcGIS Pro, but the downloaded file behaves as raster/tiled imagery rather than an extractable vector zoning layer. It is a map-extraction/manual candidate, not a fast FeatureServer adapter.

Expected fire effort if PDF/manual path is approved: **4-8 hours** for georeferencing/color segmentation/manual cleanup plus a separate validation pass. Expected fire effort for live Class B adapter: **not available** until a municipal/vendor FeatureServer or GIS export is acquired.

## Summary table

| Path | URL | HTTP / result | Content sample | Verdict |
|---|---|---:|---|---|
| Official township page | `https://www.ohara.pa.us/` | `403` | Cloudflare "Just a moment..." challenge | Blocked for curl |
| Official zoning page | `https://www.ohara.pa.us/zoning-ordinance` and `/zoning-hearing-board/pages/zoning-code-zoning-map-and-zoning-hearing-board-application` | `403` | Cloudflare challenge | Blocked for curl |
| Official zoning map PDF | `https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf` | `200` | PDF 1.7, 20,861,469 bytes, Creator `Esri ArcGISPro 3.3.0.52636`, one page | PIVOT only |
| PDF vector/geospatial extraction | downloaded PDF | GDAL opens as `PDF/Geospatial PDF`; `ogrinfo` fails; `pdfimages` lists tiled JPEG images; `pdftotext` empty | No extractable vector district polygons found | Not adapter-ready |
| O'Hara ZoningHub | `https://ohara.zoninghub.com/api/accounts/info` | `200` | `{"id":0,"name":null,"domain":null,"state":"None","status":"In Development","isArcGis":true,...}` | HALT |
| O'Hara ZoningHub layers | `https://ohara.zoninghub.com/api/map/layers?` | `200` | Only `Applications` and `Nonconformities`; no `Base Zoning`; no ArcGIS URL | HALT |
| ZoningHub variants | `oh0450`, `ohara-pa`, `ohara-pa-township`, `oharapa`, `ohara-township`, `ohara-township-pa` | `200` | same id `0` in-development shell | HALT |
| ArcGIS `O'Hara Fox Chapel` service | `https://services9.arcgis.com/Guv5jJnoQM8GFnGs/arcgis/rest/services/OFC/FeatureServer` | `200` | Layers `FoxChapel` and `OHara` | Boundary only |
| ArcGIS `OHara` layer | `.../OFC/FeatureServer/1` | `200`, count `1` | fields `NAME`, `TYPE`, `LABEL`, `MUNICODE`, etc.; sample `NAME="O'HARA"`, `LABEL="O Hara Township"`, `MUNICODE="931"` | Boundary only |
| ArcGIS Online search | `O Hara Township`, `Ohara Township`, `"zoning" "O Hara" "Pennsylvania"` | `200` | no relevant zoning FeatureServer; unrelated voter/park/stormwater items | HALT |
| Allegheny County ArcGIS owner search | `owner:AlleghenyCounty zoning` | `200`, total `0` | no county zoning items | HALT |
| Allegheny County ArcGIS org search | `orgid:vdNDkVykv9vEWFX4 zoning` | `200`, total `79` noisy results | council districts, police zones, trails, municipal boundaries, parcels, opportunity zones | HALT |
| Allegheny services catalog | `https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services?f=pjson` | `200` | contains `Land_Use`, `Future_Land_Use`, municipal boundaries, parcels; no zoning-named service | HALT |
| County `Land_Use` | `.../Land_Use/FeatureServer/0` | `200` | fields `FEATURECOD`, `UPDATE_YEA`; renderer values such as `Woodland`, `Athletic Field`, `Cultivated Field` | Not zoning |
| County `Future_Land_Use` | `.../Future_Land_Use/FeatureServer` | `200` | "Future Land Use, Allegheny Places"; layers `Places`, `Municipal Boundaries`, `Transportation Projects`, etc. | Not zoning |
| WPRDC ordinance/assessment | `https://data.wprdc.org/...municipal-land-use-ordinances`; property assessments | `200` | ordinance-review CSV and assessment use/class resources | Not district geometry |
| Wayback official PDF | CDX for zoningmap.pdf | `200` snapshots | `20210811171744`, `20231207042349`, `20240228120142` PDF snapshots | PDF fallback only |
| Wayback official page | CDX for zoning page | `200` snapshot | `20230415071431` HTML snapshot | No machine-readable source surfaced |
| Wayback ZoningHub wildcard | `*.zoninghub.com/*ohara*` | no O'Hara-specific account hits; generic ZoningHub homepage snapshots only | no recovered config URL | HALT |
| Zoneomics mirror | `https://www.zoneomics.com/zoning-maps/pennsylvania/ohara-township` | `200` | page metadata lists code set `C, CD-1, CD-2, R-1, R-2, R-3, R-4, SM` | Commercial mirror; not authoritative ingest source |

## Probe details

### 1. Official township site and PDF

The township website remains Cloudflare-gated to curl:

```text
https://www.ohara.pa.us/
HTTP/2 403
sample: <!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>...

https://www.ohara.pa.us/zoning-ordinance
HTTP/2 403
sample: <!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>...
```

The direct map asset is reachable:

```text
https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf
HTTP/2 200
file: PDF document, version 1.7
size: 20,861,469 bytes
```

PDF inspection:

```text
pdfinfo:
Creator: Esri ArcGISPro 3.3.0.52636
CreationDate: Tue Mar 4 02:48:18 2025 MST
Pages: 1
Page size: 2592 x 1728 pts

gdalinfo:
Driver: PDF/Geospatial PDF
Size is 2592, 1728
Corner Coordinates are pixel coordinates only

ogrinfo:
failed - unable to open '/tmp/ohara_zoningmap.pdf'

pdfimages:
multiple tiled JPEG images at 300 ppi

pdftotext:
no extracted zoning-map text
```

Interpretation: the map is official and current enough to preserve as a fallback, but it is not a direct polygon source. It may be workable through a GeoPDF/raster/manual extraction workflow.

### 2. ZoningHub and MapLink

Unlike Fox Chapel's stale ZoningHub config, O'Hara has only an in-development shell:

```text
https://ohara.zoninghub.com/api/accounts/info
HTTP 200
{"id":0,"name":null,"domain":null,"state":"None","status":"In Development","isManitowoc":false,"isArcGis":true,"inDevelopment":true,"softLaunch":false,"demo":false}
```

Layer API:

```text
https://ohara.zoninghub.com/api/map/layers?
HTTP 200
len=2
layers:
  - Applications, link `/api/applications/features`, arcGISLayerType `geojson`
  - Nonconformities, link `/api/nonconforms/features`, arcGISLayerType `geojson`
```

There is no `Base Zoning` layer, no ArcGIS FeatureServer URL, no zoning field mapping, and no renderer code set.

Also tested likely subdomains:

```text
https://oh0450.zoninghub.com/api/accounts/info
https://ohara-pa.zoninghub.com/api/accounts/info
https://ohara-pa-township.zoninghub.com/api/accounts/info
https://oharapa.zoninghub.com/api/accounts/info
https://ohara-township.zoninghub.com/api/accounts/info
https://ohara-township-pa.zoninghub.com/api/accounts/info
```

All returned the same in-development id `0` shell. This is not a stale-config recovery path like Fox Chapel.

### 3. ArcGIS Online and the `O'Hara Fox Chapel` service

ArcGIS search for `O Hara Township` found one relevant-looking service:

```text
title: OFC
owner: SarahERizk
url: https://services9.arcgis.com/Guv5jJnoQM8GFnGs/arcgis/rest/services/OFC/FeatureServer
```

Service metadata:

```json
{
  "serviceDescription": "O'Hara Fox Chapel",
  "layers": [
    {"id": 0, "name": "FoxChapel", "geometryType": "esriGeometryPolygon"},
    {"id": 1, "name": "OHara", "geometryType": "esriGeometryPolygon"}
  ]
}
```

Layer 1 (`OHara`) is a municipal boundary, not zoning:

```json
{
  "count": 1,
  "sample": {
    "NAME": "O'HARA",
    "TYPE": "TOWNSHIP",
    "LABEL": "O Hara Township",
    "MUNICODE": "931",
    "ACRES": 2247.91699218
  }
}
```

Fields include municipal-boundary attributes (`NAME`, `TYPE`, `LABEL`, `COG`, `SCHOOLD`, `FIPS`, `MUNICODE`) and no zoning-code field.

Other ArcGIS Online searches:

```text
O Hara Township
Ohara Township
"zoning" "O Hara" "Pennsylvania"
```

No O'Hara zoning FeatureServer surfaced. Results were unrelated high-hazard, park, stormwater, voter, and broad opportunity-zone items.

### 4. Allegheny County GIS aggregate layers

Allegheny County owner search:

```text
https://www.arcgis.com/sharing/rest/search?q=owner%3AAlleghenyCounty%20zoning&f=json&num=20
HTTP 200
total: 0
```

Allegheny org search for zoning returned noisy non-zoning layers:

```text
Council_Districts
PGH_Police_Zones
Trails
Municipal Boundaries
Parcel Boundaries
Opportunity Zones
DPW districts
Watersheds
```

The services catalog includes `Land_Use` and `Future_Land_Use`, but those are not municipal zoning.

`Land_Use/FeatureServer/0` fields:

```text
FID
OBJECTID
SYSTEMID
USERID
FEATURECOD
UPDATE_YEA
```

Renderer values include:

```text
Woodland
Athletic Field
Cultivated Field
Nursery and Orchard
Uncoded Land Area
```

This is land-cover/current-use classification, not O'Hara zoning districts.

`Future_Land_Use/FeatureServer` is an Allegheny Places planning service with layers like `Places`, `Municipal Boundaries`, `Trails`, `Transportation Projects`, and `Existing Land Use`. It is not a township zoning source.

### 5. WPRDC

WPRDC package search returns:

```text
Allegheny County Municipal Land Use Ordinances
resource: ordinance-reviews-thru-december-2021.csv

Allegheny County Property Assessments
resources: assessments CSV/API and data dictionary
```

This is unchanged from PR #330. The ordinance dataset contains review/amendment records, not zoning polygons. Assessment `CLASS` / `USECODE` fields describe broad existing property use, not ordinance zoning districts. They cannot defensibly populate `parcels.zoning_code`.

### 6. Wayback Machine

Official zoning map PDF CDX snapshots:

```text
20210811171744  https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf  200  application/pdf
20231207042349  https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf  200  application/pdf
20240228120142  https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf  200  application/pdf
```

Official zoning page CDX snapshot:

```text
20230415071431  https://www.ohara.pa.us/zoning-hearing-board/pages/zoning-code-zoning-map-and-zoning-hearing-board-application  200  text/html
```

ZoningHub wildcard query for `*.zoninghub.com/*ohara*` did not return an O'Hara account/config snapshot. It returned only generic ZoningHub homepage snapshots.

### 7. Other vendor/commercial paths

Targeted searches for OpenGov, Tyler, CivicPlus, Granicus, Pictometry/ConnectExplorer, and `gis-allegheny.com` did not surface an authoritative O'Hara zoning layer. `gis-allegheny.com` remains non-viable as a recovery domain.

Zoneomics has a public page:

```text
https://www.zoneomics.com/zoning-maps/pennsylvania/ohara-township
HTTP/2 200
metadata code set: C, CD-1, CD-2, R-1, R-2, R-3, R-4, SM
```

This is a commercial mirror and not an authoritative source URL for STACK ingestion. It is useful only as a weak cross-check that the PDF/manual code set likely includes those eight district labels.

## Recommendation

1. **Do not build a Class B adapter now.** No FeatureServer/MapServer/shapefile/GeoJSON source exists in the probed public paths.
2. Keep O'Hara in the LOW/PDF backlog unless Master authorizes manual extraction.
3. If Master wants to pursue O'Hara anyway, use the official `zoningmap.pdf` as the source artifact and run a PDF/manual polygon workflow, with Zoneomics' code set only as a non-authoritative cross-check.
4. Stronger acquisition path: ask O'Hara Township or its GIS contractor for the ArcGIS Pro source export behind the March 2025 zoning map PDF.

