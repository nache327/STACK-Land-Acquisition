# Wayzata Alt-Source Pivot

Date: 2026-06-24

Scope: read-only last-shot source probe after PR #339 proved the Wayzata zoning
PDF is georeferenced but not semantically coded, and PR #352 halted hatch QA
without operator/PDF-vendor data.

## Verdict

**HALT for public alternative GIS.** No public, GIS-ready Wayzata zoning
FeatureServer, shapefile, GeoJSON, or CSV surfaced from Hennepin Open Data,
Minnesota Geospatial Commons, MetroGIS, Twin Cities public ArcGIS searches, or
the city website. The only credible remaining path is a direct municipal data
request for the source layer used to publish the March 2025 zoning PDF.

## Probe Matrix

| Path | Verdict | Evidence | Production implication |
| --- | --- | --- | --- |
| Hennepin County open data portal | **HALT** | ArcGIS Online/Hennepin probes returned zero zoning hits for `Wayzata zoning`, `Hennepin Wayzata zoning`, `owner:HennepinGIS zoning`, and `Hennepin County zoning FeatureServer`. Hennepin public GIS is still useful for parcels/context, but no municipal zoning district layer surfaced. | No county-hosted Wayzata zoning backfill source. |
| MN GeoCommons | **HALT** | CKAN package API returned `count=0` for `Wayzata zoning`, `Wayzata`, and `municipal zoning`. `regional parcels` returns the known MetroGIS parcel dataset only. | Confirms Minnesota public aggregator is parcel/source context only for Wayzata, not zoning-code geometry. |
| MetroGIS / Twin Cities regional portal | **HALT** | Existing accepted Hennepin spec already found MetroGIS parcels cover Wayzata by CTU, but parcel fields do not carry zoning. Current search did not surface a Wayzata zoning sub-layer. | MetroGIS remains the parcel substrate, not the zoning-code source. |
| Wayzata city website | **HALT** | Planning page links the zoning code and map PDFs. The Maps section exposes `Wayzata-Zoning-Map-Updated-March-2025` plus land-use/design/floodplain/wetland PDFs, with no shapefile, GeoJSON, CSV, ArcGIS REST, or download portal found. | Official public spatial source remains the GeoPDF only. |
| eCode/Municode | **PIVOT: text grounding only** | Wayzata zoning is in City Code Part IX; Chapter 937 includes district/use-table grounding. This supports matrix/citation work but does not assign per-parcel zoning codes. | Useful after a zoning geometry source exists; not an alt polygon source. |
| Commercial/private aggregators | **HALT for production** | Zoneomics exposes a Wayzata marketing page, but no public source-of-record vector download and no acceptable provenance for production parcel backfill. | Do not use as production zoning geometry. |
| Direct municipal contact | **VIABLE request path** | The city Planning page says Community Development administers/enforces zoning and directs zoning information requests to `CommDev@wayzata.org`. | Send the data request below; if provided, replace the PDF-derived geometry path with the official GIS layer. |

## Source URLs Checked

- Wayzata Planning page: `https://www.wayzata.org/236/Planning`
- Official Wayzata zoning PDF: `https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025`
- Hennepin GIS hub: `https://gis-hennepin.hub.arcgis.com/`
- Minnesota Geospatial Commons: `https://gisdata.mn.gov/`
- MetroGIS parcel data page: `https://metrogis.org/how-do-i-get/parcel-data/`
- MetroGIS regional parcels package: `https://gisdata.mn.gov/dataset/us-mn-state-metrogis-plan-regional-parcels`
- Wayzata Municode: `https://library.municode.com/mn/wayzata/codes/code_of_ordinances`

## Recommended Hand-Off

Do not spend more engineering time on public Wayzata source discovery unless the
city replies or a new portal is announced. Wayzata should move to an
operator-assisted/vendor-data request queue. The GeoPDF extraction proof remains
valuable as geometry QA/reference, but it cannot truthfully assign all 21 zone
codes from public PDF data alone.

## Email Template For Master

Subject: GIS-ready zoning district data request for Wayzata zoning map

To: CommDev@wayzata.org

Hello Wayzata Community Development team,

I am working from the City of Wayzata's published zoning materials, including
the "Wayzata Zoning Map (Updated March, 2025)" PDF and Part IX of the City Code.
The PDF appears to have been exported from GIS and is georeferenced, but the
public PDF does not include a reliable district-code attribute for each zoning
polygon.

Would the City be able to provide the GIS-ready zoning district layer used to
produce the March 2025 zoning map? Any of these formats would work:

- Esri File Geodatabase or shapefile
- GeoJSON
- ArcGIS FeatureServer/MapServer endpoint
- CSV only if it includes parcel IDs or geometries

The ideal attribute fields would be the zoning district code and name, such as
`R-1`, `R-2A`, `C-4`, `PUD`, `INS`, or `P`, plus any effective-date or source
metadata available. I am not requesting owner/contact information or any
non-public parcel data; this request is only for zoning district boundaries and
district labels matching the published zoning map.

If the City does not publish this layer directly, could you point me to the GIS
data steward or vendor who maintains the zoning map source data?

Thank you,

[Master name]
