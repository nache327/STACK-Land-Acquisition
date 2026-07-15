# Session B — Lake Oswego OR (Phase 6), 2026-07-15

## Lake Oswego OR (jid 2c1736ee-48ac-4a6e-aefd-77be215a00c2) — DONE: 4 needles (CI)
- Discovery-rank-first. Bound ~100%, ring=0 → **ring-precompute done** (15 tracts) → 399 wealth&1.5ac
  town-wide (ring maxHV $804k, clears $475k). municipality='Lake Oswego'. #38: confirmed in Oregon
  (Clackamas Co; ring HV + eCode360 LOC).
- Ordinance: Lake Oswego Community Development Code (LOC) Table 50.03.002-2 (eCode360 43075916, curl+UA —
  NOT Municode). Non-residential column order verified by <td> index and validated against
  "Light manufacturing C C P C P P": NC GC HC OC EC CR&D MC WLG FMU I IP **CI** PF PNA OC RMU R-2.5.
- **SELF-STORAGE = NAMED USE, CONFINED TO CI:** §50.03.003.7 row "Storage — Self-storage facility" = P
  (permitted by-right) in the **CI** column ONLY. NOT in IP (Industrial Park), I (Industrial), CR&D, or
  any commercial district. (Corroborating: General storage / Wholesale distribution = P in CI/PF only;
  Heavy manufacturing = P in CI. LO's IP is a clean-tech/biotech campus, not warehousing.) → the warehouse
  convention does NOT extend self-storage to IP/I; self_storage prohibited everywhere except CI.
- **NEEDLES = 4 (SELECT-confirmed), all CI** (self_storage/mini_warehouse PERMITTED, li permitted).
  IP (16 w15) / I (5) / CR&D (16) / PF (21 Public Facility) clear the ring but permit no self-storage →
  correct no-op. verify_batch CLEAN, gate PASS, matrix_coverage 100%.
- Applied via scripts/_apply_lake_oswego_or_ci.py (human verdict layer; overrides the pre-existing
  machine template rows / adarench wave6 substrate). NOT a no-op after all — small but real CI needle.
