# Op-5 Puget Sound Phase 6B.1 — Kitsap + Snohomish parcel ingest (DONE); Pierce HALT (separate PR)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Tier 2 multi-county carry — Phase 6B.1 parcel ingest + jurisdiction registration for the 3 remaining Puget Sound counties surfaced in PR #264's bonus probe.
**Verdict:** **Kitsap + Snohomish DONE.** Combined 430,936 parcels live with full city/raw_attributes preservation + inline `jurisdictions.bbox` UPDATE. **Pierce HALTED** at the city-locator gap surfaced during verification — `SITUS_CITY_NM` is uniformly null in the source layer for Pierce, blocking Phase 6B.2 per-muni zoning backfill. Pierce parcels stay loaded (with raw_attributes preserved); spatial-join city derivation queued as follow-up (separate PR — Pierce-specific HALT report).
**Predecessors:** PR #259 (Phase 6A.1 King parcels, adapter pattern) · PR #264 (multi-county bbox-primitive probe) · PR #261 (inline bbox codified pattern).

---

## Headline

| County | Parcels | Wealth-band city | Bbox | Phase 6B.1 verdict |
|--------|--------:|------------------|------|--------------------|
| **Kitsap** | **116,900** | Bainbridge Island: **9,796** | inline ✓ | **DONE** — all gates clear |
| **Snohomish** | **314,011** | Mukilteo 7,661 + Mill Creek 6,237 = **13,898** | inline ✓ | **DONE** — all gates clear |
| **Pierce** | 328,832 | Gig Harbor: **0** (city field null in source) | inline ✓ | **HALT** — see separate PR |
| **TOTAL** | **759,743** | 23,694 wealth-band | 3/3 ✓ | 2 of 3 done |

**Wall-clock**: Kitsap 3.0 min · Pierce 6.8 min · Snohomish 7.4 min = ~17 min total sequential.

## Quality gates — Kitsap + Snohomish

| Gate | Threshold | Kitsap | Snohomish | Status |
|------|-----------|-------:|----------:|:------:|
| Jurisdiction registered | 1 row | ✓ `88a6b339-…` | ✓ `2302220a-…` | ✓ both |
| Parcels with geom | ≥ 99 % | 116,900 / 116,900 (100 %) | 314,011 / 314,011 (100 %) | ✓ both |
| `raw_attributes` preserved (Norfolk gate) | 0 empty `{}` | 0 / 116,900 | 0 / 314,011 | ✓ both |
| `with_city` populated (PR #233 lesson) | meaningful coverage | **99,754 / 116,900 = 85.3 %** | **312,350 / 314,011 = 99.5 %** | ✓ both |
| **`jurisdictions.bbox` populated inline (PR #261 codified)** | non-null | `[-123.023, 47.403, -122.470, 47.941]` | `[-122.438, 47.775, -120.952, 48.299]` | ✓ both inline |
| `is_residential = TRUE` | n/a (informational) | 92,917 (79.5 %) | 267,721 (85.3 %) | — |

## Wealth-band carry probe (Phase 6B.2 readiness)

Per Master's brief — each county's primary wealth-band muni populated cleanly via title-case discipline (PR #233):

| County | Target muni | Parcels in `city` (title-cased) | Phase 6B.2 readiness |
|--------|-------------|--------------------------------:|----------------------|
| Kitsap | Bainbridge Island | **9,796** | ✓ ready for WAZA backfill |
| Snohomish | Mukilteo | **7,661** | ✓ ready |
| Snohomish | Mill Creek | **6,237** | ✓ ready (anomalous 5,406 WAZA features — spot-check during Phase 6B.2) |
| Pierce | Gig Harbor | **0** | ✗ HALT — Pierce city field null |

## Pierce HALT — summary (full report in separate PR)

Pierce County's `SITUS_CITY_NM` column in the Washington State Current Parcels FeatureServer is **uniformly null** — confirmed via:

1. Distinct-values query: `1 unique value, [None]`
2. 10-row random sample from prod (post-ingest): all 10 rows had `raw->>'SITUS_CITY_NM' = NULL`
3. Alternate locator fields probed: `SUB_ADDRESS` (occasional condo/dev name, no city), `SITUS_ZIP_NR` (also null for sampled rows), `SITUS_ADDRESS` (street-only, no city embedded), `DATA_LINK` (Pierce assessor PDF link, would require scrape).

The 17-field layer schema has **no remaining city-locator alternative**. King + Kitsap + Snohomish all populate `SITUS_CITY_NM`; **only Pierce is gapped** — this is a known upstream feed-pipeline issue at WaTech, not an adapter bug.

**Pierce parcels stay loaded in prod** (328,832 rows with valid geom + raw_attributes + bbox populated). Only Phase 6B.2 per-muni zoning backfill is blocked. Recommended follow-up: spatial join to WA city boundary FeatureServer → `UPDATE parcels SET city = X WHERE ST_Within(centroid, boundary)`.

Full Pierce HALT details + forward-fix design in separate PR (PR #267 style halt report per PR #216 / PR #221 / PR #242 / PR #253 precedent).

## Three codified updates applied

1. **PR #253 lesson** — `preflight` is read-only pipeline shape check only. No in-DB ROLLBACK gate runs.
2. **PR #261 lesson — inline `jurisdictions.bbox`** — UPDATE at end of each county fire, mirroring the existing `refresh_jurisdiction_bbox` SQL. Sanity-checks lon/lat ranges per county (Pierce `[-123.5, -120.5] × [46.0, 48.0]`, Snohomish `[-123, -120] × [47, 49]`, Kitsap `[-124, -122] × [47, 48.5]`) before writing. All 3 passed sanity. The `missing_bbox` residual trap (which delayed Contra Costa until PR #261) is pre-empted for all 3 counties.
3. **PR #233 title-case discipline** — SITUS_CITY_NM (ALL-CAPS) → `parcels.city` (title-case) for Phase 6B.2 exact-equality joins against WAZA's `Jurisdiction` field. Verified for Kitsap (Bainbridge Island ✓) and Snohomish (Mukilteo ✓, Mill Creek ✓).

## Adapter design

`backend/scripts/ingest_wa_county_parcels.py` — parametrized clone of PR #259's `ingest_king_wa_parcels.py`. Three subcommands (`register` / `preflight` / `fire`) each take a `--county Pierce|Snohomish|Kitsap` argument. Standalone (Python 3.9 / PEP-604 compat). Preserves prod `_stage_parcels` shape + `INSERT … ON CONFLICT … DO UPDATE` upsert SQL verbatim. Inline `jurisdictions.bbox` UPDATE codified.

Three per-county directory pre-stages (for Phase 6B.2):
- `backend/data/pierce_wa_zoning_directory.json` — Gig Harbor (20 WAZA features) — gated by Pierce HALT
- `backend/data/snohomish_wa_zoning_directory.json` — Mukilteo (70), Mill Creek (5,406)
- `backend/data/kitsap_wa_zoning_directory.json` — Bainbridge Island (76)

## Multi-county carry — net result

Combined Tier 2 progress under the Washington Current Parcels + WAZA adapter shape:

| County | Parcels (this PR) | Status |
|--------|------------------:|--------|
| King (PR #259 + #264) | 635,186 | partial (Bellevue + Mercer Island zoning bound; matrix pending) |
| Kitsap (this PR) | **116,900** | **not_loaded → partial** (parcels + bbox; Phase 6B.2 next) |
| Snohomish (this PR) | **314,011** | **not_loaded → partial** (parcels + bbox; Phase 6B.2 next) |
| Pierce (this PR, halted) | 328,832 | parcels loaded, city null, Phase 6B.2 blocked |
| **Total Puget Sound parcels live** | **1,394,929** | (97.4 % of the 1,432,978 statewide-source carry) |

## Refresh status

3 refreshes fired (one per county). All 3 client-timed-out at 200 s (Railway proxy past 150 s ceiling). Did NOT retry per "ONE refresh per task" rule. DB-level numbers above are authoritative.

## What changed in the repo

- `backend/scripts/ingest_wa_county_parcels.py` (new) — parametrized WA county parcel adapter
- `backend/data/pierce_wa_zoning_directory.json` (new) — pre-stage (gated by Pierce HALT)
- `backend/data/snohomish_wa_zoning_directory.json` (new) — pre-stage
- `backend/data/kitsap_wa_zoning_directory.json` (new) — pre-stage
- `docs/OP5_PUGET_SOUND_PHASE6B1.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-16 entry

No backend code changes.

## Operational state

Operational count unchanged: **20**. Kitsap + Snohomish move `not_loaded` → `partial` (parcels live; zoning + matrix pending). Pierce stays `not_loaded` from the operational view (parcels loaded but blocked from Phase 6B.2 by city-null gap).

## Recommended next dispatches

- **TASK E (Pierce city derivation)** — separate Pierce HALT report PR documents this. Spatial join to WA city boundary layer → backfill `parcels.city` for the 328,832 Pierce rows. Then Phase 6B.2 Pierce unblocks.
- **Phase 6B.2 Kitsap + Snohomish** — ready for dispatch after Master review. Same Class A WAZA backfill shape as PR #264 King. ~3-5h.
- **Task D (Mercer Island city-fallback)** — still queued, low priority.
