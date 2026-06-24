# Phase 2 NY/CT structural probe v2

Date: 2026-06-23  
Scope: read-only source probe for Nassau NY, Suffolk NY, and Fairfield CT wealth-band municipalities beyond Greenwich/Stamford. No ingest, no matrix authoring, no prod writes.

## Bottom line

**Verdict:** Phase 2's best next-fire path is **Fairfield CT municipal Class B**, not Nassau county retry. Three CT wealth-band munis that were previously frictional now have anonymous live municipal zoning sources:

1. **Westport CT** - AxisGIS public web map exposes `Zoning/FeatureServer/58`, 107 polygons, `ZONE_` field, 50/50 sampled non-null.
2. **New Canaan CT** - Tighe & Bond public `MapServer/89`, 65 polygons, `ZONING` + `Code` fields, 50/50 sampled non-null.
3. **Wilton CT** - QDSGIS public `FeatureServer/13`, 47 polygons, `Description` field, 47/47 sampled non-null; also parcel/MAT layers carry embedded `zoning`.

**Nassau NY remains blocked for immediate operational work.** NYS ITS 2026 public parcels do **not** include Nassau. The only reachable Nassau source is the same 420,594-feature 2020 layer implicated in B8, with Garden City identifiable but no zoning-like parcel field. A countywide Nassau retry would be a B8 scaling experiment plus substrate-only unless paired with a per-muni zoning source that did not surface here.

**Suffolk NY has a clean parcel-source upgrade but not a zoning-source unlock.** NYS ITS includes Suffolk with 586,600 public 2025 parcels and good town fields. East Hampton and Southampton can be carved out by `CITYTOWN_NAME`, but no anonymous county/town zoning FeatureServer surfaced in this probe. Treat Suffolk as parcel-substrate-ready, zoning-source-missing.

## Ranked next-fire order

| Rank | Target | Source class | Sample result | Expected ops lift | Recommendation |
|---:|---|---|---|---:|---|
| 1 | **Westport CT** | Class B per-muni live FeatureServer | 107 zoning polygons; `ZONE_`; 50/50 sampled non-null | +1 | Fire after Fairfield per-muni registration; strongest immediate CT add-on. |
| 2 | **New Canaan CT** | Class B per-muni live MapServer | 65 zoning polygons; `ZONING` + `Code`; 50/50 sampled non-null; 16 distinct codes | +1 | Fire with Westport or immediately after; replaces Vessel-token dependency for this muni. |
| 3 | **Wilton CT** | Class B live FeatureServer, possible Class C municipal parcel source | 47 zoning polygons; `Description`; 47/47 non-null; parcel sample 50/50 embedded `zoning` | +1 if Master adds Wilton to Phase 2 wave | Strong source, but confirm whether Wilton is accepted as a 58-list/wealth-band operational unit. |
| 4 | Darien CT | Class D/B PDF/manual | No public zoning FeatureServer found; official regulations/map PDFs only | +1 only with PDF/manual path | Keep behind Westport/New Canaan/Wilton. |
| 5 | Suffolk NY East Hampton / Southampton | Parcel substrate Class A-ish via NYS ITS; zoning Class B/D unknown | Suffolk parcels 586,600; East Hampton 25,611; Southampton 52,728; no zoning service surfaced | +1-2 only after town zoning source found | Good future Long Island canary, not immediate flip. |
| 6 | Nassau NY Garden City | Parcel source unchanged; zoning source missing | Nassau 420,594; Garden City 7,798; no zoning field; NYS ITS excludes Nassau | +0 immediate | Do not spend Lane A capacity on countywide Nassau unless the goal is B8/chunked-ingest validation. |

## Source-class summary

| Geography | Parcel source | Zoning source | Class rating | HALT/PASS |
|---|---|---|---|---|
| Nassau NY | Nassau ArcGIS layer `Nassau_parcels/FeatureServer/6`, 420,594 features, `SPATIAL_YR=2020` | No county or Garden City zoning FeatureServer surfaced; parcel fields have no zoning | Parcel substrate only; zoning Class D/B unknown | **HALT** for operational flip |
| Suffolk NY | NYS ITS `NYS_Tax_Parcels_Public/MapServer/1`, 586,600 public 2025 parcels | No countywide or East Hampton/Southampton/Sag Harbor zoning FeatureServer surfaced | Parcel Class A-ish aggregator; zoning Class B/D unknown | **PASS for parcel substrate, HALT for flip** |
| Westport CT | Fairfield prod parcels already carry `city='Westport'` from PR #228 | AxisGIS public `Zoning/FeatureServer/58` | Class B per-muni live FeatureServer | **PASS** |
| New Canaan CT | Fairfield prod parcels already carry `city='New Canaan'` from PR #228 | Tighe & Bond public `NewCanaanDynamic/MapServer/89` | Class B per-muni live MapServer | **PASS** |
| Darien CT | Fairfield prod parcels already carry `city='Darien'` from PR #228 | Official town PDFs; no public zoning FeatureServer found | Class D/B PDF/manual | **HALT** for live-source path |
| Wilton CT | Fairfield prod parcels already carry `city='Wilton'` from PR #228; QDSGIS also has parcel/MAT layers with `zoning` | QDSGIS public `CT_Wilton_Adv_Viewer_Layers/FeatureServer/13`; OpenGov parcel/MAT layers have embedded `zoning` | Class B live FeatureServer; possible per-muni Class C if using municipal parcels | **PASS** |

## Nassau NY

### Parcel source landscape

NYS ITS statewide public parcels:

- Service: `https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer`
- Layer: `https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1`
- Publication: May 2026.
- Nassau query: `COUNTY_NAME = 'Nassau'` returned `count=0`.
- Service description lists authorized public-share counties including Suffolk and Westchester, but **not Nassau**.

Therefore NYS ITS does not change Nassau's B8-era source landscape.

Reachable Nassau layer:

`https://services6.arcgis.com/a523XM128lX5Nsff/arcgis/rest/services/Nassau_parcels/FeatureServer/6`

Live probe:

| Probe | Result |
|---|---:|
| Total parcels | 420,594 |
| Garden City parcels by `UPPER(MUNI_NAME) = 'GARDEN CITY'` | 7,798 |
| Sampled Garden City records | 5 shown; 50-feature probe earlier found all `MUNI_NAME='Garden City'` |
| Spatial vintage | `SPATIAL_YR=2020` |
| Zoning-like fields | None |

Garden City sample attributes:

```json
{
  "COUNTY_NAM": "Nassau",
  "MUNI_NAME": "Garden City",
  "CITYTOWN_N": "Hempstead",
  "PARCEL_ADD": "115 CHESTNUT ST",
  "PROP_CLASS": "210",
  "USED_AS_CO": " ",
  "USED_AS_DE": " ",
  "PRINT_KEY": "34.-108-39",
  "SWIS": "282011",
  "SPATIAL_YR": 2020
}
```

Field audit: `COUNTY_NAM`, `MUNI_NAME`, `CITYTOWN_N`, `PARCEL_ADD`, `PROP_CLASS`, `USED_AS_CO`, `USED_AS_DE`, `PRINT_KEY`, `SWIS`, `SPATIAL_YR`. No `ZONE`, `ZONING`, `DISTRICT`, or equivalent field.

ArcGIS search probes for `Nassau County NY zoning FeatureServer` and `Garden City NY zoning FeatureServer` did not surface a relevant zoning source. One `Garden City Zoning Web App` result resolved to Garden City, Utah, not Garden City NY.

### Nassau verdict

**HALT for operational flip.** The parcel layer is reachable but unchanged from the B8 plateau class. It can identify Garden City, but parcel ingest alone cannot populate `zoning_code`. No live Garden City zoning source surfaced. Countywide Nassau remains a scaling experiment, not a high-confidence ops-count sprint.

Recommended next action only if Master revisits Nassau:

1. Treat Garden City as a per-muni jurisdiction target, not a Nassau umbrella target.
2. First find a Garden City zoning polygon source or accept a PDF/manual source path.
3. Separately decide whether B8/chunked ingest work is worth doing for the 420k parcel source.

## Suffolk NY

### Parcel source landscape

Suffolk is covered by NYS ITS public parcels:

`https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1`

Live probes:

| Probe | Result |
|---|---:|
| Suffolk total | 586,600 |
| East Hampton by `CITYTOWN_NAME = 'East Hampton'` | 25,611 |
| Southampton by `CITYTOWN_NAME = 'Southampton'` | 52,728 |
| Sample field coverage | County/town fields populated; no zoning field |
| Spatial vintage | `SPATIAL_YR=2025` in sampled rows |

Prior same-session 50-row sample showed `COUNTY_NAME='Suffolk'`, populated `MUNI_NAME` and `CITYTOWN_NAME`, and no zoning-like field. Example sampled shape:

```json
{
  "COUNTY_NAME": "Suffolk",
  "MUNI_NAME": "Amityville",
  "CITYTOWN_NAME": "Babylon",
  "PARCEL_ADDR": "...",
  "PROP_CLASS": "...",
  "USED_AS_CODE": null,
  "USED_AS_DESC": null,
  "SPATIAL_YR": 2025
}
```

NYS ITS fields include `COUNTY_NAME`, `MUNI_NAME`, `SWIS`, `PARCEL_ADDR`, `PRINT_KEY`, `SBL`, `CITYTOWN_NAME`, `PROP_CLASS`, `USED_AS_CODE`, `USED_AS_DESC`, values, dimensions, utilities, and building attributes. No `ZONE` / `ZONING` / district field appears.

### Zoning source search

ArcGIS portal probes returned no relevant public zoning FeatureServer for:

- `Suffolk County NY zoning FeatureServer`
- `East Hampton NY zoning FeatureServer`
- `Southampton NY zoning FeatureServer`
- `Sag Harbor NY zoning FeatureServer`

The only Suffolk-ish result was an unrelated NYS DEC shellfish closures map.

### Suffolk verdict

**PASS for parcel substrate, HALT for operational flip.** Suffolk is materially better than Nassau because NYS ITS gives a fresh 2025 public parcel source and town carveouts are straightforward. It still needs town-level zoning source discovery before Lane A can flip any Long Island wealth pocket.

Recommended next action if Master wants Long Island:

1. Pick a single town canary: East Hampton or Southampton.
2. Probe that town's planning/GIS pages and zoning map downloads in a dedicated 45-60 minute source search.
3. If a live town zoning FeatureServer appears, run it as a per-muni Class B target. If only PDF maps exist, defer until PDF/GeoPDF tooling is available.

## Fairfield CT wealth-band munis

Baseline: PR #228 populated `parcels.city` from `raw->>'Town_Name'` for Fairfield CT. Existing counts from `docs/OP5_FAIRFIELD_CT_CITY_REINGEST.md`:

| Muni | Fairfield prod parcels |
|---|---:|
| Westport | 9,947 |
| New Canaan | 7,386 |
| Darien | 5,831 |
| Wilton | 2,561 |

Vessel Tech remains token-gated per `backend/scripts/_drafts/_vessel_tech_arcgis_scan.md`, so this probe focused on anonymous direct municipal sources.

### Westport CT - PASS

AxisGIS app:

`https://www.axisgis.com/WestportCT/`

The page exposes:

- Web map id: `9563742132e5493e8387f7dbf4fe36f2`
- ArcGIS org/domain: `https://westport15.maps.arcgis.com`
- Public zoning layer in the web map:
  `https://services5.arcgis.com/lxjwLyi2Sx6yHvMJ/arcgis/rest/services/Zoning/FeatureServer/58`

Layer metadata:

| Field | Value |
|---|---|
| Name | `Westport Zoning` |
| Geometry | polygon |
| Total features | 107 |
| Code field | `ZONE_` |
| 50-feature sample | 50/50 non-null `ZONE_` |

Sample zone values:

`AA`, `OSRD`, `A`, `GBD`, `AAA`, `MHP`, `RORD2`.

Source class: **Class B per-muni live FeatureServer**.

Risk: the layer also has overlays (`APOZ`, `Open Space`, `Inclusionary Housing Overlay District`, `CAM Line`, `Village District Overlay`) under the same service. Lane A should use layer 58 as base zoning and treat overlay layers separately unless Master authorizes overlay-aware backfill.

### New Canaan CT - PASS

Web GIS:

`https://hosting.tighebond.com/NewCanaanCT/`

Settings JS exposes:

`https://hostingdata3.tighebond.com/arcgis/rest/services/NewCanaanCT/NewCanaanDynamic/MapServer`

Zoning layer:

`https://hostingdata3.tighebond.com/arcgis/rest/services/NewCanaanCT/NewCanaanDynamic/MapServer/89`

Layer metadata:

| Field | Value |
|---|---|
| Name | `Zoning` |
| Geometry | polygon |
| Total features | 65 |
| Fields | `ZONING`, `Code` |
| 50-feature sample | 50/50 sampled rows non-null for `ZONING` + `Code` |
| Distinct `Code` values | 16 |

Sample attributes:

```json
[
  {"ZONING": "1 Acre Residence Zone", "Code": "A"},
  {"ZONING": "Waveny Zone", "Code": "Q"},
  {"ZONING": "A Residence Zone", "Code": "F"},
  {"ZONING": "1/3 Acre Residence Zone", "Code": "M"}
]
```

Source class: **Class B per-muni live MapServer**.

Risk: prior pre-stage noted adopted-source vs 2025 update material ambiguity for citations. Use this layer for zone-code population, but cite adopted New Canaan regulations/eCode, not draft update packets.

### Darien CT - HALT for live-source path

Town source:

`https://www.darienct.gov/301/Zoning-Regulations-Map`

The town page provides current regulations, amendment PDFs through Amendment 104 effective May 10, 2026, and zoning map PDFs. The visible ArcGIS link on town pages resolves to:

`https://darienct.maps.arcgis.com/apps/webappviewer/index.html?id=271a6ba339ec4e7887bf559e0f7acef0`

That item is **AED Locator**, not zoning:

- Item title: `AED Locator`
- Type: Web Mapping Application
- Tags: AEDs, Fire Service, Public Safety

ArcGIS portal probes for Darien zoning returned no relevant FeatureServer. Direct town pages expose PDFs and civic pages, not a queryable zoning layer.

Source class: **Class D/B PDF/manual**.

Recommendation: Keep Darien behind Westport/New Canaan/Wilton unless Master explicitly wants a PDF/manual map extraction target.

### Wilton CT - PASS

ArcGIS search surfaced QDSGIS services:

- `https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/CT_Wilton_Adv_Viewer_Layers/FeatureServer`
- `https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/CT_Wilton_OpenGov_FS/FeatureServer`

Base zoning layer:

`https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/CT_Wilton_Adv_Viewer_Layers/FeatureServer/13`

Layer metadata:

| Field | Value |
|---|---|
| Name | `Zoning Effective -10/29/2018` |
| Geometry | polygon |
| Total features | 47 |
| Fields | `Zoning`, `ZoneNum`, `Description` |
| 47-feature sample | 47/47 non-null `Description` |

Sample zoning attributes:

```json
[
  {"Zoning": 12, "ZoneNum": 5, "Description": "CRA-10"},
  {"Zoning": 16, "ZoneNum": 2, "Description": "R-1A"},
  {"Zoning": 20, "ZoneNum": 9, "Description": "DRB"},
  {"Zoning": 13, "ZoneNum": 13, "Description": "DE-10"}
]
```

Additional municipal parcel/MAT source:

`https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/CT_Wilton_OpenGov_FS/FeatureServer/0`

50-row parcel sample:

| Field | Result |
|---|---|
| `zoning` | 50/50 non-null |
| sample values | `R-2` |
| city field | `WILTON` |

Source class: **Class B per-muni live FeatureServer** for polygon backfill; possible **per-muni Class C** if Lane A chooses to ingest/align municipal parcel records from QDSGIS/OpenGov instead of Fairfield county parcels.

Risk: The zoning polygon layer is dated 2018. The parcel layer may be newer but field names differ (`Description` vs parcel `zoning`). Lane A should prefer polygon backfill first and use the parcel embedded field as a validation/crosswalk aid.

## Expected ops-count lift

| Scenario | Expected lift | Notes |
|---|---:|---|
| Fire Westport + New Canaan direct municipal sources | +2 | Best immediate Phase 2 wave. Both are Fairfield wealth-band candidates and no longer depend on Vessel access. |
| Add Wilton | +1 | Strong anonymous source, but confirm Master wants Wilton as a 58-list/wealth-band operational unit. |
| Add Darien | +0 immediate / +1 with PDF tooling | No live zoning source found. |
| Nassau Garden City | +0 immediate / +1 if source acquired | Parcel source identifies Garden City but no zoning source. |
| Suffolk Long Island canary | +0 immediate / +1-2 if town zoning source acquired | Parcel source is good; zoning source missing. |

Most realistic near-term Phase 2 lift from this probe: **+2 to +3** (Westport, New Canaan, optional Wilton). This is independent of Vessel Tech B2B access.

## Handoff recommendations

1. **Dispatch Lane A on Westport CT and New Canaan CT first** if Master wants immediate Phase 2 expansion. Both have anonymous live zoning polygon sources and existing Fairfield `city` substrate.
2. **Add Wilton CT if accepted into the operational target set.** It has the strongest source profile of the four CT add-ons, including both polygon and parcel-embedded zoning evidence.
3. **Do not retry Nassau countywide as an ops sprint.** NYS ITS excludes Nassau and the available 420k layer is the B8-class source with no embedded zoning.
4. **Treat Suffolk as a future Long Island parcel canary, not an immediate flip.** The public NYS parcel source is good enough to make Suffolk worth a dedicated town-zoning source probe.
5. **Keep Darien in PDF/tooling backlog** unless a new municipal or vendor source appears.

