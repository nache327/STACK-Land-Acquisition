# Plymouth MA / Hingham Acquisition Spec

Date: 2026-06-23

Purpose: read-only re-evaluation of the Hingham, MA (Plymouth County) zoning source, in light of the Westchester Class B proof primitive and per-muni jurisdiction pattern now established. PR #222 was halted historically because MassGIS statewide zoning coverage was incomplete. This spec confirms that a different, usable per-muni / regional Class B source now exists for Hingham.

Scope is narrow: this is a Lane A scoping spec for Hingham specifically. Plymouth County is treated as a per-muni jurisdiction problem, not a county-wide aggregator problem, because Massachusetts does not publish a statewide zoning Class A layer and Plymouth County itself does not publish a county-wide zoning layer.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **MassGIS Standardized Assessors' Parcels (statewide L3)** |
| Parcel source URL | `https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0` |
| Canonical zoning source | **MAPC Zoning Atlas (regional, ~101 Greater Boston munis incl. Hingham)** |
| Zoning source URL | `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2` (`zoning_full`) |
| Zoning overlay source URL | `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/0` (`overlay_districts`) |
| Verified class | **Class B per-muni (regional aggregator covers Hingham), VERIFIED live** |
| Class C embedded parcel zoning | **YES, partial**. MassGIS parcel layer carries a `ZONING` field; Hingham coverage 7,475 / 8,894 = 84.0% non-null. Codes are mostly aligned with bylaw codes but some legacy values (`R1`, `R3`, `XX`, `00`, `IA`, `IB`) do not match current bylaw. |
| Class A statewide separate zoning layer | **NO**. MassGIS does not publish a current statewide zoning layer (last statewide compile was 1999). |
| Lane A effort estimate | **2-4 days** for Hingham-only proof using MAPC layer; **3-5 days** for parcel + Class B + matrix seed end to end |
| Multi-county / multi-muni carry | **YES, regional**. MAPC source covers 101 Greater Boston munis including 5 Plymouth Co towns (Hingham, Hull, Cohasset, Marshfield, Hanover, Duxbury, Norwell). Same adapter unlocks the others. |
| Recommended dispatch | **MEDIUM-HIGH**. Hingham is a wedge wealth-pocket Phase 4 target with a live, code-bearing, queryable Class B source plus an 84% Class C fallback. The MAPC adapter pattern carries to 7+ Plymouth Co peers. |

## Why This Is Different From PR #222

PR #222 halted because MassGIS's own zoning layer was incomplete (1999 vintage, never refreshed, missing many South Shore towns). That remains true today — there is still no usable MassGIS statewide zoning Class A.

What changed since PR #222:

- The MAPC (Metropolitan Area Planning Council) regional zoning atlas v0.2 is live, queryable, code-bearing, and explicitly covers Hingham with 15 base zoning districts plus 7 overlay districts.
- The Mass Zoning Atlas / Suffolk Law team also published a 2023-vintage NZA dataset covering all 352 MA jurisdictions (downloadable shapefile via `https://www.mercatus.org/sites/default/files/2025-09/ma_zoning_atlas_2023_1.zip`, behind Cloudflare; not the preferred primitive but a corroborating proof of coverage).
- MassGIS standardized assessors parcels also expose an embedded `ZONING` field with 84.0% non-null coverage for Hingham, opening a Class C path even without polygon zoning.

The combination of a regional Class B publisher + a per-parcel Class C fallback removes the original blocker.

## Current Prod State

Hingham / Plymouth County have not been re-probed against `/api/jurisdictions` or `/api/admin/coverage` during this scoping (read-only research only). Treat as `NOT-LOADED-NEEDS-INGEST` pending Lane A handoff.

## Canonical Parcel Source

**MassGIS Massachusetts Property Tax Parcels (Standardized Assessors / Level 3)**

- Catalog: `https://www.mass.gov/info-details/massgis-data-property-tax-parcels`
- ArcGIS item: `https://gis.data.mass.gov/datasets/massgis::massachusetts-property-tax-parcels/about`
- FeatureServer: `https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer`
- Parcel layer: `https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0`
- Tile fallback: `https://tiles.arcgis.com/tiles/hGdibHYSPO59RG1h/arcgis/rest/services/MassGIS_Level3_Parcels/MapServer`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `Massachusetts Property Tax Parcels` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | NAD83 Massachusetts Mainland (meters), `wkid=26986` |
| Capabilities | `Query,Extract,Sync` |
| Hingham filter | `TOWN_ID=131` |
| Hingham parcel count | 8,894 |
| Hingham last edit (sample) | `LAST_EDIT=20110211`; FY field on most rows = `2025` |
| Hingham `ZONING` non-null | 7,475 of 8,894 = **84.0%** |

Hingham parcel fields exposed include `MAP_PAR_ID`, `LOC_ID`, `POLY_TYPE`, `MAP_NO`, `SOURCE`, `LAST_EDIT`, `TOWN_ID`, `PROP_ID`, `BLDG_VAL`, `LAND_VAL`, `OTHER_VAL`, `TOTAL_VAL`, `FY`, `LOT_SIZE`, `LS_DATE`, `LS_PRICE`, `USE_CODE`, `SITE_ADDR`, `ADDR_NUM`, `FULL_STR`, `CITY`, `ZIP`, `OWNER1`, `OWN_ADDR`, `OWN_CITY`, `OWN_STATE`, `OWN_ZIP`, `LS_BOOK`, `LS_PAGE`, **`ZONING`**, `YEAR_BUILT`, `BLD_AREA`, `UNITS`, `RES_AREA`, `STYLE`, `NUM_ROOMS`, `LOT_UNITS`, `STORIES`, `GlobalID`.

Sample Hingham parcel rows (abbreviated):

| MAP_PAR_ID | SITE_ADDR | ZONING | USE_CODE | TOTAL_VAL | OWNER1 |
|---|---|---|---|---:|---|
| `1312090000000150` | `24 ACCORD POND DRIVE` | `RB` | `1010` | 916,400 | MORRIS PATRICK & SANDERSON MARGARET |
| `1311790000000570` | `1 MONUMENT CIRCLE` | `RB` | `1010` | 891,300 | GILL GEOFFREY E & SHANNON |

Class C gate result: **PASS PARTIAL**. `ZONING` is genuine zoning-district code (`RA`, `RB`, `RC`, `RD`, `BA`, `BB`, `IP`, `BR`, `I`, `C`) for the bulk of parcels. Legacy / unmapped values (`R1`, `R3`, `XX`, `00`, `IA`, `IB`) show up on a minority of rows and should be flagged as "low confidence" in the matrix output rather than treated as authoritative.

## Canonical Zoning Source

**MAPC Zoning Atlas v0.2** (Metropolitan Area Planning Council, Greater Boston regional)

- Site: `https://zoningatlas.mapc.org/`
- About: `https://zoningatlas.mapc.org/reports/1/`
- GitHub: `https://github.com/MAPC/zoning-atlas`
- MapServer root: `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer`
- Overlay districts layer (id 0): `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/0`
- Zoning simple layer (id 1, generalized for low zoom): `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/1`
- **Zoning full layer (id 2, full attribute table — preferred adapter target)**: `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2`

Service-level probe (MapServer root):

| Check | Result |
|---|---:|
| Service description | "A test service with feature access for the Zoning Atlas, with the full attribute table included with the base zoning polygons. Based on the 8/3/20 version of the data. Map and data changed from MA State Plane to Web Mercator to avoid projecting on the fly. v0.2" |
| Capabilities | `Query,Map,Data` |
| Spatial reference | Web Mercator, `wkid=102100`, `latestWkid=3857` |
| Server currentVersion | 11.3 |
| Total layers | 3 (overlay_districts, zoning_simple, zoning_full) |

Layer 2 (`zoning_full`) live probe:

| Check | Result |
|---|---:|
| Layer name | `zoning_full` |
| Geometry | `esriGeometryPolygon` |
| Max record count | 2,000 |
| Regional bbox (Web Mercator) | `xmin=-7977225.44`, `ymin=5161343.11`, `xmax=-7856170.21`, `ymax=5272289.81` |
| Total polygons (all 101 munis) | 1,775 |
| Distinct municipalities | 101 |
| Hingham polygon count | **15** |
| Hingham `spatialrec` (DATEMODIFIED) | NULL (no per-row vintage; service-level vintage = 2020-08-03) |
| Hingham bbox (Web Mercator) | `xmin=-7896057.39`, `ymin=5184614.28`, `xmax=-7884429.26`, `ymax=5202126.38` |

Schema (32 fields total) — zoning-code-bearing field is **`zo_code`**, with corresponding `zo_name`, `zo_usety` (integer use type code), `zo_usede` (use description). Additional standards columns: `mnls_eff` (min lot size effective), `lapdu` (lot area per dwelling unit), `mxht_eff` (max height effective), `mxdu_eff` (max DUs effective), `dupac_eff` (DU per acre effective), `far_eff` (FAR effective), plus `_spec` and `_esval` siblings for "as specified" and "estimated value" variants.

All 15 Hingham `zoning_full` rows (live):

| zo_code | zo_name | zo_usety | zo_usede | mulfam2 |
|---|---|---:|---|---:|
| `131BR` | Business Recreation | 2 | restaurant, commercial amusement (by special permit only) | 0 |
| `131I` | Industrial | 2 | manufacturing, marina, freight terminal, motor vehicle repair, business office | 0 |
| `131IP` | Industrial Park | 2 | manufacturing, freight terminal, business office | 0 |
| `131LIP` | Limited Industrial Park | 2 | business office, bank, light industrial | 0 |
| `131OO` | Official and Open Space | 4 | conservation, recreation | 0 |
| `131OP` | Office Park | 2 | professional office | 0 |
| `131RA` | Residence A | 1 | Multi Family | 1 |
| `131RB` | Residence B | 1 | Two Family Conversion | 1 |
| `131RC` | Residence C | 1 | Two Family Conversion | 1 |
| `131RD` | Residence D | 1 | Multi Family | 1 |
| `131RE` | Residence E | 1 | Garden Apartment | 1 |
| `131WR` | Waterfront Recreation | 2 | marina | 0 |
| `131WB` | Waterfront Business | 2 | marina | 0 |
| `131BA` | Business A | 3 | commercial, professional offices, retail | 1 |
| `131BB` | Business B | 3 | commercial, professional offices, retail | 1 |

These 15 codes correspond 1:1 to the Hingham Zoning By-Law (revised through April 29, 2025) base districts. `zo_code` prefix `131` = Hingham's MA Town ID 131. Codes are real zoning bylaw codes, not CAD/utility/planning-framework noise (contrast with Fountain Hills and with the look-alike `Hingham_UDF_Zones` Vanasse Hangen Brustlin layer described in the Rejected Candidates section below).

Overlay districts layer (layer id 0) live probe for Hingham:

| ZONECODE | Overlay_Ty | Likely meaning |
|---|---|---|
| `131OVF-DO` | FLEX | Flexible overlay (district overlay) |
| `131OVF-HO` | FLEX | Flexible overlay (housing overlay) |
| `131OVF-W` | FLEX | Flexible overlay (waterfront) |
| `131OVF-SHDO` | FLEX | South Hingham Downtown Overlay (per Hingham bylaw) |
| `131OVS-PWSO` | SD | Public Water Supply Overlay (special district) |
| `131OVR-APW-HAPD` | RESTR | Restricted (Aquifer Protection / Historic Area Protection) |
| `131OVR-FWPD` | RESTR | Restricted (Flood/Wetland Protection District) |

Class B verdict: **PASS, source-of-record candidate**. The layer is live, queryable, code-bearing, covers Hingham completely (15/15 base districts confirmed against the bylaw), carries overlay districts, and uses a stable per-muni prefix (`131*`) that's safe to filter. Spatial reference is Web Mercator, so no projection step required on the way into Postgres.

Caveats:

- Service description says "v0.2 test service" and "Based on the 8/3/20 version of the data." This is a 2020-vintage snapshot. For underwriting use, the data must be flagged as vintage 2020-08-03, not as live current.
- `spatialrec` (per-row DATEMODIFIED) is NULL on every Hingham row. There is no per-row vintage.
- The MAPC site itself runs against this same MapServer for its public viewer (verified in `src/components/map/Layers.jsx` in github.com/MAPC/zoning-atlas), so it is the public source-of-record. Authentication/rate limits not observed during this probe.

## Multi-County / Multi-Municipality Carry

The MAPC Zoning Atlas covers 101 Greater Boston munis. Of the 101, the following are Plymouth County wedge-cohort candidates whose zoning will be unlocked by the same adapter:

- Hingham (this spec)
- Hull
- Cohasset (also covered)
- Marshfield
- Hanover
- Duxbury
- Norwell

This is **regional carry, not statewide carry**. MAPC's footprint does not include western Mass, Cape Cod (east of Bourne), Berkshires, or central Worcester County. For those, the Mass Zoning Atlas / Suffolk Law NZA static download is the corroborating source, and adapters would need a different ingest path (static shapefile rather than ArcGIS REST).

Parcel-source carry is broader: MassGIS Standardized Assessors covers all 351 MA towns. Other Plymouth County wealth-pocket targets can reuse the same parcel filter pattern (`TOWN_ID=<town_id>`).

## Rejected Candidates

These were probed and found unsuitable:

1. **Town of Hingham GIS Map** (`https://www.hingham-ma.gov/183/GIS-Map`): the town's portal runs on PeopleGIS SimpliCITY / MapsOnline, which is a PHP/MapServer-backed Mapfile system. The map config (`/home/peoplegis/mapsonline/hinghamma/map/mo4/mo4_site_1537.map`) is server-side, not exposed as ArcGIS REST. The portal does have a "Zoning" layer, but no public FeatureServer/MapServer endpoint to query. Vendor: PeopleGIS (info@peoplegis.com), SRS `EPSG:2249`. Adapter would require either a screen-scrape or a vendor data-access request; not in scope.

2. **Hingham_UDF_Zones** (`https://services6.arcgis.com/2yV7RkwOU8zZaabr/arcgis/rest/services/Hingham_UDF_Zones/FeatureServer/0`): looks like zoning but **is not zoning**. 45 polygons, single `Zone` field with values `1`,`2`,`3`,`4` and `AreaNumber` `1`-`8`. Owner is `byron.usswald_vnagis` / `christina.woehrle_vnagis` (Vanasse Hangen Brustlin / VNA stormwater consultancy whose other items are all Holyoke street-sweeping and Veolia water utility work). The "UDF" is a utility / use-density framework, not the Town's Residence A-E / Business A-B / Industrial bylaw districts. This is the kind of look-alike CAD/utility layer that bit the Fountain Hills probe. **Do not use.**

3. **MassGIS statewide Zoning** (`https://www.mass.gov/info-details/massgis-data-zoning`): the original PR #222 blocker remains. Last coordinated statewide compile was 1999. There is no current statewide MassGIS Zoning FeatureServer that covers Hingham.

4. **Plymouth County GIS**: Plymouth County itself does not publish a county-wide zoning aggregator. Each town (Town of Plymouth, Town of Hingham, etc.) hosts its own GIS independently. The MAPC regional aggregator is the closest analog to Westchester County's countywide layer for this geography.

5. **Massachusetts Zoning Atlas / National Zoning Atlas static download** (`https://www.mercatus.org/sites/default/files/2025-09/ma_zoning_atlas_2023_1.zip`): covers all 352 MA jurisdictions including Hingham, vintage 2023, behind Cloudflare bot-protection (curl with browser user-agent still returns the Cloudflare challenge page; would need manual browser fetch or an authenticated Mercatus account). Useful as a corroborating reference if MAPC layer is ever taken down, but not a queryable live adapter target.

## Lane A Execution Shape

Recommended staged plan:

1. Register `Hingham, MA (Plymouth County)` as a per-muni jurisdiction in preview, following the per-muni jurisdiction pattern validated by King WA path 1 on 2026-06-16.
2. Ingest Hingham parcels from MassGIS Standardized Assessors with filter `TOWN_ID=131`:
   - `parcel_id`: `MAP_PAR_ID` (16-char canonical) with `LOC_ID` and `PROP_ID` retained as alternate IDs
   - `municipality` / `subjurisdiction`: `CITY` (`HINGHAM`)
   - source CRS: EPSG:26986 (NAD83 MA Mainland meters)
   - source provenance: MassGIS Property Tax Parcels FeatureServer URL + pull timestamp + FY field
3. Treat Class C `ZONING` field as a low-confidence fallback only — populate a `zoning_legacy_code` parcel column for analyst diagnostics but do not classify the parcel against it.
4. Ingest Class B zoning from MAPC Zoning Atlas v0.2 `zoning_full` (layer id 2) with filter `muni='Hingham'`:
   - `zone_code`: `zo_code`
   - `zone_name`: `zo_name`
   - `zone_use_type` integer: `zo_usety`
   - `zone_use_description`: `zo_usede`
   - `mulfam2` int -> multi-family allowed flag
   - dimensional standards: `mnls_eff`, `lapdu`, `mxht_eff`, `mxdu_eff`, `dupac_eff`, `far_eff`
   - vintage: hardcode `2020-08-03` from service description (since `spatialrec` is NULL)
   - source CRS: EPSG:3857 (Web Mercator)
5. Ingest overlay districts from MAPC layer id 0 (`overlay_districts`) with filter `ZONECODE LIKE '131%'`:
   - `overlay_code`: `ZONECODE`
   - `overlay_type`: `Overlay_Ty` (FLEX / SD / RESTR)
6. Run strengthened Class B gates before production:
   - 15 zoning polygons should cover >= 50% of the Hingham parcel bbox area
   - 1,000-parcel `ST_Within` dry-run should resolve >= 50% of parcels to a `zo_code`
   - Cross-check resolved `zo_code` against the parcel's own `ZONING` field; report agreement rate. Target: >= 70% agreement on the 7,475 non-null Hingham parcels (some legacy code drift expected).
7. Author `backend/data/plymouth_ma_zoning_directory.json` for Hingham proof only, using the 15 `zo_code` -> Hingham Zoning By-Law section URL mappings (bylaw PDF: `https://www.hingham-ma.gov/376/Zoning-By-laws-PDF`).
8. Defer Hull / Cohasset / Marshfield / Hanover / Duxbury / Norwell as follow-on per-muni jurisdictions reusing the same MAPC adapter once Hingham passes preview.
9. **Do not** attempt to scale to all 101 MAPC munis in one sprint. Treat each as its own per-muni Op-5, following the King WA / Westchester precedent.

## Effort Estimate

| Work item | Estimate |
|---|---:|
| MassGIS L3 parcel adapter for Hingham (`TOWN_ID=131`) | 4-6h |
| Reuse adapter for other MA munis (Hull, Cohasset, Marshfield, etc.) | +1-2h per muni after Hingham succeeds |
| MAPC Zoning Atlas v0.2 adapter (zoning_full + overlay_districts) | 4-8h |
| Hingham bbox + 1,000-row ST_Within dry-run preview gates | 2-4h |
| Hingham zoning directory + matrix seed | 4-8h |
| Hingham proof end to end | 2-4 days |
| Adding Hull, Cohasset, Marshfield, Hanover, Duxbury, Norwell follow-on | 1-2 days each (reuses MAPC adapter) |

Expected coverage after Hingham only:

- Hingham parcels: 8,894
- Hingham zoning districts: 15 base + 7 overlay = 22 polygons
- This is a single-muni proof, not a county-wide flip. Plymouth County total population is much larger; Hingham is roughly 24k residents.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| MAPC service is labeled "v0.2 test service" | Service may be deprecated, throttled, or replaced | Capture full row pull at ingest time; pin to specific vintage `2020-08-03`. If service goes away, the Mercatus NZA static zip is a corroborating fallback. |
| MAPC zoning data is 2020-08-03 vintage | Bylaw has been amended multiple times since (most recent revision 2025-04-29) | Flag matrix output as "MAPC 2020-08-03 vintage" rather than "current." Diff `zo_code` set against current bylaw PDF; for Hingham the 15 districts match the current bylaw 1:1, so this risk is low for base zones but moderate for dimensional standards. |
| `spatialrec` (per-row DATEMODIFIED) is NULL | No per-row vintage signal | Hardcode service-level vintage in provenance. |
| Hingham parcel `ZONING` field 16% null | Class C fallback is incomplete | Use MAPC as primary, Class C field only as a diagnostic / agreement check. |
| Hingham parcel `ZONING` legacy values (`R1`, `R3`, `XX`, `00`, `IA`, `IB`) | Stale codes drift from current bylaw codes | Flag these rows as low-confidence in matrix output; do not classify against them. |
| Multiple coordinate systems | Parcel EPSG:26986, MAPC zoning EPSG:3857, MapsOnline (rejected) EPSG:2249 | Standard geometry transform path handles it; document each CRS in the run log. |
| PeopleGIS / SimpliCITY layer not used | We bypass the Town's own publisher | The MAPC regional aggregator is what the Town's GIS staff also rely on for cross-muni comparison, and it carries richer fields than the PeopleGIS layer; this is a feature, not a regression. |
| Fountain-Hills-style look-alike (`Hingham_UDF_Zones`) gets picked up by accident | Wrong layer ingested with garbage 1-4 zone codes | Rejected explicitly in this spec (see Rejected Candidates section). Adapter must hard-code the MAPC URL and `muni='Hingham'` filter; do not search-and-resolve at runtime. |

## Verdict

Plymouth County / Hingham is **NOT blocked at zoning acquisition**. PR #222 halted on the wrong source (MassGIS statewide). The MAPC Zoning Atlas v0.2 regional service is a live, queryable, code-bearing per-muni-filtered ArcGIS REST publisher that covers Hingham with 15 base zoning districts (matching the current bylaw 1:1) plus 7 overlay districts.

This is a **Class B per-muni** classification: regional aggregator that exposes per-muni rows via `muni='Hingham'` filter. The 2020-08-03 vintage is a known caveat but acceptable for a wedge wealth-pocket Phase 4 not-loaded target.

MassGIS Standardized Assessors carries Hingham parcels with `TOWN_ID=131` (8,894 parcels) and a low-confidence Class C `ZONING` field at 84.0% coverage as a corroboration channel.

Recommended next action: schedule Hingham as a Lane A 2-4-day proof, following the per-muni jurisdiction pattern. Once Hingham passes, the same MAPC adapter unlocks Hull, Cohasset, Marshfield, Hanover, Duxbury, and Norwell with ~1-2 days additional work each.

This spec **supersedes the PR #222 HALT**. Do not re-probe Plymouth / Hingham as "blocked" — the source has changed.
