# Oregon Taxlots Feasibility

Date: 2026-06-11

Scope: verify whether the Oregon taxlot source found in PR #225 is a real multi-county operational unlock for Clackamas County, OR and Multnomah County, OR, or only a parcel-geometry source that still needs per-municipality zoning work.

## Verdict

Metro RLIS Taxlots is the canonical public parcel/taxlot source for the Portland metro area and covers both Clackamas and Multnomah counties. It is a strong regional parcel geometry source.

It is not a verified zoning-code source. The live field audit shows no zoning/zone/district fields on the taxlot layer, only property/tax/land-use fields such as `LANDUSE`, `PROP_CODE`, `TAXCODE`, `JURIS_CITY`, and `ORTAXLOT`.

Oregon should be dropped from "best regional play" for the first not-loaded operational ingestion sprint. It is a good multi-county parcel-load candidate, but it does not by itself move audit gates because it does not populate `parcel.zoning_code`.

Recommended next not-loaded sprint priority: Contra Costa County, CA first if Master wants a two-polygon operational target with a single county parcel source and municipal zoning follow-through; Allegheny County, PA if Master wants the smallest one-polygon proof; Maricopa County, AZ next for higher-value follow-up.

## Canonical Parcel Source

Primary source: Metro RLIS Taxlots (Public)

- FeatureServer: `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer`
- Layer: `Taxlots (Public)` at layer id `3`
- REST layer metadata: `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/3?f=pjson`
- Download item: `Taxlots (Public) - Download`, ArcGIS item `9d3c396ffad44649bc7451465aa300f0`
- Metro metadata: `https://www.portlandmaps.com/metadata/index.cfm?LayerID=52065&action=DisplayLayer`
- Access pattern: public ArcGIS FeatureServer and public download, no auth observed.

Metro metadata describes the extent as Clackamas County, Multnomah County, and Washington County, Oregon. It reports 606,548 features and weekly maintenance.

## Live Coverage Probe

Layer queried: `Taxlots (Public)` layer id `3`.

Counts by `COUNTY`:

| County code | County | Live count |
|---|---|---:|
| `C` | Clackamas County | 163,589 |
| `M` | Multnomah County | 282,974 |
| `W` | Washington County | 200,028 |

Target-place probe:

| Query | Live count |
|---|---:|
| `JURIS_CITY='Lake Oswego'` | 16,105 |

This confirms usable source coverage for both target counties and Lake Oswego specifically. Lake Oswego rows sampled from the taxlot layer were Clackamas-side rows with `COUNTY='C'`, `JURIS_CITY='LAKE OSWEGO'`, `LANDUSE='SFR'`, `PROP_CODE='101'`, and taxlot identifiers such as `TLID='21E10AB01600'`.

## Class C Gate: Failed

Class C requires parcel records to carry a reliable zoning field.

Live field audit on the taxlot layer returned these fields:

`TLID`, `PRIMACCNUM`, `ALTACCNUM`, `SITEADDR`, `SITECITY`, `SITEZIP`, `BLDGSQFT`, `A_T_ACRES`, `YEARBUILT`, `PROP_CODE`, `LANDUSE`, `TAXCODE`, `SALEDATE`, `SALEPRICE`, `COUNTY`, `X_COORD`, `Y_COORD`, `JURIS_CITY`, `GIS_ACRES`, `STATECLASS`, `ORTAXLOT`, `LANDVAL`, `BLDGVAL`, `TOTALVAL`, `ASSESSVAL`, `FID`, `AREA`, `HAS_MANY`, `Shape__Area`, `Shape__Length`, `PUBLIC_OWN`, `OWNERTYPE`.

No `zoning`, `zone`, `zn`, or district-code field is present.

Live row samples:

| Sample area | Observed fields |
|---|---|
| Lake Oswego | `COUNTY='C'`, `JURIS_CITY='LAKE OSWEGO'`, `LANDUSE='SFR'`, `PROP_CODE='101'`, `TAXCODE='007002'` / `007021`, `ORTAXLOT=...` |
| Multnomah County / Portland-Gresham | `COUNTY='M'`, `JURIS_CITY='PORTLAND'` or `GRESHAM`, `LANDUSE='SFR'`, `PROP_CODE='101'`, `TAXCODE='201'` / `383` / `710`, `ORTAXLOT=...` |

Conclusion: Metro RLIS Taxlots is geometry-only for zoning purposes. It is not a Class C zoning source.

## Separate Oregon Zoning Layer Probe

Candidate source: Oregon DLCD statewide zoning layer.

- FeatureServer: `https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Zoning/FeatureServer`
- Layer: `ZoneOR_Gov2Pub`, layer id `0`
- REST metadata: `https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Zoning/FeatureServer/0?f=pjson`
- Access pattern: public ArcGIS FeatureServer, no auth observed.

Service description: zoning feature class compiled by Oregon DLCD with ODOT support, containing zoning data from multiple jurisdictions in a statewide standard model, built to support 1:24000 scale.

Fields include `localZCode`, `localZDesc`, `orZCode`, `orZDesc`, `ownerName`, `ownerType`, and `gsteward`.

Live counts:

| `ownerName` | Count |
|---|---:|
| `Lake Oswego` | 269 |
| `Portland` | 2,862 |
| `Multnomah County` | 285 |
| `Clackamas County` | 1,177 |

However, target samples do not prove local municipal code availability:

| `ownerName` | Sample result |
|---|---|
| `Lake Oswego` | `localZCode=''`, `localZDesc=''`, `orZCode='Res.'` / `PF` / `MURL` / `IC`, `gsteward='Metro'` |
| `Portland` | `localZCode=''`, `localZDesc=''`, `orZCode='CG'`, `gsteward='Metro'` |
| `Multnomah County` | `localZCode=''`, `localZDesc=''`, `orZCode='CG'` / `PF80`, `gsteward='Metro'` |
| `Clackamas County` | `localZCode=''`, `localZDesc=''`, `orZCode='RR2'` / `RR5` / `FUD` / `Res.'`, `gsteward='Metro'` |

The layer has zoning polygons, but the sampled target records expose generalized Oregon codes rather than local municipal zone codes. That is not enough to bind municipal ordinances and Bergen-style matrices without additional mapping work.

## Class A Gate: Not Proven

A Class A claim requires separate zoning district polygons plus the strengthened pre-flight:

- district bbox covers >=50% of parcel bbox
- 1,000-parcel `ST_Within` dry-run >=50% match

Source-level bbox comparison is promising but incomplete:

| Area | Taxlot bbox | DLCD zoning bbox | Source bbox coverage read |
|---|---|---|---|
| Clackamas / Lake Oswego + Clackamas County owners | `[-122.8762, 44.8681, -121.6469, 45.4756]` | `[-122.8680, 44.8856, -121.6507, 45.4617]` | Roughly >90% of the taxlot bbox by rectangular overlap. |
| Multnomah / Portland + Multnomah County owners | `[-122.9330, 45.4273, -121.8193, 45.7436]` | `[-122.9292, 45.4325, -121.8197, 45.7287]` | Roughly >90% of the taxlot bbox by rectangular overlap. |

But the required `ST_Within` dry-run cannot be run against production parcels because Clackamas and Multnomah are not loaded in prod. More importantly, the live samples show blank `localZCode` for the target owners, so even a spatial join would likely populate generalized state classes, not matrix-ready local zone codes.

Conclusion: do not classify Oregon as verified Class A yet. At most, DLCD is a preview-only research candidate after RLIS parcels are staged. It should not be the first operational not-loaded sprint unless Master accepts a dedicated source-validation sprint with no guaranteed audit movement.

## Operational Unlock Estimate

| Path | What it unlocks | Effort | Audit movement |
|---|---|---:|---|
| RLIS taxlot parcel ingest only | Loads parcels for Clackamas + Multnomah (+ Washington, outside current target batch) | Days | No direct `zoning_code`; does not clear audit gates. |
| RLIS parcels + DLCD generalized zoning spatial backfill | Possible broad zoning class assignment if preview gates pass | Days to validate/build, but uncertain | Not matrix-ready unless generalized `orZCode` is accepted or mapped to local code. |
| RLIS parcels + per-municipality zoning for Lake Oswego | Targeted Lake Oswego operational path | Days to weeks | Realistic Class B path for the wealth-pocket polygon, not a whole-county multi-county unlock. |

## Final Recommendation

Do not dispatch Oregon as the first not-loaded ingestion sprint on the assumption of a multi-county zoning unlock.

Metro RLIS is valuable and should stay in the backlog as a regional parcel source, but the strengthened gates downgrade it from "best regional play" to "geometry-only source with per-muni zoning follow-up." For immediate operational progress, prioritize a single-county not-loaded target with both parcel geometry and a clearer municipal zoning path:

1. Contra Costa County, CA: strongest two-polygon candidate from the prior scoping set.
2. Allegheny County, PA: likely fastest one-polygon proof around Fox Chapel.
3. Maricopa County, AZ: high-value follow-up, but still needs municipal validation for Scottsdale and Paradise Valley.
