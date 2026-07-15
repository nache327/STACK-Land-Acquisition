# Session B exceptions — 58-pocket finish-in-place queue

## (1) Darien CT (jid 9b27e214-367c-4652-8385-99b09fe38cd6) — DONE: bound + grounded no-op
- SEPARATE jid from Fairfield county. parcels=5,831, ring dt10 DONE (all wealth-pass), was zoned=0.
- **Bound 99.6%** (5,810/5,831) via `scripts/_bind_darien_ct.py` — town parcel-GIS ZONING attribute
  (services7.arcgis.com/QoSt1vkU9IRboBnD `Darien_Current_Parcels`), APN join (our apn = '18850-'+PIN),
  provenance `darien_ct_parcels_gis`. (No standalone zoning-districts layer exists; the generic
  services.arcgis.com "Zoning_Districts" hit in search was an **Alaska** town — #38 wrong-jurisdiction,
  discarded.)
- **DEFINITIVE NO-OP: 0 self-storage needles.** Darien Zoning Law 2021 has a CLOSED LIST ("A prohibited
  use includes any use not specifically permitted in a zoning district") and DEFINES self-storage as a
  distinct use ("a warehouse ... shall not be considered a self-storage facility") that is listed as a
  permitted use in NO district. Self-storage at 131 Hollow Tree Ridge Rd required a site-specific
  Affordable-Housing amendment — confirming it is not a base-district use. Warehouse-by-right convention
  OVERRIDDEN (town separates self-storage from warehouse explicitly). Wealthy residential town, self-storage
  zoned out — same lesson as Greenwich/Hudson.
- **#38 GIS-vs-ordinance code mismatch flagged:** the parcel-GIS ZONING field uses granular legacy codes
  (CBD/DB/SB/NB/DO/DC/DMR/RNBD/MU) that do NOT appear as district names in the 2021 Zoning Law (consolidated
  to C / MU-CC / MU-NC / I / MDR / REC). GIS codes are the operative parcel designations and the matrix keys
  on them; self_storage=prohibited holds under the current law regardless of mapping. light_industrial set
  conservatively prohibited (no parcel GIS-coded to the ordinance's C/I warehouse districts; li ≠ needle).
- 19 zone rows grounded (all prohibited). verify_batch CLEAN, gate PASS, matrix_coverage 100%.
