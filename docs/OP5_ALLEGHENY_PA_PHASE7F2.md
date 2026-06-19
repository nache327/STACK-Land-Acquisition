# Op-5 Allegheny PA Phase 7F.2 — wealth-band per-muni registration

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Wave 5 final-wedge cohort after Phase 7F.1 (PR #315 MERGED). Script READY but fires only after Phase 7F.1 parcel ingest completes (gating on parcel availability).
**Verdict:** **READY TO FIRE.** Cohort script built, 5 munis identified, LABEL exact-equality filters (parcels.city set by 7F.1 adapter). Fires automatically once 7F.1 fire completes.
**Predecessors:** PR #315 Phase 7F.1 MERGED · PR #294 Hennepin Phase 7A.2 (per-muni atomic transaction pattern).

---

## TL;DR

5-muni cohort registration via PATH 1 transparent re-jurisdictioning (Bellevue/Hennepin/Fairfield/Maricopa precedent). Allegheny LABEL field is preserved verbatim in `parcels.city` by Phase 7F.1's MUNICODE→LABEL join, so cohort filter is exact-equality on city.

## 5 munis to register (LABEL exact-equality)

| Muni name (jurisdiction) | parcels.city filter | MUNICODE |
|--------------------------|---------------------|---------:|
| Fox Chapel, PA | `'Fox Chapel Borough'` | 868 |
| O'Hara, PA | `'O Hara Township'` (apostrophe-stripped) | 931 |
| Aspinwall, PA | `'Aspinwall Borough'` | 801 |
| Sewickley, PA | `'Sewickley Borough'` | 851 |
| Sewickley Heights, PA | `'Sewickley Heights Borough'` | 869 |

Note: jurisdictions.name uses STACK convention "MuniName, ST" (e.g. "O'Hara, PA" with apostrophe restored). parcels.city uses Allegheny LABEL convention (apostrophe-stripped "O Hara Township"). These differ because:
- jurisdictions.name is STACK's display name
- parcels.city is the LABEL substrate published by Allegheny GIS

## What's in this PR

- `backend/scripts/perm_muni_allegheny_cohort.py` (new) — 5-muni cohort registration script
- `docs/OP5_ALLEGHENY_PA_PHASE7F2.md` (this file)

## Fire gate

Cohort fires **after** Phase 7F.1 parcel ingest completes (PID 89084, ~580k parcels). Allegheny GIS rate-limiting like Maricopa did (Batch 3+5 returned partial results 17k+10k vs expected 50k; Batches 1+2+4 fetch ~200-260s each). ETA: 1-3h depending on rate-limit pattern.

After 7F.1 done:
```
/tmp/lane_a_venv/bin/python3 backend/scripts/perm_muni_allegheny_cohort.py \
    --i-know-this-writes-to-prod
```

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches jurisdiction_id + updated_at only
- LABEL exact-equality (PA case discipline: 'Fox Chapel Borough' etc.)
- Inline jurisdictions.bbox per muni (PR #261 codified)
- Per-muni atomic transaction (insert + UPDATE + bbox)
- Halt-and-report on bbox envelope drift

## Phase 7F.3 next dispatch (informational)

Per Master 2026-06-19: Diagnostic firing in parallel to identify any live ArcGIS FeatureServers for Allegheny munis. Greenwich precedent (LOW Path B → HIGH Path A promotion when Daniel.Clark_greenwichgis layer surfaced) could repeat for 1-3 Allegheny munis.

Wait for Diagnostic verdict (~1-2h ETA) before committing to "defer all 5 to LOW Path B ordinance". Their probe may reduce Phase 7F.3 wall-clock by 2-4h.

Per orchestrator's d7a0c7a pre-stage: 26 rows total covering all 5 munis at LOW Path B. Sewickley Heights flagged for Ordinance No. 294 PDF parsing.

## Sibling waves status

- **Hennepin**: 4/5 ops (Wayzata Option B deferred)
- **Fairfield**: 2/5 ops (Stamford + Greenwich applied/pending; 3 Vessel Tech deferred)
- **Maricopa**: PV + 4-muni registered (#310, #313); Scottsdale 7B.3 spatial backfill 85.8 % cov DB-level PASS, Pass 2 nearest_50m hung but gates already pass
- **Oakland MI**: parcel ingest 100 % done (490,581 in 17 min); bbox manually set; 5/5 munis present (Birmingham 9,778, Bloomfield Hills 1,833, Bloomfield Twp 18,224, Franklin 1,312, Beverly Hills 4,174); Phase 7E.2 next
- **Allegheny PA**: parcel ingest in flight (this PR's prerequisite)

## Wedge cohort trajectory

After Allegheny 7F.2 + 7F.3 closes:
- Theoretical ceiling **46 ops**
- Stretch: 49 with Wayzata GeoPDF + Vessel Tech B2B unlocks

Master's PR review backlog clearing: PRs #280 (audit CTE), #293/#303/#306/#307/#310/#311/#313/#314/#315 in review queue.
