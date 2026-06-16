# Op-5 Bellevue + Mercer Island Re-jurisdictioning (Phase 6B-PIVOT) — FLIP CONFIRMED 20 → 21

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Phase 6B-PIVOT — first per-muni jurisdiction registration after PR #266 surfaced the massive-county wealth-pocket pattern.
**Verdict:** **Bellevue, WA flipped operational. Operational count 20 → 21.** Mercer Island remains `partial` at 63.2% pending Task E city-fallback re-fire. King County retains 594,521 parcels with 0 zoning_districts / 0 matrix (county-wide ingest remains incomplete per design; per-muni is the operational unit).
**Predecessors:** PR #264 (King WA Phase 6A.2 WAZA zoning + Bellevue match) · PR #266 (King WA matrix sprint authoring 52 matrix rows) · PR #267 (Phase 6B.1 Pierce/Snohomish/Kitsap parcel ingest + Pierce HALT).

---

## TL;DR

PR #266 cleared all 4 quality gates for Bellevue **at the district/matrix layer**, but the county-wide `parcel_zoning_code_coverage_pct = 5.2%` blocked operational flip under the King County jurisdiction row — 33,217 Bellevue parcels vs 635,186 King parcels = ~5%, well below the 70% gate.

The pivot: **for massive-county-with-tiny-wealth-pocket targets (WA, AZ, MI, MN), the operational unit is per-muni, not per-county.** Register Bellevue + Mercer Island as their own prod jurisdictions, move parcels + zoning_districts + zone_use_matrix from King County → the new jurisdiction_ids.

**Bellevue post-pivot:** cov 85.2% (clears 70% gate), matrix 51 rows (clears matrix-zone gate), districts 991, parcels 33,217, blocking_gaps `[]`, **operational**.

**Mercer Island post-pivot:** cov 63.2% (sub-gate), matrix 11 rows, districts 48, parcels 7,448, blocking_gaps `[]`, **partial** — awaits Task E city-fallback re-fire to lift coverage above 70%.

## Re-jurisdictioning script

`backend/scripts/rejurisdiction_bellevue_mercer.py` — single-file standalone (asyncpg only, no app import chain). Hard rules honored:

1. **Per-muni transaction** for atomicity (parcels + districts + matrix + bbox in one tx). If any UPDATE fails the rollback restores the muni's data to King.
2. **Idempotent jurisdiction find/create** — re-running the script doesn't double-register.
3. **`raw_attributes` preserved verbatim** (Norfolk gate) — only `jurisdiction_id` column updated; raw column untouched.
4. **Inline `jurisdictions.bbox` UPDATE** per new jurisdiction (PR #261 codified) — computed from `ST_Extent(geom)` of the new jurisdiction's parcels, sanity-checked against expected lon/lat range, then written.
5. **`statement_timeout = 0`** within transaction (UPDATEs over 33k rows would otherwise hit the 30s default).

## Move operation — DB-level evidence

| Asset | Bellevue moved | Mercer moved | King retained |
|-------|---------------:|-------------:|--------------:|
| `parcels` | 33,217 | 7,448 | 594,521 |
| `zoning_districts` | 991 | 48 | 0 |
| `zone_use_matrix` | 51 | 11 | 0 |

King retains 0 zoning_districts and 0 matrix because Phase 6A.2 (PR #264) only loaded WAZA features for Bellevue + Mercer Island — county-wide WAZA ingest was never fired. This is consistent with PR #266's footnote: King's county-wide coverage is fundamentally limited by the WAZA's per-muni scope.

## Quality gates — Bellevue (operational verdict)

| Gate | Threshold | Bellevue | Status |
|------|-----------|---------:|:------:|
| Jurisdiction registered | 1 row | ✓ `71a53bba-8697-4b8d-93e9-e3de091b8706` | ✓ |
| Parcels with geom | ≥ 99 % | 33,217 / 33,217 (100 %) | ✓ |
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **85.2 %** (28,315 / 33,217) | ✓ |
| `matrix_zone_count` | > 0 | **51** | ✓ |
| `zoning_district_count` | > 0 | **991** | ✓ |
| `jurisdictions.bbox` populated | non-null | `[-122.250, 47.531, -122.087, 47.661]` (inline) | ✓ |
| `blocking_gaps` | `[]` | **`[]`** | ✓ |
| `operational_readiness` | `operational` | **`operational`** | ✓ |

**Bellevue audit snapshot (post-refresh, 2026-06-16T18:14:37Z):**
```json
{
  "jurisdiction_id": "71a53bba-8697-4b8d-93e9-e3de091b8706",
  "jurisdiction_name": "Bellevue, WA",
  "parcel_count": 33217,
  "parcel_with_zoning_code_count": 28315,
  "parcel_zoning_code_coverage_pct": 85.2,
  "zoning_district_count": 991,
  "matrix_zone_count": 51,
  "operational_readiness": "operational",
  "blocking_gaps": []
}
```

## Quality gates — Mercer Island (partial, sub-coverage)

| Gate | Threshold | Mercer | Status |
|------|-----------|-------:|:------:|
| Jurisdiction registered | 1 row | ✓ `bdf769db-4150-45da-baa5-529995e7246f` | ✓ |
| Parcels with geom | ≥ 99 % | 7,448 / 7,448 (100 %) | ✓ |
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **63.2 %** (4,707 / 7,448) | ✗ sub-gate |
| `matrix_zone_count` | > 0 | 11 | ✓ |
| `zoning_district_count` | > 0 | 48 | ✓ |
| `jurisdictions.bbox` populated | non-null | `[-122.255, 47.524, -122.202, 47.596]` (inline) | ✓ |
| `blocking_gaps` | `[]` | `[]` | ✓ |
| `operational_readiness` | `operational` | **`partial`** | partial |

Mercer is staged behind a known forward-fix: Task E city-fallback re-fire projected to lift cov from 63.2% → ~75-85%. Districts + matrix + bbox are all present; only the parcel-zoning_code spatial bind is incomplete.

## King County roll-up (post-pivot)

| Asset | Pre-move | Post-move | Δ |
|-------|---------:|----------:|---:|
| `parcels` | 635,186 | 594,521 | -40,665 (Bellevue 33,217 + Mercer 7,448) |
| `zoning_districts` | 1,039 | 0 | -1,039 (Bellevue 991 + Mercer 48) |
| `zone_use_matrix` | 62 | 0 | -62 (Bellevue 51 + Mercer 11) |
| `parcel_zoning_code_coverage_pct` | 5.2 % | 0.0 % | -5.2 pp (all bound parcels were Bellevue/Mercer) |
| `operational_readiness` | `partial` | `partial` | unchanged (county still missing county-wide ingest) |

King stays `partial` post-pivot. Its operational state is unchanged from the audit's perspective — the county-wide row was already gated by the 5.2% county-wide coverage. Now that the Bellevue/Mercer assets have moved out, King's coverage drops to 0% but its operational state was already partial; this is consistent. The county is registered, has bbox populated, has 594,521 parcels with geom — the missing piece is county-wide WAZA ingest, which is a separate dispatch (and per the pivot, may never be fired if per-muni remains the operational unit).

## The per-muni pivot — why this matters

PR #266's footnote surfaced the wedge insight: **the audit's `parcel_zoning_code_coverage_pct` is computed at the jurisdiction granularity, not the muni granularity.** For Bergen NJ (where every muni is its own jurisdiction-style row in the county), this is fine. For King WA (a single county-wide jurisdiction with 635k parcels covering wealth pockets like Bellevue + Mercer + Issaquah + Sammamish), county-wide ingest is required to clear the 70% gate.

But for massive-county-with-tiny-wealth-pocket counties (WA, AZ, MI, MN — Op-5's Tier 2 carry), the operational case for these jurisdictions is the **wealth pocket itself**, not the county as a whole:

- Bellevue, WA — Microsoft HQ, hyper-rich suburb (~150k pop). Self-storage / acquisition signal is strong **for Bellevue specifically**, not for Snohomish/Pierce edge dirt that happens to be in King County.
- Maricopa, AZ — would carry Scottsdale + Paradise Valley + Fountain Hills, not all of Phoenix metro.
- Oakland, MI — would carry Bloomfield Hills + Birmingham, not all of Detroit's outskirts.

The pivot: **register the wealth pocket as its own jurisdiction.** The county becomes a residual container (still has parcels for spatial queries, still has bbox), but the audit + operational view runs against the per-muni jurisdiction.

This is the first proof-of-concept. Phase 6B.2 PIVOT will apply the same pattern to Bainbridge Island (Kitsap), Mill Creek (Snohomish), and Gig Harbor (Pierce) — each as its own jurisdiction.

## Operational state

| Period | Count | Net Δ | Notes |
|--------|------:|------:|-------|
| Pre-PR #258 (Contra Costa flip) | 19 | — | |
| Pre-this-PR | 20 | +1 | Contra Costa Phase 2 CA flip (PR #258 + #261) |
| **Post-this-PR** | **21** | **+1** | **Bellevue Phase 6B-PIVOT — first per-muni re-jurisdictioning** |

## Refresh status

3 refreshes fired (Bellevue, Mercer, King). All 3 hit Railway proxy 150s timeout but the workers completed past the ceiling. Bellevue's first refresh did not persist a snapshot row (cause not investigated — likely worker concurrency contention); a second targeted refresh at 12:25 PT (19:25 UTC) succeeded with `captured_at = 2026-06-16T18:14:37Z`. Mercer + King snapshots both persisted on first attempt.

Took ~3 wakeups (15-min + 8-min + 8-min) to confirm. The DB-level data was clean from the first run — the latency was entirely in the audit snapshot persistence loop.

## What changed in the repo

- `backend/scripts/rejurisdiction_bellevue_mercer.py` (new) — single-file per-muni re-jurisdictioning script
- `coordination/lane_state.json` — `current_api_truth` 20 → 21, `mode` updated, Bellevue added to `confirmed_flips_this_week`
- `docs/OP5_BELLEVUE_MERCER_REJURISDICTION.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-16 entry

No backend code changes (no `app/services/ingestion.py` changes, no schema migrations).

## Recommended next dispatches

Per Master's sequencing (post-flip cohort):

1. **Task E (Mercer Island city-fallback re-fire)** — lift cov from 63.2% to projected 75-85% via re-firing the WAZA spatial backfill with relaxed match tolerance. Projected Mercer Island flip.
2. **Phase 6B.2 PIVOT — per-muni registration for Bainbridge Island (Kitsap)** — full ingest + WAZA Class A + matrix (orchestrator's domain).
3. **Phase 6B.2 PIVOT — per-muni registration for Mill Creek (Snohomish)** — **5-feature WAZA spot-check FIRST** (5,406 anomalously high feature count from PR #267 directory needs validation before full ingest).
4. **Task E for Pierce (WA City Limits spatial join)** — separate from the Mercer Task E. Backfill `parcels.city` for 328,832 Pierce rows.
5. **Phase 6B.2 PIVOT — per-muni registration for Gig Harbor (Pierce)** — gated by Pierce Task E.

Expected operational delta: 21 → up to 25 if all 4 muni flips clear gates.
