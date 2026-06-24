# Phase 6 Secondary Munis Probe

Date: 2026-06-24

Scope: read-only diagnostic ranking for wealth-pocket-adjacent secondary
municipalities that could produce opportunistic +0.5-polygon wins without
touching production ingest, parcels, or zone-use matrices.

## Ranked ROI

| Rank | Target | Verdict | Why |
| --- | --- | --- | --- |
| 1 | **Englewood, CO** | **VIABLE** | City ArcGIS exposes zoning polygons and parcel-zoning polygons with `NEWZONE`. Existing docs already mark Englewood matrix-sprintable after ingestion. |
| 2 | **Greenwood Village, CO** | **PIVOT / likely viable after authority QA** | City-owned ArcGIS exposes an Urban zoning layer with `CustomID` district codes and existing parcel layer. Needs confirmation that Urban "existing zoning" is authoritative enough for production, but signal is strong. |
| 3 | **Manchester-by-the-Sea, MA** | **VIABLE source, lower immediate ROI** | Town ArcGIS Hub/AxisGIS sync exposes a `Zoning` polygon layer with direct `ZONING` values. Needs parcel substrate and ordinance/matrix grounding. |
| 4 | **Marblehead, MA** | **PIVOT / QA needed** | Public ArcGIS search finds a `Marblehead_ZoningLandUse` FeatureServer with a zoning layer and `ZONE` values, but several blank/null zone polygons require cleanup and owner/provenance QA. |
| 5 | **Brookville + Old Westbury, NY** | **HALT for immediate production; PIVOT for atlas reconnaissance** | Long Island Zoning Atlas is useful research context and says it digitized/manual-coded 1,200+ districts, but the public app API/vector-tile path did not resolve to an immediately ingestible source. Municipal pages expose maps/eCode, not direct GIS services. Nassau structural fix is still the gating work. |

## 1. Colorado Wealth Tail: Greenwood Village + Englewood + DTC

### Englewood, CO

**Verdict: VIABLE.**

Primary GIS sources:

- Zoning district polygons:
  `https://agiso.englewoodco.gov/public/rest/services/LandUsePlanning/BaseZoningDistrictBoundaries/MapServer/0`
- Parcel-zoning polygons:
  `https://agiso.englewoodco.gov/public/rest/services/Parcels/ParcelsZoningNew/FeatureServer/0`
- Englewood open-data portal:
  `https://data-englewoodgov.opendata.arcgis.com/`

Probe quality:

- Zoning district layer: 94 polygons.
- Distinct `NEWZONE` values sampled: `I-1`, `I-2`, `M-1`, `M-2`,
  `MU-B-1`, `MU-B-2`, `MU-R-3-A`, `MU-R-3-B`, `MU-R-3-C`, `PUD`,
  `R-1-A`, `R-1-B`, `R-1-C`, `R-2-A`, `R-2-B`.
- Useful fields: `NEWZONE`, `TYPE`, `DSCRPT`, `PUDNUM`,
  `Regulations_Link`.
- Parcel-zoning layer: 11,744 polygons with `PIN`, `ADCITY`, `NEWZONE`.

Production note: this is the cleanest secondary candidate in this probe. It
has both district-level geometry and parcel-zoning geometry. The next diagnostic
would be a bounded Arapahoe/Englewood preview source spec, not more source
discovery.

### Greenwood Village, CO

**Verdict: PIVOT / likely viable after authority QA.**

Primary GIS sources:

- City maps page:
  `https://greenwoodvillage.com/593/Maps`
- City-owned parcel data:
  `https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/Parcel_City_and_County_Data/FeatureServer`
- City-owned Urban public-view zoning-like service:
  `https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/b16e6a436dc24550b521986d2a71f11a_public_view_1593194820169/FeatureServer`

Probe quality:

- Parcel layer: 5,742 polygons with `PIN`, situs fields, parcel class/value
  fields, and geometry.
- Urban service layer 1 `Zones`: 6,024 polygons.
- `Zones.CustomID` sampled 28 values: `A`, `B-1`, `B-1 PUD`, `B-2`,
  `B-2 PUD`, `B-3`, `B-3 PUD`, `B-4`, `B-4 PUD`, `L-I`, `M-C`,
  `O-1`, `O-2`, `R-.05 PUD`, `R-.1 PUD`, `R-.25`, `R-.25 PUD`,
  `R-.5 PUD`, `R-.75 PUD`, `R-1.0`, `R-1.0 PUD`, `R-1.5 PUD`,
  `R-2.0`, `R-2.0 PUD`, `R-2.5`, `R-2.5 PUD`, `T.C.`, `Unknown`.
- Layer metadata includes `PlanningMethod='zoning'` and
  `PlanningHorizon='existing'` in sample rows.

Production note: strong but needs a short authority check before ingest because
the service is an Urban planning-model layer, not a plainly named "zoning
district boundaries" layer. If accepted, Greenwood is a good companion to
Englewood in an Arapahoe secondary sprint.

### DTC

**Verdict: HALT as standalone municipality.**

Denver Tech Center is an employment/submarket area, not a single municipal
zoning authority. Treat DTC as a geography filter across Greenwood Village,
Englewood, Centennial, Denver, and/or Arapahoe source layers only after the
actual jurisdiction targets are selected.

### Arapahoe County fallback

Existing CO source docs identify Arapahoe County zoning at:

`https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/AC_WSS_Arapahoe_County_Zoning/FeatureServer/89`

Probe quality:

- 1,236 polygons.
- Direct `ZONING` field, with sampled values like `RR-A` and `SH PUD`.

Production note: use as cross-check/fallback only. Municipal zoning authority
for Englewood/Greenwood should come from city services where available.

## 2. North Shore Boston: Marblehead + Manchester-by-the-Sea

### Manchester-by-the-Sea, MA

**Verdict: VIABLE source, lower immediate ROI.**

Primary GIS sources:

- Town ArcGIS Hub:
  `https://access-manchester-by-the-sea-mbtsma.hub.arcgis.com/`
- AxisGIS sync service:
  `https://services8.arcgis.com/EvnSQRphNDboBLpY/arcgis/rest/services/AxisGISDataSync/FeatureServer`
- Zoning layer:
  `https://services8.arcgis.com/EvnSQRphNDboBLpY/arcgis/rest/services/AxisGISDataSync/FeatureServer/225`

Probe quality:

- Zoning layer: 133 polygons.
- Direct fields: `ZONINGD_`, `ZONINGD_ID`, `ZONING`.
- Distinct `ZONING` values sampled: `A`, `B`, `C`, `D-1`, `D-2`, `E`,
  `G`, `LCD`.

Production note: geometry signal is clean. The remaining work is parcel source
alignment and ordinance/matrix grounding, not source discovery.

### Marblehead, MA

**Verdict: PIVOT / QA needed.**

Primary GIS sources:

- AxisGIS viewer:
  `https://www.axisgis.com/MarbleheadMA/`
- Zoning/land-use FeatureServer:
  `https://services.arcgis.com/3RiQsDoOeneF0Q0P/arcgis/rest/services/Marblehead_ZoningLandUse/FeatureServer`
- Zoning layer:
  `https://services.arcgis.com/3RiQsDoOeneF0Q0P/arcgis/rest/services/Marblehead_ZoningLandUse/FeatureServer/1`

Probe quality:

- Zoning layer: 54 polygons.
- Direct `ZONE` field.
- Distinct sampled values: blank/null plus `B`, `B1`, `B1 SG`, `BR`,
  `CR`, `ECR`, `ESR`, `GR`, `HBR`, `SCR`, `SESR`, `SGR`, `SR`, `SSR`,
  `SU`, `U`.

Production note: Marblehead likely can be recovered, but it is less clean than
Manchester because the sampled zoning layer includes blank/space zone values
and the FeatureServer owner is not obviously the municipality. Use only after
source-of-record/provenance and blank-zone QA.

## 3. Long Island Wealth Tail: Brookville + Old Westbury

**Verdict: HALT for immediate production; PIVOT for reconnaissance.**

Public sources checked:

- Long Island Zoning Atlas:
  `https://www.longislandzoningatlas.org/`
- Brookville map page:
  `https://www.villageofbrookville.gov/map`
- Old Westbury maps page:
  `https://www.villageofoldwestbury.gov/182/Maps-of-the-Village-of-Old-Westbury`
- Old Westbury eCode link exposed on the village page:
  `https://www.ecode360.com/OL0821`

Probe quality:

- ArcGIS Online searches for `Brookville NY zoning FeatureServer`,
  `Old Westbury zoning FeatureServer`, `Brookville zoning atlas`, and
  `Old Westbury zoning atlas` returned no direct municipal zoning service.
- Long Island Zoning Atlas frontend says the dataset was manually compiled and
  updated through 2025, with boundaries digitized from GIS where available and
  PDFs/paper maps for villages without GIS. That is useful reconnaissance, but
  not a municipal source-of-record.
- The atlas frontend exposes `/api/v1` strings and a `LI-Zoning-2022` route,
  but direct endpoint probes for common JSON resources returned 404 or the app
  shell, not an immediate FeatureServer/GeoJSON source.

Production note: do not prioritize Brookville/Old Westbury until Nassau
structural work is resolved or the atlas data can be obtained with clear license
and source-of-record caveats. These targets may still be valuable, but they are
not quick +0.5 wins from public GIS alone.

## Recommended Dispatch Order

1. **Englewood CO mini-source spec**: city zoning polygons + city parcel-zoning
   polygons, then join/coverage check against Arapahoe parcel substrate.
2. **Greenwood Village authority QA**: confirm Urban service `Zones` layer is
   acceptable as current zoning; if yes, pair with city parcel layer.
3. **Manchester-by-the-Sea MA**: clean zoning layer, but starts a new MA
   workflow with parcel alignment/matrix grounding.
4. **Marblehead MA**: source exists, but blank-zone/provenance QA comes first.
5. **Long Island wealth-tail**: hold behind Nassau structural fix or formal
   atlas data access.
