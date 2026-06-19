# Maricopa AZ City-Limits Source Verdict

Date: 2026-06-19

Purpose: read-only diagnostic for the Scottsdale city-boundary prefilter required by Maricopa Phase 7B.2. Prior Maricopa diagnostics found that raw county parcel `PropertyCity='SCOTTSDALE'` has postal-city bbox noise and fails the Class A bbox primitive against Scottsdale zoning polygons. This document identifies the boundary source Lane A should use before Scottsdale spatial backfill.

## Bottom line

| Field | Verdict |
|---|---|
| Source class verdict | **CLEAN STATE AGGREGATOR**, with a Scottsdale city-owned shortcut available |
| Recommended reusable source | AZGeo `Arizona Incorporated Places Boundaries (Cities and Towns)` |
| Recommended REST endpoint | `https://services6.arcgis.com/clPWQMwZfdWn4MQZ/arcgis/rest/services/Incorporated_Places_Boundaries/FeatureServer/0` |
| Scottsdale immediate shortcut | `https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/4` (`City Limits`, one feature) |
| Field mapping | AZGeo: `Name` title-case city name; match to Maricopa parcel `PropertyCity` by `UPPER(Name)` |
| Case discipline | Boundary source title case (`Scottsdale`); Maricopa parcels uppercase bare (`SCOTTSDALE`) |
| Scottsdale bbox verdict | **PASS.** AZGeo and Scottsdale city-owned bboxes match the Scottsdale zoning bbox and remove raw `PropertyCity` spillover. |
| Estimated Lane A work | **1-2h** for Scottsdale if using city-owned `City Limits`; **2-4h** to add reusable AZGeo prefilter for all Maricopa munis |
| Recommended action | Use Scottsdale `City Limits` for immediate Phase 7B.2 velocity; implement AZGeo incorporated-place lookup if Lane A wants reusable Maricopa city prefiltering. |

Important correction: the prompt's "~24 sq mi" expectation for Scottsdale does **not** match the authoritative sources probed here. AZGeo reports Scottsdale at **184.56 sq mi**, and Scottsdale's own City Limits layer reports **184.5 sq mi**. This aligns with Scottsdale's known north-south footprint and with the Scottsdale zoning layer bbox from `docs/MARICOPA_AZ_ACQUISITION_SPEC.md`. Do not reject the source because it is not 24 sq mi.

## Recommended source

Primary reusable layer:

```text
AZGeo - Arizona Incorporated Places Boundaries (Cities and Towns)
https://services6.arcgis.com/clPWQMwZfdWn4MQZ/arcgis/rest/services/Incorporated_Places_Boundaries/FeatureServer/0
```

Service metadata:

| Check | Result |
|---|---|
| Geometry | `esriGeometryPolygon` |
| Spatial reference | WGS84, `wkid=4326` |
| Max record count | 2,000 |
| Capabilities | `Query,Extract` |
| Object id field | `OBJECTID` |
| Key city field | `Name` |
| Additional fields | `Region_Code`, `FIPS`, `AreaType`, `POP2020`-`POP2024`, `SQ_Miles`, `SQ_Acres` |
| Hub item modified | 2025-12-15 |
| Service description | AZDOR is named as authoritative owner of boundary polygons; ASLD adds supplemental attributes. |
| Caveat | The service description says the data does not represent a legal record. That is acceptable for parcel prefiltering, not for legal boundary certification. |

Live probe:

```text
GET /query
where=UPPER(NAME) IN ('SCOTTSDALE','PARADISE VALLEY','CAREFREE','CAVE CREEK','FOUNTAIN HILLS')
outFields=*
returnGeometry=false
```

Result: 5 / 5 target and adjacent Maricopa munis are present.

| Name | Region_Code | AreaType | POP2024 | SQ_Miles |
|---|---|---|---:|---:|
| Scottsdale | `SC` | city | 246,170 | 184.5628 |
| Paradise Valley | `PV` | town | 12,523 | 15.3831 |
| Carefree | `CA` | town | 3,657 | 8.7926 |
| Cave Creek | `CK` | town | 5,177 | 37.6440 |
| Fountain Hills | `FH` | town | 23,696 | 20.3156 |

### Bbox checks

AZGeo incorporated-place extents, `outSR=4326`:

| Muni | xmin | ymin | xmax | ymax |
|---|---:|---:|---:|---:|
| Scottsdale | -111.9609428851 | 33.4476401446 | -111.7560499764 | 33.9005267687 |
| Paradise Valley | -112.0128305620 | 33.5092640312 | -111.9171520969 | 33.5825225398 |
| Carefree | -111.9651129641 | 33.7993645390 | -111.8738693969 | 33.8572464851 |
| Cave Creek | -112.0305177679 | 33.7883170233 | -111.9086126204 | 33.9006200698 |
| Fountain Hills | -111.7873744704 | 33.5678888668 | -111.6986835667 | 33.6403545240 |

Comparison to accepted Maricopa spec:

| Source | Scottsdale bbox |
|---|---|
| Raw Maricopa parcels where `PropertyCity='SCOTTSDALE'` | `[-111.994941, 33.376245, -111.466830, 33.964735]` |
| Scottsdale zoning layer `OpenData/MapServer/24` | `[-111.960916, 33.447629, -111.756064, 33.900477]` |
| AZGeo incorporated-place boundary | `[-111.960943, 33.447640, -111.756050, 33.900527]` |
| Scottsdale city-owned City Limits layer | `[-111.960916, 33.447629, -111.756063, 33.900477]` |

Verdict: the boundary sources match the Scottsdale zoning layer. The bad bbox is the postal-city parcel subset, not the municipal boundary.

## Scottsdale city-owned shortcut

Scottsdale publishes its own City Limits layer in the same `OpenData` MapServer family as the zoning layer:

```text
https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/4
```

Live probe:

| Check | Result |
|---|---|
| Layer name | `City Limits` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Arizona Central State Plane, `wkid=2868` |
| Feature count | 1 |
| Fields | `OBJECTID`, `sq_miles`, `Shape` |
| `sq_miles` | 184.5 |
| Extent, WGS84 | `[-111.9609158532, 33.4476289987, -111.7560631308, 33.9004767034]` |

Use this if Lane A only needs Scottsdale Phase 7B.2 now. It is the lowest-friction source because:

- it is one feature;
- it is city-owned;
- it is in the same CRS/server family as Scottsdale zoning `OpenData/MapServer/24`;
- its bbox exactly matches the Scottsdale zoning bbox.

Limitation: it has no `Name` field and only solves Scottsdale. Use AZGeo for a reusable multi-muni Maricopa prefilter.

## Field-mapping prediction

### AZGeo reusable path

Boundary source:

```text
boundary_name_field = Name
boundary_filter = UPPER(Name) = :property_city
```

Parcel source:

```text
parcel_city_field = PropertyCity
parcel_city_case = uppercase bare
examples = SCOTTSDALE, PARADISE VALLEY, CAREFREE, CAVE CREEK, FOUNTAIN HILLS
```

Recommended matching discipline:

1. Normalize both sides with `UPPER(TRIM(...))`.
2. Use `Name` only for city/town selection, not as a zoning field.
3. Preserve `PropertyCity` as raw postal/assessor value but do not trust it for boundary inclusion.
4. For Scottsdale, require `parcel centroid ST_Within(boundary geom)` before zoning backfill from `OpenData/MapServer/24`.

### Scottsdale shortcut path

If using `OpenData/MapServer/4`, no name mapping is needed because there is one feature. Filter parcels by spatial containment only, optionally with `PropertyCity='SCOTTSDALE'` as a performance prefilter if Lane A wants a smaller candidate set.

## Fallback sources checked

### Older AZGeo / ASLD Cities service

```text
https://azgeo.az.gov/arcgis/rest/services/asld/Cities/FeatureServer/0
```

This also works and covers all five Maricopa target/adjacent munis. It has `Name`, population fields, and Web Mercator geometry. However, the newer hosted AZGeo incorporated-place layer is preferable because it is WGS84 and exposes `SQ_Miles`, `SQ_Acres`, `FIPS`, and `AreaType`.

### Maricopa County Cities and Towns

```text
https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Maricopa_County_Cities_and_Towns/FeatureServer/0
```

This is public and current-looking, but it is **not the recommended primary prefilter**. It contains city/town annexation polygons:

- layer name: `CityAndTownAnnexations`
- total count: 6,285
- target/adjacent rows: 163 annexation polygons for Scottsdale / Paradise Valley / Carefree / Cave Creek / Fountain Hills
- key field: `Juris` uppercase, e.g. `SCOTTSDALE`
- attributes include ordinance/effective-date fields and ordinance PDF links

It can be dissolved by `Juris`, but AZGeo already provides one dissolved incorporated-place feature per city/town. Keep the Maricopa County layer as an audit trail / annexation-vintage fallback, not the first Lane A implementation.

### MAG

MAG has a public maps/data portal and regional services, but no MAG source is needed for this specific blocker because AZGeo and Scottsdale city-owned layers already pass. Do not spend Phase 7B.2 time on MAG unless both AZGeo and Scottsdale OpenData are unavailable from the runtime environment.

### Census TIGER fallback

The 2024 Arizona incorporated-place TIGER/Line shapefile is reachable:

```text
https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_04_place.zip
```

Use only if ArcGIS sources fail. It is reliable and universal, but lower priority because it adds file download/extract handling and is not as directly tied to Arizona state/local boundary maintenance.

### OSM / OpenAddresses

Not recommended. Use only as a last-resort reconnaissance check because licensing, vintage, and boundary fidelity are less clear than AZGeo, Scottsdale OpenData, or Census TIGER.

## Lane A implementation estimate

### Fast Scottsdale-only path

Estimated **1-2h**:

1. Pull Scottsdale `City Limits` from `OpenData/MapServer/4`.
2. Restrict candidate parcels to centroid/representative point within the city-limits polygon.
3. Run Class A pre-flight against Scottsdale zoning `OpenData/MapServer/24`:
   - district bbox covers >=50% of filtered parcel bbox
   - 1,000-parcel or all-filtered dry-run `ST_Within` >=50%
4. Fire Scottsdale zoning backfill only if pre-flight passes.

### Reusable Maricopa prefilter path

Estimated **2-4h**:

1. Add a generic incorporated-place boundary lookup from AZGeo by `UPPER(Name)`.
2. Materialize or cache boundaries for `SCOTTSDALE`, `PARADISE VALLEY`, `CAREFREE`, `CAVE CREEK`, and `FOUNTAIN HILLS`.
3. Apply boundary filter per target municipality before municipal zoning backfills.
4. Reuse for future Maricopa munis where `PropertyCity` has postal noise.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| AZGeo service description says boundaries are not a legal record | Low for this use | Use only as parcel prefilter; zoning source remains city-owned zoning layer. |
| Scottsdale area expectation mismatch | Medium | Use 184.5 / 184.56 sq mi as correct source truth; the "~24 sq mi" expectation is not Scottsdale. |
| Boundary vintage vs parcel/zoning vintage | Medium | Scottsdale OpenData City Limits is same server family as zoning and should be preferred for immediate Scottsdale. |
| Parcel centroid on boundary edge | Low/medium | Use representative point/centroid with spot checks; capture dropped parcel count near boundary if Lane A tooling supports it. |
| Multi-polygon city geometry handling | Low | ArcGIS returns polygons; pipeline should preserve multipart geometry. |
| Maricopa County annexation layer tempting but not dissolved | Medium | Do not use it as primary unless dissolving by `Juris`; AZGeo is cleaner. |
| Rate limits / auth | Low | All probed REST endpoints returned public JSON without auth. |

## Final recommendation

For Scottsdale Phase 7B.2, use:

```text
https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/4
```

as the immediate city-boundary prefilter because it is a one-feature city-owned layer that exactly matches Scottsdale zoning.

For Maricopa reusable city-prefilter work, use:

```text
https://services6.arcgis.com/clPWQMwZfdWn4MQZ/arcgis/rest/services/Incorporated_Places_Boundaries/FeatureServer/0
```

with `UPPER(Name)` matched to Maricopa parcel `PropertyCity`. This is the clean state-aggregator path and covers Scottsdale, Paradise Valley, Carefree, Cave Creek, and Fountain Hills.
