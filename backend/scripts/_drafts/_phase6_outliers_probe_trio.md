# Phase 6 Outliers Probe Trio

Date: 2026-06-23

Scope: read-only diagnostic probe of the three remaining single-polygon Phase 6 outliers: Miami-Dade FL / Pinecrest, Multnomah-Clackamas OR / Lake Oswego, and Summit UT / Park City corridor. No ingest was run.

Method: live REST metadata and 50-feature samples where a public FeatureServer/MapServer was available; PR #227 was read first for the Oregon dead-end context.

## PR #227 Context

PR #227 (`DIAGNOSTIC - DO NOT MERGE: audit deadzone and Oregon taxlots feasibility`) was merged. Its Oregon finding still holds for the regional sources:

- Metro RLIS Taxlots is a strong parcel/taxlot source for Clackamas, Multnomah, and Washington Counties, but it has no zoning/zone/district field.
- Oregon DLCD statewide zoning has polygons, but Lake Oswego / Portland / Multnomah / Clackamas samples had blank `localZCode` and `localZDesc`; only generalized `orZCode` values were populated.
- Therefore Oregon is not a regional Class A/Class C zoning unlock by itself. Lake Oswego must use city zoning geometry or stay halted.

## Miami-Dade FL / Pinecrest

| Source | Source class | URL | 50-feature sample quality | Verdict |
|---|---|---|---|---|
| Miami-Dade `Parcel_poly` | County parcel geometry | `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/Parcelpoly_gdb/FeatureServer/0` | 50 rows returned; fields are parcel identifiers only: `PID`, `FOLIO`, `TTRRSS`, `PARCEL`, `SUBCODE`, `CONDOFLG`, edit metadata. No owner/address/zoning. Good geometry key source, not enough alone. | PIVOT |
| Miami-Dade `PaParcelView` / Pinecrest filtered | County parcel + assessment view | `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/PaParcelView_gdb/FeatureServer/0` | 50 rows for `TRUE_SITE_CITY='Pinecrest'`; usable `PID`, `FOLIO`, `TRUE_SITE_ADDR`, `TRUE_SITE_CITY`, `DOR_CODE_CUR`, `DOR_DESC`, `LOT_SIZE`. No zoning, but strong parcel attribution. | VIABLE |
| Village of Pinecrest Zoning | Per-muni Class B zoning | Experience: `https://experience.arcgis.com/experience/dfe679d563c24f12a0740f0b8ce4a6df`; layer: `https://services3.arcgis.com/0IbOaQdCzMiaAcDv/arcgis/rest/services/Zoning/FeatureServer/1` | 50 rows returned from `Pinecrest_Zoning_JAN2025_Updt`; fields include `PID`, `FOLIO`, address parts, `ZONE`, `ACRES`. Sample zones included `EU-M`, `EU-1`, `EU-S`, `BU-2`, `PS`. This is the cleanest outlier source because zoning rows already carry parcel keys. | VIABLE |
| Florida DOR / FGIO statewide parcels | Statewide parcel fallback | Item: `https://www.arcgis.com/home/item.html?id=efa909d6b1c841d298b0a649e7f71cf2`; layer: `https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0` | 50 unfiltered rows returned; fields include `CO_NO`, `PARCEL_ID`, `PHY_ADDR1`, `PHY_CITY`, `DOR_UC`, `PA_UC`, `ASMNT_YR`. It is an annual DOR parcel/tax-roll layer, not zoning. Targeted Pinecrest/county filters were slow/rejected during this quick probe. | PIVOT |

Miami-Dade verdict: **VIABLE** via Pinecrest municipal zoning plus Miami-Dade `PaParcelView`. This is a real Class B candidate and likely the cheapest of the three because `PID`/`FOLIO` appear in both the parcel view and the zoning layer.

Expected ops-count lift if Master commits an ingest sprint: **+1 polygon** for Pinecrest, assuming registration + parcel load + Pinecrest `ZONE` backfill + municipal matrix/citations.

Expected sprint shape: 2-4 days for a focused ingest/backfill/matrix pass. Parcel geometry can come from Miami-Dade; zoning can come directly from the Pinecrest layer.

## Multnomah / Clackamas OR / Lake Oswego

| Source | Source class | URL | 50-feature sample quality | Verdict |
|---|---|---|---|---|
| Metro RLIS Taxlots | Regional parcel geometry | `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/3` | 50 Lake Oswego rows returned with `TLID`, `PRIMACCNUM`, `SITEADDR`, `SITECITY`, `LANDUSE`, `PROP_CODE`, `TAXCODE`, `COUNTY`, `JURIS_CITY`, `ORTAXLOT`. Sample rows were Clackamas-side (`COUNTY='C'`) and mostly `LANDUSE='SFR'`; no zoning field. | PIVOT |
| City of Lake Oswego `Zoning_cache` | Per-muni Class B zoning geometry | `https://maps.ci.oswego.or.us/server/rest/services/Zoning_cache/MapServer/150` | 50 zoning polygon rows returned; fields include `LAYER`, `LINK`, `INFO`, `ACRES`. Sample local zones included `R-10`, `R-5`, `EC/R-0`, `I`, `EC`, `PNA`; `INFO` links to Lake Oswego code sections. Usable local zoning geometry, although this is a cached MapServer layer with duplicated scale layers. | VIABLE |
| Oregon DLCD statewide zoning | Statewide generalized zoning | `https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Zoning/FeatureServer/0` | 50 Lake Oswego rows returned; `localZCode` and `localZDesc` were blank on all 50; only generalized `orZCode`/`orZDesc` values such as `Res.`, `PF`, `MURL`, `IC`, `MURM` were present. | HALT |

Oregon verdict: **VIABLE only by pivoting to Lake Oswego city zoning**. RLIS remains the parcel source, but it is not a zoning source. DLCD remains halted for matrix-grade local zoning because 50/50 Lake Oswego samples had blank local code fields.

Expected ops-count lift if Master commits an ingest sprint: **+1 polygon** for Lake Oswego, assuming RLIS taxlots are staged, Lake Oswego city zoning polygons are spatially joined, and the LOC code sections behind the `INFO` links are matrix-authored.

Expected sprint shape: 4-7 days if the MapServer layer is acceptable as zoning geometry; longer if Master requires a source-normalized Lake Oswego download rather than cached scale-layer extraction.

## Summit UT / Park City Corridor

| Source | Source class | URL | 50-feature sample quality | Verdict |
|---|---|---|---|---|
| Summit County Zoning Service | County / unincorporated zoning | Item: `https://www.arcgis.com/home/item.html?id=c2aef92854e242d08ffe78d27da58834`; service: `https://services2.arcgis.com/gyfpgFh2Wj2gglYD/arcgis/rest/services/Zoning_Service/FeatureServer` | Layer 0 was not zoning polygons; it was `Ridgelines`. Actual zoning layers are layer 2 (`Snyderville Basin Planning District`) and layer 3 (`Eastern Summit County Planning District`). Snyderville returned 34 rows, not 50, with `Zone_`, `Zone_Abbre`, `Description`, `DescLink`, `AllowedUseLink`; sample zones included `RR`, `RC`, `TC`, `CC`, `NC`. Eastern Summit returned 44 rows with `Label`, `DESCRIPTIO`, `DescLink`, `AllowedUseLink`; sample zones included `AG-10`, `AG-20`. | VIABLE |
| Park City Municipal Zoning | City Class B zoning | Item: `https://www.arcgis.com/home/item.html?id=3dfd05f619154b9d882834d5b7cf269d`; layer: `https://services1.arcgis.com/wmY050uFnMPcgSCc/arcgis/rest/services/Zoning/FeatureServer/0` | 50 rows returned; fields include `ZoneID`, `ZoneType`, `Name`, `Link`, `ZoneHeight`, `message`, `message2`, `FARMax`. Sample zones included `ROS`, `RD`, `E`, `HR1`, with code links to Park City LMC. This confirms the city source behind the already-loaded Park City operational subset. | VIABLE |
| UT AGRC Summit parcels | Statewide parcel fallback | `https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Summit_LIR/FeatureServer/0` | 50 rows returned; fields include `COUNTY_NAME`, `PARCEL_ID`, `SERIAL_NUM`, `PARCEL_ADD`, `PARCEL_CITY`, `TAX_DISTRICT`, `TOTAL_MKT_VALUE`, `PARCEL_ACRES`, `PROP_CLASS`, `SUBDIV_NAME`. Good parcel fallback, but no zoning field. | PIVOT |
| UT AGRC generalized zoning | Statewide generalized zoning in progress | `https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/planning_generalized_zoning/FeatureServer/0` | 50 unfiltered rows returned with `source_zone`, `source_desc`, `gen_zone`, `county`, `city`, `statute`; first samples were Duchesne / Tabiona. Filter `county='Summit'` returned 0 rows. | HALT |

Summit verdict: **VIABLE, with a scope split**. Park City proper is already loaded/operational per `docs/PHASE6_STRUCTURAL_DIAGNOSTIC.md`; do not spend a county ingest sprint if the target polygon is entirely Park City city parcels. If the polygon is Promontory / Snyderville Basin / unincorporated Summit, Summit County zoning plus AGRC/Summit parcels is a viable separate ingest path.

Expected ops-count lift if Master commits an ingest sprint: **+1 polygon only if the polygon is outside already-loaded Park City**. If the polygon is Park City proper, ingest lift is **+0** and the correct work is a matrix/citation cleanup on existing Park City rows.

Expected sprint shape: 2-5 days after polygon confirmation. County zoning is small and explicit, but parcel-to-zone join must be spatial and the matrix needs separate Summit County code handling for Snyderville/Eastern districts. Park City city zoning is cleaner but mostly redundant with current loaded state.

## Ranked Next-Fire Order

| Rank | Target | Why | Expected ops-count lift |
|---:|---|---|---:|
| 1 | Miami-Dade FL / Pinecrest | Cleanest Class B path. Pinecrest zoning rows carry `PID`/`FOLIO`, matching county parcel keys; no statewide detour needed. | +1 |
| 2 | Summit UT / unincorporated Park City corridor | Viable if polygon is Promontory/Snyderville/unincorporated Summit. Small zoning layers with local codes; AGRC parcels are available. Confirm polygon first because Park City city proper is already loaded. | +1 conditional; +0 if already Park City |
| 3 | Clackamas/Multnomah OR / Lake Oswego | Viable only via Lake Oswego city zoning + RLIS parcels. More moving parts than Pinecrest, and PR #227 remains a hard halt for RLIS-as-zoning or DLCD local-code use. | +1 |

## Final Recommendation

Fire **Pinecrest first** if Master wants the cheapest new operational polygon. It has the clearest parcel-key bridge and a municipal zoning layer with explicit `ZONE`.

Fire **Summit second only after polygon confirmation**. If the polygon is already within Park City city limits, skip ingest and queue a Park City matrix/citation sprint instead. If it is Promontory/Snyderville Basin/unincorporated Summit, a separate Summit County ingest is feasible.

Fire **Lake Oswego third**. It is no longer a halt once the city `Zoning_cache` MapServer is accepted, but the regional Oregon sources alone remain non-operational for zoning.
