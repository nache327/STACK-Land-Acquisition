# DuPage IL / Hinsdale Acquisition Spec

Date: 2026-06-23

Purpose: read-only Lane A scoping for a possible per-muni Class B zoning ingestion targeting Hinsdale, IL (DuPage County), the remaining Phase 4 not-loaded wealth-pocket polygon for DuPage. DuPage County itself is already registered in prod with 336,715 parcels loaded (0 zoning_code coverage, "parcels-only" classification). The Cook IL 1.87M headless ingest is in flight separately; this spec does not interact with it.

## Bottom Line

| Field | Verdict |
|---|---|
| Canonical parcel source | **DuPage County ParcelsWithRealEstateCC FeatureServer** (already loaded in prod, 337,155 live count vs 336,715 loaded) |
| Parcel source URL | `https://gis.dupageco.org/arcgis/rest/services/DuPage_County_IL/ParcelsWithRealEstateCC/FeatureServer/0` |
| Canonical zoning source for Hinsdale | **NONE FOUND** |
| Verified class | **Class D / HALT** |
| Class C embedded parcel zoning | **NO**. DuPage `ParcelsWithRealEstateCC` has 96 fields; none are zoning-district-bearing. Has `TAXCODE`, `EXEMPTCODE`, `REA017_PROP_CLASS`, plus 15+ administrative-district fields (MUNICIPALITY, FIREPROTECTIONDISTRICT, LIBRARYDISTRICT, etc.) but no `ZONE`, `ZONING`, `ZONE_CODE`, `ZONE_CLASS`, or analog. |
| Class A statewide separate zoning layer | **NO**. Illinois does not publish a statewide zoning FeatureServer. CMAP (regional MPO for Cook/DuPage/Kane/Kendall/Lake/McHenry/Will) Data Hub does not publish an aggregated municipal zoning layer analogous to MAPC's `zoning_full`. The National Zoning Atlas Illinois project is "analyzing" 1,396 IL jurisdictions but exposes no public REST endpoint or shapefile download; its editor portal is HTTP 403 (authenticated). |
| Class A county-aggregated separate zoning layer | **NO, fundamental gap**. DuPage County only publishes `Zoning/UnincorporatedZoningData/MapServer/0` (layer name `Uninc_Zoning`, fields `ZCODE`+`ZONING`, 13 codes R-1 through I, Link_to_Ord URL). This is **unincorporated DuPage only**. Hinsdale is an incorporated village; its zoning is not in this layer. |
| Class B per-muni Hinsdale FeatureServer | **NO, no usable publisher found**. Village of Hinsdale GIS audit: zero AGOL items under `VillageOfHinsdale`, `VOHinsdale`, `VOH_`, `Hinsdale_` ownership. Village website (`villageofhinsdale.org`) has no interactive map, no GIS portal, no embedded ArcGIS viewer. Only zoning resource is a static PDF (`Hinsdale Zoning Map 2022 no overlay.pdf`) and an external American Legal code library (`codelibrary.amlegal.com/codes/hinsdaleil/`). |
| GIS Consortium membership | **NO**. Hinsdale is not a GIS Consortium member. DuPage Co members are Glen Ellyn, Carol Stream, Bensenville, Elmhurst, Glendale Heights, Willowbrook. The `ags.gisconsortium.org` Winnetka-pattern unlock does not carry to Hinsdale. |
| Multi-muni carry potential | **NONE for the wealth-pocket cohort**. Oak Brook, Burr Ridge, Clarendon Hills, Western Springs, Downers Grove are all NOT in GIS Consortium and also lack publicly indexed AGOL-owned zoning FeatureServers. Same Class D failure mode likely repeats per-muni. |
| Lane A effort estimate | **N/A — HALT**. No source to operationalize. Estimated 2-3 days of further phone/email outreach to Village of Hinsdale Community Development would be required to even establish whether internal GIS exists; not in scope. |
| Recommended dispatch | **HALT**. Park DuPage Phase 4 Hinsdale ingest. Do not re-probe for 3+ months unless a publisher signal changes (e.g. Hinsdale joins GIS Consortium, MAPC-equivalent regional aggregator launches for IL, NZA exposes a REST endpoint). |

## Current Prod State

Per task brief (not re-probed during this scoping):

- DuPage County, IL: registered jurisdiction, 336,715 parcels loaded, 0 zoning_code, classified "parcels-only"
- Hinsdale village: not separately registered; would require per-muni jurisdiction registration under the King WA Path 1 pattern if a zoning source existed

The Cook IL 1.87M ingest (separate headless agent, per memory note `project_cook_il_headless_inflight_2026_06_23`) is in flight and was not touched.

## Canonical Parcel Source

DuPage County's own parcel FeatureServer is already the source-of-record and is already loaded.

- County GIS portal: `https://www.dupageco.org/GIS/`
- Open data hub: `https://gisdata-dupage.opendata.arcgis.com/`
- Parcel viewer (interactive): `https://gis.dupageco.org/parcelviewer/`
- **ParcelsWithRealEstateCC FeatureServer (canonical)**: `https://gis.dupageco.org/arcgis/rest/services/DuPage_County_IL/ParcelsWithRealEstateCC/FeatureServer/0`

Live REST probe:

| Check | Result |
|---|---:|
| Layer name | `ParcelsRealEstate` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Illinois State Plane East NAD83 (feet), `wkid=102671`, `latestWkid=3435` |
| Capabilities | `Query, Create, Update, Delete, Uploads, Editing, Extract` |
| Max record count | 1,000 |
| Countywide parcel count | 337,155 |
| Field count | 96 |

Hinsdale is filterable via `MUNICIPALITY` admin-district field (not probed for exact value spelling in this read-only pass — likely `HINSDALE` or `Hinsdale`).

Class C gate result for parcel layer: **FAIL**. Out of 96 fields, the closest tax/zoning-adjacent fields are:

- `TAXCODE` (4-char tax code, not zoning)
- `EXEMPTCODE` (1-char exemption code)
- `REA017_PROP_CLASS` (Illinois property classification code, e.g. residential 0050 / commercial 0010 — tax classification, not zoning district)
- 15+ administrative district columns: `MUNICIPALITY`, `FIREPROTECTIONDISTRICT`, `LIBRARYDISTRICT`, `PARKDISTRICT`, `SANITARYDISTRICT`, `GRADESCHOOLDISTRICT`, `UNITSCHOOLDISTRICT`, `COMMUNITYCOLLEGEDISTRICT`, `WATERCOMMISSION`, `AIRPORTAUTHORITY`, `HIGHSCHOOLDISTRICT`, `MOSQUITOABATEMENTDISTRICT`, `SURFACEWATERDISTRICT`, `SPECIALSERVICEDISTRICT`, `SPECIALPOLICEDISTRICT`

None of these resolve to a Hinsdale zoning-district code (e.g. R-1, R-2, R-3, R-4, R-5, B-1, B-2, O, OS, I) per the Hinsdale Zoning Code Article II.

## Zoning Source Audit (All Probed Candidates Failed)

### Candidate 1: DuPage County Unincorporated Zoning (REJECTED — wrong scope)

- MapServer: `https://gis.dupageco.org/arcgis/rest/services/Zoning/UnincorporatedZoningData/MapServer`
- Layer 0: `https://gis.dupageco.org/arcgis/rest/services/Zoning/UnincorporatedZoningData/MapServer/0`
- Layer name: `Uninc_Zoning`
- Geometry: `esriGeometryPolygon`
- Spatial reference: `wkid=102671` (IL State Plane East feet)
- Capabilities: `Map, Query, Data`
- Max record count: 1,000
- Fields: `ZCODE` (double, 1-13), `ZONING` (string, e.g. R-1 through R-7, business/industrial), `Link_to_Ord` (string URL), plus geometry and shape area/length
- **Rejection reason**: explicitly scoped to UNINCORPORATED DuPage. Hinsdale is incorporated; its zoning bylaw (Hinsdale Village Code) is enforced by the Village, not by DuPage County. The county zoning ordinance does not govern Hinsdale parcels. Bbox primitive cannot pass — the county's unincorporated polygons by definition exclude the Village footprint.

### Candidate 2: Village of Hinsdale own FeatureServer (REJECTED — not published)

- AGOL search for owners `VillageOfHinsdale`, `VOHinsdale`, `VOH_*`, `Hinsdale_*`, `*_Hinsdale`: zero items returned
- AGOL search for `q="Hinsdale" IL` and `q=Hinsdale IL zoning`: returned only StoryMaps by university students, Hinsdale Lake Terrace PACE/Metra transit layers owned by `Francisco.Mari_DuPage` (a DuPage Co staffer publishing transit data, not zoning), and unrelated Hinsdale Humane Society projects
- Village website probe (`https://www.villageofhinsdale.org/` and `/government/index.php`): no interactive map, no GIS portal, no embedded ArcGIS viewer, no MapsOnline / PeopleGIS / Cartegraph endpoint linked. Only map asset is a static PDF (`Hinsdale Zoning Map 2022 no overlay.pdf`) and the architectural guide map (also static PDF)
- Zoning code is published via American Legal: `https://codelibrary.amlegal.com/codes/hinsdaleil/latest/hinsdale_il_zoning/0-0-0-39` — text-only, no spatial data
- **Rejection reason**: no live publisher exists. Village relies on internal staff using a static PDF + amlegal text code. There is no FeatureServer to ingest.

### Candidate 3: `services7.arcgis.com/R9CVCgaSS8Zy2txP/.../2021_Zoning_Districts` (REJECTED — WRONG JURISDICTION, look-alike)

- Surfaced as the top-ranked Bing/Google match for "Village of Hinsdale IL zoning ArcGIS FeatureServer"
- Layer name `Zoning Districts`, geometry polygon, single `ZONE_CLASS` field — looks zoning-shaped
- **On inspection, this is the Town of Brownsburg, Indiana** zoning layer (service description: "This map serves at the Official Zoning Map of the Town of Brownsburg, as prepared by the Department..."; copyright references "Ordinance 2012-17, effective February 1, 2013")
- WKID 2245 (Indiana State Plane West, feet) confirms Indiana
- **Rejection reason**: same Fountain Hills failure mode (look-alike from a different geography). Hard-flag in adapter so it does not get auto-resolved by URL search heuristics.

### Candidate 4: GIS Consortium (Winnetka pattern carry) (REJECTED — Hinsdale is not a member)

- `ags.gisconsortium.org/arcgis/rest/services/` folder listing: `CEH, DataSharing, GISC, Training, Utilities, VBV, VFM, VGE, VGH, VHP, VLG, VLZ, VMD, VMG, VNB, VNR, VRF, VRO, VSP, VSW, VWB, VWN, VWR` — no `VHN`, `VHD`, `VHI`, `HND`, or any Hinsdale prefix
- GIS Consortium members page (`public.gisconsortium.org/members/`): DuPage Co members are Glen Ellyn (2013), Carol Stream (2015), Bensenville (2015), Elmhurst (2021), Glendale Heights (2022), Willowbrook (2025). Hinsdale is not listed.
- **Rejection reason**: the Winnetka-pattern unlock (commit 6a07d03, Cook IL probe surfacing `ags.gisconsortium.org` for Winnetka) does not carry. Hinsdale would need to join GIS Consortium for this path to become viable.

### Candidate 5: CMAP Data Hub (regional MPO aggregator) (REJECTED — no zoning layer)

- Data Hub: `https://datahub.cmap.illinois.gov/`
- Open data portal: `https://cmap-cmapgis.opendata.arcgis.com/`
- CMAP covers 7-county region (Cook/DuPage/Kane/Kendall/Lake/McHenry/Will) — geographically would include Hinsdale
- Search for "zoning" on Data Hub returned only the Chicago Metropolitan Planning Area (MPA) Boundary item — boundary polygon, not zoning content
- **Rejection reason**: CMAP does not publish an MAPC-equivalent regional zoning atlas. CMAP's focus is transportation/land-use planning analyses, not parcel-level zoning aggregation. There is no `Zoning_Atlas_v01/MapServer/2` equivalent.

### Candidate 6: National Zoning Atlas Illinois (REJECTED — no public REST/download)

- Project page: `https://www.zoningatlas.org/illinois`
- States the NZA is "analyzing zoning conditions across all 1,396 jurisdictions" in Illinois (would include Hinsdale)
- Editor status portal `https://edit.zoningatlas.org/atlas/status/?areatype=state&areaid=17`: HTTP 403 Forbidden (authentication required, no public per-jurisdiction status)
- No public shapefile download, no GeoJSON, no ArcGIS REST endpoint surfaced
- Mercatus-style static download (precedent: Plymouth MA spec used the Mercatus NZA 2023 MA zip) was searched for IL: nothing equivalent surfaced
- Contact path: `info@landuseatlas.org`
- **Rejection reason**: project may eventually publish IL data but currently nothing public-queryable exists. Unlike MA (where MAPC `Zoning_Atlas_v01/MapServer/2` is live), there is no live IL analog.

### Candidate 7: Hinsdale internal MapsOnline / PeopleGIS / Cartegraph endpoint (NOT FOUND)

- Plymouth MA precedent: Hingham used PeopleGIS SimpliCITY at `hingham-ma.gov/183/GIS-Map` (rejected there because server-side mapfile, no REST)
- Hinsdale equivalent probe: no `/183/`, `/GIS/`, or `/maps/` path linked from Village navigation. No vendor signature (no MapsOnline, no PeopleGIS, no Cartegraph URL pattern surfaced)
- **Rejection reason**: even the rejected-fallback vendor path does not appear to exist for Hinsdale. Stronger negative signal than Hingham.

## Multi-Muni Carry

There is no carry. The Class D failure mode is structural:

- DuPage County does not aggregate incorporated-village zoning
- Hinsdale itself does not publish a FeatureServer
- The GIS Consortium pattern (which carries Glen Ellyn, Carol Stream, Bensenville, Elmhurst, Glendale Heights, Willowbrook within DuPage) does not include the wealth-pocket cohort: Hinsdale, Oak Brook, Burr Ridge, Clarendon Hills, Western Springs, Downers Grove, Naperville — none are members
- CMAP has no zoning aggregator
- NZA has no public IL endpoint

Each non-GIS-Consortium DuPage village would need a separate per-muni probe and would likely return the same HALT verdict. The wealth-pocket cohort in DuPage is structurally underserved by public GIS infrastructure relative to MAPC-covered Greater Boston, the GIS Consortium-covered Chicago northern suburbs (Winnetka, Wilmette), or Washington's WAZA-covered cities.

Note: a follow-on probe for **Elmhurst** (joined GIS Consortium 2021) would be straightforward — Elmhurst is the only DuPage wealth-adjacent muni in GIS Consortium. The folder `VLG` or `VGE` in `ags.gisconsortium.org` may carry Elmhurst zoning. Elmhurst is not on the Phase 4 wealth-pocket list per the task brief, so this is a flagged follow-on, not in scope here.

## Rejected Candidates Summary

| Candidate | Reason |
|---|---|
| DuPage Co `Uninc_Zoning` | Wrong scope (unincorporated only; Hinsdale is incorporated) |
| Village of Hinsdale own FeatureServer | Does not exist (zero AGOL items, no portal, only static PDF) |
| `services7.arcgis.com/R9CVCgaSS8Zy2txP/.../2021_Zoning_Districts` | Wrong jurisdiction (is Brownsburg, Indiana — look-alike, hard-flag for adapter) |
| GIS Consortium | Hinsdale not a member |
| CMAP Data Hub | No zoning layer published |
| National Zoning Atlas IL | No public REST or shapefile |
| Hinsdale MapsOnline/PeopleGIS/Cartegraph | No vendor endpoint exists |

## Lane A Execution Shape

**None recommended.** This is a HALT.

If forced to proceed, the only viable paths would be:

1. **Manual digitization** from the static Hinsdale Zoning Map 2022 PDF (`https://www.villageofhinsdale.org/document_center/FormsToDownload/Hinsdale%20Zoning%20Map%202022%20no%20overlay.pdf`) — would require ~40+ hours of GIS staff time to georeference, vectorize, and code-attribute the 10-12 base districts. Not in scope for Lane A. Outputs would be vintage 2022, no vintage signal, no overlay coverage.

2. **Direct outreach** to Village of Hinsdale Community Development requesting GIS shapefile delivery. Plymouth MA spec rejected this kind of outreach as "vendor data-access request; not in scope." Same reasoning applies here.

3. **Wait for NZA IL** to publish a public endpoint. Timeline unknown; project is "analyzing" per their public statement, no published release date.

4. **Encourage Hinsdale to join GIS Consortium** (out of scope, would unlock the Winnetka pattern if it happened).

## Effort Estimate

| Work item | Estimate |
|---|---:|
| Lane A operational ingest | **N/A — HALT** |
| Manual PDF digitization (rejected) | 40+ hours |
| Outreach to Village CD (rejected) | unknown timeline |
| Re-probe in 3 months | 30 min |

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Phase 4 list pressure pushes Lane A to ingest Hinsdale anyway | Wasted ingest effort, no zoning coverage, polluted DB | This spec is the gate. Mark Hinsdale Phase 4 as `Class D HALT` in the not-loaded queue. |
| Brownsburg IN look-alike (`R9CVCgaSS8Zy2txP/.../2021_Zoning_Districts`) gets auto-resolved by URL search | Wrong jurisdiction zoning ingested for Hinsdale parcels (Fountain Hills repeat) | Hard-flag this URL in any auto-resolution layer. Adapter must require explicit per-muni URL provenance. |
| DuPage Co `Uninc_Zoning` gets miscategorized as countywide | Incorporated villages get null zoning, but adapter thinks they have it | The county layer's name `Uninc_Zoning` is unambiguous; document scope in any ingest spec that uses it. |
| GIS Consortium member list changes | Hinsdale may join, unlocking the Winnetka pattern | Re-check `public.gisconsortium.org/members/` in 6 months. |
| NZA IL publishes a REST endpoint | New Class A unlock | Re-check `https://www.zoningatlas.org/illinois` quarterly. |
| Elmhurst (GIS Consortium member) gets confused for the Hinsdale path | Wrong wealth-pocket municipality flipped | Elmhurst is a separate scoping question; this spec is scoped to Hinsdale only. |

## Verdict

DuPage IL / Hinsdale is **BLOCKED at zoning acquisition**. Class D HALT.

The structural gap is publisher-side: DuPage County aggregates only unincorporated zoning, the Village of Hinsdale does not publish a FeatureServer (relies on static PDF + amlegal text code), Hinsdale is not in GIS Consortium (the Winnetka unlock), CMAP does not publish a regional zoning atlas (MAPC's MA model is not replicated in IL), and the National Zoning Atlas IL has no public REST endpoint yet.

DuPage parcels remain Class C-eligible only on the assessor classification field `REA017_PROP_CLASS`, which is a tax property class, not a zoning district — same negative pattern as the King WA `LANDUSE_CD` finding.

**Recommended next action**: park Hinsdale Phase 4 in the not-loaded queue with `Class D HALT — no usable per-muni zoning source as of 2026-06-23`. Do not re-probe for 3+ months unless one of the following publisher signals changes:

1. Hinsdale joins the GIS Consortium (re-check `public.gisconsortium.org/members/` quarterly)
2. National Zoning Atlas IL exposes a public REST or downloadable IL layer (re-check `https://www.zoningatlas.org/illinois` quarterly)
3. CMAP launches an MAPC-equivalent regional zoning atlas (no announced plan)
4. Village of Hinsdale Community Development publishes any new map portal (re-check `villageofhinsdale.org` annually)

This spec exists so DuPage / Hinsdale is **not re-probed by a future Lane A research probe in 3 weeks**. The negative finding is durable until one of the above publisher signals changes. Elmhurst (the only DuPage wealth-adjacent GIS Consortium member, joined 2021) is flagged as a separate follow-on scoping target outside the Phase 4 wealth-pocket list.
