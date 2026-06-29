# Catch #12 — Multi-stage job restart / auto_score completion gap

READ-ONLY diagnostic. No application code changed. Investigated by reading the
orchestration path end to end. All file:line refs are to the state of the repo
on branch `parcellogic/coordination-lane-state-jun-25`.

---

## 1. Stage-transition + lock/heartbeat flow (as found)

### Enqueue path (prod = Dramatiq, NOT BackgroundTask)

- `backend/app/api/jobs.py:144` (and `:321`, `:352`) call
  `enqueue_pipeline_job(job.id)`.
- `backend/app/services/job_queue.py:36-37` — `enqueue_pipeline_job` is
  `process_pipeline_job.send(...)`, i.e. a **Dramatiq actor** message, not a
  FastAPI `BackgroundTask`. (The docstring on `run_job_pipeline` at
  `pipeline.py:1212` still says "Runs as a FastAPI BackgroundTask" — stale; the
  real driver is the Dramatiq worker.)
- The actor wrapper:
  `job_queue.py:20-33`
  ```python
  @dramatiq.actor(max_retries=2, min_backoff=30_000, max_backoff=300_000,
                  time_limit=60 * 60 * 1000)   # 60 min
  def process_pipeline_job(job_id: str) -> None:
      from app.services.pipeline import run_job_pipeline
      asyncio.run(run_job_pipeline(uuid.UUID(job_id)))
  ```
  Each invocation spins up a **fresh event loop via `asyncio.run`**.

### Pipeline claim + lock + heartbeat start

`pipeline.py:1210-1269` (`run_job_pipeline`):

- `:1219-1224` claims the row with `SELECT ... FOR UPDATE NOWAIT`; on
  `OperationalError` it logs "already locked" and returns.
- `:1229-1234` skips terminal jobs and (mostly) already-locked jobs.
- `:1247-1252` sets `status=running`, `locked_by=hostname`, `locked_at=now()`,
  `attempts += 1`, commits.
- `:1254` **starts the heartbeat**:
  `heartbeat_task = asyncio.create_task(_heartbeat_locked_at(job_id))`.
- `:1256` runs the inner `_run(db, job)`; on success marks ready, on
  `JobCancelled` commits cancelled, on `Exception` calls `mark_job_failed`.
- `:1264-1269` cancels the heartbeat in `finally`.

### Heartbeat

`pipeline.py:1192-1205`:
```python
async def _heartbeat_locked_at(job_id, interval=60):
    while True:
        await asyncio.sleep(interval)               # 60 s
        async with async_session_maker() as hb_db:  # SHARED engine
            ... hb_job.locked_at = now_utc(); await hb_db.commit()
```
Refreshes `locked_at` every 60 s using the module-level `async_session_maker`
(the **shared `engine`** from `db.py:87-93`, built with `NullPool`).

### Stage sequence in `_run` (`pipeline.py:1272-2269`)

`discover_layers` (`:1276`) → `jurisdiction_persistence` (`:1325`) →
`download_parcels` (`:1368`) → `ingest_parcels` (`:1513`, calls
`ingestion.ingest_parcels`) → post-ingest: `parcel_bbox_refresh` (`:1594`),
`census_tracts_precompute` (`:1615`), fire-and-forget
`enqueue_ring_metrics_precompute` (`:1651`) → `download_zoning` (`:1697`) →
`ingest_zoning` (`:1727`) → `backfill_zoning` (`:1747`,
`backfill_parcel_zoning_from_districts`) → `zoning_overlays_bulk` (`:1766`) →
[county-only] `sibling_zoning_backfill` (`:1892`, **`asyncio.timeout(1800)`**),
`crosswalk_cities` (`:1935`) → `zone_matrix_bootstrap` (`:1969`) →
`coverage_refresh` (`:2018`) → `run_overlays` (`:2034`) → `parse_ordinance`
(`:2169`, optional) → `complete_feasibility` + **`auto_score`** (`:2233-2251`) →
`status=ready` + `locked_at=None` (`:2253-2263`).

`auto_score` **is a real pipeline stage** (`:2233-2251`, wrapped in
`asyncio.timeout(900)`), not a separate enqueue. Its failure is non-fatal
(caught at `:2249`), and `status=ready` is still written right after at `:2253`.
So failure mode (e) is **refuted**: auto_score cannot "silently not fire" as a
separate job — it is inline and the job still reaches `ready` even if it raises.

### Restart / re-claim mechanism

`backend/app/services/job_watchdog.py` — `recover_stale_jobs`:
```python
STALE_AFTER_SECONDS = 25 * 60   # :12   (25 min)
MAX_ATTEMPTS = 3                # :13
...
select(Job).where(Job.status.in_(ACTIVE_JOB_STATUSES),
                  Job.locked_at.isnot(None),
                  Job.locked_at < cutoff)        # :20-25
... elif (job.attempts or 0) < MAX_ATTEMPTS:
        job.status = retrying; job.locked_by = None; job.locked_at = None
        enqueue_pipeline_job(job.id)             # :34-38  ← RE-ENQUEUE
```
This is the only thing that restarts a running pipeline. It is driven from
`backend/app/main.py:42-61`:
- `:55` runs once on **API startup** (every web deploy / dyno restart).
- `:44-52,61` a loop runs it **every 5 minutes** while the API is up.

`backend/scripts/queued_job_watchdog.py` is a **different, alert-only** tool
(`find_stuck_queued_jobs`, `:30`) — it reports `status=queued` jobs older than
10 min and never re-enqueues. It is NOT the restart mechanism (and also launches
the daily digest, `:139`). Do not confuse the two.

---

## 2. Ranked root-cause hypotheses (with code evidence)

### (a) Lock-heartbeat starvation during a long *synchronous* stage → watchdog re-claim → restart  — **LEADING**

The watchdog re-enqueues any `ACTIVE` job whose `locked_at < now-25min`
(`job_watchdog.py:12,24`). The heartbeat must refresh `locked_at` at least once
per 25 min. Two ways it can miss that window:

1. **CPU-bound stage blocks the event loop.** The heartbeat is a coroutine on
   the *same* loop as the pipeline (`pipeline.py:1254`). The parcel **mapping
   loop** in `ingestion.ingest_parcels` is pure-Python and synchronous:
   `ingestion.py:502-512`
   ```python
   for idx, values in enumerate(gdf.itertuples(index=False, name=None), start=1):
       row = dict(zip(columns, values))
       mapped = _map_row(...)        # calls _normalize_geom → shapely make_valid
       ...
       if progress_callback is not None and idx % 1000 == 0:
           await progress_callback("mapping", idx, len(gdf))
   ```
   The only `await` is the progress callback every 1000 rows, and that callback
   only actually awaits network I/O every 2000 rows
   (`pipeline.py:1545` `if completed % 2000 == 0`). Between those points the
   loop never yields, so `asyncio.sleep(60)` in the heartbeat cannot wake.
   `_normalize_geom` runs `shapely.make_valid` per row (`ingestion.py:359-360`)
   — on a 280k–420k-parcel county (Bergen 281k, Nassau 420k) this loop is the
   single longest *CPU* block in the pipeline and can hold the loop for many
   minutes uninterrupted. If total mapping + the gaps between yields stretch the
   wall-clock between two successful heartbeat commits past 25 min, the watchdog
   re-enqueues the job → **a second `process_pipeline_job` runs from
   `discover_layers`**. This matches the Montgomery PA observation (pass 1
   relock → full pass 2 from discover_layers).

2. **Heartbeat write itself silently fails on the shared engine.** The
   heartbeat uses `async_session_maker` (shared `engine`, `db.py:87-93`).
   Everywhere else in the worker the code is at pains to build a **fresh**
   `make_engine()` per `asyncio.run` because the shared engine's asyncio
   internals get bound to a destroyed loop in the Dramatiq worker (see the long
   comments at `job_queue.py:44-57`, `db.py:46-51`). The heartbeat is the one
   long-lived background coroutine that still uses the shared maker. If its
   `commit` throws (MissingGreenlet / dead pgbouncer socket / "bound to a
   different event loop"), the exception is swallowed at `pipeline.py:1204-1205`
   (`logger.debug`, no escalation) and `locked_at` simply stops advancing. The
   loop keeps "running" but the watchdog now sees it as stale → re-claim.

Either path produces exactly catch #12's signature: a long real run that the
watchdog decides is dead and restarts. The 25-min cutoff vs the 60-min actor
`time_limit` is the structural mismatch — **the pipeline is allowed to run up to
60 min, but the watchdog declares it dead at 25 min of heartbeat silence.** The
Bergen "~65 min, 0 rows" precedent fits: a job that exceeds the actor's 60-min
`time_limit` is killed mid-run by Dramatiq, while the watchdog had already
re-enqueued a competing copy at 25 min.

### (b) Web BackgroundTask stalls on deploy/dyno churn — **REFUTED for the pipeline**

Prod enqueues via Dramatiq (`job_queue.py:36-37`), not BackgroundTasks. The
pipeline runs on the resilient worker. (BackgroundTasks remain the risk for the
*listing-match* path — `job_queue.py:151-160` documents catch #25 as the same
family — but that is a sibling, not the parcel pipeline.) Ironically, the
**watchdog that does the restarting lives in the web process** (`main.py`), so a
web dyno restart fires `recover_stale_jobs` immediately on boot
(`main.py:55`) — a web deploy *during* a long worker stage will re-claim the
in-flight worker job. This is a real contributor but secondary to (a).

### (c) Swallowed exception between post_ingest and auto_score leaving the job hung — **LOW**

Every post-ingest stage that can throw is wrapped in try/except that is
explicitly non-fatal and continues (`zoning` `:1789`, `sibling` `:1913`,
`crosswalk` `:1952`, `bootstrap` `:1981`, overlays `:2095`, ordinance `:2192`,
auto_score `:2249`). The path from `complete_feasibility`/auto_score to
`status=ready` (`:2253-2263`) has no intervening unguarded await that would
leave the job hung without either reaching `ready` or hitting the outer
`mark_job_failed`. So a "hang between post_ingest and auto_score" is not
supported by the code — a true hang would be a blocked await (covered by (a)),
not a swallowed exception.

### (d) Idempotency / resume gap on restart — **CONFIRMED as a real (secondary) defect**

There is a helper `_step_completed` (`pipeline.py:74-83`) that checks for a
completed `JobStep`, **but it is never called** — grep shows no call site. The
only resume guards are coarse data-existence checks:
- parcels: `parcels_cached = existing_count > 1000` (`:1402`) skips
  download+ingest if >1000 parcels already exist.
- zoning districts: `_skip_zd_download = _zd_count > 0 and not job.force`
  (`:1690`).

These are *data* checks, not *stage* checks. On a non-forced restart they skip
the two biggest stages, so a restart is cheaper than a cold run — but Montgomery
PA "redid everything." That is consistent with the restart happening **before**
parcels crossed the >1000 threshold (i.e. during the mapping/COPY of pass 1, so
pass 2 still saw an empty/partial table), OR with the COPY's temp-table
transaction (`ingestion.py:686-720`) not having committed visible rows yet.
Net: resume is partial and best-effort; there is no per-stage idempotency
ledger, so a mid-`ingest` restart re-runs the whole download+ingest. By design?
Partly — but the unused `_step_completed` shows a finer-grained resume was
intended and never wired in.

### (e) auto_score is a separate enqueue that can silently not fire — **REFUTED**

auto_score is inline at `pipeline.py:2233-2251` and `status=ready` follows
unconditionally at `:2253`. There is also a *second* re-score in the ring-metrics
actor (`job_queue.py:123-134`), which is additive insurance, not the primary
path. No silent-no-fire gap.

---

## 3. Single most-likely root cause

**Lock-heartbeat starvation (hypothesis a) — the 25-min watchdog stale cutoff is
shorter than the real wall-clock between heartbeat refreshes on large
jurisdictions, so `recover_stale_jobs` re-enqueues a still-running pipeline.**

The two starvation channels reinforce each other:
1. The synchronous parcel-mapping loop (`ingestion.py:502-512`, shapely
   `make_valid` per row) blocks the event loop between sparse `await`s, so the
   heartbeat coroutine can't run.
2. When it does run, the heartbeat writes via the **shared engine**
   (`pipeline.py:1197`) — the exact engine the rest of the worker avoids — and
   any failure is swallowed at debug level (`:1204-1205`), so `locked_at`
   silently freezes.

Both leave `locked_at` older than 25 min while the job is genuinely alive;
`job_watchdog.py:24` then matches it and `:38` re-enqueues → restart from
`discover_layers`. This is the smell in Montgomery PA and the stall/0-row
outcome in Bergen.

---

## 4. Proposed minimal line-level fix + test plan

Three small, independent changes (any one helps; all three together close it):

### Fix 1 — raise the watchdog cutoff to exceed the actor time limit
`backend/app/services/job_watchdog.py:12`
```python
# was: STALE_AFTER_SECONDS = 25 * 60
STALE_AFTER_SECONDS = 70 * 60   # > the 60-min Dramatiq time_limit + slack
```
Rationale: the actor (`job_queue.py:28`) is allowed 60 min. A job is not
"dead" until Dramatiq itself kills it at 60 min; the watchdog must not pre-empt
that. 70 min gives margin. This single one-line change removes the structural
25-vs-60 mismatch that creates the duplicate run.

### Fix 2 — harden the heartbeat against event-loop starvation + silent failure
`backend/app/services/pipeline.py:1192-1205`
- Use a **fresh `make_engine()`** for the heartbeat (mirror the worker actors at
  `job_queue.py:54-57`) instead of the shared `async_session_maker`, so a
  loop-bound shared engine can't make every heartbeat throw.
- Escalate persistent heartbeat failures from `logger.debug` to `logger.warning`
  (`:1205`) so a frozen `locked_at` is *visible* in logs instead of silent.

### Fix 3 — stop the mapping loop from starving the loop
`backend/app/services/ingestion.py:511-512`
- Add a bare `await asyncio.sleep(0)` on the same cadence as the progress
  callback (or yield every N rows) so the heartbeat coroutine gets scheduling
  turns even when `_progress_commit`'s network await is skipped (it only fires
  every 2000 rows at `pipeline.py:1545`). Or move the CPU-bound mapping into
  `asyncio.to_thread(...)` so it never blocks the loop at all (preferred — it
  also lets the heartbeat run continuously through the whole mapping phase).

Optional follow-up (resume correctness, addresses (d)): wire the existing but
unused `_step_completed` (`pipeline.py:74-83`) into each stage so a restart
skips already-`completed` JobSteps instead of relying on the >1000-parcel data
heuristic.

### Repro / test plan
1. **Unit (deterministic):** monkeypatch `STALE_AFTER_SECONDS` low (e.g. 2 s)
   and `_heartbeat_locked_at` interval high (e.g. 5 s); run a fake job whose
   `_run` sleeps 4 s of *blocking* work (no await), then assert
   `recover_stale_jobs()` would re-enqueue it — demonstrating the starvation
   window. Re-run with Fix 3's `await asyncio.sleep(0)` injected and assert it
   does NOT re-enqueue.
2. **Heartbeat-write test:** force the shared engine's session `.commit()` to
   raise (simulate loop-bound/dead conn); assert with current code `locked_at`
   stops advancing silently; with Fix 2 it logs a warning and (fresh engine)
   succeeds.
3. **Integration (prod-shaped):** ingest a large county locally with a
   synthetic 280k-row GeoDataFrame and the watchdog loop running at a short
   interval; with current code observe a second `process_pipeline_job`
   firing from `discover_layers` (look for two `pipeline_event ... stage=
   discover_layers event=started` lines for one job_id at `pipeline.py:1276`);
   with the fixes, observe exactly one.
4. **Query to confirm in prod history** (read-only): count jobs that have >1
   completed `discover_layers` JobStep —
   `SELECT job_id, COUNT(*) FROM job_steps WHERE step='discover_layers'
   GROUP BY job_id HAVING COUNT(*) > 1;` — each such job is a confirmed
   restart. (`attempt` on `JobStep` is incremented at
   `job_tracking.py:85-86`, so `attempt > 1` rows are the same signal.)

---

## 5. Family relationship to #10 and #30

- **Catch #10 (ops-cron freshness):** same operational-liveness family. #10 is
  about the *cron/digest* tick not firing (the
  `queued_job_watchdog._run_digest_tick` workaround, `queued_job_watchdog.py:
  139-167`, exists because Railway ignored the cron `startCommand`). #12 is the
  inverse failure of the *other* watchdog: `recover_stale_jobs` fires too
  eagerly because its liveness signal (`locked_at`) is unreliable. Both are
  "the heartbeat/freshness signal does not reflect reality."
- **Catch #30 (Dramatiq worker restart):** direct cousin. The pipeline runs in
  the Dramatiq worker (`job_queue.py:30-33`); a worker restart mid-run loses the
  in-process heartbeat task entirely, so `locked_at` freezes and the
  web-process watchdog (`main.py:55`) re-claims the job — the same restart
  symptom as #12 but triggered by worker churn instead of heartbeat starvation.
  Fix 1 (longer cutoff) also softens #30 by giving a bounced worker more time to
  resume before the web watchdog steals the job. The sibling listing-match
  actor (catch #25, `job_queue.py:151-160`) is the same lesson applied to a
  different job class: move long work off the fragile web BackgroundTask onto
  the worker.

Common thread across #10/#12/#25/#30: **long-running work + an unreliable
liveness signal + an eager recovery/restart mechanism.** Catch #12's specific
defect is the 25-min watchdog cutoff being shorter than the 60-min job budget,
compounded by a starvable/silent heartbeat.
