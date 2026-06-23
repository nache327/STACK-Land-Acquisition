# Cook IL / Winnetka zoning source probe

Date: 2026-06-23  
Scope: read-only source viability probe for Cook County, IL parcel ingest and Winnetka zoning-code population.

## Verdict

**Cook County parcel ingest alone: HALT for operational flip.**

Cook County has a strong public parcel source, but the live parcel layer does **not** carry an embedded zoning field. Cook County also publishes zoning data only for **unincorporated** areas. That does not cover Winnetka, which is an incorporated village and the Phase 4 wealth-pocket target.

**Winnetka per-muni path: PASS / viable Class B FeatureServer.**

Village of Winnetka publishes a public GIS Consortium zoning layer with polygon geometry and a clean `ZONED` field. A Winnetka per-muni jurisdiction can use the Cook parcel substrate plus Winnetka zoning polygons for spatial backfill. This is not a Cook umbrella flip.

Bottom line:

| Target | Parcel source | Zoning source | Source class | Gate verdict |
|---|---|---|---|---|
| Cook County umbrella | Cook County current parcels | Unincorporated-only county zoning | Class D / incomplete county zoning | **HALT**: umbrella stays zoning-code blocked |
| Winnetka per-muni | Cook County current parcels filtered to `City='WINNETKA'` | Village of Winnetka GIS Consortium zoning layer | **Class B per-muni FeatureServer** | **PASS**: viable spatial-backfill source |

## Live source evidence

### Cook County parcel substrate

Public current parcel layer:

`https://gis.cookcountyil.gov/traditional/rest/services/cookVwrDynmc/MapServer/44`

Live metadata:

- Layer name: `Current Parcel`
- Geometry: polygon
- Capabilities: `Map,Query,Data`
- County parcel count probe: `1,419,180`
- Winnetka parcel count probe with `UPPER(City) = 'WINNETKA'`: `4,813`
- Winnetka share of current Cook parcel layer: about `0.34%`

Field audit:

- Address / muni field: `City`
- Parcel ID fields: `PIN14`, `Pin10`
- Assessment / class fields: `TaxCode`, `BLDGClass`, `value_description`, `NBHD`, `Town`
- **No embedded zoning field found** in layer metadata.

Five-row Winnetka sample from the parcel layer included `PIN14`, `City`, `Town`, `TaxCode`, `BLDGClass`, `value_description`, `NBHD`, `LandValue`, and `LandSqft`; none carried a zoning-code equivalent.

This rules out a Class C embedded-zoning path for the headless parcel ingest.

### Cook County zoning layer

Cook County public unincorporated zoning layers:

- `https://gis.cookcountyil.gov/traditional/rest/services/economicDevelopment/MapServer/2`
- `https://gis.cookcountyil.gov/traditional/rest/services/unincZoneRules/FeatureServer/0`

Live metadata for `economicDevelopment/MapServer/2`:

- Layer name: `UnincorporatedZoneAggregate`
- Geometry: polygon
- Capabilities: `Map,Query,Data`
- Code fields: `ZoneID`, `ZoneDesc`, `ZoneOrdinanceName`
- Sample 50 features: `50/50` non-null `ZoneID`
- Sample codes: `R1`, `R4`, `I1`, `P1`, `C4`

This is a valid zoning source for Cook County's unincorporated territory only. It is not a countywide zoning layer for incorporated municipalities such as Winnetka.

### Winnetka village zoning layer

Public web map:

`https://www.arcgis.com/sharing/rest/content/items/4c1f956d35e74e528af0a969b4659441`

Metadata:

- Title: `Village of Winnetka Zoning Map`
- Owner: `ashuman_WinnetkaIL`
- Type: `Web Map`
- Access: `public`

Backing service:

`https://ags.gisconsortium.org/arcgis/rest/services/VWN/AGOL_VWN_Project/MapServer/0`

Live metadata:

- Layer name: `Zoning`
- Geometry: polygon
- Capabilities: `Map,Query,Data`
- Spatial reference: Illinois StatePlane East, `wkid 102671`, `latestWkid 3435`
- Code field: `ZONED`
- Description field: `ZONINGDESCRIPTION`
- Ordinance pointer: `ZONINGDOCUMENT`

Live sample:

- Total zoning polygons: `64`
- Non-null `ZONED`: `64/64` (`100%`)
- Sample 50 features: `50/50` non-null `ZONED`

Distinct Winnetka zoning codes from the live layer:

| Code | Polygon count | Description | Ordinance pointer |
|---|---:|---|---|
| `B1` | 13 | Multi-Family Residential | Village Code - Chapter 17.32 |
| `B2` | 4 | Multi-Family Residential | Village Code - Chapter 17.36 |
| `C1` | 3 | Neighborhood Commercial District | Village Code - Chapter 17.40 |
| `C2` | 6 | General Retail Commercial | Village Code - Chapter 17.44 |
| `D` | 1 | Light Industrial | Village Code - Chapter 17.28 |
| `R1` | 1 | Single-Family Residential | Village Code - Chapter 17.28 |
| `R2` | 5 | Single-Family Residential | Village Code - Chapter 17.24 |
| `R3` | 6 | Single-Family Residential | Village Code - Chapter 17.20 |
| `R4` | 9 | Single-Family Residential | Village Code - Chapter 17.16 |
| `R5` | 16 | Single-Family Residential | Village Code - Chapter 17.12 |

The layer is small, queryable, polygonal, and code-bearing. It is suitable for Lane A's Class B per-muni spatial-backfill pattern after registering `Village of Winnetka, IL` as the operational jurisdiction.

## Alignment to the headless Cook parcel ingest

The headless Cook ingest matters as a **parcel substrate** if it preserves:

- `PIN14` or equivalent parcel identifier
- parcel geometry
- `City='WINNETKA'` or another reliable municipality selector

It does **not** matter as a Cook County operational flip by itself:

- Cook county total: about `1.42M` parcel features
- Winnetka subset: about `4.8k` parcel features
- Winnetka share: about `0.34%`
- County-level 70% zoning-code coverage cannot be reached from one North Shore wealth-pocket municipality.

Recommended operational unit is therefore **per-muni Winnetka**, not Cook County umbrella.

## Recommended Lane A path

1. Finish Cook parcel ingest only if it is needed to create the parcel substrate.
2. Register `Village of Winnetka, IL` as a separate per-muni jurisdiction.
3. Move/filter Cook parcel rows where `City='WINNETKA'` into the Winnetka jurisdiction, subject to Lane A's normal city-boundary or parcel-count sanity checks.
4. Ingest Winnetka zoning polygons from:

   `https://ags.gisconsortium.org/arcgis/rest/services/VWN/AGOL_VWN_Project/MapServer/0`

5. Map `ZONED` -> `zoning_code`.
6. Run spatial backfill from Winnetka zoning polygons to Winnetka parcels.
7. Apply/verify the matrix rows for the 10 observed codes.

Estimated effort if Cook parcels have already landed cleanly:

- Per-muni registration and parcel reassignment: `30-60 min`
- Winnetka zoning polygon ingest: `15-30 min`
- Spatial backfill + audit refresh: `15-30 min`
- Matrix authoring/apply for 10 codes: `1-2h` if not already pre-staged

Expected result: Winnetka can flip operational as a per-muni jurisdiction. Cook County should remain a residual umbrella with no operational expectation.

## Risks

- **Cook parcel `City` is assessor/postal style.** It sampled cleanly for Winnetka, but Lane A should still compare parcel count and geography against a Winnetka boundary before final reassignment.
- **Coordinate system:** both Cook and Winnetka services report Illinois StatePlane East (`wkid 102671`, `latestWkid 3435`), which is favorable for spatial joins, but ingest should normalize to the existing DB geometry convention.
- **Winnetka zoning vintage:** sample `DATEMODIFIED` values are mostly 2019 with some later edits. This is acceptable for a source probe, but Lane A should preserve source timestamps/provenance.
- **County unincorporated layer is a trap for this target.** It has a clean zoning field but does not apply to incorporated Winnetka.

## Final classification

Cook IL parcel ingest is **not parcel-only theater** if the campaign intends to carve out Winnetka per-muni next. It is **parcel-only theater** if anyone expects Cook County umbrella to clear operational gates from parcel ingest alone.

Classification:

- Cook County umbrella: **HALT / zoning-coverage gate blocked**
- Winnetka: **PASS / Class B per-muni FeatureServer**

