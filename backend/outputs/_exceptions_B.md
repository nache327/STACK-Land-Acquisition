# Session B exceptions

Prior Session-B work (separate branches, not on this one): Hudson NJ JC-bind (no-op,
`project_hudson_nj_outcome`); Union NJ Atlas dry-run (superseded — Union is D's).

---

# Essex County NJ (jid 67541a18) — Session-B grounding (2026-07-14)
Shared with A (A = Fairfield + West Caldwell; B = Livingston + Millburn + Roseland).
Applied via `scripts/_apply_essex_nj_batchB.py` (muni-scoped, human_reviewed, verbatim citations).
verify_batch = CLEAN, gate PASS; combined A+B = 144 needles. B contributes **78**:
Livingston 53, Roseland 16, Millburn 9. **Re-score SKIPPED** (shared → coordinator reconciles).

## FLAG for coordinator/Nache — Livingston I/CI vs §170-88K (affects 38 of the 53 Livingston needles)
Livingston has an internal tension I resolved by the coexistence reading but want reviewed:
- **I (§170-117A(6))** lists "Moving and storage operations and self-storage facilities" as a by-right
  primary use; **CI (§170-118A(3)(c))** lists "Warehouses, including self-storage facilities
  (mini-warehouses)" by-right. → grounded self_storage **PERMITTED** (conf 0.90). These 2 zones = 38
  wealth-ring needles (CI 27 + I 11).
- BUT **§170-88K** (Conditional Uses) says self-storage "shall be permitted **only** in the R-L and R-L2
  Zones as conditional uses," and §170-88 has a clause "Requirements for conditional uses shall take
  precedence over any regulations for the zone."
- **My reading (grounded):** §170-88 is a permissive conditional-use framework ("the Planning Board may
  approve conditional uses as herein permitted"); a use listed **by-right** in I/CI is not a "conditional
  use" there, so §170-88K's "only" scopes the *conditional* pathway (R-L/R-L2) and does not repeal the
  express by-right I/CI listings — which survived a 2014 amendment (§170-117 amended 12-1-2014, self-storage
  retained). Precedence clause governs conditional-use *standards*, not other zones' by-right grants.
- **Weaker exclusivity reading:** treat §170-88K "only" as controlling → demote I/CI self_storage to
  prohibited, leaving just R-L/R-L2 conditional (15 needles). If coordinator/Nache prefer this, flip
  I & CI to prohibited in the apply script.

## #38 catches (coordinator's named districts were partly mislabeled)
- **Livingston R-L / R-L2** = §170-115/116 "Research Laboratory" — office/research/institutional (closed
  primary-use list), NOT residential despite the R- prefix. Correctly grounded as self-storage CONDITIONAL
  (via §170-88K), li prohibited — NOT as residential and NOT as light-industrial. (Coordinator's caution
  confirmed.)
- **Millburn "C"** = §DRZ-606.1 **Conservation-Recreation** (the ~650-ac South Mountain Reservation), NOT a
  commercial district → prohibited. The only Millburn needle is **CMO** (§DRZ-606.9): warehouses by-right +
  self-storage unnamed + no global clause → warehouse convention → ss/mw conditional, li permitted.
- **Roseland "C"/"CR"** = §30-30 **Conservation / Conservation-Recreation**, NOT commercial → prohibited.
  The real Roseland needle is **RM** = §30-404.5 Research/Manufacturing (self-storage a named conditional
  use §30-404.5c.1 → ss/mw conditional, li permitted). OB-2/OB-3/B-1/B-2 = office/business → prohibited.

## Acres sanity note
Several Livingston/Millburn residential zones carry absurd-acre lots (e.g. R-2 maxacre 79,900; R-1 9,467)
— clearly bad assessor acreage, but all in prohibited residential zones so 0 needle impact. The needle
zones (I/CI/CMO/RM + R-L/R-L2) have sane max acreages (CI 14.9, I 165.8 river/utility parcel, RM 34.5).

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
