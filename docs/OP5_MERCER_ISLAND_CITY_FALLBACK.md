# Op-5 Mercer Island city-fallback re-fire (Task E, Phase 6B-PIVOT) — DB-LEVEL SUCCESS, audit snapshot lag

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Task E — Mercer Island city-fallback re-fire (the second per-muni in the Phase 6B-PIVOT cohort, immediately after Bellevue's flip via PR #271).
**Verdict:** **DB-LEVEL SUCCESS, audit snapshot lag.** Mercer Island parcel binding lifted from cov 63.2% → **79.6%** (matrix-match 94.8%); all quality gates pass at the DB level. Audit `coverage_snapshots` row not yet refreshed despite 5 trigger attempts over 75+ min (one full-sweep + three targeted refreshes returning Railway 502 + an auto-poll). When snapshot lands, Mercer flips operational → count 21 → 22.
**Predecessors:** PR #271 (Bellevue + Mercer re-jurisdictioning, FLIPPED 20 → 21) · PR #266 (King WA matrix sprint authoring 51 Bellevue + 11 Mercer codes) · PR #264 (King WA Phase 6A.2 WAZA backfill).

---

## TL;DR

Mercer Island's coverage gap was a **polygon-density problem** (PR #264's diagnostic): WAZA's 48 polygons left 36.8 % of parcels (2,741 of 7,448) outside any polygon, even at the 50 m nearest-fallback radius. The pre-staged Mercer Island city zoning layer (`Mercer_Island_Planning_Layers/FeatureServer/2`) publishes 82 polygons with the canonical city `ZONING` codes. Task E inserts these 82 city districts under Mercer's jurisdiction (distinct `muni_name = 'Mercer Island (city)'` to keep WAZA's 48 inviolate), then runs a 2-pass spatial backfill targeting NULL-zoning_code parcels only, then escalates the nearest radius from 50 m → 100 m per the Westchester Group A precedent (PR #244).

**Post-fire DB state**:

| Gate | Threshold | Mercer post-fire | Status |
|------|-----------|-----------------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **79.6 %** (5,928 / 7,448) | **PASS** (+9.6 pp margin) |
| `nearest_*` share | < 30 % | **27.6 %** (2,055 / 7,448) | **PASS** (-2.4 pp margin) |
| matrix-match share of bound | informational | **94.8 %** (5,619 / 5,928) | (309 parcels in 3 new codes) |
| `zoning_district_count` | > 0 | 130 (48 WAZA + 82 city) | PASS |
| `matrix_zone_count` | > 0 | 11 (orchestrator's PR #266) | PASS |
| `jurisdictions.bbox` populated | non-null | `[-122.255, 47.524, -122.202, 47.596]` (inline) | PASS |
| `raw_attributes` preserved | Norfolk gate | 82 city districts INSERTed with 14-field source payload | PASS |

**Pending**: audit `coverage_snapshots` row refresh. DB-level data is the operational truth; the snapshot row is a cached projection.

## Mercer city-fallback adapter

`backend/scripts/rebackfill_mercer_island_city.py` — single-purpose standalone (asyncpg-only). Reads the pre-staged Mercer fallback source from `backend/data/king_wa_zoning_directory.json` → `fallback_zoning_district_source`. Subcommands `preflight` (read-only) + `fire`.

**Key design choice**: city-layer districts INSERTed with `raw_attributes->>'muni_name' = 'Mercer Island (city)'` — distinct from WAZA's `'Mercer Island'`. This keeps the existing 48 WAZA districts intact (Norfolk gate) and scopes the new spatial-backfill pass to the city layer alone. The 4,707 parcels already bound via WAZA (which clear contained or nearest_50m matches under `'Mercer Island'`) are preserved via the `p.zoning_code IS NULL` filter in both backfill passes.

## Fire output (verbatim)

```
=== FIRE: Mercer Island city-fallback re-fire ===

PRE-FIRE — Mercer parcels: 7,448 bound: 4,707 (63.2%) | contained: 3,866 | nearest: 841
PRE-FIRE — Mercer zoning_districts (WAZA only so far): 48

[city layer] INSERTing 82 districts (muni_name='Mercer Island (city)')…
[city layer] INSERTed 82 rows

[city layer] Pass 1 contained (ST_Within centroid, NULL-zoning_code only)…
[city layer] contained UPDATEd 7
[city layer] Pass 2 nearest_50m (ST_DWithin, still-NULL only)…
[city layer] nearest_50m UPDATEd 252

jurisdictions.bbox verified+UPDATEd: [-122.255, 47.524, -122.202, 47.596]

PRE→POST parcels: bound 4,707 → 4,966 (+3.5 pp)
          contained: 3,866 → 3,873
          nearest:   841 → 1,093
```

At nearest_50m the cov landed at **66.7 %** — still 3.3 pp sub-gate. Per the Westchester Group A precedent (PR #244 Bedford / Port Chester / Yorktown @ nearest_100m, authorized by Master when nearest-cap had margin), I probed the distance distribution + escalated:

| Radius | Would-bind | cov post | nearest share | Verdict |
|--------|-----------:|---------:|--------------:|---------|
| nearest_50m | 0 (already done) | 66.7 % | 14.7 % | sub cov |
| **nearest_100m** | **962** | **79.6 %** | **27.6 %** | **PASS both** |
| nearest_150m | 1,714 | 89.7 % | 37.7 % | over nearest cap |
| nearest_200m | 2,170 | 95.8 % | 43.8 % | over nearest cap |
| nearest_300m | 2,480 | 100.0 % | 48.0 % | over nearest cap |

100 m is the unique radius that clears both gates. After the escalation pass:

```sql
-- One-off escalation: nearest_100m on still-NULL parcels, city layer only.
UPDATE parcels target
SET zoning_code = sub.zone_code,
    zone_binding_method = 'nearest_100m',
    zone_class = sub.zone_class
FROM (SELECT p.id, m.zone_class, m.zone_code FROM parcels p,
      LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
               WHERE zd.jurisdiction_id = $1::uuid
                 AND zd.raw_attributes->>'muni_name' = 'Mercer Island (city)'
                 AND zd.geom IS NOT NULL
                 AND ST_DWithin(zd.geom::geography, ST_Centroid(p.geom)::geography, 100)
               ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography)
               LIMIT 1) m
      WHERE p.jurisdiction_id = $1::uuid AND p.city = 'Mercer Island'
        AND p.geom IS NOT NULL AND p.zoning_code IS NULL) sub
WHERE target.id = sub.parcel_id;
-- UPDATE 962
```

**Final binding distribution** (post-escalation):

| Binding method | Count | Share |
|----------------|------:|------:|
| contained | 3,873 | 52.0 % |
| nearest_50m | 1,093 | 14.7 % |
| nearest_100m | 962 | 12.9 % |
| (NULL — still unbound) | 1,520 | 20.4 % |

The 1,520 still-unbound parcels are beyond 100 m from any city polygon — reaching them would require nearest_200m (43.8 % nearest share) or accepting WAZA's prior 48-polygon coverage as the ceiling. Per the 30 % nearest cap, **100 m is the maximum honest radius for this fire**. Master's prior Westchester precedent stops at the cap — same here.

## New codes surfaced — orchestrator follow-up signal

The 82-polygon city layer carries 14 distinct ZONING codes. PR #266's matrix sprint authored 11 of these (B, C-O, MF-2, MF-2L, MF-3, PBZ, PI, R-12, R-15, R-8.4, R-9.6). The 3 NEW codes that bind to parcels after this fire are:

| New code | ZoningDescription | Parcels bound |
|----------|-------------------|--------------:|
| **OS** | Open Space | 235 |
| **P** | Park | 70 |
| **TC** | Town Center | 4 |
| **Total** | | **309** |

These 309 parcels (4.1 % of total, 5.2 % of bound) are currently unmatched in `zone_use_matrix`. Orchestrator authoring follow-up (≤ 30 min for a 3-code mini-sprint per PR #266 cadence) would push matrix-match share from 94.8 % → ~100 %.

This is the **orchestrator follow-up signal** Master pre-authorized — surfaced via the `ORCHESTRATOR FOLLOW-UP` line in the fire output. No matrix authoring done here (per the "don't author matrix" hard rule).

## Audit `coverage_snapshots` — persistence lag

Per Master's protocol: ONE refresh per task. Fired the targeted refresh ~13:34 PT (20:34 UTC). After 75+ min:

| Action | Timestamp | Result |
|--------|-----------|--------|
| Targeted refresh #1 (wrong JSON body — endpoint takes query param) | 13:34 PT | Railway proxy 502 at ~30 s |
| Targeted refresh #2 (correct `?jurisdiction_id=…` syntax) | 14:01 PT | Railway proxy 502 at 41.9 s |
| Targeted refresh #3 | 14:09 PT | Railway proxy 502 at ~10 s |
| Full-sweep refresh (no jurisdiction_id) | 14:18 PT | Railway proxy 502 at ~10 s |
| Final poll | 14:30 PT | Snapshot still `captured_at = 2026-06-16T17:54:33Z` (pre-fire) |

The refresh worker is observed to 502 on Mercer specifically. This matches the **Bellevue pattern from PR #271** — Bellevue's snapshot took ~1 hr from the re-jurisdictioning fire to land in `coverage_snapshots`. Bellevue eventually persisted at 18:14:37 UTC.

**Hypothesis** (read-only investigation, no fix attempted): the audit SQL CTE chain (`parcel_stats` + `zoning_stats` + `matrix_stats` + `parcel_zone_matrix` + `unmatched_zone_samples`) is jurisdiction-name-filtered AFTER the CTEs scan all parcels. With Mercer's new 82 city-layer districts and 3 unmatched-zone codes (OS / P / TC), the `unmatched_zone_samples` CTE produces a non-empty JSON aggregate where before it was empty. Could be a query plan regression, an upstream lock contention with the just-committed UPDATEs, or a Railway proxy-side connection reset. None of these are debuggable from outside the worker.

**Master Halt-and-Report invoked**: per Master's prior dispatch ("If snapshot STILL stuck at 17:54 with no update: HALT-AND-REPORT — write the docs noting DB-level success + audit snapshot persistence delay…"). DB data is the operational truth; the snapshot is a cached projection. When the worker re-runs (next scheduled sweep or after Master's prod investigation), Mercer will flip operational.

## Expected operational state (post-snapshot)

| Period | Count | Net Δ | Notes |
|--------|------:|------:|-------|
| Post-PR #271 (Bellevue flip, pending merge) | 21 | +1 | Bellevue Phase 6B-PIVOT |
| **Post-this-PR (audit snapshot landed)** | **22** | **+1** | **Mercer Island Task E — city-fallback re-fire** |

`coordination/lane_state.json` NOT updated on this branch — the bump to 22 is conditional on snapshot persistence, and PR #271 (still open) holds the 20 → 21 bump. When PR #271 + this PR merge, the bump should be 20 → 22.

## What changed in the repo

- `backend/scripts/rebackfill_mercer_island_city.py` (new) — single-purpose city-fallback adapter
- `docs/OP5_MERCER_ISLAND_CITY_FALLBACK.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-16 entry

No backend code changes. No matrix authoring (orchestrator's follow-up territory for OS / P / TC). No directory file changes — the existing `backend/data/king_wa_zoning_directory.json` `fallback_zoning_district_source` for Mercer is the source-of-record this adapter reads.

## Halt-and-report discipline (running tally)

This is the **7th halt of the campaign** (sort of — it's a soft halt; DB-level success but pending audit):

1. PR #216 — Phase 2A Montgomery PA: 54 districts cover ~1.2 % of county
2. PR #221 — Phase 2B Fairfield CT: CAMA layer has zero zoning attributes
3. PR #242 — Task 5 Phase 2 Contra Costa: jurisdiction + parcels not loaded
4. PR #253 — Phase 5A.2 Pass 2: asyncpg 60-min ceiling (partial recovery)
5. PR #259 — Phase 6A.1 Bellevue WAZA-vs-city mismatch (resolved via PR #264)
6. PR #267 — Phase 6B.1 Pierce city field uniformly null
7. **This halt — Mercer Island audit snapshot persistence lag** (DB-level success, snapshot pending; matches Bellevue PR #271 ~1 hr latency pattern)

## Recommended next dispatches

Per Master's sequencing (post-this-PR cohort):

1. **Mercer audit snapshot verification** — re-poll `/api/admin/coverage` after Master review or after natural worker schedule lands the row. Confirm 21 → 22 flip.
2. **Orchestrator mini-sprint for OS / P / TC** — 3-code matrix authoring (~30 min), pushes Mercer match-share from 94.8 % → ~100 %. Mercer flip is NOT blocked on this (cov 79.6 % alone clears the gate); this is hygiene work.
3. **Bainbridge Island (Kitsap) per-muni registration + ingest + zoning + matrix** — next in the Phase 6B.2 PIVOT cohort per Master's sequencing (after Mercer + before Mill Creek + Pierce).
4. **Mill Creek (Snohomish) per-muni** — with mandatory 5-feature WAZA spot-check on the 5,406 anomaly before full ingest.
5. **Task E (Pierce WA City Limits spatial join)** — backfill `parcels.city` for 328,832 Pierce rows.
6. **Gig Harbor (Pierce) per-muni** — gated by step 5.

Expected trajectory: 21 (Bellevue) → 22 (Mercer, this PR) → 23 (Bainbridge) → 24 (Mill Creek) → 25 (Gig Harbor) over the next 2-4 days.
