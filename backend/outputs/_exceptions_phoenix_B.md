# Session B — Phoenix AZ cluster (Phase 6), 2026-07-15

## TARGET 1 — Scottsdale AZ (jid 8e31ce3a-67cd-4e62-b975-a4e799b59876) — DONE: 196 needles
- Was zoning-bound 86% (127,222/147,886), ring=0. **Ring-precompute done** (per-city worker path;
  job 3acdb18e, 84 tracts, 146s) → 7,885 wealth&1.5ac town-wide.
- Ordinance via Municode content-API (client 4271 / product 10075 / job 425135; curl+UA): Zoning
  Ordinance Appendix B, Art. XI **Table 11.201.A** Land Use Table. District column order verified:
  S-R C-S C-1 C-2 C-3 C-4 S-S C-O PNC PCC PCoC **I-1 I-G** P-1 P-2.
- **Warehouse-by-right convention:** Table 11.201.A lists "Wholesale, warehouse and distribution" = P
  (by-right) in I-1 & I-G (and C-3/C-4), "Light manufacturing" = P in I-1/I-G. No separate self-storage/
  mini-storage/mini-warehouse use row → self-storage UNNAMED → warehouse-by-right ⇒ ss/mw **CONDITIONAL**,
  li **PERMITTED**, lgc prohibited. Grounded the 7 I-1/I-G zoning_code variants (base district governs;
  PCD/ESL/HD/(C) overlays don't change self-storage permission), overriding pre-existing human_reviewed=
  False template rows. `scripts/_apply_scottsdale_az.py`, municipality='SCOTTSDALE' (AZ UPPERCASE).
- **NEEDLES = 196 (SELECT-confirmed, human-reviewed):** I-1 98 / I-1 PCD 80 / I-G 10 / I-1 (C) 4 /
  I-1 PCD ESL (HD) 2 / I-1 ESL (HD) 1 / I-G (C) 1. verify_batch CLEAN, gate PASS.
- **C-3/C-4 FLAG (not grounded):** C-3/C-4 also permit "Wholesale, warehouse and distribution" by-right
  (106 wealth&1.5ac) → the convention would extend self-storage=conditional there. Held (commercial,
  outside the "I-1/I-G industrial" scope) — coordinator greenlight to arm. Also "Internalized community
  storage" (P in C-1..C-4/PNC/PCC/I-1) is ambiguous (likely accessory community storage, not commercial
  self-storage) — NOT relied on; worth a definition check if the coordinator wants C-1/C-2 revisited.

## TARGET 2 — Paradise Valley AZ (jid a79a7175-8e11-44a7-874d-5d9d79e53d99) — confirmed NO-OP, bind deferred
- 9,847 parcels, zoning UNBOUND (zone_class all NULL); Maricopa assessor land-use codes only (5,190 =
  3.1 single-family; rest residential variants). ring=0.
- **Confirmed pure-residential no-op (0 needles) — as expected.** Paradise Valley has NO industrial or
  commercial zoning districts by town design (all large-lot single-family; resorts/schools/churches
  operate under Special Use Permits within residential zones). No self-storage-permitting district can
  exist → 0 needles regardless of binding. Did NOT force a verdict (per instruction).
- **Bind deferred — no clean source found.** #38: the "Paradise GIS" webmap
  (aba17facad154e269ed7b6d0705b1bd3) is **Paradise, UTAH** (gis.cachecounty.gov) — wrong jurisdiction,
  discarded. The only PV-AZ zoning FeatureServer surfaced ("Paradise Valley PublicViewing - Zoning",
  services8.arcgis.com/N334FOEnkH2pYwmq) is an **ASU student project** (owner NR218_2208_3_ntrane) and
  returns 0 layers (empty/private). The town portal (paradisevalleyaz.gov) uses ArcGIS Experience apps
  with no anonymously-enumerable zoning service. → HANDOFF: official PV zoning-districts layer (or paste)
  to bind; but the no-op result stands regardless (no non-residential zoning to arm).
