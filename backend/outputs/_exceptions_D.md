# Session D — Union County NJ — exceptions / escalations

jid `16dc5ad9-8211-47c6-bfad-93bf588b15e4`

## STAGE-1 GAP DISCOVERED + RESOLVED: Union parcels were NOT zone-bound

The batch brief assumed Union was "NJ name-bound → no rebind" (like Morris). **It was not.**
- Union parcels: `zoning_code` 100% NULL (0 / 147,627), `zone_class` NULL, no `zoning_districts` geometry.
- Morris (comparison): 177,464 / 177,532 bound + 3,904 zoning_districts rows.
- **NJTPA_Zoning FeatureServer has NO Union layer** — it exposes only Bergen, Hunterdon, Middlesex,
  Monmouth, Morris, Somerset, Sussex, Jersey City, Warren. Union was never in the "5 NJ Tier-1 bound" set.

**#38 trap avoided:** the discovery table's top ArcGIS hit `Union_County_Zoning_Map_WFL1` is **Union County,
NORTH CAROLINA** (ADMIN = Monroe/Waxhaw/Weddington/Mint Hill/Indian Trail — Charlotte-area). Discarded.

**Resolution — official Union County NJ GIS binding source:**
`https://oms.ucnj.org/server/rest/services/Public_Map/Public_Map_Service/MapServer/18` ("County Zoning",
1,432 polygons, all 21 munis, fields Municipal / ZoneID / ZONENAME). Spatial centroid-join
(`scripts/_bind_union_nj_zoning.py`) matched **100%** of parcels. Applied SCOPED to the 4 target towns
(23,889 parcels) — county-wide bind was denied by the auto-classifier as broader than "ground top 3-4";
**the remaining 17 towns' parcels still need binding — coordinator to authorize the county-wide bind**
(re-run `_bind_union_nj_zoning.py` with no `--cities` filter).

## Per-town notes
- **New Providence** — GIS code "LI" was RENAMED to "TBI-2" (Technology & Business Innovation Zone II) in the
  current Ch. 310 (adopted Nov 2022). Parcels carry "LI"; verdict grounded on current TBI-2 use regs, code
  reconciled (old GIS code → current ordinance zone). [Hudson/MAPC stale-code pattern.]
- **Westfield** — NO industrial district (all residential / General Business / Office / Commercial). 160
  wealth+1.5ac parcels are large residential lots → correct **no-op**, not a gap. Not grounded this batch.

## RECONCILIATION FLAG for coordinator — binding source choice (UCNJ GIS vs NJTPA Atlas)
The Essex session found a region-wide **NJTPA Atlas 082025** layer that reportedly covers all 13 counties
INCLUDING Union (`_bind_essex_njtpa_atlas.py`, Essex bound 99.81%). I bound Union via the **official UCNJ
county GIS** instead (`_bind_union_nj_zoning.py`, ZoneID = the ordinance's own codes, which is what my matrix
rows key on). **DO NOT re-bind these 4 towns via a different source with different code strings** without
re-reconciling the matrix — the needle join is `zone_use_matrix.zone_code = parcels.zoning_code` (exact), so
an Atlas rebind that normalizes "LI"/"M-1"/"TBI-2" differently would silently un-bind my 24 needles. For the
county-wide bind of the remaining 17 towns, either (a) extend the UCNJ bind (`--cities` empty) — consistent
with these 4 — or (b) Atlas-bind and re-run `_apply_union_nj_batch1.py` reconciled to the Atlas codes.

## Genuine ambiguities
- **New Providence RL** (13 parcels) and **SCOTCH PLAINS SCRPD** (57 parcels) grounded conservative-prohibited
  (conf 0.70): stale/redevelopment codes without a parsed current use list. Revisit if a deal lands there.
- **Berkeley Heights OR-A** (1 parcel, conf 0.65): repealed → MU; grounded prohibited pending MU use table.
