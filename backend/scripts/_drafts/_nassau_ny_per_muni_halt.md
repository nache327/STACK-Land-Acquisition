# Nassau NY per-muni wealth-tail source probe

Date: 2026-06-23  
Scope: read-only probe for per-municipality Nassau zoning sources that could bypass the countywide Nassau block. No ingest, no matrix edits, no production writes.

## Verdict

**HALT.** The Nassau countywide block also holds at the probed per-muni wealth-tail level. No target exposed an anonymous public zoning polygon source with parcel-joinable zone codes.

The only Nassau-located ArcGIS candidate found during this pass is Town of Hempstead's public `ToH_Zoning_Maps` service. Live sampling confirmed it is a zoning-map sheet index, not zoning district polygons:

- Source: `https://services6.arcgis.com/bqUwpAFaDo5lm9eK/arcgis/rest/services/ToH_Zoning_Maps/FeatureServer`
- Layer: `1`, `ToH_Zoning_Maps`
- Count: `215`
- Sampled geometry: polygons in Nassau / Town of Hempstead extent
- Sampled fields: `OBJECTID`, `IndexNo`, `FileName`, `Location`, `GlobalID`, `Shape__Area`, `Shape__Length`
- Sample rows: `210, Point Lookout.pdf`, `211, Jones Beach, Point Lookout.pdf`, `212, Jones Beach.pdf`
- Missing for adapter use: no `ZONE`, `ZONING`, `DISTRICT`, or equivalent semantic zone-code field; features represent map-sheet coverage, not zoning districts.

Therefore no Class B adapter was built.

## Probe pattern

For each target I checked:

1. ArcGIS Online / REST discovery for direct FeatureServer or MapServer zoning layers.
2. Municipal website GIS/map pages and zoning-map links.
3. eCode360 / municipal-code presence as text-grounding only.
4. Sampled up to 50 features for live ArcGIS candidates that looked relevant.

## Target verdicts

| Target | Verdict | Evidence |
|---|---|---|
| Village of Garden City | **HALT** | No Garden City NY zoning FeatureServer surfaced. A `Garden City Zoning Layers` FeatureServer was sampled but geocoded to Utah (`-111.44..-111.38`, `41.89..41.99`) and rejected as a false positive. Garden City remains eCode/PDF/source-request only. |
| Village of Old Westbury | **HALT** | Village website exposes map/PDF and eCode links, including `https://www.villageofoldwestbury.gov/182/Maps-of-the-Village-of-Old-Westbury` and `https://ecode360.com/OL0821`; no public FeatureServer/MapServer/GeoJSON zoning polygons surfaced. |
| Village of Brookville | **HALT** | Village website exposes zoning-code/map content through its municipal site (`https://www.villageofbrookville.gov/map`, `https://www.villageofbrookville.gov/Zoningcodeonly`) but no public ArcGIS REST/vector zoning endpoint surfaced. |
| Village of Sands Point | **HALT** | Municipal site and eCode chapter are public (`https://www.sandspoint.gov/`, `https://ecode360.com/SA0704`, Chapter 176), but no anonymous public zoning polygon layer surfaced. Search evidence suggests GIS is consultant/municipal-internal rather than public downloadable data. |
| Village of Roslyn Estates | **HALT** | Public municipal site exists at `https://www.villageofroslynestates.gov/`; eCode zoning chapter exists at `https://ecode360.com/12382820`. No public zoning FeatureServer/MapServer/GeoJSON surfaced. |
| Town of North Hempstead | **HALT** | Town publishes zoning-map PDFs at `https://www.northhempsteadny.gov/departments/buildings/zoning_maps.php` and code at `http://ecode360.com/NO0081`, but no public zoning vector layer surfaced. |
| Town of Hempstead | **HALT** | Public ArcGIS service found, but live sample showed a 215-feature zoning-map PDF sheet index, not zoning district polygons/codes. No adapter-grade zoning polygon source surfaced. |

## ArcGIS candidates sampled

### Rejected: Garden City Zoning Layers

URL: `https://services1.arcgis.com/QjiQKkFtXufcXWpu/arcgis/rest/services/Garden_City_Zoning_Layers/FeatureServer`

Reason rejected: false-positive geography, not Nassau NY.

| Layer | Count | Fields | Sample bbox |
|---|---:|---|---|
| `Overlay` | 15 | `Type`, `GlobalID`, shape fields | `(-111.4110, 41.9056, -111.3862, 41.9598)` |
| `Garden City Zoning` | 139 | `Zone`, `GlobalID`, shape fields | `(-111.4398, 41.8959, -111.3806, 41.9858)` |

Sample values (`Hillside Estates`, `Recreational Residential`, `PUD/PRUD`) also match the false-positive service rather than Nassau's Garden City code examples (`R-40`, `R-20`, `R-12`, `R-8`, `R-6`, `CO`, `C`, `I`).

### Rejected: Town of Hempstead zoning-map index

URL: `https://services6.arcgis.com/bqUwpAFaDo5lm9eK/arcgis/rest/services/ToH_Zoning_Maps/FeatureServer/1`

Reason rejected: map-sheet polygons only; no zoning district semantics.

| Probe | Result |
|---|---|
| Count | `215` |
| Geometry | polygon |
| Sample bbox | `(-73.7549, 40.5749, -73.4678, 40.6304)` |
| Fields | `OBJECTID`, `IndexNo`, `FileName`, `Location`, `GlobalID`, shape fields |
| Sample rows | `Point Lookout`, `Jones Beach, Point Lookout`, `Jones Beach` |

## Structural finding

This confirms Diagnostic PR #361's Nassau warning at the per-muni level:

- Nassau parcel substrate is still not enough because public parcel records do not carry zone codes.
- The named wealth-tail villages expose zoning text/PDF references, not anonymous public zoning polygons.
- Town-level public GIS, where present, is not equivalent to a zoning district layer.
- Several public hints show municipal GIS exists through consultants or internal ArcGIS environments, but not as public source-of-record vector downloads.

## Recommended next action

Use an operator or municipal data-request path instead of further anonymous web probing.

Minimum request:

1. GIS-ready zoning polygon data for the incorporated village or town.
2. Zone code / district field preserved as adopted on the official zoning map.
3. Coordinate reference system and publication/effective date.
4. Permission to use the data for parcel-level zoning validation.

If Master wants a Long Island adapter in the meantime, Nassau should remain parked and the next probe should target Suffolk town-level zoning, where NYS ITS provides a current public parcel substrate but zoning source discovery remains open.
