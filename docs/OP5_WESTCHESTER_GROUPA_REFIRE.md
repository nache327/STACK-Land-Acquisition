# Op-5 Westchester Group A re-fire — DONE (3 sub-coverage gates cleared)

**Owner:** Lane A
**Date:** 2026-06-15
**Sprint type:** PR #238 polish — re-fire 3 sub-coverage Westchester munis at `nearest_within_meters=100` per the diagnostic in PR #241.
**Verdict:** **All three Group A munis cleared both gates exactly as predicted.** Westchester county-wide coverage 85.96 % → 86.37 % (+0.41 pp).

---

## Headline

PR #238 ingested 37 Westchester munis; 5 fell below the 70 % coverage gate. PR #241 (Task 6 diagnostic, read-only) characterized the unmatched parcels and projected that 3 of the 5 could clear both gates at `nearest_within_meters=100`. Master authorized the re-fire.

**Predictions vs actual (per-muni)**:

| muni | predicted bind | actual bind | predicted cov | actual cov | predicted near% | actual near% | gate-clear? |
|------|---------------:|------------:|--------------:|-----------:|----------------:|-------------:|:-----------:|
| Bedford | +85 | **+85** | 70.2 % | **70.16 %** | 3.34 % | **3.34 %** | ✓ marginal |
| Port Chester | +382 | **+382** | 76.1 % | **76.14 %** | 23.50 % | **23.50 %** | ✓ |
| Yorktown | +585 | **+585** | 71.4 % | **71.40 %** | 13.89 % | **13.89 %** | ✓ |

**Exact match on all 9 numbers.** The diagnostic was the production prediction.

## Script

`backend/scripts/refire_westchester_groupa_nearest100.py` —
Pass-2-only re-fire. Districts already loaded in PR #238; this
script only touches parcels whose `zone_binding_method` was still
`NULL` (the unmatched residual from PR #238 fire). No re-INSERT
of districts; no re-stamp of already-bound parcels. Low risk.

Per-muni transaction isolation. Halt-on-failure gate check after
each muni — coverage < 70 % or nearest share ≥ 30 % exits non-zero
and stops the batch (none triggered).

## Group B (left as-is)

Per PR #241 diagnostic: **North Salem (55.8 %)** and **Somers
(55.7 %)** stay at their PR #238 coverage. The diagnostic showed
that no nearest threshold clears both gates for these two —
North Salem breaches the 30 % cap at any threshold that gets cov
above 70 %; Somers can't clear cov at 100 m and breaches the cap
at 200 m. Per-muni Class B from each muni's own GIS portal is the
heavier fallback if Master ever authorizes.

## County roll-up

| Metric | PR #238 (end) | Post Group A re-fire | Δ |
|---|---:|---:|---:|
| parcels bound | 221,698 | **222,750** | +1,052 |
| county coverage | 85.96 % | **86.37 %** | +0.41 pp |
| nearest_* | 10,242 | **11,294** | +1,052 |
| nearest share (of bound) | 4.62 % | **5.07 %** | +0.45 pp |
| sub-coverage munis at <70 % | 5 | **2** (NSM, SOM) | -3 |

## Refresh status

`POST /api/admin/coverage/refresh` fired at 2026-06-15. Client
timed out at 200 s (Railway proxy past 150 s ceiling). Did NOT
retry per the "ONE refresh per task" hard rule. DB-level numbers
above are authoritative.

## What changed in the repo

- `backend/scripts/refire_westchester_groupa_nearest100.py` (new) —
  the Pass-2-only re-fire script, committed for reproducibility.
- `docs/OP5_WESTCHESTER_GROUPA_REFIRE.md` (this file).
- `docs/PHASE2_PROGRESS.md` §15 — entry.

No backend code changes. No directory file changes (the directory
entries are unchanged from PR #238).

## What this doesn't change

- **Operational verdict**: Westchester county-wide stays partial.
  Coverage gate was already cleared at the county level (86.37 % >>
  70 %); the operational flip waits on matrix authoring
  (orchestrator's Westchester sprint per PR #240 covers this).
- **Group B**: North Salem + Somers stay at their pre-existing
  partial coverage. Accept-as-is per PR #241 recommendation.

## Operational state

Operational count unchanged: **19** (Westchester County flipped
2026-06-12 per the matrix sprint in PR #240; PHASE2 §15 entry
captures the 18 → 19 transition). This re-fire polish lands on a
county that's already operational — Westchester County coverage
now firmly above 70 % gate floor at 86.37 % (was 85.96 %),
exactly the kind of polish that holds the gate firmly above the
floor as Master framed it.
