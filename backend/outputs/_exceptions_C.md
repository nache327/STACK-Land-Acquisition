# Session C exceptions — New Canaan + Darien CT (ct-newcanaan-darien-batch1)

## Darien CT (jid 9b27e214-367c-4652-8385-99b09fe38cd6) — STAGE-1 BLOCKED (not grounded)
**Do NOT ground.** Darien is Stage-1 blocked exactly like the earlier NJ Tier-1 / A-Essex case:
- parcels: 5,831 — **`zoning_code` is NULL on 100% of them** (0% zone-bound).
- `zone_use_matrix`: 0 rows.
- Grounding now would only create false, unmatchable rows (the m.zone_code=p.zoning_code join
  can't match a NULL code) → silent 0-scoring, no needles, no value. So it is deliberately skipped.

**Good news — Stage 3 is already done:** `parcel_ring_metrics` has 5,831 dt=10 rows for Darien
(ring precompute complete). The ONLY missing piece is Stage-1 spatial zone binding.

**A bindable zoning-polygon source DOES exist** (this is the A/Essex situation — a source is
available, the bind just hasn't been run). Options, in order of preference:
  1. **Town of Darien ArcGIS** — `https://darienct.maps.arcgis.com/` publishes a zoning layer
     (streets/wetlands/zoning). New Canaan's identical situation was solved by binding to its town
     Tighe & Bond zoning layer (`hostingdata3.tighebond.com/.../NewCanaanDynamic/MapServer` L89,
     `Code`->`ZONING`); Darien's town layer is the direct analog. Confirm the layer + its zone-code
     field, then run the standard spatial bind (ST_Within(ST_Centroid)) like New Canaan.
  2. **CT ECO / CT Geodata Portal** — `https://geodata.ct.gov/maps/CTECO::darien` (statewide parcel
     collection; check for an accompanying municipal zoning polygon).
  3. **WestCOG** (Darien is in the Western CT COG region) regional zoning polygons.

**Next action (Stage-1 owner, not this grounding session):** bind Darien parcels to the town zoning
polygon → then a normal grounding pass can run (expected another estate-residential no-op given
Darien's profile, but must be grounded on its own ordinance once bound). CT ordinance is on the
Darien P&Z site / eCode/amlegal.

## New Canaan CT (jid 2580f226…) — GROUNDED, correct no-op (0 needles)
- 100% zone-bound (7,386 parcels, 16 letter codes A–Q). Ring-ready (4,807 dt=10).
- #38 layer check PASSED: parcel letter codes = the Town GIS zoning-layer `Code` field, decoded via
  the authoritative `Code`->`ZONING` legend (Tighe & Bond NewCanaanDynamic/MapServer L89). Note
  'I' = **Business A**, NOT Institutional — confirms the #38 caution.
- Estate-residential + "Village District" business zones (Retail A/B, Business A/B/C/D); **no
  industrial zone**. Self-storage / self-service storage / mini-warehouse is a permitted use in
  **no** zone (whole-text: 0 self-storage hits; the single "warehous" hit is a Business-B parking
  computation — a dimensional-mention, not a use grant). All 16 zones grounded PROHIBITED. Correct
  no-op (Greenwich/Westport pattern). verify_batch: needles=0 gate=PASS CLEAN.
