# Four Stuck Munis Alternate Zoning-Code Source Probe

**Date:** 2026-06-22
**Status:** Read-only diagnostic. No code changes, ingest, matrix authoring, or database writes.
**Scope:** Bloomfield Township MI, Franklin MI, Fox Chapel Borough PA, and O Hara Township PA. All four have per-muni jurisdictions and matrix substrate, but `parcels.zoning_code` is null, so they cannot flip operational without a zoning-code source.

## Bottom Line

| Muni | Verdict | Best source found | Field / code path | Lane A wall-clock if Master accepts | Risk |
| --- | --- | --- | --- | ---: | --- |
| Bloomfield Township, MI | **BLOCKED for immediate flip** | Official ordinance + zoning-map PDFs only | No parcel zoning field; no live zoning FeatureServer found | 4-8h if GeoPDF/vector extraction is authorized; otherwise defer | PDF/manual geometry; assessing fields are not zoning |
| Franklin, MI | **BLOCKED for immediate flip** | Current official zoning-map PDF only | No parcel zoning field; no live zoning FeatureServer found | 3-6h if GeoPDF/vector extraction is authorized; otherwise defer | PDF/manual geometry; small parcel count but no machine-readable zones |
| Fox Chapel, PA | **PARTIAL / source-recovery path** | ZoningHub API exposes stale ArcGIS layer config | Expected `ZONECLASS` field; direct FeatureServer URL now returns ArcGIS `Invalid URL` | 0.5-1h if ZoningHub/Borough restores service; 3-6h via PDF/GeoPDF | Strongest near-hit, but not fireable anonymously today |
| O Hara, PA | **BLOCKED for immediate flip** | WPRDC ordinance-review rows + assessment land-use only | WPRDC `CLASS` / `USECODE` are use/assessment classes, not zoning districts | 4-8h if map extraction or municipal data request succeeds; otherwise defer | No public zoning layer; Cloudflare blocks township page curl |

**Campaign verdict:** 0 of 4 are immediately fireable from a defensible zoning-code source. Fox Chapel is the only meaningful near-unlock because ZoningHub still publishes layer metadata pointing to a base-zoning service and code field. The ArcGIS backing service is no longer queryable, so this is a **B2B/vendor or borough data-request path**, not a Lane A anonymous-ingest path.

If Master accepts lower-fidelity land-use substitution, WPRDC and Oakland assessing fields could label broad residential/commercial/industrial use, but that would not be ordinance-precision zoning and would violate the campaign's current truthfulness discipline.

## Shared Finding: Parcel Fields Are Not Zoning

### Oakland County MI parcel source

Source:

```text
https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1
```

Live schema fields relevant to this probe:

```text
CVTTAXCODE
CVTTAXDESCRIPTION
PIN
CLASSCODE
SITEADDRESS
SITECITY
STRUCTURE_DESC
```

`CVTTAXDESCRIPTION` is the municipal/civil-taxing-unit key, not zoning. `CLASSCODE` is an assessing class. `STRUCTURE_DESC` is building style. None can produce district codes such as Bloomfield Township `R-1`, `R-2`, `B-2`, `O-1`, or Franklin village zoning districts.

Bloomfield Township sample distribution:

```text
CLASSCODE  STRUCTURE_DESC   count
401        Colonial/2Sty    7,521
401        Ranch            4,466
407        Ranch            1,848
407        Colonial/2Sty    1,571
401        TriLevel/Quad    1,449
402        blank              592
201        blank              279
```

Franklin sample distribution:

```text
CLASSCODE  STRUCTURE_DESC   count
401        Colonial/2Sty      378
401        Ranch              369
401        Contemporary       115
402        blank               80
401        Other               56
```

These are useful for owner/property analytics, not `parcels.zoning_code`.

### Allegheny County PA parcel + assessment sources

Parcel geometry source:

```text
https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0
```

Live parcel fields are sparse:

```text
PIN
MAPBLOCKLOT
MUNICODE
CALCACREAGE
NOTES
PSEUDONO
COMMENTS
```

No zone-equivalent field exists in the parcel layer.

WPRDC assessment source:

```text
https://data.wprdc.org/dataset/property-assessments
```

WPRDC assessment dictionary defines:

```text
CLASS / CLASSDESC    Broad general use of parcel: residential, utilities, industrial, commercial, other, government, agricultural
USECODE / USEDESC    More detailed primary use; about 200 categories
```

Fox Chapel + O Hara assessment sample:

```text
MUNICODE  CLASSDESC    USECODE  USEDESC                     count
931       RESIDENTIAL  010      SINGLE FAMILY               3,126
868       RESIDENTIAL  010      SINGLE FAMILY               1,845
931       RESIDENTIAL  050      CONDOMINIUM                   347
931       RESIDENTIAL  100      VACANT LAND                   346
868       RESIDENTIAL  100      VACANT LAND                   138
931       COMMERCIAL   447      OFFICE - 1-2 STORIES           32
931       COMMERCIAL   480      OFFICE/WAREHOUSE               31
931       INDUSTRIAL   340      LIGHT MANUFACTURING            27
```

This can identify broad existing land use but cannot distinguish Fox Chapel `A`, `B`, `C`, `D`, `I-O` by parcel or O Hara zoning districts. Treat it as **not acceptable for zoning_code population** unless Master deliberately lowers the truthfulness bar.

## Bloomfield Township, MI

### Sources Probed

- Oakland parcel layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Oakland county composite planning layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseLandUseMapService/MapServer/15`
- Bloomfield Township Planning & Zoning page: `https://www.bloomfieldtwp.org/pbo/planning-zoning/`
- Bloomfield Township zoning ordinance page: `https://www.bloomfieldtwp.org/clerk/zoning-ordinance/`
- Bloomfield Township zoning map PDF: `https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf`
- Bloomfield Township zoning ordinance PDF: `https://www.bloomfieldtwp.org/media/4qbd0omj/2026-03-24-bloomfield-zoning-ordinance_secured.pdf`
- ArcGIS Online searches for `Bloomfield Township zoning`, `Bloomfield Township MI zoning FeatureServer`, `Charter Township Bloomfield zoning`, `Bloomfield Twp zoning map`

### Findings

No municipal zoning FeatureServer surfaced. The township site publishes current ordinance and zoning-map PDFs, both reachable. The Oakland county `Composite Master Plan` layer is still not zoning; it carries future/general land-use values like:

```text
Commercial/Office
Single Family, 14,000 to 43,559 sq. ft.
Recreation/Conservation
```

### Verdict

**Blocked for immediate flip.** No source can populate `parcels.zoning_code` without map extraction/digitization. The only credible path is GeoPDF/vector extraction from the official township zoning map, then spatial backfill. If the PDF is not georeferenceable, manual polygon tracing is required.

Recommended action if Master wants to pursue: **GeoPDF/manual polygon tooling**, not parcel-field crosswalk.

## Franklin, MI

### Sources Probed

- Oakland parcel layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Franklin maps page: `https://www.franklin.mi.us/community/maps.php`
- Franklin zoning map PDF: `https://cms7files.revize.com/franklinmi/document_center/Community/Maps/Zoning%20Map%20Adopted%202.12.24.pdf`
- Franklin municipal code: `https://codelibrary.amlegal.com/codes/franklin/latest/overview`
- ArcGIS Online searches for `Franklin MI zoning FeatureServer`, `Village of Franklin MI zoning`, and `Franklin Michigan zoning map`

### Findings

No municipal zoning FeatureServer surfaced. The Franklin maps page exposes a current official zoning map PDF adopted `2024-02-12`; the PDF is reachable and about 5 MB. The Oakland parcel fields are broad assessing fields only.

### Verdict

**Blocked for immediate flip.** Franklin is a clean small-muni PDF candidate, but it is not an anonymous FeatureServer or parcel-field candidate. A GeoPDF/vector extraction sprint could be relatively small because the jurisdiction has only 1,312 parcels, but Lane A cannot populate zoning codes from current machine-readable public data.

Recommended action if Master wants to pursue: **GeoPDF/manual polygon tooling**; otherwise defer.

## Fox Chapel Borough, PA

### Sources Probed

- Fox Chapel ZoningHub / MapLink UI: `https://fo2332.zoninghub.com/`
- ZoningHub map-layer API: `https://fo2332.zoninghub.com/api/map/layers?`
- ZoningHub account API: `https://fo2332.zoninghub.com/api/accounts/info`
- ZoningHub debug site pages: `https://fo2332.zoninghub.com/api/debug/site-pages`
- Fox Chapel official classifications page: `https://www.fox-chapel.pa.us/185/Classifications`
- Fox Chapel schedule PDF: `https://ecode360.com/attachment/FO2332/FO2332-400a%20Sch%20of%20Dist%20Regs%20Uses%20and%20Structures.pdf`
- Fox Chapel zoning map PDF: `https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf`
- WPRDC parcel and assessment sources

### ZoningHub Near-Hit

The ZoningHub account API returns:

```json
{
  "id": 85,
  "name": "Borough of Fox Chapel",
  "domain": "FO2332",
  "state": "Pennsylvania",
  "status": "Closed",
  "isArcGis": true
}
```

The ZoningHub map-layer API exposes a Base Zoning layer:

```text
Layer name: Base Zoning
Layer URL: https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0
Field mapping: Abbreviation -> ZONECLASS
Renderer field: ZONECLASS
Renderer values: A, B, C, D, I-O
```

This is exactly the missing primitive Lane A needs. However, direct ArcGIS probes against that URL return:

```json
{
  "error": {
    "code": 400,
    "message": "Invalid URL",
    "details": ["Invalid URL"]
  }
}
```

The services folder for `services8.arcgis.com/MkUfAWaYm2SQf4Qa` no longer lists `FO2332_Zoning_20211206_wgs84`, and ArcGIS Online search for `FO2332_Zoning_20211206_wgs84` returns no item.

### Findings

Fox Chapel has the strongest near-unlock:

- ZoningHub confirms the layer was built as GIS, not just a static PDF.
- ZoningHub identifies the district field as `ZONECLASS`.
- ZoningHub renderer confirms the code set expected from the ordinance: `A`, `B`, `C`, `D`, and `I-O`.
- The backing ArcGIS service appears deleted, unpublished, renamed, or moved behind a private/tokened service.

### Verdict

**Partial source, not immediately fireable.** Do not classify as HIGH Path A until Lane A can query the FeatureServer directly or obtain the current replacement URL/token from ZoningHub/Borough.

Recommended source-recovery path:

1. Ask Fox Chapel Borough or ZoningHub/CivicWebware for the current GIS export behind `FO2332` Base Zoning.
2. Request either a live FeatureServer URL/token or a shapefile/GeoJSON export containing `ZONECLASS`.
3. If access is restored, Lane A can run a normal Class A spatial backfill in roughly 0.5-1h because the code set is only five districts.
4. If access is not restored, use the official zoning map PDF as a GeoPDF/manual polygon candidate.

## O Hara Township, PA

### Sources Probed

- WPRDC parcel and assessment sources
- WPRDC Municipal Land Use Ordinances CSV: `https://data.wprdc.org/dataset/allegheny-county-municipal-land-use-ordinances`
- O Hara township website and zoning ordinance page: `https://www.ohara.pa.us/zoning-ordinance`
- ArcGIS Online searches for `O Hara Township zoning FeatureServer`, `Ohara Township zoning`, `O Hara zoning map`, `O Hara ZoningHub`, `O Hara Township Base Zoning`

### Findings

No public ArcGIS FeatureServer surfaced. The township site is Cloudflare-gated from curl in this environment. WPRDC's Municipal Land Use Ordinances dataset contains ordinance-review metadata, not district geometry. It includes O Hara rezoning rows with fields like:

```text
Existing Zoning: SM; CD-2; C, RGOD
Rezoning location: between Freeport Rd & river, to Fox Chapel in the west and Blawnox in the east
```

Those rows are amendment/review records, not a parcel-level zoning map. They cannot populate `parcels.zoning_code`.

### Verdict

**Blocked for immediate flip.** No defensible parcel-field or public zoning-layer source surfaced. The only paths are municipal data request, PDF/map extraction, or a future hidden-service discovery.

Recommended action if Master wants to pursue: request current zoning GIS/map data from O Hara Township planning/zoning staff; otherwise defer to GeoPDF/manual tooling.

## Lower-Fidelity Fallback Analysis

The broad-use fallback is technically possible but not recommended:

- Oakland `CLASSCODE` / `STRUCTURE_DESC` can separate residential-style parcels from commercial/industrial/other classes.
- Allegheny `CLASS` / `USECODE` can separate residential, commercial, industrial, government, public park, vacant land, etc.
- These fields can support **land-use classification**, not **zoning district classification**.

Using them as `parcels.zoning_code` would create pseudo-zone codes like `RESIDENTIAL/SINGLE FAMILY` or `CLASSCODE 401`, which would not match the municipal zoning ordinances or the matrix rows that orchestrator authored. That would be a truthfulness regression and would likely fail future audit/verdict reviews.

## Final Recommendation

1. **Do not expect these four to flip through ordinary LOW Path B matrix authoring.** Matrix substrate alone cannot substitute for `parcels.zoning_code`.
2. **Pursue Fox Chapel first if Master wants a quick salvage attempt.** It has a real ZoningHub source trail and a known district field (`ZONECLASS`), but requires vendor/borough access recovery because the backing ArcGIS service is invalid today.
3. **Treat Bloomfield Township, Franklin, and O Hara as GeoPDF/manual-tooling candidates**, not hidden-FeatureServer candidates.
4. **Reject parcel assessment class fallback** unless Master explicitly accepts lower-fidelity pseudo-zoning. It is not ordinance-precision zoning.

## Source Links

- Oakland Tax Parcel Plus: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Oakland Composite Master Plan layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseLandUseMapService/MapServer/15`
- Bloomfield Township zoning map PDF: `https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf`
- Bloomfield Township zoning ordinance PDF: `https://www.bloomfieldtwp.org/media/4qbd0omj/2026-03-24-bloomfield-zoning-ordinance_secured.pdf`
- Franklin maps page: `https://www.franklin.mi.us/community/maps.php`
- Franklin zoning map PDF: `https://cms7files.revize.com/franklinmi/document_center/Community/Maps/Zoning%20Map%20Adopted%202.12.24.pdf`
- Allegheny parcels: `https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0`
- WPRDC property assessments: `https://data.wprdc.org/dataset/property-assessments`
- WPRDC municipal land-use ordinances: `https://data.wprdc.org/dataset/allegheny-county-municipal-land-use-ordinances`
- Fox Chapel ZoningHub: `https://fo2332.zoninghub.com/`
- Fox Chapel ZoningHub map layers API: `https://fo2332.zoninghub.com/api/map/layers?`
- Fox Chapel stale Base Zoning service URL: `https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/FO2332_Zoning_20211206_wgs84/FeatureServer/0`
- Fox Chapel classifications page: `https://www.fox-chapel.pa.us/185/Classifications`
- Fox Chapel zoning district map PDF: `https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf`
- O Hara zoning ordinance page: `https://www.ohara.pa.us/zoning-ordinance`
