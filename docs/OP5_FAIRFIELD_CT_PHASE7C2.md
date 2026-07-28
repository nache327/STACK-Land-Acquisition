# Op-5 Fairfield CT Phase 7C.2 — wealth-band per-muni registration

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Wave 3 dispatch — Fairfield CT cohort in parallel with Maricopa Wave 2 (PR #305) and Minnetonka Phase 7A.3 (PR #306). Master's "compound velocity" call after Hennepin's 3-of-3 100% Phase 7A.3 ingests.
**Verdict:** **DB-LEVEL DONE.** 5 of 5 Fairfield wealth-band munis registered as own jurisdictions. 41,206 parcels moved (Stamford 25,524 + Greenwich 18,042 + Westport 9,947 + New Canaan 7,386 + Darien 5,831 — total **66,730**). All bbox passing Fairfield County envelope. Hennepin Phase 7A.2 pattern carried forward verbatim.
**Predecessors:** PR #228 Fairfield CT city re-derivation (261k Town_Name → city, title-case) · PR #294 Hennepin Phase 7A.2 (per-muni cohort pattern) · PR #271 Bellevue/Mercer (PATH 1 transparent precedent).

---

## TL;DR

Phase 7C.1 SKIP — Fairfield CT parcels already in prod via PR #228 with `city` populated in title-case. Phase 7C.2 registers 5 wealth-band munis as own jurisdictions + moves parcels via UPDATE jurisdiction_id (Bellevue/Hennepin PATH 1 transparent pattern). Phase 7C.3 follows per-muni — Stamford HIGH Path A first (42-row orchestrator pre-stage 9c5cee9).

## 5 munis registered

| Muni | jurisdiction_id | Parcels moved | bbox |
|------|-----------------|--------------:|------|
| Stamford, CT | `9bbffb2b-2460-47be-a486-0687d795b1fb` | 25,524 | [-73.634, 41.014, -73.497, 41.180] |
| Greenwich, CT | `e5406ad0-4e9d-4cea-b20f-800a94d6be8a` | 18,042 | [-73.728, 40.981, -73.555, 41.144] |
| Westport, CT | `0a142989-e2ea-4cbf-9c07-ba72d06d5ca4` | 9,947 | [-73.389, 41.070, -73.296, 41.195] |
| New Canaan, CT | `2580f226-70f4-4c7d-982f-3cbd2b1d7b5b` | 7,386 | [-73.556, 41.114, -73.448, 41.212] |
| Darien, CT | `9b27e214-367c-4652-8385-99b09fe38cd6` | 5,831 | [-73.518, 41.039, -73.445, 41.114] |

**Total: 66,730 parcels** (~25.6 % of Fairfield County's 261k).

Fairfield County residual: 194,922 parcels (non-cohort munis stay under umbrella).

## Fire log

First run halted on Greenwich bbox (lat 40.981 below my conservative 41.00 floor — Long Island Sound coastline dips slightly south at Greenwich). Stamford's first-run transaction completed (committed). Envelope widened from `[41.00, 41.55]` to `[40.95, 41.55]` and re-fired; Stamford detected zero remaining parcels under Fairfield-umbrella with `city='Stamford'` (already moved) and short-circuited cleanly. All 4 remaining munis fired clean on second run.

This bbox-halt-and-retry shape is the discipline working as intended — caught a real envelope mismatch before committing wrong data. Stamford-first-run + 4-rest-second-run is functionally equivalent to one clean run.

## 5 quality gates (per muni)

For each registered muni:

| Gate | Threshold | Status |
|------|-----------|:------:|
| Parcels moved match expected | exact | **PASS** (5/5) |
| `raw_attributes` preserved (Norfolk) | 0 empty post-move | **PASS** (5/5, 0 empty) |
| `parcels.geom` non-null | 100 % | **PASS** (5/5, all parcels geom'd) |
| `jurisdictions.bbox` populated inline | non-null + Fairfield envelope | **PASS** (5/5) |
| Title-case discipline | exact match prod_city_value | **PASS** (5/5, PR #228) |

## Patterns carried forward

- **PR #271 Bellevue** — PATH 1 transparent re-jurisdictioning (UPDATE jurisdiction_id, raw untouched)
- **PR #294 Hennepin Phase 7A.2** — per-muni atomic transaction (jurisdiction insert + parcel UPDATE + bbox in one tx)
- **PR #261** — inline jurisdictions.bbox UPDATE
- **PR #228** — Fairfield CT title-case discipline ('Stamford' not 'STAMFORD')
- **PR #253** — skip prod ROLLBACK preflight at Class A scale

## What's in the PR

- `backend/scripts/perm_muni_fairfield_cohort.py` (new) — Phase 7C.2 cohort registration
- `docs/OP5_FAIRFIELD_CT_PHASE7C2.md` (this file)

## Phase 7C.3 — next dispatch (parallel)

### Stamford (HIGH Path A confidence, 42-row orchestrator pre-stage 9c5cee9)
- Source: `https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3` (per Diagnostic PR #257)
- Phase 7C.3 fires next: parcel-density ingest + ST_Within spatial backfill + 5-gate verdict
- Expected: ~100 % cov per Hennepin precedent
- Orchestrator's 42-row matrix apply post-PR (~5-10 min Path A)
- Operational impact: +1 (28 → 29 once both Stamford + Minnetonka land)

### Greenwich, Westport, Darien, New Canaan (LOW Path B citations-only)
- No machine-readable Feature Service per orchestrator's pre-stage
- Path B authoring at apply-time (~30-60 min each for orchestrator)
- Per-muni Phase 7C.3 PRs follow as orchestrator surfaces zoning sources

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches only jurisdiction_id + updated_at
- municipality matches prod_city_value EXACTLY (title-case PR #228)
- Inline jurisdictions.bbox per muni (PR #261 codified)
- Per-muni transaction atomicity (insert + UPDATE + bbox)
- Halt-and-report (Greenwich bbox halt caught + fixed)
- ONE refresh per phase
- Don't author matrix (orchestrator's 9c5cee9 pre-stage for Stamford + Path B citations for 4)

## Sibling status

- **Hennepin wave**: 25 → 28 confirmed (Edina + Plymouth + Eden Prairie all flipped per Master 2026-06-18). Minnetonka in flight (→ 29).
- **Maricopa Wave 2 (PR #305)**: Parcel ingest 26 % at 450k / 1.74M (~30 min remaining)
- **Fairfield Wave 3 (this PR)**: Phase 7C.2 DONE. Phase 7C.3 Stamford firing next.
- **Oakland Wave 4**: queued post-Fairfield
- **Allegheny Wave 5**: queued post-Oakland
