# Project Status — Last updated 2026-05-11 (session close)

**TL;DR.** Production is healthy after a two-day worker outage was root-caused and fixed. Backend on Railway (`pipeline_version=9c59baa6317c`, deployment `52f7c5bb`, port 5432 session-mode pooler). Frontend on Vercel at `https://zoning-finder.vercel.app`. Worker (dramatiq) is alive and processing jobs end-to-end. Philadelphia overlays — the standing P1 from the prior session — are populated (546,889 zoning_overlays). NJ priority cities (Hoboken / Elizabeth / New Brunswick) all reach `ready`. NYC ingestion still fails on a connection-resilience bug whose fix lives on an unmerged branch.

---

## Audit snapshot

| Item | Value |
|---|---|
| Local `main` SHA | `9c59baa6317c8977f459002e453e6f4239314540` |
| `origin/main` SHA | `9c59baa6317c8977f459002e453e6f4239314540` |
| Deployed Railway SHA | `9c59baa6317c` (matches main) |
| Railway deployment id | `52f7c5bb-2b39-4a35-a054-bd488f184109` SUCCESS @ 2026-05-11 11:58 MDT |
| Railway service | `capable-serenity` (project `outstanding-rebirth`, env `production`) |
| Backend URL | https://capable-serenity-production-0d1a.up.railway.app |
| Frontend URL | https://zoning-finder.vercel.app |
| DATABASE_URL mode | Supabase pooler `aws-1-us-east-2.pooler.supabase.com:5432` (**session mode**) |
| Redis | Railway internal `redis.railway.internal:6379` |
| Alembic head on disk | `0017_parcel_flood_wetland_nullable.py` |
| Alembic revision applied to prod DB | `0017` (matches disk) |
| Working tree | Clean except untracked `STATUS.md` and `ORPHAN_BRANCH_AUDIT.md` (this commit) |

---

## Deployed services

| Service | URL / SHA | Status |
|---|---|---|
| API + worker (Railway, single service `capable-serenity`) | https://capable-serenity-production-0d1a.up.railway.app | healthy |
| `pipeline_version` | `9c59baa6317c` | live |
| Frontend (Vercel) | https://zoning-finder.vercel.app | HTTP 200 — auto-deploy disabled |
| Postgres | Supabase prod pooler `aws-1-us-east-2.pooler.supabase.com:5432` | session-mode pooler |
| Redis | Railway internal | ok |

Health-check + version are exposed at `GET /health` and `GET /api/debug/env`.

---

## Operational data (this session)

### Jurisdictions verified or newly indexed today

| Jurisdiction | Job id | Parcels | Notes |
|---|---|---:|---|
| Philadelphia, PA | `6ac464a7-17fc-4b32-bbbd-c6e882e04add` (post_ingest) | 547,299 | **546,889 zoning_overlays inserted** (raw asyncpg path, commit 9c59baa). P1 from prior STATUS resolved. |
| Hoboken, NJ | `7998dfae-e3a0-4ea2-9ede-a4de60e987eb` (ready) | 143,305 | Full pipeline (parcels + zoning + AADT + overlays) ran end-to-end via pipeline.py |
| Elizabeth, NJ | `85cffbc6-461e-4c8e-9df5-ca3b23e031d9` (ready) | 147,627 | Same |
| New Brunswick, NJ | `35265425-7a35-4fcc-9b9b-1ca3be4e6900` (ready) | 245,616 | Mapped to Middlesex County, NJ (`9c039328-…`). 237,890 AADT parcels. |
| New York, NY / NYC | `f0b77b56-…` (FAILED) | 0 ingested | Downloaded 856,670 MapPLUTO features, then `ConnectionDoesNotExistError` while updating job progress. See known issues. |

Exact `zoning_overlays` counts for the NJ cities were not captured in this session's log buffer (rolled off), but each of the three reaches the pipeline's `complete_feasibility` stage which only runs after `bulk_ingest_zoning_for_jurisdiction` succeeds.

---

## Critical deployment drift incident — multi-day worker stall

This is the single most important thing to read before the next session.

### What happened

From `2026-05-09 ~06:00 UTC` to `2026-05-11 ~16:24 UTC` (≈ 58 hours), **every job submitted to production sat in the `queued` state and never advanced.** Five jobs accumulated (Hoboken / Elizabeth / New Brunswick / NYC × 2) before the cause was diagnosed.

### Root cause

Migration `0017_parcel_flood_wetland_nullable.py` (added in commit `e184052` on local branch `claude/agitated-khayyam-58c0d9`) was applied to the production Supabase DB — most likely via someone running `railway up` or `alembic upgrade head` from a local checkout of that branch — but the migration file was **never merged into `origin/main`**.

After that, every subsequent Railway redeploy from main built the image from a source tree that lacked the `0017` file. The container start command is:

```sh
alembic upgrade head && dramatiq app.worker --processes 2 --threads 2 & uvicorn app.main:app ...
```

On boot, `alembic upgrade head` failed with:

```
ERROR [alembic.util.messaging] Can't locate revision identified by '0017'
FAILED: Can't locate revision identified by '0017'
```

The `&&` short-circuited, so `dramatiq app.worker` never executed. The shell then proceeded past the `&` to launch `uvicorn`, which booted normally. The Railway container looked completely healthy:

- `/health` returned `200 OK`
- API responded to every HTTP request
- `pipeline_version` was reported correctly

…because the failure mode was a missing background process, not a crashed foreground one.

### Fix

`05d4102 fix(alembic): restore 0017 migration so alembic upgrade head succeeds` — the migration file was copied verbatim from `e184052` onto main. Production schema already had the change applied, so `alembic upgrade head` recognised `0017` and moved past it. dramatiq launched on the next redeploy. The 5 queued jobs were picked up within seconds of the fresh worker booting.

### Defensive follow-ups (not yet implemented)

- The Dockerfile CMD should be restructured so a dramatiq exit is fatal to the container (e.g. drop `&` and run uvicorn+dramatiq under `honcho`/`supervisord`/`tini` so any process death tears down the container). Today a single backgrounded process can die and Railway will never notice.
- A scheduled `audit_zoning_coverage.py` or simpler "jobs queued >5 min" check would have alerted within the hour rather than two days.
- Procedural: nothing should reach production except via merged commits on `origin/main`. The `railway up`-from-local pattern that applied `0017` to prod without committing it is the actual cultural root cause.

---

## Remaining known issues

### 1. NYC ingestion fails after MapPLUTO download

Job `f0b77b56` failed with:

```
asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation
[SQL: UPDATE jobs SET progress=$1::JSONB, updated_at=now() WHERE jobs.id = $2::UUID]
```

The MapPLUTO download takes ~6.4 min for 856,670 features; the Supabase pgbouncer is dropping the SQLAlchemy session's underlying server connection during that window. The fix exists on orphan branch `claude/agitated-khayyam-58c0d9` in commit `e184052` — `_set_status` was extended with a raw-asyncpg fallback path for exactly this case (see commit message: *"_set_status now falls back to a raw asyncpg UPDATE when the SQLAlchemy session goes stale during ingest"*). See `ORPHAN_BRANCH_AUDIT.md` for the recommended cherry-pick.

### 2. `POST /api/jobs/{job_id}/cancel` returns HTTP 500

The cancel **executes correctly** — `status=cancelled`, `locked_by=NULL` — but FastAPI then fails to serialize the response with `fastapi.exceptions.ResponseValidationError: <exception str() failed>`. Callers see 500 but should treat it as success and verify state with `GET /api/debug/jobs`. Likely a pydantic v2 vs SQLAlchemy `JobRead` shape mismatch in the cancelled path. Pre-existing bug, not introduced this session.

### 3. Orphan branch contains prod-relevant code outside main

See `ORPHAN_BRANCH_AUDIT.md` for the full classification. Highlights:

- Phase 2/3 county handlers (Westchester / Nassau / Fairfield / Fairfax / Loudoun / Mont. PA / Mont. MD / Howard MD) — **only on orphan**
- `_send_with_retry` exponential backoff in `arcgis_query.py` — **only on orphan**
- `_set_status` raw-asyncpg fallback in `pipeline.py` — **only on orphan**
- New APN / address / zoning field candidates for NY / CT / VA / MD / PA layers — **only on orphan**
- Phase 2/3 bootstrap scripts and `rerun_flood_overlay.py` — **only on orphan**

The orphan branch also pre-dates several main commits (it's missing the recent jurisdictions admin endpoints I/we added) — a naive merge will produce conflicts in `debug.py`, `jurisdictions.py`, `spatial_backfill.py`, `zoning_system.py`.

### 4. Pre-existing items carried over from prior STATUS

These were on the previous STATUS and were not addressed this session:

- **P2** — `zoning_rules.city='unknown'` leak: partially mitigated by `7aef614` (jurisdiction-first city resolution cherry-pick) for the per-parcel lookup path, but `bulk_ingest_zoning_for_jurisdiction` still uses `COALESCE(NULLIF(TRIM(p.city), ''), 'unknown')` directly. Philly parcels have `city=NULL` so Philly's 546,889 overlays were all written under `city='unknown'`. Tracking separately.
- **P3** — AADT skipped on Essex / Passaic (90s timeout on large jurisdictions).
- **P4** — `state='NE'` orphan jurisdiction rows.
- **P5** — Vercel auto-deploy disabled (`vercel.json` git.deploymentEnabled: false).
- **P6** — `audit_zoning_coverage.py` overstates `partial`.

---

## Commits added to `origin/main` this session

| SHA | Subject |
|---|---|
| `9c59baa` | fix(zoning_system): bulk_ingest_zoning on raw asyncpg, 7200s timeout |
| `6a24850` | feat(jurisdictions): admin endpoint to upload zoning shapefile/GeoJSON *(your commit)* |
| `7d8249d` | feat(debug): /run-bulk-zoning-overlays/{id} — overlays-only admin endpoint |
| `05d4102` | fix(alembic): restore 0017 migration so alembic upgrade head succeeds |
| `5ffa039` | fix(spatial_backfill): raw asyncpg + 7200s timeout for parcel zone UPDATE |
| `7aef614` | fix: jurisdiction-first city/state resolution in zoning lookup *(cherry-pick of 307e3ab)* |

---

## What "done" looks like vs prior STATUS

- [x] Production deploys cleanly without manual intervention
- [x] NJ ingestion produces `ready` jobs end-to-end for the 4 priority cities
- [x] AADT works (or skips cleanly on huge jurisdictions)
- [x] `pipeline_version` reported on `/health`
- [x] **Philadelphia `zoning_overlays` populated (P1)** — 546,889 rows
- [x] **Remaining NJ priority cities (Hoboken / Elizabeth / New Brunswick) ingested**
- [ ] NYC ingestion validated end-to-end — **failing on connection-drop bug, fix exists on orphan branch**
- [ ] `city='unknown'` rules leak resolved — partial (lookup path fixed; bulk path still leaks)

---

## Recommended next-session priority

1. **Cherry-pick the `_set_status` raw-asyncpg fallback from orphan `e184052`** (NYC unblock). Smallest surgical change; the rest of the orphan branch can be triaged later.
2. **Reconcile the orphan branch** — see `ORPHAN_BRANCH_AUDIT.md` for the per-file decision matrix.
3. **Harden the container start command** so dramatiq death is fatal to the container — defends against another silent worker stall.
4. **Patch `/api/jobs/{job_id}/cancel`** to return a clean response (avoid surfacing ORM/SQLAlchemy state through `response_model=JobRead` on the cancellation path).

---

## Quick reference

### URLs

- Frontend: https://zoning-finder.vercel.app
- API: https://capable-serenity-production-0d1a.up.railway.app
- Health: `/health` and `/api/debug/env`
- Admin: `/api/admin/jobs?stale_only=true&limit=50`, `/api/debug/jobs?limit=20`
- Backfill-only endpoint (new this session): `POST /api/debug/run-bulk-zoning-overlays/{jurisdiction_id}` *(works in worker context; for HTTP use, expect Railway proxy to kill the request at ~60-90s on big jurisdictions — submit a job instead)*
- Stuck-job repair: `POST /api/debug/fix-zoning/{jurisdiction_id}` and `/fix-zoning-all`

### Critical files

- `backend/app/services/pipeline.py` — orchestration
- `backend/app/services/spatial_backfill.py` — now uses raw asyncpg (5ffa039)
- `backend/app/services/zoning_system.py` — `bulk_ingest_zoning_for_jurisdiction` now uses raw asyncpg (9c59baa)
- `backend/app/services/overlays.py` — flood/wetland/AADT
- `backend/app/api/debug.py` — operational endpoints
- `backend/alembic/versions/0017_parcel_flood_wetland_nullable.py` — restored to main (05d4102)
- `frontend/app/dashboard/[jobId]/page.tsx` — main user-facing page

### Common SQL

```sql
-- Latest jobs
SELECT id, jurisdiction_input, status, finished_at, LEFT(error_message,80)
FROM jobs ORDER BY created_at DESC LIMIT 10;

-- Stuck / in-flight
SELECT id, jurisdiction_input, status,
       ROUND(EXTRACT(EPOCH FROM (now()-locked_at))/60) AS min_locked
FROM jobs WHERE finished_at IS NULL ORDER BY locked_at NULLS LAST;

-- Overlay coverage for a jurisdiction
SELECT COUNT(*) FROM zoning_overlays o
JOIN parcels p ON p.id = o.parcel_id
WHERE p.jurisdiction_id = '821d1007-9dec-4fad-868a-104385d5ef43';  -- Philly
```
