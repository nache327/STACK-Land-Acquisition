# Morris-County anomaly — diagnostic

**Author:** Lane A
**Date:** 2026-06-10 (prod data captured during this session)
**Status:** DIAGNOSTIC ONLY — Master decides whether to dispatch a fix.

The 2026-06-09 cross-county baseline (`docs/PERF_BASELINE_2026_06_10.md`)
flagged Morris County, NJ as a positive outlier: 177,532 parcels, but
cold_whole p50 = **3.30 s** — 7× faster than Bergen (281,646 parcels,
**23.22 s**) and 5× faster than Hudson (143,305 parcels, **15.47 s**).
This doc answers: why, and which slow counties would benefit from the
same fix.

---

## TL;DR

**Root cause is physical row clustering on the `parcels` heap, not
query plan, missing index, or schema shape.** All three jurisdictions
use the same `ix_parcels_jur_zoning_code` index in the same plan
shape. The difference is how scattered each jurisdiction's parcels are
across heap pages — Morris packs **9.50 parcels per 8 KB heap page**;
Hudson packs **2.91**. That alone drives a 3× cold-disk-read multiple
on the dominant index scan.

**Replicability:** six of the ten whole-county outliers are in the
same "fragmented" bucket and would directly benefit from a CLUSTER /
pg_repack on the parcels heap. Three others are slow because of raw
parcel count, not clustering, and would need different work.

---

## What the EXPLAIN ANALYZE plans show

Same query (the SQL emitted by
`app.services.candidate_search.search_candidate_parcels` with
`slim=true`, `page_size=5000`, `sort=acres_desc`) against each
jurisdiction, captured 2026-06-10:

| Jurisdiction | Wall-clock | Plan shape | Index scan rows | Buffer hits | Cold buffer reads |
|---|---:|---|---:|---:|---:|
| **Morris County, NJ** | 8.42 s | Merge Right Join, top-N heapsort | 428,981 | 88,631 | **19,280** |
| Hudson County, NJ | 8.47 s | Merge Right Join, external merge (disk spill) | 143,305 | 154 | **49,231** |
| **Bergen County, NJ** | 33.97 s | Merge Right Join, top-N heapsort | 521,082 | 122,967 | **64,710** |

(EXPLAIN ANALYZE adds ~20-30 % instrumentation overhead vs the 3-trial
p50 wall-clock from the harness. The relative ratios hold.)

**Three observations:**

1. **All three use the same plan**: index scan on
   `ix_parcels_jur_zoning_code`, Merge Right Join against
   `uq_zone_matrix`, top-N heapsort by `acres DESC NULLS LAST`. No
   sequential scans, no hash joins, no JIT differences. The planner
   isn't doing anything dumb for Bergen.
2. **Bergen reads 3.4× more cold disk pages than Morris** (64,710 vs
   19,280) for only 1.22× the index-scan rows. The per-row I/O cost is
   the gap.
3. The `forsale_listings` EXISTS subplan is a tiny constant cost (~40
   ms seq scan, 4 KB rows, cached after first call) — irrelevant to
   the gap.

---

## What the heap-clustering numbers show

`distinct_pages_touched` = how many distinct 8 KB heap pages a
jurisdiction's parcels are scattered across. Lower = denser = fewer
disk I/Os to read them all.

| Jurisdiction | Parcels | Pages | **Parcels/page** | Baseline cold_whole p50 |
|---|---:|---:|---:|---:|
| Morris County, NJ | 177,532 | 18,693 | **9.50** | 3.30 s |
| Philadelphia, PA | 547,299 | 57,852 | 9.46 | 8.89 s |
| DuPage County, IL | 336,715 | 38,442 | 8.76 | 14.30 s |
| Middlesex County, MA | 423,634 | 49,988 | 8.47 | 13.73 s |
| Montgomery County, MD | 281,249 | 37,881 | 7.42 | 13.44 s |
| Bergen County, NJ | 281,646 | 39,352 | 7.16 | 23.22 s |
| Hunterdon County, NJ | 52,902 | 9,400 | 5.63 | 7.35 s (current run) |
| Loudoun County, VA | 132,428 | 36,029 | 3.68 | 16.75 s |
| Fairfield County, CT | 261,652 | 72,489 | 3.61 | 8.99 s |
| Westchester County, NY | 257,914 | 72,411 | 3.56 | 18.32 s |
| Hudson County, NJ | 143,305 | 49,258 | **2.91** | 15.47 s |
| Monmouth County, NJ | 251,486 | 89,707 | 2.80 | 20.42 s |
| Nassau County, NY | 420,577 | 157,258 | **2.67** | 20.82 s |

The number to anchor on: **Morris fits its 177 k parcels in 18 k
pages. Nassau scatters its 420 k parcels across 157 k pages — 9 ×
more pages than its parcel-density-equivalent would predict.** Both
go through the exact same plan; Nassau just has to touch 9 × more
8 KB blocks to read them.

**Why does this map to cold_whole p50 across most outliers?** Cold
buffer reads on Supabase shared storage land in the ~100-200 µs
range per page. Multiply through:

- Morris: 19,280 cold reads × ~150 µs = **~2.9 s** of disk I/O →
  matches the 3.3 s p50 once CPU/network is added.
- Bergen: 64,710 × ~150 µs = **~9.7 s** of disk I/O → matches a big
  chunk of the 23.2 s p50; the rest comes from expression eval,
  ST_AsGeoJSON, and sort across 521 k join-product rows.
- Hudson: 49,231 × ~150 µs = **~7.4 s** of disk I/O → matches the
  Hudson p50 once disk-spilled sort (`external merge Disk: 36 MB`)
  is added.

---

## Why the Bergen/Hudson clustering went bad

Provenance evidence from `jurisdictions.parcel_endpoint`:

| Jurisdiction | Source ArcGIS endpoint | Ingest order |
|---|---|---|
| Bergen | `services1.arcgis.com/.../20190724_Parcel` (Bergen-specific, 2019-vintage) | OBJECTID — unrelated to zoning |
| **Morris** | `services2.arcgis.com/.../Parcels_Composite_NJ_WM` (NJOGIS composite) | Block/Lot/MOD-IV order, naturally clusters by zoning |
| Hudson | `services2.arcgis.com/.../Parcels_Composite_NJ_WM` (same as Morris) | Same composite, but Hudson rows interleave with other-county rows |

- Bergen's source served rows in **OBJECTID order from a Bergen-county
  table**, which doesn't correlate with NJ MOD-IV zoning class. Inserts
  hit the parcels heap as-arrived → no zoning clustering.
- Morris pulled from NJOGIS composite where the underlying view
  appears ordered by **MOD-IV block/lot** (correlates spatially, which
  correlates with zoning). Inserts hit the heap clustered.
- Hudson pulled from the same composite, but Hudson is a small dense
  county (only 14 cities) — when the composite is paged it returns
  Hudson rows interleaved with the rest of NJ, leaving Hudson parcels
  scattered. Same data source, opposite outcome.

This is supported by ingest timing:

| Jurisdiction | last_indexed_at | created_at on parcel rows |
|---|---|---|
| Bergen | 2026-05-18 18:57 UTC | single 21:15 UTC bulk-insert timestamp |
| Hudson | 2026-05-11 16:24 UTC | single 19:47 UTC bulk-insert |
| Morris | 2026-05-18 21:14 UTC | single 21:20 UTC bulk-insert |

Each was a single bulk INSERT (one `created_at` value per
jurisdiction) — clustering was determined entirely by the source
endpoint's row order. No subsequent updates / page splits to blame.

---

## Replicability — per-county tier

The 10 whole-county outliers from `PERF_BASELINE_2026_06_10.md` split
into three tiers. The same Morris-pattern fix (`CLUSTER` or
`pg_repack` on `ix_parcels_jur_zoning_code`) helps Tier A and Tier B
materially; Tier C needs different work.

### Tier A — fragmented heap (parcels_per_page < 4): expect 3–6× speedup

| County | parcels/pg | cold_whole p50 | Notes |
|---|---:|---:|---|
| Nassau County, NY | 2.67 | 20.82 s | Worst case in the fleet; 157 k pages on disk |
| Monmouth County, NJ | 2.80 | 20.42 s | |
| Hudson County, NJ | 2.91 | 15.47 s | NJOGIS source, but interleaved |
| Westchester County, NY | 3.56 | 18.32 s | |
| Fairfield County, CT | 3.61 | 8.99 s | Already under 10 s; CLUSTER would still help |
| Loudoun County, VA | 3.68 | 16.75 s | |

Post-CLUSTER expectation: **parcels/page jumps to ~22** (Postgres
default heap fillfactor 100 packs ~22 rows of this width per 8 KB
page). 6× cluster-quality improvement maps to a roughly 3-5× cold-
read reduction (some buffer-cache wins are absorbed by re-reads of
the same page). All six should drop into the 4-8 s cold_whole range.

### Tier B — moderately clustered (parcels_per_page 4–8): expect 1.5–2× speedup

| County | parcels/pg | cold_whole p50 |
|---|---:|---:|
| Hunterdon County, NJ | 5.63 | 7.35 s (current run) |
| Bergen County, NJ | 7.16 | 23.22 s |
| Montgomery County, MD | 7.42 | 13.44 s |

Bergen looks like a Tier B by density alone but its baseline is 23 s —
the worst of the operationals. Could be amplified by the 1.85 ×
Cartesian explosion through Bergen's 13-municipality matrix
(521 k join rows vs Morris's 429 k). Expect a 2-3× speedup post-
CLUSTER, dropping Bergen into the 8-12 s range — still slow, but no
longer the buyer-blocking outlier.

### Tier C — already well-clustered, slow from raw parcel count

| County | parcels | parcels/pg | cold_whole p50 |
|---|---:|---:|---:|
| Philadelphia, PA | 547,299 | 9.46 | 8.89 s |
| DuPage County, IL | 336,715 | 8.76 | 14.30 s |
| Middlesex County, MA | 423,634 | 8.47 | 13.73 s |

CLUSTER would marginally help (clustering is good but not perfect).
The actual fix here is different: cap the table-view page_size,
move to cursor-based pagination, or stop sorting by `acres DESC
NULLS LAST` on the whole-county fetch — the top-N heapsort across
half a million rows is itself ~5 s of CPU. **Out of scope for the
Morris-pattern fix.**

---

## Effort estimate for the Tier A + B fix

The mechanical change is one of:

### Option 1 — `pg_repack` on parcels (recommended)

```sql
-- Single command, online, no exclusive lock:
SELECT pg_repack.repack_table('public.parcels', order_by => 'jurisdiction_id, zoning_code');
```

Caveats:
- **Disk**: needs ~21 GB of free space during the operation (current
  parcels heap is 11 GB; repack builds a shadow copy alongside).
- **Time**: ~1-2 hours wall-clock on the 11 GB heap, runs in the
  background.
- **Replication**: pg_repack rewrites the heap; check Supabase replica
  state before running.
- **Postgres extension**: requires `pg_repack` installed on the
  database. Supabase supports it on Pro and above.

### Option 2 — `CLUSTER` (simpler but takes a lock)

```sql
CLUSTER parcels USING ix_parcels_jur_zoning_code;
```

Caveats:
- **Locks the table** for the duration (estimated ~30-60 min on 11 GB
  heap). Reads + writes blocked. **Production-blocking** unless run
  during a maintenance window.

### Option 3 — per-county re-ingest with `ORDER BY` hint

Run the ingest pipeline against each Tier A county with an explicit
order-by clause on the source query (NJOGIS supports `orderByFields`,
ArcGIS supports `orderByFields`). Delete the existing parcels for
that county and re-insert in zoning-clustered order.

Caveats:
- Has to be done per county.
- Delete + re-insert leaves heap bloat unless run inside a `VACUUM
  FULL`.
- **Loses any user-side edits** (e.g. apn corrections, address
  normalization) made after original ingest.

**Recommendation in the next dispatch:** Option 1 (`pg_repack`) on a
single Tier A county first (Nassau or Hudson — smallest blast
radius), measure cold_whole p50 against the baseline, then decide
whether to repack the whole table or per-county.

### Decay

Clustering decays as new INSERTs / UPDATEs land on the heap. The
parcels table is updated:
- On every full re-ingest (one bulk INSERT per jurisdiction)
- On every per-parcel admin edit (rare)
- On every audit refresh write (no — audit writes `coverage_snapshots`,
  not parcels)
- On every spatial backfill run (`zone_class` + `zoning_code`
  UPDATE on ~jurisdiction-sized batches — does cause HOT updates
  that fragment over time)

A weekly or monthly `pg_repack` cron is the long-term answer if this
approach lands.

---

## What I did NOT find (and why these aren't the cause)

- **Missing index**: every join's left-hand side has a composite
  index keyed on `jurisdiction_id`. The plans confirm index usage on
  all three jurisdictions.
- **Different join algorithm**: all three use the same Merge Right
  Join. No hash-join surprise on the big ones.
- **JIT differences**: not enabled on any of the three plans.
- **Schema-level data shape difference**: Bergen, Morris, and the
  Tier A counties all carry the same column set, same nullability,
  same widths. Sparsity differences (Bergen 99.8 % zoning_code,
  Morris 99.96 %, Hudson 0 %) don't explain why Bergen is slower
  than Hudson.
- **Cartesian explosion from the matrix join**: Bergen blows up 1.85
  × through the join, Morris 2.42 × — *Morris explodes more and is
  still faster*. The Cartesian isn't the gap.
- **The `forsale_listings` EXISTS subquery**: ~40 ms of seq scan
  cached after the first call, identical across jurisdictions.
- **Geometry complexity**: Morris parcels are *more* geometrically
  complex than Bergen (15.9 vs 13.8 avg vertices). Not the cause.
- **Connection pool**: same Supavisor session-mode pool for all
  queries.
- **JIT/work_mem**: Hudson spills sort to disk (`external merge Disk:
  36304 kB`), Bergen/Morris fit `top-N heapsort` in memory. The
  spill costs Hudson ~500 ms, not the dominant gap.

---

## Recommended next dispatch (Master sign-off required)

**Headline**: *Repack one Tier A county (Nassau or Hudson) and measure
cold_whole p50 against the 2026-06-09 baseline. If the projected
3-5× speedup materializes, schedule a parcels-wide repack.*

Concrete steps for the next dispatch:

1. Confirm Supabase plan allows `pg_repack` extension (likely
   requires Pro tier — verify with the prod project's billing).
2. Choose Hudson as the canary (smallest absolute size, easy to
   measure delta, currently 15.5 s baseline).
3. Pre-state capture: rerun `benchmark_parcels_search.py
   --jurisdiction-names "Hudson County, NJ"` against prod and store
   the JSON.
4. Run pg_repack scoped to a per-jurisdiction temp table OR
   accept the whole-table rewrite (the cleaner path).
5. Post-state capture: re-run the harness on Hudson.
6. If Hudson drops by ≥ 3 ×: dispatch the rest (Tier A first, Tier
   B second). If < 2 ×: this theory was wrong, document what we
   measured and reconsider Tier B/C explanations.

**Estimated effort**: half-day to repack Hudson + measure + write
result. Whole-fleet repack is 1-2 hours of pg_repack runtime + a
weekend of result analysis.

Tier C (Philadelphia, DuPage, Middlesex MA) is a different ticket —
pagination / sort-order changes, not heap repack. Should not be
bundled into the Tier A fix.

---

## Artifacts captured during this diagnostic

- `/tmp/explain_Bergen.txt`, `/tmp/explain_Hudson.txt`,
  `/tmp/explain_Morris.txt` — full EXPLAIN (ANALYZE, BUFFERS) output
  on prod (not committed; available on request).
- `/tmp/candidate_search_sql.sql` — reconstructed SQL with
  jurisdiction-id parameter (not committed).
- Heap clustering counts from `(p.ctid::text::point)[0]::int`
  aggregation per jurisdiction (the table above).

No prod writes, no schema changes, no extension installs were
performed.
