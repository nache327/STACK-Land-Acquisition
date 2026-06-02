# Op-5 Dispatch J + O — Final Gate Before Factory Decision

**Owner:** Master Planning Thread
**Authorized:** 2026-06-04
**Context:** Op-5 proof has converged. 3 CP3 results in: Fort Lee accuracy 9/10 + Garfield accuracy 10/10 + Hackensack accuracy 4/10 mixed (georef issue). All 3 fail coverage gate (≥70%). Diagnosis: coverage gap is platform-side (centroid-only `ST_Within` in `spatial_backfill.py`), Hackensack also needs georef refit. These two dispatches close both gaps and produce the final factory go/no-go decision.

---

## Dispatch J — Lane A: spatial_backfill nearest-district fallback

**Owner lane:** Lane A (backend/integrator)
**Branch:** new worktree off `main`
**Scope:** ~50-100 LOC + tests. Backend pipeline code only. No Op-5 work. No matrix work.

### Paste-ready brief for Lane A worker

```
You are LANE A — INTEGRATOR. Dispatch J: platform-side coverage fix for the Op-5 pipeline.

Read first:
- backend/app/services/spatial_backfill.py — current implementation
- backend/app/services/pipeline.py:1617 — caller / hook point
- backend/scripts/audit_zoning_coverage.py — coverage % computation
- docs/OP5_PROOF_PLAN.md sections on coverage failure (F7)
- coordination/lane_state.json

Goal:
Add a "nearest-district fallback" path to spatial backfill so parcels not contained in any zoning district can be optionally bound to their nearest district within a tunable radius. This is the platform-side fix that closes the Op-5 proof's coverage gap (Fort Lee: 57.6% → ~80%+; Garfield: 40.9% → ~80%+ per distance histogram).

Required changes:

1. Extend `backfill_parcel_zoning_from_districts` in backend/app/services/spatial_backfill.py:
   - New kwarg: `nearest_within_meters: float | None = None` (default None = current behavior, fully backward compatible)
   - When set: after the ST_Within pass, for any parcel still missing zoning_code, run a second pass using ST_DWithin to find the nearest district within N meters. Use ST_Distance for tie-breaking. LATERAL subquery for performance.
   - Use raw asyncpg with `SET statement_timeout = 0` like the existing path
   - Preserve the >99% skip optimization

2. Add binding-method tracking on parcels:
   - Prefer: add a `zone_binding_method` column to the `parcels` table via Alembic migration (values: NULL | 'contained' | 'nearest_<N>m' as a varchar). 
   - Alternative if you want zero-migration: store in an existing JSONB column like `parcels.metadata.zone_binding_method`. Choose whichever is more idiomatic for this repo (check existing parcels schema first).
   - Populate on every write from this service.

3. Update audit_zoning_coverage.py:
   - In `_summarize_jurisdiction` (or equivalent), split coverage % by binding_method
   - Add output fields: `parcel_zoning_code_coverage_pct_contained`, `parcel_zoning_code_coverage_pct_nearest`
   - Keep the existing `parcel_zoning_code_coverage_pct` as the combined number for the operational gate (≥70% remains the gate)
   - This lets master read the contained-vs-inferred split without changing the operational definition

4. Tests:
   - Add unit test in backend/tests/test_spatial_backfill.py covering the nearest-district path on a small fixture
   - Add integration test verifying that audit output includes the binding-method split

5. Validation on preview branch:
   - Preview branch ref: bbvywbpxwsoyvdvygvyw
   - Fort Lee jurisdiction is loaded with Op-5 polygons (55 + 36 from v3 vision pass = 91 active polygons, matrix is 31 rows at 100% match)
   - Run: spatial_backfill on Fort Lee with nearest_within_meters=50.0
   - Report: before/after parcel_zoning_code_coverage_pct, binding_method distribution
   - Run: spatial_backfill on Fort Lee with nearest_within_meters=200.0 (a more aggressive fallback)
   - Report same metrics
   - Pick the most defensible default for production (likely 50m, but data tells the story)

6. PR:
   - Open against main
   - Title: feat(pipeline): nearest-district fallback in spatial_backfill (Op-5 coverage fix)
   - Do NOT merge without Master review
   - Body must include: Fort Lee before/after numbers, binding-method distribution, rationale for the chosen default

Hard rules:
- No prod ingest
- No Op-5 pipeline changes (do not touch backend/scripts/op5_*.py, backend/scripts/extract_pdf_*.py, or backend/app/prompts/op5_*.md)
- No matrix work (do not touch backend/scripts/pattern_*_adjudication.py)
- No UI work
- No coordination JSON edits — Master Planning owns those
- Stop with PR opened (not merged); report URL + Fort Lee before/after numbers

Expected output:
- One PR against main
- Before/after Fort Lee coverage numbers proving the fix works
- Binding-method distribution showing what fraction of parcels are 'contained' vs 'nearest_Nm'
- Recommendation for production default (your call based on the data)

When done, report back here so Master can decide on Hackensack georef-v2 results, then on factory dispatch.
```

---

## Dispatch O — Op-5 orchestrator: Hackensack georef refit via Mapbox

**Owner lane:** Op-5 orchestrator (existing)
**Branch:** continues on orchestrator's workspace
**Scope:** Re-runs Hackensack pipeline with Mapbox-based GCPs replacing the failed Nominatim attempt. No platform changes.

### Paste-ready brief for the Op-5 orchestrator

```
Dispatch O — Hackensack georef refit via Mapbox geocoder.

Background:
Dispatch K failed Hackensack because Nominatim cannot resolve street-intersection queries. Result was Hackensack 4/10 spot-check on honest mixed sample. The vision-LLM uncovered-region pass also failed because the CP1 georef projected unbound parcel clusters outside the source render — i.e. the affine transform itself is too imprecise. This dispatch replaces the geocoder.

Reuse existing platform integration:
- backend/app/services/mapbox_isochrone.py uses the Mapbox token already in env (MAPBOX_TOKEN or similar — confirm against existing usage)
- Mapbox Geocoding API at https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json?access_token={token} resolves street intersections like "Main St and Anderson St, Hackensack, NJ" cleanly
- Same auth pattern; same env

Steps:
1. Render Hackensack source PDF to PNG at ≥300 DPI (you already have this at /tmp/op5_proof/hackensack/source_render.png).
2. Run vision-LLM on the render with a new prompt asking specifically for 8-10 named ground control points: "Identify 8-10 specific landmarks in this zoning map suitable for georeferencing. Prefer street intersections (e.g. 'Main St and Anderson St'). Include parks, schools, bridges, river bends, and named civic buildings as fallback. For each, return {pixel_x, pixel_y, label, label_type: 'intersection'|'landmark'|'civic'}."
3. For each GCP candidate, query Mapbox Geocoding:
   - For intersections: query "{label}, Hackensack, NJ" with proximity bias around Hackensack centroid
   - For landmarks: same with full label
   - Accept the highest-relevance result with type=='address' or 'poi'
   - Discard GCPs that Mapbox cannot resolve confidently (>10m precision)
4. If <6 GCPs survive: use vision-LLM to identify more landmarks; do NOT proceed with <6.
5. Compute new affine transform via least-squares fit on the 6-10 GCPs.
6. Report RMS error in meters and per-GCP residuals. Target: RMS <30m, no single GCP residual >100m.
7. Re-project the existing Hackensack polygons (50 from CP1 + any from prior vision uncovered-region attempts) through the new affine.
8. Re-ingest to preview branch (bbvywbpxwsoyvdvygvyw).
9. Re-run spatial backfill (current centroid-only path; Dispatch J's nearest-fallback may not be merged yet — that's fine, test on current path).
10. Re-spot-check 10 random Hackensack parcels (use seed 2026 to ensure a different sample from prior runs).
11. Compute spot-check accuracy on the honest mixed sample (same query semantics as the original 6/10 result, not the zoned-only 10/10).

Target:
- RMS georef error <30m
- Spot-check ≥9/10 on the honest mixed sample
- If RMS lands but spot-check stays <9/10: report which specific failures remain and their category (polygon_spans_multiple_zones, wrong_label_on_correct_polygon, or something new)

Outputs:
/tmp/op5_proof/hackensack/cp3_v3_summary.md
/tmp/op5_proof/hackensack/georef_v2.json (GCP list + Mapbox responses + affine + RMS)
/tmp/op5_proof/hackensack/polygons_labeled_v2.geojson (post-refit)
/tmp/op5_proof/hackensack/spot_check_v3.json
/tmp/op5_proof/hackensack/mapbox_geocode_log.json (every Mapbox query + response for audit)

Hard rules:
- No prod ingest
- No platform changes (do not touch backend/app/services/spatial_backfill.py or pipeline.py)
- No PRs merged
- No coordination JSON edits
- Stop for Master review

When Dispatch J's PR is open AND Dispatch O lands a spot-check result, Master will trigger Dispatch P (final re-validation gate across all 3 towns) and make the factory go/no-go call.
```

---

## What gates the final factory decision

After Dispatch J PR is open + Dispatch O completes, Master triggers a final re-validation:
- Apply J's branch to preview, re-run spatial backfill with `nearest_within_meters=50.0` for all 3 towns
- Re-spot-check all 3 towns with fresh seeds
- Report 3×3 gate state (coverage, spot-check, binding-method distribution)

Decision tree:
| Outcome | Decision |
|---|---|
| 3/3 PASS coverage ≥70% AND spot-check ≥9/10 | GO factory. Authorize 25-agent build. |
| 2/3 PASS (Hackensack still fails accuracy) | GO with raster carve-out. Vector-class → factory; raster-class → operator-assisted. |
| Fort Lee+Garfield PASS but binding-method >50% inferred | GO with binding-method transparency. Customer UI flags inferred bindings. |
| <2/3 PASS | NO-GO redesign. Pivot to operator-assisted at scale. |

Most likely outcome based on current data: GO with raster carve-out (2/3 PASS).
