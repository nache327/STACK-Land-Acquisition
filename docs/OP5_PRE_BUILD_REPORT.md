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

---

# CP-Pre v2 (post-Master-decisions on Findings 1/2/3)

Master accepted the three findings (1: cap at 14; 2: wire real heavy logic; 3: discovery fallback + backfill). Two parallel agents executed the amendments, plus orchestrator-led docs amendments and the real Westwood smoke test. Results below.

## A2 — PR #178 amended with real pipeline (Finding 2)

Two agent commits + three orchestrator-led runtime-bug fixes pushed to `adarench/op5-pre-build-a-orchestrator`:

| commit | author | purpose |
|---|---|---|
| `5b68219` | A2 agent | wire real extraction/ingest/backfill/audit defaults via new `backend/scripts/op5_lib/{extraction,ingestion_helpers}.py` |
| `0d76a50` | A2 agent | cap `--max-parallel` default at 14 (Finding 1) |
| `e3b7802` | C1 agent | `discover_map_url_from_website` fallback in classifier (Finding 3) |
| `7d0c4fb` | orchestrator | fix Census Geocoder onelineaddress doesn't resolve plain place names; switched to TIGERweb REST API |
| `117cfa6` | orchestrator | cap PDF render pixels (Westwood's 48"×66" page OOM-killed at 300 DPI = 285 Mpx ≈ 850 MB RGB) |
| `ed44213` | orchestrator | downsize PNG before vision call (Anthropic 10 MB image cap; A2's code sent 16.7 MB and got 400) |

Tests: A2 reports 37/37 pass locally (25 runner + 12 classifier). The three orchestrator runtime fixes do not have direct unit tests; they exercise on the smoke test instead.

## C1 — PR #178 + PR #179 amended with map_url discovery (Finding 3)

| commit | branch | purpose |
|---|---|---|
| `e3b7802` | `op5-pre-build-a-orchestrator` | added `discover_map_url_from_website` + 16 tests |
| `f5483b1` | `op5-pre-build-c-county-directories` | ran discovery + backfilled 4 directories |
| `4341d2b` | `op5-factory-pre-build` | appended "Pre-build C contract precondition" section to OP5_FACTORY_72H_PLAN.md |

Backfill counts (sequential probe with realistic Chrome UA):

| County | discovered / total | rate |
|---|---|---|
| Essex | 2 / 22 | 9.1% |
| Middlesex NJ | 6 / 25 | 24.0% |
| Monmouth | 4 / 53 | 7.5% |
| Burlington | 6 / 40 | 15.0% |
| **Total** | **18 / 140** | **12.9%** |

**Materially below the 50% target Master set.** Root causes per C1 agent: ~24/53 Monmouth homepages returned HTTP 403 (CivicPlus/Cloudflare bot mitigation, even with a Chrome UA), NJ muni sites bury zoning maps 3+ levels behind JS mega-menus (bs4 can't traverse), scoring intentionally conservative to avoid false positives like "Residential Zoning Application Checklist.pdf". Further increases would require Playwright (disallowed) or per-site selectors (out of scope).

Spot-inspection confirms the 18 discovered URLs are real zoning maps. Munis without a discovered map_url remain `null` and will route to Phase 0 `absent` → operator queue.

## Finding 1 — orchestrator docs amend

`fb9ed7e` on `adarench/op5-factory-pre-build` updates `docs/OP5_FACTORY_72H_PLAN.md` Phase 1 from "20-agent swarm" to "14-agent swarm" with recomputed Phase 1 budget (51-54 h, still inside 72 h gate).

## Real Westwood smoke test result — **CARVE-OUT, not operational**

Per Master's brief, ran the new `op5_per_muni_runner.py` against Westwood end-to-end with the now-real extraction path. Result:

```json
{
  "status": "carve_out",
  "county": "bergen",
  "muni": "Westwood Borough",
  "carve_reason": "empty color_to_zone (text-only legend)",
  "source_class": "vector",
  "vision_label_count": 0,
  "wall_clock_s": 538.78
}
```

Pipeline stages executed cleanly:
1. PDF fetch via httpx (1.5 MB, 200 OK)
2. Vector classification via pdfplumber lines > 50 (23,476 lines) ✅
3. Place bbox via TIGERweb (Westwood borough centroid + envelope) ✅
4. PDF render at scaled DPI 158 (capped from 300 to stay under 80 Mpx) ✅
5. OpenCV color-segmentation ✅
6. **Anthropic vision call returned 200 OK with 0 high-confidence (≥0.75) inline zone labels** → carve-out path fires
7. Idempotent artifact written: `/tmp/op5_factory/bergen/westwood/carve_out.json`

**What we learned:**
- The runner's end-to-end shape, error handling, idempotency, exit codes, and carve-out branch all work in production-shaped conditions.
- Westwood happens to be **text-only-legend class** for the new pipeline's vision-LLM prompt: vision sees the rendered map but cannot extract inline zone-code labels at ≥0.75 confidence. Either the map genuinely lacks inline labels (printed legend off-page) OR the prompt + 158 DPI is too strict for Westwood's label density. Distinguishing requires looking at the rendered PNG, which is a manual operator step.
- **The green-path (extract → ingest → backfill → audit at coverage ≥70%) has NOT been validated end-to-end yet.** The smoke test exercised every stage up to the vision label step; ingest / backfill / audit code paths were not run because the muni carved out before reaching them.
- Westwood may have been a poor choice for the smoke test target. The Master brief noted Westwood is on the "Paramus vendor tenant per docs/archive/BERGEN_INGEST_RUNBOOK.md (already-validated source)" — but that validation was via the vendor tenant, NOT via the Op-5 PDF pipeline. They are different code paths.

## New Finding 4 — `op5_town` tag collision risk

`normalize_muni_token('Garfield city')` → `'garfield'`. This **collides with the proof state's `op5_town='garfield'` tag** on Bergen preview. A2's ingest documents "never touching Fort Lee/Garfield/Hackensack proof state" but the safeguard is by tag, not by ingest-stage label, so a factory run on Garfield/Fort Lee/Hackensack would DELETE the proof state during the idempotent "remove prior rows under same op5_town tag" step.

Detected during this report's smoke-test planning. We did NOT run the new runner against Garfield (preserving the proof state). Master decision needed:
- **Option F1**: change A2's tag scheme to `op5_factory_{normalized_muni}` so factory runs never collide with proof tags.
- **Option F2**: hardcode a protect-list in the runner that refuses to ingest into op5_town ∈ {fort_lee, garfield, hackensack} (or refuses to delete prior rows that don't carry the `op5_factory=true` marker).
- **Option F3**: accept the risk and physically isolate the proof state in a separate raw_attributes namespace before factory launch.

Recommend **F2**: minimal code, clearest intent, future-proof.

## Updated ready-for-launch confidence

**MEDIUM-LOW** (unchanged from CP-Pre v1; reasons differ).

What's improved since CP-Pre v1:
- A2's heavy logic is wired (Finding 2 addressed in code).
- Discovery fallback exists (Finding 3 partially addressed).
- The pipeline runs end-to-end without crashing (3 runtime bugs fixed during smoke test).
- The carve-out branch is validated end-to-end on real data.

What's still blocking HIGH:
1. **Green-path not validated end-to-end on any muni.** Westwood carved out at vision-label step. We have not seen a muni complete the ingest → backfill → audit → coverage ≥70% trip via the new runner.
2. **map_url discovery rate is 12.9%, not 50%.** Phase 0 will mark ~87% of new-county munis as `absent` → operator queue. Factory throughput model assumed ≥80% vector-class; we're closer to 13% × 4 counties + 100% Bergen.
3. **Finding 4 op5_town tag collision** is a live foot-gun against the proof state.
4. **No measured per-muni wall clock for a green-path muni.** Westwood took 9 min to carve out; a green-path run would be longer (ingest + backfill + audit) but we don't know how much. The 3.5 h per-muni budget in OP5_FACTORY_72H_PLAN.md was estimated from the proof's hand-coded runs, not measured on the new runner.

## Master decisions needed before Phase 0 launch

1. **Smoke test follow-up**: which Bergen muni should we re-attempt the smoke test against? Recommend selecting one that is NOT in the proof set and has known inline zone labels — `Ramsey Borough`, `Ridgewood Village`, or `Paramus Borough` are likely candidates. If we cannot find a non-proof Bergen muni that reaches operational, the factory is non-viable as currently scoped.
2. **Finding 4**: Option F2 (recommended) or alternative.
3. **Acceptance or revision of the 12.9% map_url discovery rate.** Either accept that ~87% of non-Bergen factory work routes to the operator queue, or invest in a richer discovery (Playwright authorization, per-vendor scraper, manual operator queue for directory build, etc).
4. **Optional**: investigate whether the vision-label prompt needs revision. The A2 prompt requires the model to self-filter at ≥0.75 confidence. Looser thresholds + post-hoc filtering OR multi-pass prompts (legend extraction → inline label match) may catch more munis.

## STOP for CP-Pre re-review

All three Master-authorized findings have been executed. A new Finding 4 surfaced. The smoke test ran but Westwood carved out — green-path is unvalidated. Confidence remains MEDIUM-LOW pending decisions on the four items above.

---

# CP-Pre v3 (post-Master-decisions on Findings 1/4/5 + Decision 3)

Master approved Findings 1/4/5 + Decision 3 + the two-smoke-test gate (Westwood ArcGIS path + Ridgewood PDF path). Hard constraint: "Two more pre-build iterations maximum. If CP-Pre v3 review shows we still don't have green-path success on both an ArcGIS muni AND a PDF muni in Bergen, Master will abandon the 25-agent factory thesis."

This report documents iteration 2 (F2 + F5 amend + scope amend + two smoke tests). **The factory thesis is in trouble.**

## What landed (commits in iteration 2)

| commit | branch | purpose |
|---|---|---|
| `8e5b369` | PR #178 | **F2** — `ProofStateCollisionError` + `assert_no_proof_state_collision` helper. DELETE gains `op5_factory='true'` filter. 28/28 tests pass. **Integration test against live preview Garfield (215 proof rows): DELETE returned 0 rows, raised collision error, all 215 proof rows untouched.** |
| `ada866c` | PR #178 | **F5** — `arcgis_lookup.py` + classifier + runner ArcGIS-first branch. 15/15 new tests + 59/59 total op5 tests pass. Verified lookups: Westwood→`Westwood_Zoning_2019` candidate; Carlstadt→NJSEA `MUN_CODE LIKE '0205%'`; Paramus→verified; Closter→None (excluded); Hackensack→None. |
| `2cab048` | PR #178 | **carve-out fix** — runner skipped PDF-only carve-out conditions (`empty color_to_zone`, `vision_label_count==0`) for ArcGIS/NJSEA classes. Without this, Westwood always carved out on the empty-color-map check even though the ArcGIS branch correctly identified it. |
| `07692ed` | factory-pre-build | docs: Phase 1A (Bergen 70) / Phase 1B (18 non-Bergen with discovered map_url) / operator queue (~134-142) split per Decision 3 + ArcGIS routing notes. Recomputed Phase 1 wall-clock: ~24-36 h. |

## Smoke test 1 — Westwood (ArcGIS path) — **FAILED green-path**

```
arcgis-first route for Westwood Borough -> arcgis_candidate (Westwood_Zoning_2019)
Total features to download: 3686
Downloaded 3686 total features
Mapping 3686 zoning GDF rows → ZoningDistrict dicts …
WARNING: Skipped 3686 zoning rows (null geometry or missing code)
ERROR: No usable zoning rows after mapping — aborting
arcgis ingest Westwood Borough: inserted=0 tagged=0
backfill skipping Bergen — 281000/281646 parcels (99.77%) already have zoning_code
{
  "status": "complete",
  "operational": true,                      ← spurious; jurisdiction-wide
  "polygons_written": 0,                    ← TRUE NEW POLYGONS = 0
  "zone_codes": [],
  "matrix_rows": 0,
  "parcel_zoning_code_coverage_pct": 99.89, ← Bergen-wide, NOT Westwood
  "matrix_match_pct_of_zoned": 84.5,        ← Bergen-wide
  "spot_check_pass_pct": 0.0,               ← Westwood-scoped, 0/10 PASS
  "binding_method_distribution": {"unknown": 3593},
  "wall_clock_s": 387.88
}
```

What worked end-to-end:
- ArcGIS lookup → `arcgis_candidate` classification ✅
- Probe `returnCountOnly=true` → 3686 features ✅
- ArcGIS download (4 pages, pagination) → 3686 features in GeoDataFrame ✅
- `default_audit_muni` returned a structured result (spot-check, binding distribution) ✅
- F2 protect-list did NOT fire (Westwood doesn't have prior proof rows) ✅

What broke:
- **`app.services.zoning_ingestion.ingest_zoning_districts` rejected ALL 3686 features**: `Skipped 3686 zoning rows (null geometry or missing code)`. F5's adapter didn't normalize Westwood's ArcGIS field names (`ZONE` or `ZONE_CODE` or similar) to the platform's expected `zone_code` column. **0 polygons inserted to preview.**
- **Audit-coverage % is jurisdiction-wide, not muni-scoped.** A2's `default_audit_muni` claimed to scope by `parcels.city = ?` but the 99.89% number is Bergen-wide. Either A2 wired the wrong audit call or `audit_zoning_coverage.py --json` returns whole-jurisdiction even with a city filter. This makes per-muni operational status impossible to compute from the runner's audit result.
- **Spot-check 0/10 (correctly muni-scoped)** confirms Westwood ends up with no `op5_factory='true'` districts and so no parcels get bound. The `binding_method_distribution: {"unknown": 3593}` shows all 3593 Westwood parcels carry pre-existing zoning_code from a non-Op5 source with no `zone_binding_method` set.

**Green-path FAILED.** Operational gate (`coverage ≥70%` + `spot-check ≥9/10`) not met on Westwood. The "operational": true in the output is a bug in the operational-gate computation that relies on the bogus jurisdiction-wide coverage %.

## Smoke test 2 — Ridgewood Village (PDF path) — **BLOCKED, did not complete**

```
INFO httpx | HTTP Request: GET https://mods.ridgewoodnj.net/.../Zone_Map_2022_27X27.pdf "HTTP/1.1 200 OK"
INFO httpx | HTTP Request: GET tigerweb.geo.census.gov/.../Places_CouSub_ConCity_SubMCD/MapServer/4/query "HTTP/1.1 200 OK"
WARNING op5_lib.extraction | TIGERweb bbox lookup failed for Ridgewood, NJ: Expecting value: line 1 column 1 (char 0)
WARNING op5_lib.extraction | no Census place bbox for Ridgewood, NJ — carving out
```

Manual probe of the same URL:
```
$ curl -s "https://tigerweb.geo.census.gov/.../MapServer/4/query?where=BASENAME%3D%27Ridgewood%27..."
<html><head><title>Request Rejected</title></head><body>The requested URL was rejected. Please consult with your administrator.</body></html>
```

The TIGER WAF blocked our IP after the session's repeated programmatic requests during fixes/smoke tests. The Westwood TIGER lookup worked at the start of the session; subsequent requests get rejected. Switching to a Chrome User-Agent (tested) did NOT unblock — appears to be IP/rate-based.

A2's `_census_place_bbox` has no retry / backoff / IP-rotation; on WAF block it returns `None` and the runner falls through to the carve-out path. **Ridgewood smoke did not exercise the PDF green-path at all** — it carved out at the bbox-lookup step before render / color-segmentation / vision / ingest.

## Two new bugs surfaced (NOT triaged for fix per Master's iteration cap)

| # | Bug | Severity | Fix shape |
|---|---|---|---|
| 6 | `_ingest_arcgis_source` doesn't normalize FeatureServer field names to the platform's `zone_code` column → 0 polygons inserted | **Blocker** (no ArcGIS muni can land via the factory in current state) | F5 adapter needs a field-mapping layer: introspect the FeatureServer's `fields` endpoint, map common variants (`ZONE`, `ZONE_CODE`, `Zone_Code`, `ZoneCode`) onto `zone_code`, OR derive from `extra_raw_attributes`. ~1-2 agent-hours. |
| 7 | `default_audit_muni` returns jurisdiction-wide coverage % instead of muni-scoped | **High** (operational gate computation is wrong; no per-muni accountability) | A2's audit helper needs to filter `audit_zoning_coverage.py`'s output by `city = <muni>` post-hoc OR run a custom muni-scoped query. ~1-2 agent-hours. |

Plus a third infrastructure note:
- TIGER WAF block is real and recurring. A2's `_census_place_bbox` needs retry+UA-rotation OR Bergen needs a pre-loaded place-bbox cache file (Bergen has 70 munis; cache them once at build time). The proof's pipeline avoided this by using the GENZ2024 shapefile (downloaded once, queried locally), not a per-request HTTP API.

## Are we at the abandonment trigger?

**Per Master's explicit constraint:**
> "If CP-Pre v3 review shows we still don't have green-path success on both an ArcGIS muni AND a PDF muni in Bergen, Master will abandon the 25-agent factory thesis."

Current state:
- ArcGIS muni green-path: **0 polygons inserted** due to bug 6 → **FAILED**
- PDF muni green-path: **never executed** due to TIGER WAF block → **NOT VALIDATED**

Per the strict reading of the hard constraint, **Master should abandon the factory thesis and shift to operator-assisted Op-5 at scale**.

The orchestrator's honest assessment: the factory implementation has shown a recurring pattern across iterations — each fix surfaces another infrastructure-shaped bug (Census Geocoder broken → swap to TIGER → TIGER WAF blocks; PDF OOM → cap → vision image cap → resize; runner stubs → fill in → field mapper drops; carve-out condition → fix → audit scope wrong). The proof's pipeline avoided many of these by running each muni manually with hand-tuned scripts. **The 25-agent factory thesis assumed the proof's per-muni pipeline could be made unattended at scale; the cumulative evidence does not support that assumption.**

## Counter-argument for not abandoning yet

Two of the three remaining infrastructure bugs (bug 6 ArcGIS field mapping, bug 7 audit scope) are small and well-understood (combined ~3-4 agent-hours). If Master is willing to accept ONE more iteration despite the explicit cap, those fixes plus a TIGER bbox cache could plausibly unlock both green-paths in a 4-6 hour iteration. The protective infrastructure (F2 collision guard, F5 ArcGIS routing, op5 directory data, review UI, DB capacity report) is all already shipped.

The orchestrator recommends Master make this call explicitly rather than the orchestrator silently iterating past the cap. Both outcomes are defensible:

- **GO ABANDON** (strict reading): factory thesis non-viable in 72 h budget. Shift NJ Tier-S work to operator-assisted Op-5 (3-4 weeks of operator labor for 88 munis at proven 55-80 min/muni rates).
- **GO ONE MORE ITERATION** (relaxed cap): close bugs 6+7+TIGER cache, re-smoke Westwood + Ridgewood. Hard stop at iteration 3 outcome regardless.

## Updated ready-for-launch confidence

**LOW.** Down from MEDIUM-LOW (CP-Pre v2).

Reasons:
- F2 protect-list is working and verified — proof state is safe.
- F5 ArcGIS routing logic is correct but the ingest adapter doesn't deliver any data.
- Audit scope is wrong — the operational-gate computation cannot be trusted.
- TIGER dependency is fragile under repeated probing.
- Iteration cap reached without green-path on either smoke target.

## Artifacts

- `/tmp/op5_smoke_westwood_v6.log` — Westwood ArcGIS run (387s, 0 polygons inserted)
- `/tmp/op5_smoke_ridgewood_v1.log` — Ridgewood PDF run (carved out at TIGER step)
- Live preview Garfield rows: 215 (verified untouched after F2 integration test)
- Latest PR #178 commits: `8e5b369` (F2), `ada866c` (F5), `2cab048` (carve-out fix)
- Latest factory-pre-build commits: `07692ed` (Phase 1A/1B split), this report.

## STOP for CP-Pre v3 Master decision

Awaiting Master decision: **abandon factory thesis** (strict reading of the iteration cap), or **authorize one more bounded iteration** to close bugs 6 + 7 + TIGER cache and re-smoke. Both arguments above.
