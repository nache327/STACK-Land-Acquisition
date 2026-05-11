# Orphan branch audit — `claude/agitated-khayyam-58c0d9`

**Generated:** 2026-05-11 (session close)
**Branch base:** local-only (not on origin)
**Diff scope:** `main..claude/agitated-khayyam-58c0d9`
**Decision deadline:** before any further `railway up` deploys from any local branch, OR before merging this branch

---

## Why this audit exists

Migration `0017_parcel_flood_wetland_nullable.py` from this branch was applied to production Supabase but the migration file was never on `main`. That caused a 58-hour silent worker outage (see `STATUS.md` → *Critical deployment drift incident*). This audit ensures we know exactly what else lives on this branch so the same thing doesn't recur with a different file.

---

## Commits unique to orphan branch (4)

| SHA | Subject |
|---|---|
| `1e33625` | feat(ingest): Phase 2 — Westchester NY, Nassau NY, Fairfield CT |
| `da47d52` | fix(ingest): set statement_cache_size=0 on raw asyncpg connections |
| `22f9a59` | fix(ingest): IF NOT EXISTS + TRUNCATE for _stage_parcels temp table |
| `e184052` | feat(ingest): Phase 3 — DC/Mid-Atlantic counties (Fairfax/Loudoun VA, Mont/Howard MD, Mont PA) |

These four commits together touch 10 source files and add 3 scripts. The branch is also missing recent main work (`ae8805c`, `6072b78`, `5ffa039`, `7aef614`, `7d8249d`, `9c59baa`) — so a literal merge will conflict heavily in any file both sides edited.

---

## Per-file decision matrix

Legend:
- **CHERRY-PICK** = pull the orphan version's specific change into main with a focused commit
- **MERGE** = need a proper 3-way merge against main's current state
- **DISCARD** = the change is either already on main (we already restored it) or no longer needed
- **REVIEW** = needs human judgement before deciding

### Migrations

| File | Status | Decision | Notes |
|---|---|---|---|
| `backend/alembic/versions/0017_parcel_flood_wetland_nullable.py` | already on main as of `05d4102` | DISCARD | We restored this file to main on 2026-05-11. Diff against orphan should now be empty. |

### Source files

| File | Lines diff | Decision | Why |
|---|---:|---|---|
| `backend/app/services/pipeline.py` | +342 / -? | **CHERRY-PICK** (high priority) | Adds `_raw_asyncpg_url()` helper, `_set_status` raw-asyncpg fallback for stale SQLAlchemy sessions, and the Phase 2/3 county configs. The `_set_status` fallback is the **NYC unblock** — same bug that killed job `f0b77b56` today. The county configs are net-new and additive. Recommend two smaller cherry-picks: (a) just the `_set_status` + `_progress_commit` raw-asyncpg path, (b) the new KNOWN_JURISDICTIONS entries. |
| `backend/app/services/ingestion.py` | +210 / -? | **CHERRY-PICK** | New APN field candidates: `ACCTID` (MD), `SWIS_PRINT_KEY_ID`/`SWIS_PRINT`/`MUNI_PARCEL_ID`/`PRINT_KEY`/`SBL` (NY), `link_1` (CT CAMA), `PA_MCPI` (Loudoun VA), `TAXPIN` (Mont PA). Address candidates `ADDRESS_1` (Fairfax VA), `Location_1` (CT). Zoning `ZONECODE` (Fairfax VA), `ZO_ZONE` (Loudoun VA). `_resolve_acres` clamp to 9,999,999. `_is_in_flood_zone` returns None (not False) when source has no flood field — this is what 0017's NOT-NULL drop is for. Purely additive ingestion intelligence. |
| `backend/app/services/arcgis_query.py` | +98 / -? | **CHERRY-PICK** | `_send_with_retry` with 4-attempt exponential backoff on 502/503/504/transport errors. Hardens every FeatureServer call. Net-positive. Useful for everyone, not just Phase 2/3. |
| `backend/app/services/zoning_ingestion.py` | +6 / -? | **CHERRY-PICK** | Small — `ZONECODE`/`ZO_ZONE` on the zoning-district field-candidate list, `ZD_ZONE_NAME` on the long-name list (Loudoun). One-line additive change. |
| `backend/app/services/overlays.py` | +4 / -? | **REVIEW** | Tiny diff; almost certainly the `None` tri-state propagation that pairs with the ingestion change. Verify it doesn't conflict with `249eb4a fix: AADT overlay on raw asyncpg + isolate failure` and `9b0fe69 fix: index _aadt_roads + 90s cap on AADT UPDATE`. |
| `backend/app/services/buybox_scoring.py` | +4 / -? | **REVIEW** | Tiny diff; pre-dates the buybox server-side work that landed on main. Verify it doesn't undo `feat(buybox): server-backed saved filters` (5ec2cff). |
| `backend/app/services/spatial_backfill.py` | +38 / -? | **DISCARD** | This file was rewritten on main as `5ffa039 fix(spatial_backfill): raw asyncpg + 7200s timeout`. Main's version is newer + addresses the same goal. Orphan's version is from an earlier era. |
| `backend/app/services/zoning_system.py` | +145 / -? | **REVIEW (likely DISCARD)** | Main has `9c59baa fix(zoning_system): bulk_ingest_zoning on raw asyncpg, 7200s timeout` + `7aef614 fix: jurisdiction-first city/state resolution`. Diff is 145 lines but both branches were changing the same area. Compare carefully — main is probably newer and complete. |
| `backend/app/api/debug.py` | +0 / -29 | **DISCARD** | The orphan branch removed 29 lines that exist on main. Main has `7d8249d feat(debug): /run-bulk-zoning-overlays/{id}` which isn't on orphan. **Do NOT merge or the new endpoint disappears.** |
| `backend/app/api/jurisdictions.py` | +0 / -406 | **DISCARD** | The orphan branch is missing 406 lines that exist on main — specifically `ae8805c chore(jurisdictions): admin endpoint to dedupe empty rows`, `6072b78 feat(jurisdictions): admin endpoint to backfill zoning + spatial join`, and `6a24850 feat(jurisdictions): admin endpoint to upload zoning shapefile/GeoJSON`. **Do NOT merge or those endpoints disappear.** |

### Scripts (new files on orphan)

| File | Decision | Why |
|---|---|---|
| `backend/scripts/ingest_phase2_ny_ct.py` | **CHERRY-PICK** | Phase 2 bootstrap (Westchester / Nassau / Fairfield CT). Net-new, no main equivalent. Standalone — drops in cleanly. |
| `backend/scripts/ingest_phase3_dc_midatlantic.py` | **CHERRY-PICK** | Phase 3 bootstrap (Fairfax / Loudoun VA, Mont PA, Mont/Howard MD). Same pattern. |
| `backend/scripts/rerun_flood_overlay.py` | **CHERRY-PICK** | Operational tool that runs flood overlay on existing parcels with `in_flood_zone IS NULL`. Useful regardless of the Phase 2/3 work — fits the new tri-state model from `0017`. |

---

## Recommended order of operations

**Phase A — unblock NYC (smallest possible patch):**

1. Cherry-pick *only* the `_set_status` raw-asyncpg fallback and `_progress_commit` raw-asyncpg conversion out of `e184052`'s `pipeline.py` diff. Resolve conflicts against main's current `pipeline.py` (which has `1627cd2`'s `_safe_job_id()` helper and `db.refresh()` after rollback). Test by resubmitting `New York, NY` and confirming it survives the 6-min MapPLUTO download.
2. Cherry-pick `arcgis_query.py`'s `_send_with_retry` — independently useful, easy to review.

**Phase B — bring Phase 2/3 ingestion online:**

3. Cherry-pick `ingestion.py` field-candidate additions (APN / address / zoning lists).
4. Cherry-pick `zoning_ingestion.py` six-line additions.
5. Cherry-pick the new `KNOWN_JURISDICTIONS` entries in `pipeline.py`.
6. Cherry-pick the 3 new scripts (`ingest_phase2_ny_ct.py`, `ingest_phase3_dc_midatlantic.py`, `rerun_flood_overlay.py`).

**Phase C — reconcile and retire the branch:**

7. Hand-review `overlays.py`, `buybox_scoring.py`, `zoning_system.py` for any net-new intent that isn't already on main.
8. Once everything intentional has been ported, **delete the local branch** (`git branch -D claude/agitated-khayyam-58c0d9`) so it can't be `railway up`'d into prod again.

**Phase D — procedural fix so this doesn't recur:**

9. Remove `railway up` permissions, or at minimum stop running it from local feature branches. The only sanctioned path to prod should be `git push origin main` → Railway auto-deploy.

---

## Quick verification commands

```bash
# How far behind main is the orphan branch?
git log claude/agitated-khayyam-58c0d9..main --oneline | wc -l

# Files diff vs main
git diff --name-status main..claude/agitated-khayyam-58c0d9

# Cherry-pick just one file's worth of changes from a commit (interactive)
git checkout claude/agitated-khayyam-58c0d9 -- backend/scripts/rerun_flood_overlay.py

# Cherry-pick a whole commit (preferred when surface is tight)
git cherry-pick <orphan-sha>
```
