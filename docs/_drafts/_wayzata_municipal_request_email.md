# Wayzata Municipal GIS Data Request Email

To: Wayzata Planning Dept / Community Development

Subject: GIS data request

Hello Wayzata Planning and Community Development team,

I am working on operational zoning mapping for Wayzata using the city's public
zoning materials, including the March 2025 zoning map PDF and Part IX of the
City Code. We can read the published PDF as map geometry, but the PDF does not
reliably expose each polygon's zoning district code as data.

Would the City be willing to provide the GIS-ready zoning district layer used
to produce the current zoning map?

The most useful format would be any of the following:

- Esri shapefile or File Geodatabase
- GeoJSON
- ArcGIS FeatureServer or MapServer endpoint
- CSV only if it includes parcel IDs or polygon geometry

The fields we need are simple: zoning district code and district name for each
zoning polygon, such as `R-1`, `R-2A`, `C-4`, `PUD`, `INS`, or `P`, plus any
source date or effective-date metadata the City maintains. We do not need
owner names, resident contact information, assessment data, or any other
non-public parcel information.

Why we are asking: we are trying to build a zoning-validated parcel map for
Wayzata so parcel-level zoning can be tied back to the City's official zoning
districts rather than inferred manually from a rendered PDF.

What we can provide back: once validated, we can share a parcel-to-zoning
crosswalk or summary output showing each mapped parcel and its zoning district
code. That may be useful as an independent QA artifact against the current
published map.

If the City does not directly maintain this GIS layer, could you point me to
the GIS data steward or mapping vendor who maintains the source data for the
zoning map?

Thank you,

[Master name]
