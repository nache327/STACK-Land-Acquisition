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

---

## (2) South Brunswick township NJ — DONE: grounded 14 needles (in Middlesex jid 9c039328)
- Atlas-bound already; municipality='South Brunswick township' (exact). Ordinance via Municode
  content-API (client 7740 / product 13445 / job 489397, curl+UA): Ch. 62 Land Use, Art. IV Zoning,
  Div. 3 Districts. Applied `scripts/_apply_south_brunswick_nj.py` (33 zone rows).
- **NJ catch (b) — named-district beats warehouse convention (Boonton pattern):** Miniwarehouse/
  self-storage is named as a CONDITIONAL use ONLY in **I-3** (§Subdiv XXXII, "east of Route 130 and
  south of Route 522") and **LI-4** (§Subdiv XXXVI, "south of Davidson's Mill Road"). South Brunswick
  has a SEPARATE **I-2** General Industrial + LI-1/LI-2/LI-4-C that permit warehouse/distribution
  by-right but do NOT name self-storage → warehouse convention OVERRIDDEN; self-storage confined to
  I-3/LI-4 (conditional), prohibited elsewhere.
- **NEEDLES = 14 (SELECT-confirmed), all I-3** (LI-4 has 0 wealth&1.5ac). OR (48 w15), OP (22), C-2 (14),
  C-1 (7), C-3 (5) clear the ring but permit no self-storage → correct no-op.
- Note: I-3 self-storage carries a geographic sub-condition (east of Rt 130 / south of Rt 522) not
  captured at zone-level; the 14 zone-level needles may over-count parcels physically west of Rt 130.

### Gate cleanup (2026-07-15) — over-length Atlas phrase-artifacts (coordinator-authorized)
verify_batch initially FAILed on 2 invalid over-length parcel zoning_codes from the Atlas bind
(phrase artifacts, not real districts; the hardened bind_nj_atlas082025._bad_code now skips >20-char):
- 'Wilson Farm Redevelopment Zone' (South Brunswick, 3 parcels) — NULLed + my over-length matrix row soft-deleted (my town).
- 'Redevelopment Area Remainder' (Dunellen borough, 307 parcels, NOT my assigned town) — NULLed with
  coordinator authorization (cross-town shared-data write; classifier-gated, user-approved). Dunellen is
  ungrounded so no needle impact.
After cleanup: Middlesex verify_batch CLEAN, gate PASS, needles=107 (South Brunswick 14 / Monroe 55 /
Cranbury 24 / Edison 14).
