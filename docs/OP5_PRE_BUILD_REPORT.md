# Op-5 Factory — Pre-build Report (CP-Pre)

**Author:** Op-5 Factory Orchestrator
**Status:** STOPPED for Master CP-Pre review. Do NOT launch Phase 0 yet.
**Date:** 2026-06-03
**Source plan:** `docs/OP5_FACTORY_72H_PLAN.md`, `docs/OP5_PROOF_DECISION.md`

---

## PRs delivered (4/4)

| # | Pre-build | PR | Branch | Status | Lines |
|---|---|---|---|---|---:|
| A | Factory orchestrator scripts | [#178](https://github.com/nache327/STACK-Land-Acquisition/pull/178) | `adarench/op5-pre-build-a-orchestrator` | OPEN, CI green | +1,792 / −0 |
| B | Review queue UI | [#177](https://github.com/nache327/STACK-Land-Acquisition/pull/177) | `adarench/op5-pre-build-b-review-ui` | OPEN, CI green | ~720 |
| C | 4 county directories | [#179](https://github.com/nache327/STACK-Land-Acquisition/pull/179) | `adarench/op5-pre-build-c-county-directories` | OPEN, CI green | ~6,500 |
| D | DB capacity report + script | [#180](https://github.com/nache327/STACK-Land-Acquisition/pull/180) | `adarench/op5-pre-build-d-db-capacity` | OPEN, checks SKIPPED | ~600 |

All four PRs target `main`, none merged. Master reviews at CP-Pre per the hard rules.

---

## Three findings that need Master decisions before launch

### Finding 1 — DB capacity hard-caps at 14 concurrent agents, not 25 (Pre-build D)

The Supabase Supavisor session-mode pool is hard-capped at **15 client connections** (Pre-build D agent observed the pooler emit `max clients are limited to pool_size: 15`). Stress test result:

| concurrency | latency p50 | p95 | p99 | error rate | throughput |
|---:|---:|---:|---:|---:|---:|
| 14 | 1,343 ms | 1,389 ms | 1,444 ms | 0.00% | 10.16 cycles/s |
| 25 | — | — | — | **3.09% (10/25 workers never connected)** | (no gain) |

Throughput at 14 == throughput at 25 in cycles/s (the DB itself has plenty of headroom — 60 max_connections, ~10 in use at sample). The pooler is the bottleneck, not the database.

**Decision needed at CP-Pre:** one of
- **Option D1 (safe):** Cap `op5_factory_orchestrator --max-parallel` at **14**. Phase 1 wall-clock projects to ~52.5 h instead of the planned 36-44 h — still inside the 72 h budget.
- **Option D2 (more parallelism):** Authorize a small Lane A follow-up PR to make `spatial_backfill.py` (and the factory's per-muni ingest path) connect directly to `aws-1-us-east-2.compute.amazonaws.com:5432` bypassing Supavisor. Lets us hit 25.

PR #180 ships the snapshot + check script + recommendation regardless. Recommendation in PR is Option D1.

### Finding 2 — PR #178 runner has stubbed extraction/ingest hooks (Pre-build A)

The agent shipped three scripts with the right shape, idempotency, exit codes, and a 19-test test suite. But the four heavy-work functions in `op5_per_muni_runner.py` are stubs:

| function | actual behavior in PR | comment in code |
|---|---|---|
| `default_extract_polygons_from_map` | Downloads PDF + classifies vector/raster — but returns `polygons=[]` even for vector | "factory orchestrator injects extractor" |
| `default_ingest_polygons` | Returns stub jurisdiction_id, no DB write | "stub — real ingest is injected" |
| `default_run_backfill` | No-op | "orchestrator injects the real DB call" |
| `default_audit_muni` | No-op | (same) |

The agent's stated rationale: building the real OpenCV color-segmentation + asyncpg PostGIS ingest + `backfill_parcel_zoning_from_districts` wiring "risks crossing into Slot-1 hot files." That's only partly true — color-segmentation is pure new code under `backend/scripts/`, asyncpg-direct ingest is the exact pattern `backend/scripts/pattern_bergen_garfield_adjudication.py` already establishes (and was authored within scope by the proof). The brief asked for an end-to-end runner; this is a shell.

**Decision needed at CP-Pre:** one of
- **Option A1 (accept scaffolding):** Merge as-is. Either the Phase-0-launch Master dispatch authors a second PR that fills in the hooks, or the orchestrator runtime injects them via `--extractor-cmd`. Factory cannot launch Phase 1 until those land.
- **Option A2 (revise PR #178):** Send back to the same agent (or a fresh one) with instructions to wire the real OpenCV + asyncpg paths inline, mirroring `pattern_bergen_garfield_adjudication.py`. Estimated ~6-10 additional agent-hours.

Recommendation: **A2.** Phase 1 throughput depends entirely on whether the runner actually runs.

### Finding 3 — PR #179 ships with zero `map_url` populated (Pre-build C)

All 140 munis across 4 counties have `map_url: null`. The agent populated `website_url` for 140/140 and `ordinance_url` for 134/140 — strong work on those two — but explicitly skipped the map-URL probing to stay within the 6-hour budget cap. Rationale: "Phase 0 discovery will handle null at runtime."

That's only true if `op5_discovery_classify.py` is set up to discover map URLs FROM website_url, not just probe a provided map_url. Inspection of PR #178: the classifier only probes the provided `map_url`; with `null` it short-circuits to `absent`. Net effect if both PRs land as-is: **0 of 140 new-county munis classify as anything but `absent`.**

**Decision needed at CP-Pre:** one of
- **Option C1 (extend discovery):** Add map-URL discovery logic to `op5_discovery_classify.py` (search the muni website for `/zoning`, `/planning-board`, `.pdf` links containing "zoning_map"). Small follow-up to PR #178 or a separate PR. ~2-4 agent-hours.
- **Option C2 (extend PR #179):** Send PR #179 back to fill in `map_url` via probing. The agent estimates this would be ~6-10 hours for all 140 munis.
- **Option C3 (operator queue):** Accept all 140 new-county munis as carve-out-to-operator. Defeats the factory throughput model — only the 70 Bergen munis would be factory-routable.

Recommendation: **C1.** Extending discovery serves both this dispatch AND any future county additions.

---

## Smoke test result — Westwood (Bergen)

Per the brief, ran the new `op5_per_muni_runner.py` end-to-end on Westwood Borough (Bergen, known-vector):

```
$ python backend/scripts/op5_per_muni_runner.py --county bergen --muni "Westwood Borough"
INFO httpx | HTTP Request: GET https://westwoodnj.gov/DocumentCenter/View/297/Zoning-Map-PDF "HTTP/1.1 200 OK"
INFO op5_per_muni_runner | default_extract_polygons_from_map: vector classification only; returning empty polygons (factory orchestrator injects extractor)
INFO op5_per_muni_runner | carve-out: bergen/Westwood Borough — empty color_to_zone (text-only legend)
{
  "status": "carve_out",
  "county": "bergen",
  "muni": "Westwood Borough",
  "muni_code": "0267",
  "carve_reason": "empty color_to_zone (text-only legend)",
  "source_class": "vector",  ← classification correct
  "color_to_zone_keys": [],  ← stub returned empty
  "vision_label_count": 0,
  "map_url": "https://westwoodnj.gov/DocumentCenter/View/297/Zoning-Map-PDF",
  "ordinance_url": "https://ecode360.com/13848225",
  "wall_clock_s": 9.39
}
```

**What works:**
- PDF discovery + download (1.5 MB, application/pdf, 200 OK).
- Vector classification via `pdfplumber.pages[0].lines` count (23,476 lines on the Westwood PDF — strong vector signal).
- Idempotency: re-running the runner finds the `carve_out.json` and exits no-op.
- Exit code 2 (carve-out path correctly distinct from operational / not-operational / transient-error).
- Artifact path layout: `/tmp/op5_factory/{county}/{muni_normalized}/carve_out.json`.

**What does NOT work:**
- The carve-out reason is misleading: it says "empty color_to_zone (text-only legend)" but the actual cause is the stubbed extractor returning empty. A real Westwood run with proper extraction would not carve out — Westwood is a vector-class muni.
- No coverage % or spot-check sample was produced (runner short-circuited at carve-out).
- No preview ingest happened.

So the smoke test validates the **orchestration shell** but cannot validate the **factory pipeline**. Per Finding 2 above, this is by design in PR #178 — a real smoke test requires the stubs filled in.

---

## Pre-factory DB snapshot (Finding 4 — informational)

PR #180's `pre_factory_db_snapshot.json` captures the current preview state:

| Metric | Value |
|---|---:|
| Total parcels | 10,285,645 |
| Total zoning_districts | 48,387 |
| Total zone_use_matrix rows | 5,103 |
| Jurisdictions | 87 |
| Active connections at snapshot | ~10 |
| Snapshot file | `/tmp/op5_factory/pre_factory_db_snapshot.json` |

Op-5 proof state (Fort Lee 99 polygons + 31 matrix rows, Garfield 215 polygons + 10 matrix rows, Hackensack 50 polygons) is included in the 48,387 / 5,103 totals (under Bergen's `4bf00234-...` jurisdiction). Pre-build D defensively excludes these from the stress-test target.

PostGIS index health: GIST indexes on `zoning_districts.geom` and `parcels.geom` are healthy. EXPLAIN ANALYZE on Monmouth (251 k parcels × 137 districts) shows index hits on both `ST_Within` (110 ms / 500 rows) and `ST_DWithin` (3,360 ms / 500 rows; slower due to `::geography` per-row distance compute — expected).

---

## ETA vs 24-hour pre-build budget

Pre-build started at H−24 (approximately). Parallel-agent execution:

| Pre-build | Agent wall clock | Spec budget |
|---|---:|---:|
| A | ~10 min | ~8 h |
| B | ~8 min | ~4 h |
| C | ~12 min | ~8 h |
| D | ~27 min | ~3 h |

**Total wall clock: ~30 minutes** (agents ran in parallel). Spec budgeted **~24 hours**. We are well inside budget.

The remaining work to close the pre-build properly is the **Master decisions on Findings 1-3 + any follow-up PRs they trigger**. Estimated:
- Finding 1 (Option D1): zero — accept the cap and proceed.
- Finding 2 (Option A2): ~6-10 agent-hours to fill in extraction/ingest hooks on PR #178.
- Finding 3 (Option C1): ~2-4 agent-hours to add map-URL discovery to `op5_discovery_classify.py`.

If Master accepts both A2 and C1, total remaining pre-build work is ~8-14 agent-hours, comfortably inside the 24 h spec budget.

---

## Ready-for-launch confidence

**MEDIUM-LOW.**

- Reasoning for "medium": the four PRs land the **shape** of the factory cleanly — orchestrator dispatch, per-muni shell with idempotency + carve-out exits, admin review UI, county directories with website + ordinance URLs, DB capacity confirmed at 14 agents. The architecture seams are right.
- Reasoning for "low": Phase 1 CANNOT execute until two gaps close — PR #178's stubs need real implementations (Finding 2), and PR #179's `map_url` field needs either filling in or discovery-side fallback (Finding 3). Launching Phase 0 right now would produce 140 new-county munis classified as `absent` (Bergen's 70 would still classify but extraction would still no-op for all of them).

If Master closes Findings 2 + 3 with the recommended A2 + C1 options, confidence moves to **HIGH** and Phase 0 can launch.

---

## What is NOT in this report

- A full Phase 0 + Phase 1 dispatch prompt — the brief says that's a separate Master dispatch after CP-Pre.
- A merge plan for the 4 PRs — Master decides merge order and any pre-merge revisions at CP-Pre.
- Operator-queue intake runbook for carve-outs — separate post-factory docs PR per `OP5_FACTORY_72H_PLAN.md` §"What ships AFTER the factory".

---

## STOP for CP-Pre review

Awaiting Master decision on Findings 1, 2, and 3. After Master signs off, Phase 0 dispatch can be authored and launched.
