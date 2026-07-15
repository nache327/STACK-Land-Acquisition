# Nassau County NY (jid c72002c7-1f3e-48e4-be98-04e420776fdb) — Phase-2 status + handoff (2026-07-15)

## What was blocking, what's now done
Nassau was **doubly-gapped**: `parcels.city` NULL for ALL 420,577 parcels AND `zoning_code` = 0 (ring10
already 95.8% done, 402,700). NY has **no regional zoning aggregate** (unlike NJ's NJTPA), and **Nassau
County publishes NO countywide zoning layer** (its GIS `gis.nassaucountyny.gov` has parcels/`TownCity`
boundaries/addresses only; the parcel layer carries NYS land-use class `luc`, NOT zoning). Zoning lives
only at the 69-municipality level.

**DONE this session — the municipality bind:** `parcels.city` backfilled from the ingest blob
`raw->>'MUNI_NAME'` (the authoritative NYS assessing municipality — village name where incorporated, else
town). 69 distinct munis; `city_source='raw_muni_name'`. No spatial join needed (the data was already in
`raw`). This unblocks the buybox join (`municipality = parcels.city`) for the whole county. Script:
`backend/scripts/_backfill_nassau_city.py`.

## The needle IS real — and it's concentrated in the 3 TOWNS, not the 69 villages
Discovery via NYS `PROP_CLASS` proxy (in-ring dt10 HV≥475k/HHI≥100k, acres≥1.5), by municipality:

| Municipality (MUNI_NAME) | comm+ind (4xx/7xx) | warehouse/storage (44x) | industrial (7xx) |
|---|---|---|---|
| **Oyster Bay** (town unincorp) | 517 | **120** | **105** |
| **North Hempstead** (town) | 290 | 45 | 34 |
| **Hempstead** (town unincorp) | 814 | 34 | 13 |
| **Freeport** (village) | 275 | 8 | 12 |
| **Glen Cove** (city) | 53 | 6 | 9 |
| Garden City | 381 | 0 | 0 (retail/office only) |

The wealthy **Gold Coast villages are correct no-ops** (Muttontown 0 whse, Upper/Old Brookville ~0,
North Hills 0, East Hills ~0 — pure-residential estate zoning, same lesson as Greenwich/Cherry Hills).
**The industrial needle sits in the town unincorporated areas + Freeport/Glen Cove** — i.e. **3 town
ordinances + 2 small city/village ones**, NOT 69 villages. Tractable.

## ⛔ ZONING SOURCE — BLOCKED (correction 2026-07-15, supersedes the earlier "FeatureServer located")
**The zoning-source situation is worse than first reported. Nassau has NO accessible spatial zoning layer.**
- ❌ **WRONG-JURISDICTION TRAP (do NOT use):** `services7.arcgis.com/R9CVCgaSS8Zy2txP/.../2021_Zoning_Districts`
  is **Brownsburg / Hendricks County, INDIANA — NOT Town of Oyster Bay, NY.** A web search conflated it (it
  happens to have I1/I2/EC/HC/M1-M3 codes + a "Town of Oyster Bay"-ish hit). Proof: its `Parcel_Info` records
  read `PropertyCity=Brownsburg`, Indiana township names (Lincoln/Brown), Indiana parcel IDs
  (`32-07-12-300-...`), and CRS wkid **2966 = Indiana East State Plane** (its geometry reprojects to
  ~-86.4°,39.9° = Indiana, not -73.5°,40.9° = Nassau). A dry-run centroid bind gave **0% coverage** (correctly
  — the geometry is 1,000 mi away), so **no parcels were bound** (verified Oyster Bay zoned=0). Had it been
  applied blind it would have poisoned NY parcels with Indiana zoning. Catch #38 at the source layer.
- ❌ Nassau County GIS (`gis.nassaucountyny.gov`) — parcels/`TownCity`/addresses only, **no zoning**.
- ❌ NYS GIS Clearinghouse (`gisservices.its.ny.gov`) — Locators/Utilities only, no zoning.
- ✅ **Real Town of Oyster Bay NY zoning = PDF maps only** (oysterbaytown.com/wp-content/uploads/Zone-Maps-all.pdf,
  TOB-Zoning-Maps.pdf) + the **correct ordinance** eCode360 **OY1221 Chapter 246 §246-5.2 Schedule of Use
  Regulations** (this IS Oyster Bay NY — verified title). #38 note still holds for the REAL town: M1/M2/M3 =
  Multiple-family Residential. "Warehouse, distribution and storage" = PP in I1/I2 per the schedule.

**⇒ Nassau grounding is BLOCKED on zoning-source acquisition.** No per-parcel or polygon zoning layer exists
for the NY towns; zoning is PDF-map-only. To ground, someone must EITHER (a) georeference the town zoning-map
PDFs into polygons (heavy GIS), (b) locate a hidden town/LRV REST zoning layer (not found via county/NYS/town
sites), or (c) obtain a per-parcel zoning table (e.g. the town's Citizenserve/permitting export or a paste).
This parallels the Essex-NJ Stage-1 escalation — except NY has no NJTPA-style regional aggregate to rescue it.

## Ready-to-execute plan for the grounding batch (next session)
1. **Bind Oyster Bay zoning** (spatial centroid-within, geopandas — the `bind_nj_atlas082025.py` pattern):
   fetch the 9,107 OB polygons (outSR 4326), sjoin the `city='Oyster Bay'` parcels' centroids, write
   `zoning_code`=ZONE_CLASS, `zoning_code_source='oysterbay_gis_2021'`. (~80k OB parcels; village parcels
   have their own MUNI_NAME so they won't wrongly pick up town codes.)
2. **Ground Oyster Bay** I1/I2/EC (+ commercial) from § 246-5.2 (parse the attachment table): warehouse/
   storage PP ⇒ ss/mw per convention; verbatim citations (#37); M1/M2/M3 = multifamily no-op (#38);
   closed-list sweep (#57/#58); lgc→prohibited.
3. Repeat bind+ground for Hempstead-town, North Hempstead-town, Freeport, Glen Cove (source each layer).
4. `verify_batch` + `postingest_gate` + direct SELECT needle count (#42). NOTE: full-county needle LATERAL
   is slow on 420k — use the targeted per-(muni,zone) count over grounded permitted/conditional zones.

## Handoff to coordinator (updated 2026-07-15)
- **jid c72002c7-1f3e-48e4-be98-04e420776fdb** — municipality-bound (city from MUNI_NAME, 100%); ring done
  (95.8%). **Current wealth-gated needles: 0** and **BLOCKED** — zoning cannot be bound: no county/NYS/regional
  spatial zoning layer, towns are PDF-map-only, and the one "FeatureServer" a search surfaced is Brownsburg
  INDIANA (wrong jurisdiction — flagged above, NOT bound). Needle POTENTIAL is real (Oyster Bay ~120 whse +
  105 ind in-ring) but ungroundable until a zoning source is acquired.
- **DECISION NEEDED:** Nassau is a Stage-1 zoning-acquisition project, not a same-session grounding batch.
  Options: (a) PDF-map georeferencing per town, (b) hunt a hidden town/LRV REST zoning layer, (c) per-parcel
  zoning paste/export. Recommend deprioritizing vs. pockets that only need ring+ground on already-bound jids
  (per the 58-pocket ledger) until a zoning source is secured. No CoStar / re-score run (per instructions).
