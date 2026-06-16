# Op-5 Contra Costa CA bbox metadata fix — FLIP CONFIRMED (19 → 20)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Free flip — populate `jurisdictions.bbox` for Contra Costa County, CA
**Verdict:** **Contra Costa flipped operational. Operational count 19 → 20. First Phase 2 CA county to flip.**
**Predecessors:** PR #253 (Phase 5A.2 zoning backfill) · PR #258 (county-wide matrix sprint cleared 3 of 4 blockers).

---

## Headline

| Metric | Before (PR #258 audit, 21:18 UTC) | After (post-bbox refresh, 04:30 UTC) |
|---|---|---|
| `jurisdictions.bbox` | `null` | `[-122.4356, 37.7185, -121.5347, 38.1010]` |
| `operational_readiness` | `partial` | **`operational`** |
| `blocking_gaps` | `['missing_bbox']` | **`[]`** |
| `matrix_zone_count` | 499 (55 stragglers pending) | **554** (stragglers landed) |
| `parcel_zoning_code_coverage_pct` | 71.4 % | 71.4 % |
| `self_storage_classified_parcel_pct` | 100.0 % | 100.0 % |
| **Operational count** | **19** | **20** |

## Root cause

PR #258's orchestrator matrix sprint cleared 3 of 4 Contra Costa blockers (`no_zone_use_matrix`, `no_matrix_matches_for_parcel_zones`, `low_matrix_match_pct`). The 4th — `missing_bbox` — was a **metadata-only gap**: `jurisdictions.bbox` is a column populated from `ST_Extent(parcels.geom)`, which Lane A's Phase 5A.1 parcel ingest (PR #250) didn't touch.

The audit at `backend/scripts/audit_zoning_coverage.py:467-468` checks `row.has_bbox`; when null, it appends `missing_bbox` to `blocking_gaps`, which flips the verdict to `partial` regardless of how complete the matrix/zoning side is.

## Fix

One-off script `backend/scripts/update_contra_costa_bbox.py`:

```python
# Computes [minLng, minLat, maxLng, maxLat] over 387,492 parcel geoms;
# mirrors app.services.spatial_backfill.refresh_jurisdiction_bbox SQL.
SELECT ST_XMin(ST_Extent(geom)), ST_YMin(...), ST_XMax(...), ST_YMax(...)
FROM parcels WHERE jurisdiction_id = '7ad622d4-…' AND geom IS NOT NULL;
# → [-122.4356, 37.7185, -121.5347, 38.1010]

UPDATE jurisdictions SET bbox = '[…]'::jsonb WHERE id = '7ad622d4-…';
```

The computed extent matches the acquisition spec's expected bbox to within rounding (spec: `[-122.439, 37.712, -121.533, 38.102]`). Sanity-checked the bbox falls in the CA Bay Area lon/lat range before writing.

## Verification

Audit snapshot before:
- `captured_at: 2026-06-15T21:18:52` · `operational_readiness=partial` · `blocking_gaps=['missing_bbox']` · `has_bbox=null`

Audit snapshot after (ONE refresh fired post-UPDATE; client timed out at 200 s but Railway worker continued):
- `captured_at: 2026-06-16T04:30:51` · **`operational_readiness=operational`** · **`blocking_gaps=[]`** · `matrix_zone_count=554` (the 55 stragglers from PR #258 also landed in this refresh window) · `parcel_zoning_code_coverage_pct=71.4 %`

## Lesson — pattern codified

Per Master's dispatch: "jurisdictions.bbox populated AS PART OF the ingest, not as separate residual." Phase 6A.1 King WA's PR #259 did NOT populate bbox; the same residual will fire there. Going forward, all new parcel-ingest dispatches must populate `jurisdictions.bbox` at fire time via the existing `refresh_jurisdiction_bbox` helper or an equivalent inline UPDATE.

For King WA, the bbox UPDATE will be included in the Phase 6A.2 zoning-backfill dispatch (Task B) to avoid the same trap.

## What changed in the repo

- `backend/scripts/update_contra_costa_bbox.py` (new) — one-off fix script
- `docs/OP5_CONTRA_COSTA_CA_BBOX_FIX.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-16 FLIP entry
- `coordination/lane_state.json` — `current_api_truth` 19 → 20; mode updated; new flip entry in `confirmed_flips_this_week`; net `13 + 9 - 2 = 20`

No backend code changes. No matrix authoring. No new zoning data.

## Operational state

**Operational count 19 → 20.** Contra Costa County, CA is the first Phase 2 CA county to flip operational. The Westchester NY (PR #240) + Contra Costa CA (PR #258 + this fix) pair validates the Bergen catchall pattern across both NY (Class B per-muni) and CA (Class A statewide) substrates.
