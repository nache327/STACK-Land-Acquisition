# Project Status — Last updated 2026-06-01

**TL;DR.** Active work is the **LIR `has_structure` backfill** on branch `feat/county-city-drilldown` (7 commits ahead of `origin/main`, **not yet merged**). Its goal: unblock `vacancy_unknown` parcels in Salt Lake County so Hot Deals / Worth a Look stop returning zero matches in SLCo. The last 6 commits are iteratively hardening the AGRC LIR fetcher (WAF user-agent, dropped bbox, POSTed chunks, 429 rate-limit handling) — converging but **not yet confirmed working end-to-end**. `origin/main` is at `c9a306a` (PR #156, ops day-2 reconcile). Production runs on Railway (service renamed **ParcelLogic**) + Supabase pooler (session mode, port 5432) + Vercel frontend.

> ⚠️ **This file was reconstructed from git history + auto-memory on 2026-06-01.** The prior snapshot (`9c59baa`, 2026-05-11) was ~338 commits stale. Items marked _(verify)_ below were inferred from commits/memory and should be confirmed against the live Railway `/health` and the DB before relying on them.

---

## Audit snapshot

| Item | Value |
|---|---|
| Current working branch | `feat/county-city-drilldown` |
| Working-branch HEAD | `503181e` fix(lir): respect AGRC rate limit |
| `origin/main` HEAD | `c9a306a` Merge PR #156 (docs day-2 reconcile), 2026-06-01 |
| Branch vs main | **+7 ahead, 0 behind** — the LIR backfill series is unmerged |
| Commits since prior STATUS (`9c59baa`) | ~338 |
| Deployed Railway SHA | _(verify via `/health` → `pipeline_version`)_ — should track `origin/main` `c9a306a` |
| Railway service | **ParcelLogic** (renamed 2026-05-13; was `capable-serenity`) |
| Backend URL | `https://capable-serenity-production-0d1a.up.railway.app` _(verify — URL may have changed with rename)_ |
| Frontend URL | https://zoning-finder.vercel.app |
| Production DB | **Supabase** pooler `aws-1-us-east-2.pooler.supabase.com:5432` (session mode). Railway's own Postgres tile is a **stale, unused** instance — ignore it. |
| Redis | Railway internal `redis.railway.internal:6379` |

---

## In-flight work — LIR `has_structure` backfill (this branch, unmerged)

**Branch:** `feat/county-city-drilldown` · **Files:** `backend/app/services/lir_has_structure_backfill.py` (new), endpoint in `backend/app/api/jurisdictions.py`, `backend/tests/test_lir_has_structure_mapping.py`.

**Problem it solves.** County-wide UGRC parcel ingests (SLCo et al.) leave `parcels.has_structure` NULL on most rows because the non-LIR parcel layer is sparse on `LAND_USE`/`PROP_TYPE`. Every NULL row fails the dashboard's `vacancy_unknown` viability check → Hot Deals / Worth a Look surface **zero** matches in SLCo despite ~400k parcels with real demographics.

**Approach.** AGRC publishes a per-county LIR layer with a `PROP_CLASS` string. The backfill mines `PROP_CLASS` for a vacancy signal (Vacant/Undeveloped → `False`; Residential/Commercial/Industrial/Mixed → `True`; Tax-Exempt/Greenbelt/unknown → leave NULL). Idempotent — only fills `has_structure IS NULL`.

**Commit progression (368af52 → 503181e), all AGRC-fetcher hardening:**
1. `368af52` feat — initial backfill service + endpoint + tests
2. `1cf58ed` focused `outFields` fetch
3. `1a5e792` surface fetcher diagnostics + drop `page_size`
4. `2761fa4` browser `User-Agent` + `Accept` header to clear AGRC WAF
5. `11b005b` drop bbox filter (layer is already county-scoped)
6. `5a82e2d` POST feature-chunk queries to dodge AGRC URL-length limit
7. `503181e` respect AGRC rate limit (429 retry + per-call throttle, ~600 calls/min envelope)

**Next on this branch:** confirm a full SLCo backfill run completes against AGRC without 429/WAF/timeout, verify Hot Deals returns non-zero in SLCo, then merge to `main`.

---

## Major themes landed since 2026-05-11 (on `main`)

Reconstructed from git log — these are the work clusters, not an exhaustive list.

- **Salt Lake County county-model** — county = one jurisdiction + city filter. Zoning backfill from sibling jurisdictions (`1f5dc0f`, `9e28b76`), sibling discovery driven off `parcels.city` not the unreliable `county` field (`7b22c4d`), zone-matrix `municipality` text + partial-index fix (`9f0008e`), cross-namespace spatial-join zoning fallback (`8e200ca`). See memory: `project_slco_county_model`, `project_sibling_discovery`, `project_ugrc_zoning_attribute`.
- **Ring-metrics server-side precompute** — Python port of the frontend `computeRingMetrics` + parity tests, Parts A+B+C backend, ACS 404-skip, dashboard gating then revert once server cache warm (`abd8cb3`, `c2c182d`, `e480229`, `9c885b1`).
- **Overlay performance** — subdivide + index overlay polygons for fast spatial join (`69dcb65`); index `parcels(jurisdiction_id, city)` + ANALYZE after big UPDATEs (`00e65ae`).
- **Duplicate-ingest prevention + Utah County config** (`28b3b96`).
- **Daily digest** — runs via `queued_job_watchdog.py` (Railway ignored the cron `startCommand`); send hour = `DIGEST_SEND_HOUR_UTC` (default 12). Many `fix/digest-*` branches: cooldown poison, cron-hour gate, skip recently-alerted, factor-breakdown truncation. See memory: `project_digest_runs_via_watchdog`.
- **Listings layer** — smart matching, manual reassign, rematch-all, map pin toggle, surface polish.
- **Buybox / Hot Deals** — server-side buybox + ring server cache, Hot Deals v2 spec/preset, saved filters.
- **Zoning matrix sprints** — Norfolk MA, Middlesex MA, Howard MD, Loudoun VA, Allentown PA batches.
- **NJ statewide** — MODIV backfill, NJ county registry, NJDCA Municipal Zoning Directory now drives per-parcel matrix (memory: `project_nj_njdca_unlock_2026-05-29`).

---

## How work + state is tracked now

The project moved to a **multi-lane coordination model**. State lives in three places — check all three at session start:

1. **`STATUS.md`** (this file) — narrative project state + change summary. Refresh when it goes stale.
2. **`coordination/`** — machine-readable orchestration state (per `coordination/README.md`):
   - `lane_state.json` — per-lane status/task/branch/blocker/KPI delta _(last updated 2026-05-27 — also stale; verify)_
   - `blockers.json` — active + recently-cleared blockers
   - `dispatch_queue.json` — merge/retry sequencing + dependency order
3. **`docs/PHASE2_PROGRESS.md`** — phase progress + audit truthfulness (the lane-state `progress_doc` source).

Recent `origin/main` history is dominated by `docs(ops):` reconcile commits (PRs #143–#156) that close lane days and authorize the next — that cadence is the source of truth for what's been applied/merged.

---

## KPI snapshot _(from `coordination/lane_state.json`, 2026-05-26 — verify)_

| Metric | Value |
|---|---:|
| Honest operational jurisdictions | 45 |
| Trustworthy parcel verdicts | 3,292,352 |
| Avg unclear share (partials) | 18.3% |
| Failed jobs (14d) | 42 |
| Fake operationals | 0 |

---

## Known issues / open threads

1. **SLCo Hot Deals returns zero** — the reason the LIR backfill exists (above). Not resolved until that branch merges and a full SLCo run completes.
2. **Utah County ingest stalls** — mapping phase chews 24+ min; needs a `make_valid` short-circuit on already-valid geoms before retry. (memory: `project_utah_county_ingest_stuck`)
3. **UGRC county pulls leave `zoning_code` NULL** — run `_backfill-zoning-from-siblings` after every county ingest. (memory: `project_ugrc_zoning_attribute`)
4. **`zone_matrix` quirks** — `uq_zone_matrix` is a partial INDEX not a constraint; `municipality` is text; `pipeline.py:2087` has a latent `ON CONFLICT` bug. (memory: `project_zone_matrix_quirks`)
5. **Carried over from old STATUS _(verify still apply)_:** `city='unknown'` bulk-ingest leak; AADT timeouts on large jurisdictions; `POST /api/jobs/{id}/cancel` returns 500 despite succeeding.

---

## Deferred / strategy calls

- **Acres floor vs urban infill** — keep Hot Deals at a 1.5-ac floor (suburban thesis) vs lowering it for urban infill. Revisit when a blocked urban deal lands. (memory: `project_acres_floor_urban_infill`)
- **County breadth > perf polish** — when the pipeline is healthy, prefer pulling another county over polishing ring-precompute / geocoder fallback. (memory: `feedback_county_breadth_priority`)

---

## Quick reference

### Critical files
- `backend/app/services/pipeline.py` — ingest orchestration
- `backend/app/services/lir_has_structure_backfill.py` — **new**, vacancy backfill from AGRC LIR
- `backend/app/services/zoning_system.py` — `bulk_ingest_zoning_for_jurisdiction` (raw asyncpg)
- `backend/app/services/spatial_backfill.py` — centroid-based parcel→zone backfill (raw asyncpg, session-mode 5432, no timeout — memory: `feedback_spatial_backfill`)
- `backend/app/services/overlays.py` — flood / wetland / AADT
- `backend/app/api/debug.py` — operational endpoints
- `backend/app/api/jurisdictions.py` — admin + LIR backfill endpoint
- `frontend/app/dashboard/[jobId]/page.tsx` — main user-facing page

### URLs / endpoints
- Frontend: https://zoning-finder.vercel.app
- Health / version: `GET /health`, `GET /api/debug/env`
- Admin jobs: `/api/admin/jobs?stale_only=true&limit=50`, `/api/debug/jobs?limit=20`
- Stuck-job repair: `POST /api/debug/fix-zoning/{jurisdiction_id}`, `/fix-zoning-all`

### Common SQL
```sql
-- Latest jobs
SELECT id, jurisdiction_input, status, finished_at, LEFT(error_message,80)
FROM jobs ORDER BY created_at DESC LIMIT 10;

-- Stuck / in-flight
SELECT id, jurisdiction_input, status,
       ROUND(EXTRACT(EPOCH FROM (now()-locked_at))/60) AS min_locked
FROM jobs WHERE finished_at IS NULL ORDER BY locked_at NULLS LAST;

-- SLCo vacancy coverage (the LIR-backfill target)
SELECT has_structure, COUNT(*) FROM parcels
WHERE jurisdiction_id = '<slco_jurisdiction_id>'
GROUP BY has_structure;
```
