# B8 Large-County Mapping Plateau Scoping

Date: 2026-06-01
Owner: Lane A
Disposition: no backend patch in this pass; deliberate scaling experiment required before more Nassau / Middlesex NJ / Fairfield retries.

## Scope

B8 is the recurring large-county parcel ingest mapping plateau / stale-lock class for jurisdictions at roughly 250k+ parcels. It currently covers:

- Nassau County, NY: job `3b4582c5-e47e-4bc7-8d38-7853e0173a89`, pipeline `6e8d7ee52c8c`, downloaded 420,594 parcels, stalled in ingest mapping at `210000 / 420594`, then Lane D cancelled the stale job with final `active_only=0` and `stale_only=0`.
- Nassau County, NY: earlier job `91bb9444-377a-4a3e-a3fb-45d7b63ba18e` became active/stale during `ingesting_parcels` with mapped progress and `0` upserted.
- Middlesex County, NJ: job `110b0a01-e723-43da-967c-bca50bba6848`, cancelled during large-county mapping plateau.
- Fairfield County, CT: job `30997930-3a03-47ce-8411-730b688a4c6d`, cancelled during large-county mapping plateau.

Evidence sources: `coordination/blockers.json` B8, `docs/PHASE2_PROGRESS.md` sections 8, 14, and 15.

## Relevant Code Path

The observed counters put B8 before matrix bootstrap, coverage refresh, overlays, and usually before COPY/upsert:

- `backend/app/services/pipeline.py:1392-1404` sets the job to `ingesting_parcels` with `ingest_phase="mapping"`, `parcels_mapped=0`, and `parcels_ingested=0`.
- `backend/app/services/pipeline.py:1407-1418` writes mapping progress to `parcels_mapped` and upsert progress to `parcels_ingested`.
- `backend/app/services/ingestion.py:454-472` maps the whole GeoDataFrame into `rows_by_apn` before upsert begins.
- `backend/app/services/ingestion.py:487` calls `_copy_upsert_parcels` only after full mapping and dedupe.
- `backend/app/services/ingestion.py:619-681` stages rows in 25,000-record COPY chunks and only then runs the merge.

Because the Nassau B8 evidence shows mapping progress with `0` upserted, the first proven failure surface is the all-at-once mapping/dedupe phase, not matrix bootstrap or overlay commit flow.

## Root-Cause Hypotheses

1. All-at-once parcel mapping/dedupe is the first scaling ceiling. `ingest_parcels` builds a full in-memory `rows_by_apn` dictionary for the entire GeoDataFrame before any database COPY starts. On Nassau-size inputs this can create a long CPU/memory-heavy phase where the worker remains active but makes slow or no terminal progress.

2. Long mapping phases outlive job-lock/watchdog expectations. Progress writes are best-effort raw asyncpg telemetry. A worker can continue mapping while the job also appears stale, especially when progress stops advancing for long enough to trigger stale-lock handling.

3. COPY/upsert and PostGIS index pressure are a later risk, not the current proven failure point. `_copy_upsert_parcels` uses 25,000-row COPY chunks and one raw asyncpg transaction. That can still fail or stall on geom/index pressure after mapping completes, but B8 evidence has not yet isolated that phase because the observed Nassau plateau happened before upsert progress.

4. Source data is unlikely to be the primary B8 class. Nassau downloaded the expected 420,594 features, and the same family appears on Middlesex NJ and Fairfield CT. The shared trait is large input size, not one broken FeatureServer layer.

## Chosen Hypothesis To Test

Test hypothesis 1: large-county jobs are stalling in the all-at-once mapping/dedupe phase before COPY/upsert.

This hypothesis is the best first target because it explains the current counters directly: `ingest_phase="mapping"`, `parcels_mapped` plateauing, and `parcels_ingested=0`.

## Scaling Experiment Plan

No retry is authorized by this memo. If Master authorizes a B8 experiment, run exactly one large-county canary, preferably Nassau County NY because it has the clearest recent evidence and a clean post-cancel queue state.

Preflight go/no-go:

- Go only if active and stale job queues are clean immediately before dispatch.
- Go only if no other large-county ingest is running.
- Do not include Monmouth, Westchester, Wake, Marlboro, or any B6/B7/B10 validation work in this experiment.
- Stop if Railway/DB observability is unavailable enough that progress counters cannot be polled.

During-run observation:

- Poll job status and progress on a fixed cadence.
- Record `ingest_phase`, `parcels_mapped`, `parcels_ingested`, `parcels_total`, `locked_at`, attempt number, and any terminal traceback.
- Mapping-phase pass condition: `parcels_mapped` reaches `parcels_total` and the job enters upserting.
- Mapping-phase fail condition: `parcels_mapped` stops advancing for 20 minutes while `parcels_ingested=0`, or the job appears in both active and stale queues with no traceback.
- Upsert-phase pivot condition: mapping completes but `parcels_ingested` stalls. If this happens, reclassify the next B8 subproblem as COPY/upsert/PostGIS pressure rather than mapping.

Operator decision points:

- If mapping stalls again before upsert, cancel the job and keep Nassau / Middlesex NJ / Fairfield parked. Next code work should be a small chunked mapping/upsert containment patch, not another retry.
- If mapping completes but upsert stalls, park retries and scope a COPY/upsert/PostGIS lock mitigation.
- If Nassau reaches ready, treat it as one canary pass only. Do not clear B8 globally until one additional large-county member of the family is validated or Master explicitly accepts Nassau-only evidence.

Likely containment patch after a confirmed mapping-phase repeat:

- Convert `ingest_parcels` from all-at-once mapping into bounded batches, preserving dedupe semantics.
- Persist/upsert each bounded batch or bounded dedupe window instead of holding all mapped rows until the end.
- Keep the existing 25,000 COPY chunk size or reduce it only after an upsert-phase failure proves COPY pressure.
- Preserve progress telemetry distinction between mapping and upserting so future stalls remain classifiable.

## Current Recommendation

Do not run more B8 retries as ordinary validation. Treat the next Nassau run as an explicit scaling experiment with predeclared cancellation criteria. No backend code PR was opened because the current task is planning/scoping and the next code change should be driven by one instrumented canary outcome.
