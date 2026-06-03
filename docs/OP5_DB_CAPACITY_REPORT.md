# Op-5 Factory — Preview DB Capacity Report

**Author:** Op-5 Pre-build D
**Snapshot date:** 2026-06-03 (UTC)
**Preview branch ref:** `bbvywbpxwsoyvdvygvyw`
**Connection mode:** session (port 5432, via Supavisor)
**PostgreSQL:** 17.6
**Alembic head:** `0040`
**Reproducible from:** `backend/scripts/op5_db_capacity_check.py --all`
**Raw results bundle:** `/tmp/op5_factory/db_capacity_results.json`
**Rollback baseline JSON:** `/tmp/op5_factory/pre_factory_db_snapshot.json`

---

## TL;DR — headline finding

**The Supavisor session-mode pool caps client connections at 15.** A 25-agent factory fan-out targeting `port 5432` (the path
`backend/app/services/spatial_backfill.py` uses today) will see roughly
**40-44% of agents fail with `EMAXCONNSESSION`** before they do any
useful work. Measured directly via the spawn test in §2: 14/25 session-mode
connections succeeded; 11/25 returned
`InternalServerError: (EMAXCONNSESSION) max clients reached in session mode -
max clients are limited to pool_size: 15`.

**Recommendation:** cap `op5_factory_orchestrator --max-parallel` at
**14** for v1, OR move the spatial-backfill UPDATE off session-mode
(direct DB connection, bypassing Supavisor) before raising parallelism
to 25. Indexes are healthy, per-cycle latency at 14 concurrent writers is
p95 1.4s, error rate is 0%, throughput is ~10 cycles/s — the DB itself
is comfortably capable; the bottleneck is the *pooler*, not the DB.

A 14-agent cap still meets the 72-hour wall-clock budget: at proven
~3.5h/muni and 14 agents, 210 munis fits in ~52h (vs ~37h for 20 agents).
Factory throughput target is met without an architectural change.

---

## 1. Pre-factory snapshot (rollback baseline)

Captured 2026-06-03 17:18 UTC. Full JSON written to
`/tmp/op5_factory/pre_factory_db_snapshot.json` and re-runnable via
`python backend/scripts/op5_db_capacity_check.py --snapshot`.

| Metric | Value |
|---|---:|
| Total jurisdictions | **87** |
| Total parcels (preview) | **10,285,645** |
| Total zoning_districts | **48,387** |
| Total `zone_use_matrix` rows | **5,103** |
| Active connections in DB at snapshot time | 16 (13 idle, 1 active, 2 unknown) |

### `parcels.zone_binding_method` distribution (pre-factory)

| Method | Rows |
|---|---:|
| `NULL` (never bound by spatial_backfill) | **10,256,719** |
| `contained` (ST_Within centroid match) | **25,759** |
| `nearest_50m` (ST_DWithin fallback) | **3,167** |
| `nearest_*` other radii | 0 |

This is the canonical "rollback target" for the binding column — any
factory-induced changes must be roll-backable to these exact counts on
the non-Op-5 jurisdictions.

### Op-5 proof town breakdown

The snapshot's substring scan for `fort lee | garfield | hackensack |
fair lawn` returned **zero matching jurisdiction rows** on the preview
branch. This is itself a finding: the Op-5 proof state described in
`docs/OP5_PROOF_DECISION.md` lives in `/tmp/op5_proof/` artifacts, not
in the preview DB as named jurisdiction rows. The factory therefore
has zero in-DB "do-not-touch" Bergen-proof state to protect at this
snapshot; the protection list (Fort Lee / Garfield / Hackensack / Fair
Lawn) is enforced *defensively* in the capacity-check script in case
that state lands between now and CP-Pre.

---

## 2. Connection pool sizing — **the bottleneck**

Inspected via `pg_stat_activity` + a direct 25-way spawn test.

| Metric | Value |
|---|---:|
| `max_connections` (Postgres backend) | **60** |
| `superuser_reserved_connections` | 3 |
| Effective non-superuser slots in Postgres | **57** |
| Current connections at sample | 7 |
| Supavisor session-mode pool size (measured) | **15** |
| Factory target parallelism | 25 |
| Spawn test — succeeded | **14 / 25** |
| Spawn test — failed (EMAXCONNSESSION) | **11 / 25** |
| Spawn test wall-clock | 0.81 s |

### What the error looks like
```
asyncpg.exceptions._base.InternalServerError:
  (EMAXCONNSESSION) max clients reached in session mode -
  max clients are limited to pool_size: 15
```

### Pre-existing connection consumers (top application_names)

```
pg_cron scheduler      | 1
pg_net 0.20.0          | 1
postgres_exporter      | 1
postgrest              | 1
Supavisor              | 1
Supavisor (auth_query) | 1
<unset>                | 1
```

### Verdict

**The DB can sustain 25 parallel writers; the *pooler* cannot.** Postgres
itself has 50+ free backend slots. Supavisor in session mode (port 5432)
is configured for `pool_size: 15`, which is the hard ceiling on
concurrent `spatial_backfill`-style operations until either:

1. The Supabase project's pooler config is raised, **or**
2. The factory routes the heavy UPDATE through a direct DB connection
   (bypassing Supavisor — connect straight to
   `db.bbvywbpxwsoyvdvygvyw.supabase.co:5432` if Supabase exposes that
   host on this plan), **or**
3. The orchestrator's max-parallel is capped at 14.

(2) is the cleanest architectural path but is **out of scope for Pre-build
D** — it would require modifying `backend/app/services/spatial_backfill.py`,
which the brief forbids. (3) is what the recommendations below adopt.

---

## 3. PostGIS index health on `zoning_districts` + `parcels`

Inspected 26 indexes via `pg_indexes`. All GIST indexes on `geom` /
`centroid` columns are present on both tables, including some legacy
duplicates (`idx_*` and `ix_*`) inherited from earlier migrations.
The duplicates do not affect correctness; they consume a small amount
of disk + INSERT cost.

### Key indexes confirmed

| Table | Index | Type | Definition |
|---|---|---|---|
| `parcels` | `ix_parcels_geom` | GIST | `(geom)` |
| `parcels` | `ix_parcels_centroid` | GIST | `(centroid)` |
| `parcels` | `ix_parcels_jurisdiction_zoning` | btree | `(jurisdiction_id, zoning_code)` |
| `parcels` | `ix_parcels_jurisdiction_binding_method` | btree | `(jurisdiction_id, zone_binding_method)` |
| `parcels` | `ix_parcels_jur_zone_class` | btree | `(jurisdiction_id, zone_class)` |
| `parcels` | `ix_parcels_jur_zoning_code` | btree | `(jurisdiction_id, zoning_code)` |
| `parcels` | `uq_parcels_jurisdiction_apn` | btree (UNIQUE) | `(jurisdiction_id, apn)` |
| `zoning_districts` | `ix_zoning_districts_geom` | GIST | `(geom)` |
| `zoning_districts` | `ix_zoning_districts_centroid` | GIST | `(centroid)` |
| `zoning_districts` | `ix_zoning_districts_jurisdiction_code` | btree | `(jurisdiction_id, zone_code)` |
| `zoning_districts` | `ix_zoning_districts_jurisdiction_class` | btree | `(jurisdiction_id, zone_class)` |

### EXPLAIN ANALYZE — sample jurisdiction

Sample target: **Monmouth County, NJ** (251,486 parcels, 137 zoning_districts).

#### Pass 1 — `ST_Within(centroid, district)` (LATERAL + LIMIT 1, same shape as `spatial_backfill`)

- Outer scan: Index Scan on `parcels` via `ix_parcels_jur_zone_class`
- Inner scan: Bitmap Heap Scan on `zoning_districts` via `BitmapAnd` of
  `ix_zoning_districts_jurisdiction_class` × `ix_zoning_districts_geom`
- Planning time: 43.9 ms
- Execution time (500 rows): **110.0 ms**
- **No sequential scans on either spatial table.**

#### Pass 2 — `ST_DWithin(geom::geography, ::geography, 100m)` (fallback shape)

- Outer scan: Index Scan on `parcels` via `ix_parcels_jur_zone_class`
- Inner scan: Index Scan on `zoning_districts` via
  `ix_zoning_districts_jurisdiction_class`, with the `geography` predicate
  evaluated as a Filter (135 rows removed per loop, 2 rows kept)
- Planning time: 0.3 ms
- Execution time (500 rows): **3,359.8 ms** — ~6.7 ms per outer parcel

### Verdict

**Indexes are healthy.** Neither ST_Within nor ST_DWithin fell back to
Seq Scan on `parcels` or `zoning_districts`. PR #149 / #172 left the
spatial index landscape in good shape.

Caveat: the ST_DWithin pass on Monmouth County is ~30× more expensive
per row than the ST_Within pass because the `geography` cast forces a
per-row distance computation on the entire shortlist returned by the
btree index (the GIST index doesn't apply once we project to
geography). This is unchanged by Pre-build D — it's a property of the
shape `spatial_backfill` already uses with `nearest_within_meters` —
but it bears noting: enabling `nearest_within_meters=100.0` on a
county-scale jurisdiction can add minutes of UPDATE time. The factory
is per-municipality, not per-county, so this is well within budget.

---

## 4. Stress test: 14 concurrent dummy ingests

(Why 14 and not 25: see §2. A 25-way run is preserved below as a
secondary data-point but cannot be the canonical safety verdict because
11/25 workers fail at connect time.)

### Test design

- Throwaway test jurisdiction created on the fly with name prefix
  `op5-cap-check-<utc-timestamp>-<uuid>`, state `NJ`, county
  `Op5CapCheck`. Refuses to overlap any Op-5 proof town name
  (defence-in-depth even though §1 confirmed none are in the DB).
- Seeded **50 zoning_districts** on a 10 × 10 grid of 1.1 km cells
  centred at lon −73.0, lat 39.0 (offshore — zero overlap with any
  real NJ jurisdiction geometry).
- Seeded **1,000 parcels** as small polygons inside the grid cells so
  their centroids land inside the seeded districts.
- Spawned **14 concurrent asyncpg workers** in session-mode (port 5432,
  `statement_cache_size=0`, `SET statement_timeout = 0`) — exactly the
  connection shape `spatial_backfill.backfill_parcel_zoning_from_districts`
  uses.
- Each worker cycle:
  1. INSERT 10 fresh parcels into the test jurisdiction (mimics the
     `zoning_ingestion`/`per_muni_runner` write shape).
  2. Run an UPDATE that joins `parcels` to `zoning_districts` via
     `ST_Within(ST_Centroid(parcel.geom), district.geom)` — same
     LATERAL+LIMIT 1 shape as `spatial_backfill` Pass 1, scoped to the
     test jurisdiction only.
- Test duration: **60 seconds**.
- Teardown: hard `DELETE` of all rows in the test jurisdiction + the
  jurisdiction itself. Verified clean (final snapshot before and after
  shows zero residual `op5-cap-check-*` rows).

### Results — 14-agent run

| Metric | Value |
|---|---:|
| Wall-clock | 61.3 s |
| Cycles attempted | **623** |
| Cycles succeeded | **623** |
| Cycles failed | **0** |
| Workers unable to connect | **0** |
| **Error rate** | **0.00%** |
| **Throughput** | **10.16 cycles/s** |
| Latency p50 | **1,342.6 ms** |
| Latency p95 | **1,389.1 ms** |
| Latency p99 | 1,444.1 ms |
| Latency mean | 1,346.6 ms |
| Latency max | 1,457.7 ms |
| Lock contention / deadlocks observed | none |

### Results — 25-agent stress (secondary data-point)

| Metric | Value |
|---|---:|
| Wall-clock | 31.2 s |
| Cycles attempted | 324 |
| Cycles succeeded | 314 |
| Cycles failed | 10 |
| Workers unable to connect | **10 / 25** |
| Error rate | 3.09% (all from `connect_failed: EMAXCONNSESSION`) |
| Throughput | 10.08 cycles/s (effectively from 15 connected workers) |
| Latency p50 | 1,366.9 ms |
| Latency p95 | 1,422.9 ms |
| Latency p99 | 1,604.2 ms |

Note the throughput is *identical* between the 14-agent and 25-agent
runs (~10 cycles/s). That's the bottleneck speaking directly: the DB
saturates ~10 cycles/s with 14-15 workers, and adding more workers just
piles up `EMAXCONNSESSION` rejections at the pool without raising
throughput.

### Failure modes observed

- 14-agent run: **none**.
- 25-agent run: 10 of 25 workers raised
  `InternalServerError: (EMAXCONNSESSION) max clients reached in session
  mode - max clients are limited to pool_size: 15` at `asyncpg.connect`
  time, before they could issue any SQL. The 15 that connected
  completed cleanly.
- **No `40P01` deadlocks**, no `55P03` lock_not_available, no
  `57014` query_canceled (statement_timeout), no `08006`
  connection_failure mid-cycle.

### Verdict

**Safe to launch the factory at concurrency 14.** Error rate 0%, p95
latency well below the 30-second safety bar, all workers connected,
no contention. Raising concurrency above 14-15 returns *zero* additional
throughput because the bottleneck is the Supavisor session-mode pool
ceiling, not the DB.

---

## 5. Recommendations

### Recommended `op5_factory_orchestrator --max-parallel`: **14**

Hard-cap the orchestrator at 14 concurrent agents for the v1 factory
run. This produces the same throughput as the 25-agent target while
avoiding the ~44% silent connect-failure rate that a 25-agent run
would incur on the current Supavisor config.

### 72-hour budget check at 14 parallel

- 210 munis × 3.5 h per muni / 14 agents = **52.5 hours wall-clock**
- Comfortably inside the 72 h budget (Phase 1 ≤ 48 h is the original
  target — at 14 agents we slip Phase 1 to ~52 h, which is still
  inside the overall 72 h envelope once Phase 0 + Phase 3 are factored
  in).

If we *need* the 20-agent throughput (Phase 1 < 48 h) the factory
must either:
1. Have its Supabase project plan upgraded to raise Supavisor session
   pool_size beyond 15, or
2. Have `spatial_backfill` (or the per-muni runner that calls it) switch
   from `:6543/` → `:5432/` rewriting to a **direct** DB connection
   (`db.<ref>.supabase.co` host, bypassing Supavisor entirely). This
   would land as a follow-up PR after CP-Pre review.

### Recommended per-muni statement_timeout: `0` (disabled)

Match `spatial_backfill.backfill_parcel_zoning_from_districts` exactly —
on session-mode connections, set `statement_timeout = 0` so Supabase's
default 60s `statement_timeout` (which Supavisor sometimes injects on
session-mode connections) cannot cancel a county-sized UPDATE mid-flight.
This is the same setting `spatial_backfill` already uses for the same
reason; the factory should propagate it everywhere that calls
session-mode UPDATEs.

### Pre-launch tuning

| Item | Action | Owner |
|---|---|---|
| Confirm Supavisor session pool_size on production preview | Pull config or rerun `--pool-check` immediately before H+0 | Master / Pre-build D rerun |
| Drop duplicate GIST indexes (`idx_*` vs `ix_*`) | Optional, low-priority cleanup PR | Backend follow-up |
| `ANALYZE parcels; ANALYZE zoning_districts;` before launch | Refresh planner stats given the 10M-parcel scale | Operator pre-CP-Pre |
| Verify `op5_factory_orchestrator` honours `--max-parallel 14` | Pre-build A test must cover this | Pre-build A |

### Rollback procedure

1. The pre-factory snapshot at
   `/tmp/op5_factory/pre_factory_db_snapshot.json` is the **canonical
   roll-back baseline**. Re-run
   `python backend/scripts/op5_db_capacity_check.py --snapshot
   --out-snapshot /tmp/op5_factory/pre_factory_db_snapshot.json` to
   re-capture if needed.
2. To roll back a single factory muni:
   ```sql
   DELETE FROM jurisdictions
   WHERE id = '<jurisdiction_id>';  -- cascades to parcels +
                                    -- zoning_districts +
                                    -- zone_use_matrix
   ```
   This is appropriate for munis the factory **created** (didn't exist
   pre-factory).
3. To roll back factory writes against a pre-existing muni (one that
   already had parcels and we only added zoning_districts + bindings):
   ```sql
   UPDATE parcels
   SET zone_binding_method = NULL,
       zone_class = NULL
   WHERE jurisdiction_id = '<jid>'
     AND zone_binding_method IN ('contained', 'nearest_50m',
                                 'nearest_100m', 'nearest_200m')
     AND updated_at >= '<factory_start_timestamp>';

   DELETE FROM zoning_districts
   WHERE jurisdiction_id = '<jid>'
     AND created_at >= '<factory_start_timestamp>';

   DELETE FROM zone_use_matrix
   WHERE jurisdiction_id = '<jid>'
     AND created_at >= '<factory_start_timestamp>';
   ```
4. Re-run `--snapshot` and diff against the baseline:
   - `totals.parcels` must match (assuming no new parcel ingest was
     part of the rollback) **modulo** any new parcels we deliberately
     ingested for new munis.
   - `zone_binding_method_distribution.NULL` should return to ≥
     10,256,719.
   - `zone_binding_method_distribution.contained` should not exceed
     25,759 on rolled-back munis.

### Stop conditions for the factory (DB-side)

Halt the factory and notify master if any of the following trigger
during Phase 1:

1. Any session-mode connect attempt returns `EMAXCONNSESSION` (indicates
   pool saturation or another runaway consumer joined the DB).
2. Cumulative `40P01` deadlock count crosses 5.
3. Per-muni `spatial_backfill` UPDATE wall-clock exceeds 30 minutes on
   any single muni (matches the prior Fairfax incident).
4. `parcels` row count growth rate exceeds 1.5× the per-muni expected
   parcel count (indicates a bug ingesting duplicates).

---

## Appendix A — script reproducibility

All numbers above are reproducible by running:
```
# from repo root, with .env containing the preview DATABASE_URL
python backend/scripts/op5_db_capacity_check.py --all \
    --concurrency 14 --duration 60 \
    --seed-districts 50 --seed-parcels 1000
```

The script refuses to run unless `DATABASE_URL` contains the preview
branch ref `bbvywbpxwsoyvdvygvyw`. It also refuses to stress-test
against any jurisdiction name containing `fort lee | garfield |
hackensack | fair lawn`. Stress-test data is created in a throwaway
jurisdiction (name prefix `op5-cap-check-`) and cleaned up at exit
unless `--keep-test-data` is passed.

## Appendix B — what this report does NOT cover

- **Direct-DB-connection feasibility** (bypassing Supavisor). The brief
  forbids modifying `spatial_backfill.py`, so the script could not
  benchmark direct-connection throughput. Spinning up a follow-up
  capacity test that bypasses Supavisor is the natural next step if we
  decide to push past the 14-agent ceiling.
- **Long-duration (multi-hour) soak testing.** Stress test is 60 s.
  Phase 1 of the factory is a 48 h fan-out; sustained behaviour over
  multi-hour windows (vacuum cadence, WAL pressure, autovacuum
  starvation) is not covered.
- **Frontend / API-side load.** Op-5 doesn't drive frontend traffic at
  meaningful scale, but if `/admin/op5-review` (Pre-build B) ships
  before factory launch, it will add some additional Supavisor session
  consumers that the 14-cap recommendation must absorb.
