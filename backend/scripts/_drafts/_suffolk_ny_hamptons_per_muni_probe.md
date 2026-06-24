# Suffolk NY Hamptons per-muni wealth-band probe

Date: 2026-06-23  
Scope: read-only source probe for Suffolk County / Hamptons wealth-band munis and hamlets. No ingest, matrix authoring, or production writes.

## Bottom line

**Verdict: PASS for Hamptons Class B source availability.** PR #361's broad Suffolk probe was too coarse: East Hampton and Southampton both publish public ArcGIS REST zoning services. Southampton's `LandManager` service also exposes separate current-zoning layers for Sagaponack and Sag Harbor. This makes Suffolk a viable per-muni/per-town wave, not a zoning-source-missing county.

| Target | Legal/admin unit | Source verdict | Best endpoint | Zone field | Sample quality | Ranked fire order |
|---|---|---|---|---|---|---:|
| Town of East Hampton | Town | **Class B live MapServer** | `https://eh-gis.ehamptonny.gov/arcgis/rest/services/Basemaps/EHPublicMapLayers/MapServer/28` | `Zoning` | 50 / 50 nonblank; 458 polygons total | 1 |
| Wainscott | Hamlet inside East Hampton | **Covered by East Hampton town source** | Same East Hampton zoning + parcel service | `Zoning` | Source good; separate hamlet boundary not found in town service | 1b / optional carve |
| Town of Southampton | Town | **Class B live MapServer** | `https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/35` | `ZONE` | 50 / 50 nonblank; 394 polygons total | 2 |
| Bridgehampton | Hamlet inside Southampton | **Covered by Southampton town source** | Town zoning layer 35 + hamlet parcels/boundary | `ZONE` | 2,918 parcels by `HAMLET='Bridgehampton'`; town zoning source clean | 2b |
| Water Mill | Hamlet inside Southampton | **Covered by Southampton town source** | Town zoning layer 35 + hamlet parcels/boundary | `ZONE` | 2,767 parcels by `HAMLET='Water Mill'`; town zoning source clean | 2c |
| Village of Sagaponack | Incorporated village | **Class B live MapServer** | `https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/38` | `ZONE` | 8 / 8 nonblank; 5 distinct zones | 3 |
| Village of Sag Harbor | Incorporated village | **Class B live MapServer** | `https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/39` | `ZONE` | 42 / 42 nonblank; 6 distinct zones | 4 |

**Expected ops-count lift:** likely **+2 to +5** depending on Master’s operational unit choice:

- Conservative: +2 town-level flips, East Hampton + Southampton.
- Targeted Hamptons wave: +4 to +5 flips if Sagaponack, Sag Harbor, Bridgehampton/Water Mill hamlet carveouts are registered separately.
- Wainscott requires a separate hamlet/CDP boundary primitive if Master wants it as a standalone operational unit; otherwise it rides East Hampton.

## Prior context

PR #361 found:

- Suffolk has clean NYS ITS parcel substrate: `NYS_Tax_Parcels_Public/MapServer/1`.
- Suffolk total: 586,600 public 2025 parcels.
- East Hampton by `CITYTOWN_NAME = 'East Hampton'`: 25,611 parcels.
- Southampton by `CITYTOWN_NAME = 'Southampton'`: 52,728 parcels.
- NYS ITS parcel fields do not include zoning.

This probe keeps that parcel-substrate verdict and replaces the zoning-source verdict for the Hamptons canary: town-level zoning sources do exist.

## Town of East Hampton

### Source discovery

ArcGIS Online search surfaced the Town of East Hampton GIS org (`TOEHGIS`):

- Web Experience: `Public Property Search`, item `14204e91e0824d07a94c064c448fb04b`.
- Web Map: `PublicSearchMap`, item `4c2c91cde325425ca11c0900b8d55fc8`.

The web map points to:

`https://eh-gis.ehamptonny.gov/arcgis/rest/services/Basemaps/EHPublicMapLayers/MapServer`

Its item description explicitly says the map includes address information, zoning, and overlay zones for East Hampton public property search.

### Zoning layer

Layer 28:

`https://eh-gis.ehamptonny.gov/arcgis/rest/services/Basemaps/EHPublicMapLayers/MapServer/28`

| Check | Result |
|---|---|
| Layer name | `EH Zoning Boundaries` |
| Geometry | Polygon |
| Zone field | `Zoning` |
| Total zoning polygons | 458 |
| 50-feature sample | 50 / 50 nonblank `Zoning` |
| Distinct zones sampled/all queried | `A`, `A10`, `A2`, `A3`, `A5`, `B`, `CB`, `CI`, `CS`, `MF`, `NB`, `PC`, `RS`, `WF` |
| Anti-bot/auth | Public REST; no token required |

Sample rows:

| `OBJECTID` | `Zoning` |
|---:|---|
| 9 | `CI` |
| 10 | `CS` |
| 11 | `A2` |

### Parcel layer

Layer 33:

`https://eh-gis.ehamptonny.gov/arcgis/rest/services/Basemaps/EHPublicMapLayers/MapServer/33`

| Check | Result |
|---|---|
| Layer name | `EH Property Boundaries` |
| Geometry | Polygon |
| Total property features | 25,482 |
| Embedded zone field | `Zoning` |
| 50-feature sample | 50 / 50 nonblank `Zoning` |
| Sample parcel fields | `DSBL`, `GOVERN_ADDRESS`, `SCTM`, `CLASS`, `Zoning`, overlay flags |

This gives East Hampton two viable paths:

1. Class C-like parcel embedded `Zoning`.
2. Class B spatial backfill from zoning layer 28.

Recommended Lane A path: use the parcel `Zoning` field for a fast field audit, with layer 28 as the authoritative polygon cross-check. If field/polygon mismatch is low, East Hampton should be a high-confidence first Hamptons fire.

### Wainscott

Wainscott is a hamlet, not an incorporated village. It is inside East Hampton and is covered by the East Hampton town zoning/parcel services. The East Hampton service exposes village boundaries only for Sag Harbor Village and East Hampton Village; it did **not** expose a Wainscott hamlet boundary layer in the sampled public map service.

Implication: Wainscott is source-covered but not automatically carve-ready as a standalone jurisdiction. Options:

1. Treat East Hampton town as the operational unit and let Wainscott ride that flip.
2. If Master needs Wainscott standalone, add a boundary primitive from Census CDP / local planning-area PDF / another authoritative boundary source, then use East Hampton parcel `Zoning`.

## Town of Southampton

### Source discovery

Southampton’s own GIS pages expose public mapping applications. The direct REST source is:

`https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer`

This is stronger than the ePortal layer from the earlier broad search because it has a `Current Zoning` group with separate town/village zoning layers.

`Current Zoning` group:

| Layer | Name |
|---:|---|
| 35 | `Town Zoning` |
| 36 | `North Haven` |
| 37 | `Quogue` |
| 38 | `Sagaponack` |
| 39 | `SagHarbor` |
| 40 | `Southampton` |
| 41 | `Westhampton Beach` |
| 42 | `Westhampton Dunes` |

### Town zoning layer

Layer 35:

`https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/35`

| Check | Result |
|---|---|
| Layer name | `Town Zoning` |
| Geometry | Polygon |
| Zone field | `ZONE` |
| Total polygons | 394 |
| 50-feature sample | 50 / 50 nonblank `ZONE` |
| Distinct zones | 42 |
| Anti-bot/auth | Public REST; no token required |

Distinct zones:

`(QERTPD)`, `(QWRTPD)`, `APDD`, `AgPDD`, `CR120`, `CR200`, `CR40`, `CR60`, `CR80`, `HB`, `HBWCIPDD`, `HC`, `HO`, `IND-RES`, `LI200`, `LI40`, `MF44`, `MHS40`, `MPDD`, `MTL`, `MUPDD`, `NSMUPDD`, `OD`, `OSC`, `QPSUD`, `R10`, `R120`, `R15`, `R20`, `R40`, `R60`, `R80`, `RPDD`, `RTPDD`, `RWB`, `SC44`, `SCB`, `SHCRPDD`, `SMUPDD`, `TDR`, `U25`, `VB`.

Fields include direct ordinance aids:

- `DESCRIPT`
- `TYPE`
- `USE_TBL`
- `DIMENSION`

Sample `USE_TBL` value:

`https://ecode360.com/attachment/SO0286/SO0286-330a%20Residence%20Districts%20Table%20of%20Use%20Regs.pdf`

This is high-value for orchestrator matrix sprinting because the zoning layer carries use-table and dimensional-table URLs in attributes.

### Parcel / hamlet layer

Southampton ePortal layer 21:

`https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/ePortal/MapServer/21`

| Check | Result |
|---|---|
| Layer name | `Tax Parcels` |
| Total parcel features | 51,258 |
| Hamlet field | `HAMLET` |
| 50-feature sample | 49 / 50 nonblank `HAMLET` |
| Sample hamlets | `Bridgehampton`, `Water Mill`, `Village of Southampton`, `North Sea`, `Hampton Bays` |

Target hamlet/village parcel counts:

| `HAMLET` value | Parcel count |
|---|---:|
| `Bridgehampton` | 2,918 |
| `Water Mill` | 2,767 |
| `Village of Sagaponack` | 948 |
| `Sagaponack` | 461 |
| `Village of Sag Harbor` | 1,144 |
| `Sag Harbor` | 500 |

This gives a straightforward per-hamlet/per-village carveout primitive for Southampton-side targets.

## Village of Sagaponack

Layer 38:

`https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/38`

| Check | Result |
|---|---|
| Layer name | `Sagaponack` |
| Geometry | Polygon |
| Zone field | `ZONE` |
| Total polygons | 8 |
| Sample quality | 8 / 8 nonblank `ZONE` |
| Distinct zones | `AgPDD`, `OSC`, `R120`, `R40`, `R80` |
| Anti-bot/auth | Public REST; no token required |

Sample rows:

| `ZONE` | `DESCRIPT` | `TYPE` |
|---|---|---|
| `AgPDD` | Two Potato Agricultural Planned Development District | Agricultural |
| `AgPDD` | One Potato Agricultural Planned Development District | Agricultural |
| `R80` | Residence 80,000 sq. ft. | Residential |

Sagaponack therefore has a clean Class B source despite its separate village code on eCode360. This should not be treated as PDF-only.

## Village of Sag Harbor

Layer 39:

`https://gis.southamptontownny.gov/gisserver/rest/services/DataServices/LandManager/MapServer/39`

| Check | Result |
|---|---|
| Layer name | `SagHarbor` |
| Geometry | Polygon |
| Zone field | `ZONE` |
| Total polygons | 42 |
| Sample quality | 42 / 42 nonblank `ZONE` |
| Distinct zones | `OD`, `PC`, `R20`, `RM`, `VB`, `WF` |
| Anti-bot/auth | Public REST; no token required |

Sample rows:

| `ZONE` | `DESCRIPT` | `TYPE` |
|---|---|---|
| `WF` | Waterfront | Commercial |
| `RM` | Resort Motel | Commercial |
| `OD` | Office District | Commercial |

Risk: Sag Harbor Village spans Southampton/East Hampton-side geography. The Southampton `LandManager` layer likely represents the village zoning layer, but Lane A should run the usual bbox and parcel dry-run before committing. East Hampton’s public service exposes a `Sag Harbor Village` boundary but not a separate Sag Harbor zoning layer.

## Bridgehampton

Bridgehampton is a hamlet inside Southampton, not an incorporated village. It does not need a separate village zoning service.

| Check | Result |
|---|---|
| Parcel carveout | `HAMLET='Bridgehampton'` |
| Parcel count | 2,918 |
| Zoning source | Southampton `Town Zoning` layer 35 |
| Source class | Class B town FeatureServer + hamlet carveout |

Recommended action: register Bridgehampton only if Master wants hamlet-level operational units. Otherwise let it ride the Southampton town flip.

## Water Mill

Water Mill is a hamlet inside Southampton, not an incorporated village.

| Check | Result |
|---|---|
| Parcel carveout | `HAMLET='Water Mill'` |
| Parcel count | 2,767 |
| Zoning source | Southampton `Town Zoning` layer 35 |
| Source class | Class B town FeatureServer + hamlet carveout |

Recommended action: same as Bridgehampton.

## Suffolk County source check

Suffolk County’s public GIS viewer did not surface a countywide zoning layer for these towns. Its visible services are county parcel/community/environmental layers. The zoning sources are municipal/town services:

- East Hampton town ArcGIS service.
- Southampton town ArcGIS service.

This remains a per-muni/per-town Class B pattern, not a countywide Class A source.

## False positives / dead ends

- ArcGIS Online search for `Sagaponack Zoning FeatureServer` surfaced unrelated generic `Zoning` services; sampled extents and fields did not match the Hamptons target. The authoritative usable Sagaponack layer was found inside Southampton `LandManager`.
- Broad searches for `Bridgehampton`, `Water Mill`, and `Wainscott` did not surface standalone FeatureServers. Bridgehampton and Water Mill are hamlets covered by Southampton. Wainscott is a hamlet covered by East Hampton.
- Long Island Zoning Atlas remains useful context, but this probe found direct town services, so LI Zoning Atlas is not the primary ingest primitive for the Hamptons canary.

## Recommended wave plan

1. **East Hampton town first.** Source is strongest because both parcels and zoning carry `Zoning`; Wainscott can ride this town-level flip unless Master insists on a separate hamlet carve.
2. **Southampton town second.** Strong zoning layer, embedded eCode table URLs, and parcel `HAMLET` field support both town and hamlet-level plans.
3. **Sagaponack third.** Small, clean separate layer; likely fast matrix sprint.
4. **Sag Harbor fourth.** Clean separate layer, but run bbox preflight because of the Southampton/East Hampton boundary split.
5. **Bridgehampton / Water Mill as optional hamlet carveouts.** Operationally valuable if Master wants granular Hamptons flips; technically they are straightforward off the Southampton source.

## Infrastructure adapter shape

This should be a Lane A clone of the proven Class B per-muni pattern:

- Use NYS ITS or local town parcel services for parcel substrate/city-town assignment.
- For East Hampton:
  - Primary candidate: local parcel layer 33 `Zoning`.
  - QA/backfill candidate: local zoning layer 28 `Zoning`.
- For Southampton:
  - Town zoning: LandManager layer 35 `ZONE`.
  - Separate village layers: 38 `Sagaponack`, 39 `SagHarbor`, 40 `Southampton` if needed.
  - Parcel/hamlet carveout: ePortal layer 21 `HAMLET`.
- Apply strengthened gates before any write:
  - district bbox covers >= 50% parcel bbox,
  - sampled ST_Within match >= 50%,
  - 50-row field samples stay non-null/nontrivial.

## Final classification

| Target | Class | PASS/HALT |
|---|---|---|
| East Hampton | Class B, with Class C-like local parcel `Zoning` field | **PASS** |
| Southampton | Class B town FeatureServer | **PASS** |
| Sagaponack | Class B village layer in Southampton `LandManager` | **PASS** |
| Sag Harbor | Class B village layer in Southampton `LandManager`; bbox split risk | **PASS with preflight** |
| Bridgehampton | Class B hamlet carveout via Southampton town source | **PASS optional** |
| Water Mill | Class B hamlet carveout via Southampton town source | **PASS optional** |
| Wainscott | Covered by East Hampton source; standalone hamlet boundary unresolved | **PASS as town / PARTIAL standalone** |

Suffolk/Hamptons should move up the Phase 2 queue. The source blocker is not structural anymore; the remaining work is per-town/per-village registration, Class B spatial backfill, and matrix authoring.
