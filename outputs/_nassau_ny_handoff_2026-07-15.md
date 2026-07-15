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

## Zoning sources located (bindable)
- **Town of Oyster Bay** (biggest needle): FeatureServer
  `https://services7.arcgis.com/R9CVCgaSS8Zy2txP/ArcGIS/rest/services/2021_Zoning_Districts/FeatureServer/0`
  — 9,107 polygons, fields `ZONE_CLASS` (short) + `ZONE_CLASS_LONG`. Per the current 2012 ordinance.
  Industrial zones: **I1 (Low Intensity Industrial), I2 (High Intensity Industrial), EC (Employment
  Center)**; commercial C1/C2/HC/UC. **#38: M1/M2/M3 = Multiple-family Residential, NOT Manufacturing**
  (same trap as Tarrytown). Ordinance: eCode360 **OY1221 Chapter 246**; use schedule = **§ 246-5.2
  "Schedule of Use Regulations" (Attachment 17 — a large attachment table)**. Web-confirmed: "Warehouse,
  distribution and storage uses" = **PP (Permitted Principal)** in the Industrial (I1/I2) category → the
  needle is real; ground as warehouse-by-right ⇒ self-storage conditional (convention) UNLESS "self-service
  storage" is separately named. ⚠️ NY-schedule caution (memory New Rochelle lesson): the use table is an
  attachment PDF — parse it with the DOM/attachment anchor, NOT a naive text read.
- **Town of Hempstead / Town of North Hempstead**: sources still to locate (each town has its own GIS +
  ordinance; Hempstead-town has the most parcels but modest in-ring whse/ind — 34/13). Freeport + Glen Cove
  = small municipal ordinances.

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

## Handoff to coordinator
- **jid c72002c7-1f3e-48e4-be98-04e420776fdb** — municipality-bound (city from MUNI_NAME); ring done;
  zoning bind + grounding is a scoped multi-town batch (sources above). **Current wealth-gated needles: 0**
  (no zoning bound yet — structurally 0 until step 1/2). Needle POTENTIAL proven real (Oyster Bay
  ~120 whse + 105 ind in-ring is a top-tier target). No CoStar / re-score run (per instructions).
