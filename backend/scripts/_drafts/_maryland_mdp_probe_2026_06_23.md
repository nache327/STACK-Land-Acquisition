# Maryland MDP statewide GENZONE probe

Date: 2026-06-23  
Scope: read-only infrastructure probe for Maryland Department of Planning statewide `Generalized Zoning_2025`. No ingest, code, matrix authoring, or production writes.

## Verdict

**PASS as a public statewide Class A candidate, with a truthfulness caveat.**

Maryland Department of Planning publishes a public statewide generalized-zoning layer covering Maryland county/city jurisdiction codes. The layer is live, queryable without auth, and carries both:

- `GENZONE` - generalized use classification
- `ZONING` - local zoning code / district label

The layer is excellent infrastructure for a Maryland multi-county zoning-district ingest, but it is **not** a local ordinance substitute. MDP's item description explicitly says generalized zoning is not meant to determine permissible uses for a specific property and points users to local zoning offices. Use it to populate parcel `zoning_code` and district geometry; keep matrix verdicts tied to county/local ordinances.

Bottom line:

| Question | Result |
|---|---|
| Public endpoint live? | **YES** |
| Auth required? | **NO** |
| Geometry type | Polygon |
| Statewide feature count | `2,226` polygons |
| Core fields | `JURSCODE`, `ZONING`, `GENZONE`, `MUNICIPALITY_NAME`, `UPDATEYR`, `ACRES` |
| Requested county samples | Howard, Baltimore County, Anne Arundel all `50/50` non-null `GENZONE` and `ZONING` |
| Source class | **Class A: public statewide zoning polygons, not yet bound to parcels** |
| Immediate canonical 58-list lift | **0**, because current `docs/TARGET_MARKETS.md` MD counties Montgomery + Howard are already operational |
| Expansion lift if nache adds MD candidates | **Baltimore County + Anne Arundel are the best next targets** |

## Endpoint

ArcGIS item:

`https://www.arcgis.com/sharing/rest/content/items/4f97daeeaab341b18eeccc068121497c?f=json`

Service endpoint:

`https://mdpgis.mdp.state.md.us/arcgis/rest/services/PlanningCadastre/Generalized_Zoning_2025/MapServer/0`

Item metadata:

- Title: `Generalized Zoning_2025`
- Owner: `mdplanning`
- Type: `Feature Service`
- Access: `public`
- Service URL: `https://mdpgis.mdp.state.md.us/arcgis/rest/services/PlanningCadastre/Generalized_Zoning_2025/MapServer/0`

Layer metadata:

- Name: `Generalized Zoning 2025`
- Type: `Feature Layer`
- Geometry: `esriGeometryPolygon`
- Capabilities: `Map,Query,Data`
- Max record count: `2000`
- Spatial reference: Maryland StatePlane NAD83 meters, `wkid 26985`

Field audit:

| Field | Alias | Type | Notes |
|---|---|---|---|
| `GENZONE` | Generalized Zoning | string | Generalized use class |
| `OVERLAY` | Overlay | string | Optional overlay |
| `JURSCODE` | Jurisdiction Code | string | Four-letter county/city code |
| `ZONING` | Zoning | string | Local zoning district/code |
| `MUNICIPALITY_NAME` | Municipality Name | string | Present when zoning authority is municipal |
| `ABBREVIATION` | Abbreviation | string | Muni abbreviation |
| `UPDATEYR` | Update Year | string | MDP collection date |
| `ACRES` | GIS Acres | double | District area |
| `Source` | Source | string | Link to more information; often null in samples |
| `GENZONE_CAT` | Generalized Zoning Categories | string | Category-document URL |

MDP caveat from item description:

> Generalized zoning data is not meant to substitute for local zoning information and should not be used to determine permissible uses or other potential development of a specific property.

Implication: this layer is valid for polygon backfill infrastructure, not for skipping ordinance-backed matrix citations.

## Requested county samples

### Howard County (`JURSCODE='HOWA'`)

Sample query:

`where=JURSCODE = 'HOWA'`, `resultRecordCount=50`, `returnGeometry=false`

Result:

- Sample size: `50`
- `GENZONE` non-null: `50/50`
- `ZONING` non-null: `50/50`
- Total Howard feature count: `56`
- Distinct local zoning values: `34`
- Update year in first rows: `20250228`

Sample `GENZONE` values:

- `COMMERCIAL`
- `HIGH DENSITY RESIDENTIAL`
- `INDUSTRIAL`
- `LOW DENSITY RESIDENTIAL`
- `MEDIUM DENSITY RESIDENTIAL`
- `MIXED USE`

Sample `ZONING` values:

- `B-1`
- `B-2`
- `BR`
- `CAC`
- `CCT`
- `M-1`
- `M-2`
- `NT`
- `OT`
- `PEC`
- `PGCC-1`

Calibration note: repo history shows Howard is already operational and existing adjudication scripts use Howard local zoning codes such as `NT`, `M-1`, `M-2`, `PEC`, `OT`. The MDP layer's `ZONING` values align with that local-code shape.

### Baltimore County (`JURSCODE='BACO'`)

Sample query:

`where=JURSCODE = 'BACO'`, `resultRecordCount=50`, `returnGeometry=false`

Result:

- Sample size: `50`
- `GENZONE` non-null: `50/50`
- `ZONING` non-null: `50/50`
- Total Baltimore County feature count: `82`
- Distinct local zoning values: `37`
- Update year in first rows: `20250228`

Sample `GENZONE` values:

- `COMMERCIAL`
- `HIGH DENSITY RESIDENTIAL`
- `INDUSTRIAL`

Sample `ZONING` values:

- `BL`
- `BM`
- `BMB`
- `BMM`
- `BMYC`
- `BR`
- `DR 10.5`
- `DR 16`
- `MH`
- `ML`
- `O 3`
- `OR 1`
- `OR 2`
- `OT`
- `RAE 1`

Interpretation: Baltimore County is the strongest expansion target from this probe because it is visible in MDP with dense local-code coverage and nache's note names Roland Park / Ruxton as likely candidates.

### Anne Arundel County (`JURSCODE='ANNE'`)

Sample query:

`where=JURSCODE = 'ANNE'`, `resultRecordCount=50`, `returnGeometry=false`

Result:

- Sample size: `50`
- `GENZONE` non-null: `50/50`
- `ZONING` non-null: `50/50`
- Total Anne Arundel feature count: `67`
- Distinct local zoning values: `67`
- Update year in first rows: `20250228`

Sample `GENZONE` values:

- `COMMERCIAL`
- `HIGH DENSITY RESIDENTIAL`
- `INDUSTRIAL`
- `LOW DENSITY RESIDENTIAL`
- `MEDIUM DENSITY RESIDENTIAL`
- `MIXED USE`

Sample `ZONING` values:

- `A-B1`
- `A-B2`
- `A-B3`
- `A-C1`
- `A-C2A`
- `A-I1`
- `A-R1`
- `A-R2`
- `A-R3`
- `C1`
- `C2`
- `C3`
- `C4`

Interpretation: Anne Arundel is also viable from the MDP layer. Severna Park is the named expansion candidate from nache's note, but it is not currently listed in `docs/TARGET_MARKETS.md`.

## Statewide coverage summary

Statewide count query returned `2,226` polygons. Statistics grouped by `JURSCODE`:

| JURSCODE | Feature count | Acres summed from layer |
|---|---:|---:|
| `ALLE` | 61 | 270,285 |
| `ANNE` | 67 | 264,769 |
| `BACI` | 66 | 54,726 |
| `BACO` | 82 | 389,421 |
| `CALV` | 30 | 137,617 |
| `CARO` | 82 | 198,789 |
| `CARR` | 111 | 289,562 |
| `CECI` | 138 | 224,841 |
| `CHAR` | 64 | 294,228 |
| `DORC` | 60 | 359,316 |
| `FRED` | 145 | 428,772 |
| `GARR` | 49 | 420,483 |
| `HARF` | 54 | 281,027 |
| `HOWA` | 56 | 162,110 |
| `KENT` | 66 | 178,114 |
| `MONT` | 424 | 298,632 |
| `PRIN` | 52 | 280,859 |
| `QUEE` | 102 | 229,984 |
| `SOME` | 31 | 202,597 |
| `STMA` | 33 | 215,958 |
| `TALB` | 105 | 170,189 |
| `WASH` | 148 | 299,456 |
| `WICO` | 106 | 232,791 |
| `WORC` | 94 | 297,926 |

Note: a separate distinct-combination query returned smaller counts for some jurisdictions because duplicate feature rows collapse when `returnDistinctValues=true`. The table above uses ArcGIS grouped statistics, not a capped raw row page.

## Prod / 58-list overlap

Current `docs/TARGET_MARKETS.md` canonical 58-list includes MD in Phase 3 as:

- Montgomery MD: Bethesda, Potomac - already operational in docs
- Howard MD - already operational in docs

Live prod coverage retry returned:

| Jurisdiction | Parcel count | Zoning code coverage | Readiness |
|---|---:|---:|---|
| Montgomery County, MD | 281,249 | 95.3% | operational |
| Howard County, MD | 97,775 | 91.5% | operational |

Baltimore County and Anne Arundel did not appear in the coverage list returned by the probe, so treat them as not currently operational/registered unless nache has a branch-local registration outside main/prod.

Important distinction:

- **Current canonical 58-list immediate lift:** none from Montgomery/Howard because both are already operational.
- **Nache expansion candidates:** Baltimore County (Roland Park / Ruxton) and Anne Arundel (Severna Park) are the first two targets if Master expands the MD domain.

## Per-county lift ranking

| Rank | County / code | Campaign status | MDP source quality | Expected lift | Recommendation |
|---:|---|---|---|---:|---|
| 1 | Baltimore County (`BACO`) | nache expansion candidate; not in current canonical table | 82 polygons, 50/50 sample non-null, 37 distinct local codes | +1 if Roland Park / Ruxton is formalized | Best next MD proof |
| 2 | Anne Arundel (`ANNE`) | nache expansion candidate; not in current canonical table | 67 polygons, 50/50 sample non-null, 67 distinct local codes | +1 if Severna Park is formalized | Second MD proof |
| 3 | Montgomery County (`MONT`) | canonical Phase 3, already operational | 424 polygons, 100% local-code population in layer | +0 immediate | Use as regression/calibration only |
| 4 | Howard County (`HOWA`) | canonical Phase 3, already operational | 56 polygons, 50/50 sample non-null, aligns with existing Howard local codes | +0 immediate | Use as calibration |
| 5 | Prince George's (`PRIN`) | not in current target list | 52 polygons, 100% populated | unknown | Hold for customer signal |
| 6 | Frederick / Carroll / Harford / Baltimore City | not in current target list | populated | unknown | Hold for customer signal |

## Infrastructure adapter shape

Recommended execution shape if Master/nache proceeds:

1. Add a Maryland MDP statewide zoning-source adapter or directory entry for:

   `https://mdpgis.mdp.state.md.us/arcgis/rest/services/PlanningCadastre/Generalized_Zoning_2025/MapServer/0`

2. Filter by `JURSCODE` for the target county.
3. Preserve both:

   - `ZONING` as local `zone_code` candidate
   - `GENZONE` as generalized class / QA aid, not as final matrix verdict

4. Ingest polygons through the existing zoning-district ingestion path.
5. Run Lane A's strengthened Class A gates:

   - district bbox covers at least 50% of parcel bbox
   - 1,000-parcel ST_Within dry-run at least 50% match
   - nearest fallback cap / provenance gates unchanged

6. Matrix rows still need local ordinance citations by county code. `GENZONE` can triage likely residential/commercial/industrial families, but it should not replace ordinance evidence.

Expected adapter effort:

- One-county proof (Baltimore or Anne Arundel): `4-8h` after parcel substrate exists.
- Reusable statewide adapter after proof: `1-2 days` for robust JURSCODE filtering, provenance, bbox/dry-run reporting, and matrix handoff.
- Additional counties after adapter: likely `1-3h` source ingest/backfill per county plus separate matrix sprint, assuming parcel substrate already exists.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Generalized layer is not parcel-specific zoning law | Truthfulness risk if used for permitted-use verdicts | Use `ZONING` for code population only; cite local ordinances for matrix |
| Municipal zoning updates lag county updates | Muni pockets could be stale if they have zoning authority | Check `MUNICIPALITY_NAME`, `UPDATEYR`, and local GIS for target munis |
| Coarse polygons may not cover parcel boundary edge cases | Backfill misses or false joins | Run bbox and ST_Within dry-runs before writes |
| Montgomery has many district variants (`424` rows) | Matrix expansion could be heavy if reused | Avoid reworking operational Montgomery unless regression/calibration requires |
| Baltimore/Anne not in canonical `TARGET_MARKETS.md` | Count lift depends on Master/nache formalizing these candidates | Treat this as expansion scoping, not automatic 58-list work |

## Hand-off note for nache

The MDP `Generalized_Zoning_2025` layer is real, public, and strong enough for a Maryland statewide Class A zoning-district adapter proof. Howard calibration is favorable: MDP `ZONING` values include the same local-code family already used by the Howard operational matrix (`NT`, `M-1`, `M-2`, `PEC`, `OT`). The main caveat is truthfulness: MDP says the layer is generalized and not a local-use substitute, so it should populate `parcels.zoning_code` / `zoning_districts`, while matrix verdicts remain county-ordinance-cited. If you want the highest-ROI proof outside already-operational Montgomery/Howard, start with Baltimore County (`BACO`) for Roland Park / Ruxton, then Anne Arundel (`ANNE`) for Severna Park.
