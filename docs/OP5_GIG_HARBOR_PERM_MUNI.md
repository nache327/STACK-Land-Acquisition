# Op-5 Gig Harbor per-muni registration (Phase 6B-PIVOT, fifth per-muni — completes the WA wave)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Phase 6B-PIVOT cohort — final per-muni in the WA wave. Builds on Pierce Task E (PR #285) which unblocked Gig Harbor parcels via WA City Limits spatial join.
**Verdict:** **DB-LEVEL DONE. Gig Harbor is partial-with-zoning awaiting orchestrator's matrix sprint** (19 of 20 codes need authoring). Once matrix applies + audit re-runs, **Gig Harbor flips → count reaches 25 (WA wave complete)**.
**Predecessors:** PR #267 (Pierce parcels) · PR #285 (Pierce Task E city derivation) · PR #271/#274/#278/#281/#283 (per-muni pattern proofs).

---

## TL;DR

Pierce Task E (PR #285) populated `parcels.city = 'Gig Harbor'` for 5,312 Pierce rows via WA City Limits spatial join. This script picks up the pattern: register Gig Harbor as own jurisdiction, move parcels, INSERT 20 WAZA districts, spatial backfill, inline bbox.

**Gig Harbor new jid:** `a2987841-4fe9-4dd3-833e-548bb4fe0cbc`

## 5/5 Quality gates PASS

| Gate | Threshold | Gig Harbor | Status |
|------|-----------|-----------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **82.4 %** (4,375 / 5,312) | **PASS** (+12.4 pp margin) |
| `nearest_*` share | < 30 % | **11.4 %** (608 / 5,312) | **PASS** (-18.6 pp margin) |
| `raw_attributes` preserved (Norfolk) | 0 empty | 0 / 20 | **PASS** |
| `zoning_district_count` | > 0 | 20 (matches WAZA feature count) | **PASS** |
| `jurisdictions.bbox` populated | non-null | `[-122.626, 47.291, -122.568, 47.375]` (inline) | **PASS** |

## Audit snapshot

```
RESULT: {'snapshots_written': 1, 'snapshots_failed': 0,
         'summary': {'jurisdiction_count': 1, 'operational_count': 0,
                     'partial_count': 1, 'with_parcels_count': 1,
                     'with_matrix_count': 0, 'with_zoning_polygons_count': 1,
                     'with_good_matrix_match_count': 0}}
```

Partial as expected (matrix sprint pending). The 3 matrix-related blockers close on orchestrator's apply.

## 19 distinct zone codes bound (orchestrator follow-up signal)

| Code | Parcels | Code | Parcels |
|------|--------:|------|--------:|
| R-1 | 1,248 | RB-1 | 93 |
| PRD | 822 | No Zoning | 75 |
| R-2 | 600 | ED | 65 |
| RB-2 | 350 | WR | 58 |
| RMD | 300 | PI | 55 |
| B-2 | 184 | WM | 54 |
| R-3 | 121 | PCD-BP | 21 |
| DB | 110 | PCD-C | 19 |
| C-1 | 101 | B-1 | 1 |
| WC | 98 |  |  |
| **Total** | | | **4,375** |

R-1 + PRD + R-2 alone cover **62.4 %** of bound parcels — orchestrator's matrix can clear majority of Gig Harbor with 3 grounded rows. Note `No Zoning` (75 parcels) is WAZA's encoding for unzoned parcels — orchestrator handling per their convention.

(One source code `PCD-NB` had 0 matched parcels — polygon exists but no parcel centroid falls within it. Will appear in zoning_districts but not in parcel distribution.)

## Pierce Task E foundation

This dispatch follows directly from PR #285's WA City Limits spatial join. Pre-Task E, all 328,832 Pierce parcels had `city = NULL` (upstream SITUS_CITY_NM uniformly null — the original Pierce HALT). Post-Task E:

| Pierce metric | Pre-Task E | Post-Task E |
|---------------|-----------:|------------:|
| Parcels with `city` | 0 | 162,219 |
| Gig Harbor parcels | 0 (gated) | **5,312** (unblocked) |
| Tacoma parcels | 0 | 72,656 |
| Other Pierce cities | 0 | ~85,000 across 23+ munis |

## What changed in the repo

- `backend/scripts/perm_muni_gig_harbor.py` (new) — Gig Harbor per-muni adapter
- `docs/OP5_GIG_HARBOR_PERM_MUNI.md` (this file)

## WA wave complete (post-flip)

Once orchestrator's matrix sprint applies for the queued per-munis:

| Per-muni | PR | Status | Flip count |
|----------|----|----|----|
| Bellevue | #271 (merged) | **OPERATIONAL** | 20 → 21 ✓ |
| Mercer Island | #274/#278 (merged) | **OPERATIONAL** | 21 → 22 ✓ |
| Bainbridge Island | #281 | partial → operational pending matrix | 22 → 23 |
| Mill Creek | #283 | partial → operational pending matrix | 23 → 24 |
| Gig Harbor | (this PR) | partial → operational pending matrix | 24 → 25 |

At count 25, the WA wave is complete. Master review for next wave (Maricopa AZ / Hennepin MN / Fairfield CT).
