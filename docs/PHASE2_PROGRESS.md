# Phase 2 Progress — STACK Land Acquisition

**Last audit refresh:** 2026-05-26 (post PR #98, verified via `backend/tmp/audit_post_truthfulness.json`)
**Phase 2 sprint:** 1 of 6 (each sprint = 14 days; sprint window 2026-05-22 → 2026-06-05)
**Plan reference:** `/Users/arench/.claude/plans/virtual-herding-iverson.md`

## Write discipline

- Each section lists its **owner**. Only the owner edits that section.
- Numbers must cite their source (audit JSON filename + timestamp, PR number, or live psql query).
- No "approx", "likely", or "should" without a named source.
- KPI claims belong only in sections 1–4, 11; activity goes in 15.
- Drift flags get appended to section 15 (Daily Changelog) with `[DRIFT]` tag.
- Lane Status (section 9) is a one-row update per lane per session — overwrite, don't append.

## Shared orchestration state

Operational coordination has moved from workspace-local `.context/*.json` files to repo-shared `coordination/` JSON files. Lanes should use `coordination/lane_state.json`, `coordination/blockers.json`, and `coordination/dispatch_queue.json` for shared machine-readable state across Conductor workspaces.

---

## 1. Current KPI Snapshot

**Owner:** master thread (refresh after every audit)
**Source:** `backend/tmp/audit_post_truthfulness.json` (2026-05-26 18:45 UTC, post-PR-#98 verification by Lane A)

| Tier | KPI | Value | Source | Δ vs prior |
|---|---|---:|---|---:|
| 1 #1 | Honest operational jurisdictions | **45** | audit_post_truthfulness.json `.summary.operational_count` | -4 vs same-audit old readiness logic (49) |
| 1 #1 | Audit-operational jurisdictions | **45** | audit_post_truthfulness.json `.summary.operational_count` | -3 vs 2026-05-21 audit baseline (48) |
| 1 #2 | Trustworthy parcel verdict count | **3,292,352** | audit_post_truthfulness.json operational classified parcel sum | now exact |
| 1 #3 | Avg unclear share (partials) | **18.3%** | audit_post_truthfulness.json weighted partial unclear/matrix parcel share (`141,459 / 773,627`) | +0.3pp vs prior rounded estimate |
| 1 #4 | Fake-operationals | **0** | audit_post_truthfulness.json query: operational + zoning-code coverage `<70` | -4 |
| 2 #5 | Failed jobs / 14d | **42** | live `/api/admin/jobs?status=failed&limit=500`, filtered since 2026-05-12 | -5 vs prior 47 |
| 2 #5 | Stuck jobs (>10min, non-terminal) | **0** | live `/api/admin/jobs?stale_only=true&limit=500` | unchanged |
| 2 #6 | Snapshot table latest capture | 2026-05-19 21:56 UTC | live `coverage_snapshots` max `captured_at` | stale |
| 2 #7 | Ingest success last 14d | **91 ready / 42 failed / 5 cancelled** | live jobs endpoints, filtered since 2026-05-12 | refreshed window |
| 2 #8 | Jurisdictions with `bbox IS NULL` | **7** | audit_post_truthfulness.json `has_bbox=false` | unchanged |

---

## 2. Honest Operational Count

**Owner:** master thread
**Definition:** `operational_readiness = "operational"` AND `parcel_zoning_code_coverage_pct ≥ 70` AND no fake-op flags.

**Current value:** **45** (verified post-truthfulness merge)
**Audit-operational value:** **45** (post-PR-#98; truthfulness rule is now part of audit readiness)

**Phase-1 close delta:** -3 vs 2026-05-21 audit baseline (48); -4 vs same-audit old readiness logic (49).
**Confidence:** verified by `backend/tmp/audit_post_truthfulness.json` generated after PR #98 merged.

Post-merge validation: `jq '[.jurisdictions[] | select(.operational_readiness=="operational") | select(.parcel_zoning_code_coverage_pct < 70) | .name]' backend/tmp/audit_post_truthfulness.json` returns `[]`.

---

## 3. Audit-Operational Count

**Owner:** master thread
**Current value:** **45**

Source: `backend/tmp/audit_post_truthfulness.json` summary block, 2026-05-26 18:45 UTC.

**Fake-operational check:** none remain after PR #98.

**Demoted by truthfulness threshold (old readiness logic: operational; new readiness: partial):**

| jurisdiction | parcel_zoning_code_coverage_pct | rationale |
|---|---:|---|
| Bergen County, NJ | 3.1 | 273,027 of 281,646 parcels lack zoning_code |
| Draper City, UT | 65.9 | 8,694 of 25,515 parcels lack zoning_code |
| Essex County, NJ | 23.8 | 133,975 of 175,932 parcels lack zoning_code |
| Montgomery County, PA | 2.2 | 294,876 of 301,424 parcels lack zoning_code |

---

## 4. Partial Jurisdictions

**Owner:** master thread
**Count:** **29** (per `backend/tmp/audit_post_truthfulness.json`)

**Category split (Plan §"Major Strategic Realization"):**

### Category A — Matrix Partials (Lane E owns conversion)

Parcels exist, zoning binds, matrix exists, semantics incomplete.

| jurisdiction | parcels | zoned % | matrix rows | unclear rows | last action |
|---|---:|---:|---:|---:|---|
| Somerset County, NJ | 117,387 | 100.0 | 296 | 79 | Lane E PR pending merge (Task #14) |
| Norfolk County, MA | 206,365 | 74.9 | 312 | ~100 | not started |
| Middlesex County, MA | 423,634 | 92.3 | 633 | ~181 | not started |
| Highland, UT | 7,292 | 99.8 | 24 | 4 | not started |
| Morris County, NJ | 177,532 | 0.0 | 30 | 6 | matrix done; Cat-B blocker dominates |
| Hunterdon County, NJ | 52,902 | 0.0 | 14 | 0 | matrix done; Cat-B blocker dominates |

### Category B — Structural Coverage Partials (Lane B owns)

Parcels exist but county-wide zoning layer absent. NOT matrix problems.

| jurisdiction | parcels | zoned % | path |
|---|---:|---:|---|
| Burlington County, NJ | 174,852 | 0.0 (1 parcel) | per-town ingest; Westampton scoped |
| Bergen County, NJ | 281,646 | 3.1 | per-town ingest; Paramus only confirmed source |
| Essex County, NJ | 175,932 | 23.8 | per-town ingest |
| Hudson County, NJ | 143,305 | 0.0 | per-town ingest; parcel ingest also broken (0 ingested) |
| Middlesex County, NJ | 245,616 | 0.0 | per-town ingest + post-PR-#85 retry |
| Passaic County, NJ | 125,785 | 0.0 | per-town ingest |
| Union County, NJ | 147,627 | 0.0 | per-town ingest |
| Ocean County, NJ | 422,330 | 0.0 | per-town ingest |
| Monmouth County, NJ | 251,486 | 5.7 | per-town ingest (matrix ~mostly done) |
| Wake County, NC | 435,434 | 0.0 | county-level ingest retry pending |
| Westchester County, NY | 257,914 | 0.0 | Phase 2 ingest retry pending |
| Nassau County, NY | 420,577 | 0.0 | Phase 2 ingest retry pending |
| Fairfield County, CT | 261,652 | 0.0 | Phase 2 ingest retry pending |

---

## 5. Structural Coverage Partials (Category B)

**Owner:** Lane B (Discovery + Coverage)
**Write format:** one row per Cat-B jurisdiction with source-acquisition status and last attempt outcome.

| jurisdiction | parcel ingest? | per-town source verified? | last attempt | status |
|---|---|---|---|---|
| Burlington County, NJ | yes (174,852 via PR #85) | Westampton only (16 rows scoped) | 2026-05-21 | pilot in progress |
| Bergen County, NJ | yes (281,646) | Paramus only (~3.1% coverage) | per BERGEN_SCALE_UP.md | hub-exhausted |
| Essex / Hudson / Passaic / Union / Ocean / Middlesex / Monmouth NJ | various | unknown | — | needs Lane B probe |
| Wake County, NC | partial | needs probe | 2026-05-19 (failed, line 1417) | retry queued |
| Westchester / Nassau NY, Fairfield CT | partial | needs probe | Phase 2 incomplete | retry queued |

_Lane B: append updates here as you probe sources and stage per-town ingests._

---

## 6. Matrix Operationalization Queue (Category A)

**Owner:** Lane E (Matrix Intelligence)
**Write format:** ranked list with unclear-row count, parcel upside, ease score, PR/owner. Re-rank after each audit refresh.

**Phase-2 Sprint-1 queue (priority order, per plan §Operationalization Queue):**

| rank | jurisdiction | unclear rows | parcels at stake | ease | PR | owner |
|---:|---|---:|---:|---|---|---|
| done | Norfolk County, MA | 88 remaining | 14,638 remaining unclear-bound | applied; partial (residential short-code batch only) | PR #100 merged (`6eb9eaf`) | Lane E |
| done | Middlesex County, MA | 172 remaining | 67,386 remaining unclear-bound | applied; partial (Lowell batch 1 only) | PR #100 merged (`6eb9eaf`) | Lane E |
| done | Highland, UT | 4 remaining | 937 remaining unclear-bound | reviewed; partial (PD-1 unsupported without adopted PD narrative) | PR #100 merged (`6eb9eaf`) | Lane E |
| done | Somerset County, NJ | 66 remaining | 2,194 remaining unclear-bound | applied; operational | #91 merged + prod applied 2026-05-26 | Lane E |
| done | Loudoun VA + Howard MD cleanup | 4 remaining active rows | 19,309 remaining unclear-bound | applied; Howard operational, Loudoun partial by design | PR #95 patched/applied/merged 2026-05-26 | Lane E |

_Lane E: append progress notes here (script written / PR opened / merged / refreshed / operational flip)._

- 2026-05-21 22:20 UTC — Somerset NJ script ready and pushed to PR #91. Dry-run: 13 rows, 10,567 parcels move unclear→classified. `PAC-2` / `PAC-3` deliberately left unclear because absent from matrix.
- 2026-05-26 18:23 UTC — Somerset NJ applied to prod via session-mode DB endpoint after Railway CLI auth remained expired. Updated 13 rows (`EP-250`, `G-B`, `LD`, `LD-1`, `LD-3`, `PAC`, `S-100`, `S-50`, `S-60`, `S-75`, `S-80`, `S-C-V`, `SMD`), moving 10,567 parcels unclear→classified. Refresh: operational, 66 remaining unclear rows, 2,194 remaining unclear-bound parcels, 98.4% classified parcel coverage.
- 2026-05-26 18:23 UTC — Loudoun + Howard cleanup applied to prod. Loudoun PR #95 corrected before apply to leave `TOWNS` and `PUD-1` unclear rather than overclassify out-of-scope / unverified rows; classified only `C1`, `PDCH`, and `PUD` (63 parcels unclear→classified). Loudoun remains partial with 2 active unclear rows / 19,298 unclear-bound parcels. Howard reviewed `2R0` and `OT`, moved 0 parcels, and remains operational with 2 active unclear rows / 11 unclear-bound parcels.
- 2026-05-26 19:19 UTC — Norfolk County MA pattern batch applied to prod via `pattern_norfolk_ma_adjudication.py`. Updated 12 rows (`G`, `GR`, `S`, `S-7`, `S1`, `S10`, `S15`, `S2`, `S25`, `S40`, `T-5`, `T-6`) using Norwood, Needham, and Brookline ordinance citations. Parcel delta: 16,489 unclear→classified. Refresh: partial, 88 remaining unclear rows, 14,638 remaining unclear-bound parcels, 90.5% classified parcel coverage.
- 2026-05-26 19:57 UTC — Middlesex County MA Lowell batch 1 applied to prod via `pattern_middlesex_ma_adjudication.py`. Updated 9 rows (`NB`, `SMF`, `SMU`, `SSF`, `TSF`, `TTF`, `UMF`, `UMU`, `USF`) using Lowell Zoning Ordinance Article XII / Section 12.9 citations. Parcel delta: 18,401 unclear→classified. Refresh: partial, 172 remaining unclear rows, 67,386 remaining unclear-bound parcels, 82.8% classified parcel coverage.
- 2026-05-26 20:19 UTC — Highland UT cleanup applied to prod via `highland_ut_matrix_adjudication.py`. `PD-1` reviewed against Highland City Development Code Article 5 and left unclear because the adopted PD narrative governs uses; zero-bind unsupported rows left unclear. Parcel delta: 0. Refresh: partial, 4 remaining unclear rows, 937 remaining unclear-bound parcels, 87.1% classified parcel coverage.
- 2026-05-26 22:41 UTC — PR #100 merged as `6eb9eaf` for the Norfolk/Middlesex/Highland matrix batch. Merge diff contains only `backend/scripts/highland_ut_matrix_adjudication.py`, `backend/scripts/pattern_middlesex_ma_adjudication.py`, `backend/scripts/pattern_norfolk_ma_adjudication.py`, and Lane E updates to this file. Validation: GitHub Backend Tests passed, Frontend Tests passed, Supabase Preview skipped; local `py_compile` passed for all three scripts.

---

## 7. Ingest Retry Queue

**Owner:** Lane B
**Write format:** jurisdiction → last-attempt outcome → next attempt.

**Eligible for free retries against post-PR-#85 substrate (zero new code):**

| jurisdiction | parcels | prior failure line | retry status | outcome |
|---|---:|---|---|---|
| Wake County, NC | 435,434 | pipeline.py:1417/1401 (parcel ingest) | not yet retried | TBD |
| Middlesex County, NJ | 245,616 | pipeline.py:1410/1688 (boundary) | not yet retried | TBD |
| Westchester County, NY | 257,914 | Phase 2 incomplete | not yet retried | TBD |
| Nassau County, NY | 420,577 | Phase 2 incomplete | not yet retried | TBD |
| Fairfield County, CT | 261,652 | Phase 2 incomplete | not yet retried | TBD |
| Marlboro, NJ | 0 (broken state) | pipeline.py:1298 | not yet retried | TBD |

_Lane B: log each retry result here. Reassess once you see outcomes — most Cat-B jurisdictions will need source acquisition even if pipeline retry succeeds._

---

## 8. Active Failures

**Owner:** Lane A (Integrator)
**Write format:** failure cluster by line + jurisdiction; resolved clusters removed.

**Last 14d (sources: `backend/tmp/jobs_all_latest.json`, `backend/tmp/job_monomouth_08b0f866.json`, `backend/tmp/job_westchester_886141e2.json`, live admin jobs `d98324cc-6c78-4e2f-a6ab-d6fb15f92835`, `3b4582c5-e47e-4bc7-8d38-7853e0173a89`, and `a9515ff6-41e3-4440-9609-8fef93e75a82`; refreshed by Master 2026-05-28 18:09 UTC):**

| count | jurisdiction(s) | pipeline line | class | status |
|---:|---|---|---|---|
| under review | Westchester County NY / Nassau County NY / Monmouth County NJ | Westchester `pipeline.py:1752`; Nassau `pipeline.py:1785` -> `await db.commit()` during/after `run_overlays`; Monmouth warning during `run_overlays` | **B6 under review:** fatal post-overlay/run_overlays terminal failure did not recur on Monmouth, but Monmouth emitted non-fatal invalid-transaction warning | Lane A/D review required before Westchester; no broad retries |
| cleared on Nassau | Nassau County, NY | `pipeline.py:1737` -> `refresh_jurisdiction_coverage_level` -> `spatial_backfill.py:152` | **B10 cleared on Nassau:** job `d98324cc` reached `run_overlays` after coverage refresh | code resolved by PR #111; do not reopen unless it recurs |
| cleared on Nassau | Nassau County, NY | `pipeline.py:1229` -> `existing_count = await db.scalar(...)` | **B9 cleared:** forced-run cache preflight failure did not recur | code resolved by PR #109 |
| cleared on Nassau and Monmouth | Nassau County NY / Monmouth County NJ; New York NY same signature | `pipeline.py:1680` -> `bootstrap_zone_use_matrix` -> `matrix_bootstrap.py:70` | **B7 cleared on Monmouth:** job `a9515ff6` reached `run_overlays` and `ready`; hard bootstrap failure did not recur | no further B7 retry required before warning review |
| active / parked | Middlesex County NJ / Fairfield County CT / Nassau County NY | ingest mapping plateau before bootstrap/overlays | **B8 reopened:** Nassau job `3b4582c5` stalled at 210,000 / 420,594 on post-PR119 retry, after earlier single happy-path job `d98324cc` | Nassau/Middlesex/Fairfield parked until mitigation or deliberate scaling experiment |
| historical | Middlesex NJ / Westchester NY / Nassau NY / Fairfield CT / Marlboro NJ | `pipeline.py:1732` -> `apply_flood_overlay` -> `overlays.py:193` | flood overlay fatal after successful parcel ingest | code resolved by PR #94; Railway deployed `116dd4e1fc45`; superseded by current B6/B7/B8 retry evidence |

_Lane A: append new clusters here. Remove resolved clusters (move to section 15 as changelog entries)._

---

## 9. Lane Status

**Owner:** each lane writes its own row. Overwrite, do not append.

| Lane | Current task | Open PRs | Blockers | Last update |
|---|---|---|---|---|
| A — Integrator | Classify Monmouth non-fatal `run_overlays` invalid-transaction warning after ready validation | PR #119 merged (`4a081ce`) | B6 fatal terminal did not recur; warning review gates Westchester; B8 reopened with Nassau parked | 2026-05-28 18:09 UTC (Monmouth job `a9515ff6` ready) |
| B — Discovery + Coverage | paused after Monmouth ready validation; Burlington per-town pilot remains separate | — | no retries until warning review; Nassau/Middlesex/Fairfield parked under B8; Westchester held | 2026-05-28 18:09 UTC (Monmouth ready) |
| C — Spatial + CRS | paused behind Monmouth warning review | — | reliability queue not clear | 2026-05-28 18:09 UTC (master) |
| D — Operator + Workflow | verify Monmouth terminal/queue state and capture warning log evidence if available | — | none for Nassau cleanup; Railway cron-log verification still blocked by expired local CLI auth | 2026-05-28 18:09 UTC (Monmouth warning review) |
| E — Matrix Intelligence | MA/Highland matrix batch commit hygiene complete; PR #100 merged; no new matrix scope started | PR #100 merged (`6eb9eaf`) | none for Lane E; Railway CLI auth remains unavailable globally | 2026-05-26 22:41 UTC |

---

## 10. Completed Jurisdictions This Sprint

**Owner:** Lane E (primarily); other lanes append when their work flips a jurisdiction operational.
**Sprint window:** 2026-05-22 → 2026-06-05.

| jurisdiction | PR | operational evidence | parcels classified | logged |
|---|---:|---|---:|---|
| Somerset County, NJ | #91 | 98.4% classified parcel coverage, 100% matrix match, 66 remaining unclear rows / 2,194 unclear-bound parcels, no blocking gaps | 117,387 | 2026-05-26 |
| Allentown, PA | #90 | 18/18 human-reviewed, 0 unclear, 100% zoned | 41,872 | 2026-05-21 |

---

## 11. Recently Operationalized (rolling 14d)

**Owner:** master thread

| jurisdiction | flipped on | lane | parcels classified |
|---|---|---|---:|
| Somerset County, NJ | 2026-05-26 (via #91 + prod apply/refresh) | E | 117,387 |
| Allentown, PA | ~2026-05-21 (via PR #90 + 8e82965 + prior matrix) | E | 41,872 |
| Howard County, MD | live before this sprint | E | 89,461 (95.6% canonical) |

---

## 12. Active PRs

**Owner:** master thread

| PR | title | lane | state | merge order |
|---:|---|---|---|---:|
| #89 | fix(audit-cli): disable statement_timeout for full-sweep against prod-scale data | A | **MERGED** (`9fed012`) 2026-05-21 | done |
| #90 | feat(allentown-2025): apply 2025 ordinance verdicts + ship vocabulary_aliases table | E | **MERGED** 2026-05-21 | done |
| #91 | feat(matrix): Somerset NJ adjudication — 13 unclear rows → prohibited/conditional | E | **MERGED** (`0893e28`) 2026-05-22 | done; prod applied/refreshed 2026-05-26 |
| #92 | fix(deploy): re-enable Vercel git deployments | A | **MERGED** (`ba7a958`) 2026-05-26 | done; Vercel deploy run `26466874832` succeeded |
| #94 | fix(pipeline): non-fatal flood + wetland overlays (match AADT containment pattern) | A | **MERGED** (`116dd4e`) 2026-05-26 | done; Railway deploy verified |
| #95 | feat(matrix): Loudoun VA + Howard MD unclear-row cleanup | E | **MERGED** (`2612bd0`) 2026-05-26 | done; patched + prod applied/refreshed |
| #97 | feat(ops): queued-job watchdog cron | D | **MERGED** (`2e8d9e0`) 2026-05-26 | done |
| #98 | fix(audit): require 70% parcel zoning coverage for operational | A | **MERGED** (`a29b86e`) 2026-05-26 | done; post-merge audit refreshed |
| #100 | feat(matrix): apply MA pattern batches and Highland review | E | **MERGED** (`6eb9eaf`) 2026-05-26 | done; CI passed; prod apply/refresh already completed |

---

## 13. Merge Queue

**Owner:** master thread
**Ordered sequencing for next merges:**

1. ~~PR #89 (audit CLI timeout)~~ ✅ merged
2. **Lane E Somerset NJ** — already verified, citations real, 10,567 parcels move. Open PR + merge.
3. ~~Lane A truthfulness patch PR #98~~ ✅ merged; post-truthfulness audit refreshed.
4. ~~Lane D watchdog PR #97~~ ✅ merged; Railway web deploy serves `2e8d9e0`, cron-log OK run still pending Railway CLI login.
5. **Lane B Burlington-pattern retries** — no PRs; operational sweep.
6. **Lane C bbox sweep** — no PRs unless bug surfaces.
7. ~~Lane E Norfolk/Middlesex/Highland matrix batch PR #100~~ ✅ merged; prod apply/refresh completed before merge.

---

## 14. Blockers

**Owner:** any lane appends; resolved blockers removed.

| ID | blocker | owner | downstream impact | status |
|---|---|---|---|---|
| ~~B1~~ | ~~audit CLI times out on prod~~ | Lane A | ~~master can't refresh KPIs~~ | **RESOLVED via PR #89** |
| ~~B2~~ | ~~Lane D watchdog PR overwrites daily-digest cron in `railway-cron.toml`~~ | ~~user / Lane D~~ | ~~watchdog can't merge~~ | **RESOLVED in PR #97** — daily digest remains in the cron command; watchdog runs from the same Railway cron service |
| ~~B3~~ | ~~truthfulness patch held pending audit verification~~ | ~~Lane A~~ | ~~sequencing~~ | **RESOLVED via PR #98** — post-merge audit generated `backend/tmp/audit_post_truthfulness.json` |
| B4 | Burlington `ready` but 0 zoning_code on 174,851 of 174,852 parcels | Lane B | Burlington reclassified Cat-B | **OPEN** — reclassified, not a defect |
| B6 | Westchester post-overlay `db.commit()` failure at `pipeline.py:1752` plus Nassau `d98324cc-6c78-4e2f-a6ab-d6fb15f92835` `run_overlays` `db.commit()` failure at `pipeline.py:1785`; Monmouth `a9515ff6` reached `ready` but emitted non-fatal `run_overlays` invalid-transaction warning | Lane A / Lane D | Westchester remains held until warning review completes | **PATCHED / DEPLOYED / WARNING UNDER REVIEW** — PR #119 merged as `4a081ce429cb1c139d21f55f31fc3c6b88bcdc34`; Monmouth fatal terminal failure did not recur, but warning `"Can't reconnect until invalid transaction is rolled back. Please rollback() fully before proceeding"` needs Lane A/D disposition |
| ~~B7~~ | ~~Nassau + Monmouth `bootstrap_zone_use_matrix` terminal failure at `pipeline.py:1680` / `matrix_bootstrap.py:70` after parcel download; Monmouth evidence shows `download_parcels` 251,486 and `ingest_parcels` 251,486 completed, no overlay step ran~~ | ~~Lane A~~ | ~~Lane B retry dispatch paused for same-signature jobs~~ | **RESOLVED via PR #106 and Monmouth validation** — Monmouth job `a9515ff6` reached `run_overlays` and `ready`; bootstrap hard failure did not recur |
| B8 | Nassau large-county ingest mapping plateau/stale-lock recurrence (`3b4582c5` stalled at `210000 / 420594` in user-provided retry evidence and was cancelled by Lane D after mapping reached `266000 / 420594`, no terminal traceback) plus Middlesex/Fairfield plateau history | Lane A / Lane B | retry sequencing; large-county scaling | **REOPENED / PARKED** — single happy-path Nassau job `d98324cc` is insufficient evidence; Lane D cancelled `3b4582c5` at `2026-05-28T17:38:22.115015Z`; final `active_only=0`, `stale_only=0`; Nassau/Middlesex/Fairfield parked until mitigation or deliberate scaling experiment |
| ~~B9~~ | ~~Nassau forced validation retry `3c7ce534-ce81-461e-bab5-76eb64e0105f` failed during `download_parcels` before parcel counters at `pipeline.py:1229 existing_count = await db.scalar(...)`; job `force=true` made the cache count unnecessary~~ | ~~Lane A~~ | ~~Nassau cannot validate B7 until forced-run cache preflight is bypassed~~ | **RESOLVED via PR #109** — merged `0afa78a07579bd9d7c78b2f529d0519b8b2b893e`; Railway `/health.pipeline_version` reports `0afa78a07579` |
| ~~B10~~ | ~~Nassau validation retry `7cda9f3e-eff5-403f-b345-ba083e359e9d` completed `download_parcels` 420,594 and `ingest_parcels` 420,577, then failed at `pipeline.py:1737` / `spatial_backfill.py:152` during `coverage_refresh` DB execute~~ | ~~Lane A~~ | ~~Nassau cannot validate B7/continue to overlays until coverage refresh uses a reliable session boundary~~ | **RESOLVED via PR #111** — merged `7411a2fa934e6fea8e80efcf1fa333ece0c8b4a5`; Railway `/health.pipeline_version` reports `7411a2fa934e` |
| B5 | alias_mappings framework abstraction (PR #86) + vocabulary_aliases table (PR #90) | logged | governance | **LOG ONLY** (Section 7 #3 in plan); not rolled back |

---

## 15. Daily Changelog

**Owner:** any lane appends (reverse chronological).

### 2026-05-28

- **VALIDATE** Monmouth County NJ only. Lane B. Job `a9515ff6-41e3-4440-9609-8fef93e75a82` on `/health.pipeline_version=ce0fb85fd899` reached `ready` at `2026-05-28T18:09:21.737917Z`. `download_parcels` completed 251,486; `ingest_parcels` completed 251,486 with `dedupe_count=0`; `bootstrap_zone_use_matrix` did not hard-fail and the job reached `run_overlays`; `coverage_refresh` passed by run order evidence; `complete_feasibility` completed. B7 is cleared for Monmouth. B6 fatal run_overlays/commit terminal failure did not recur, but `run_overlays` emitted non-fatal warning `"Can't reconnect until invalid transaction is rolled back. Please rollback() fully before proceeding"`. Lane B pauses; Lane A/D review the warning before Westchester. Final queues from Lane B: `stale_only=0`; `active_only=1` with unrelated Salt Lake County job `896e2dde-01cf-4338-8db0-befec01f82cb`.
- **DECISION** Master Planning approved parking Nassau and pivoting validation to Monmouth. Latest post-PR119 Nassau retry `3b4582c5-e47e-4bc7-8d38-7853e0173a89` ran on `/health.pipeline_version=6e8d7ee52c8c`, downloaded 420,594 parcels, and stalled in ingest mapping at `210000 / 420594` before `bootstrap_zone_use_matrix`, `coverage_refresh`, or `run_overlays`. B8 is reopened as a recurring large-county mapping/stale-lock class; prior "cleared for Nassau validation" evidence from `d98324cc` is invalidated as a single happy-path sample. B6 unblock condition changes from Nassau-only to Monmouth County NJ validation past `run_overlays`. Sequencing: Lane D cleanup is complete, Lane B runs Monmouth County NJ only, Westchester remains held, Nassau/Middlesex/Fairfield remain parked under B8, and Lane E remains paused.
- **CLEANUP** stale/active Nassau County NY job `3b4582c5-e47e-4bc7-8d38-7853e0173a89`. Lane D. Verified before cleanup via `GET /api/admin/jobs/{job_id}` plus `GET /api/admin/jobs?active_only=true&limit=500` and `GET /api/admin/jobs?stale_only=true&limit=500`: status `ingesting_parcels`, attempts `2`, mapping `266000 / 420594` at check time, upserted `0`, `locked_at=2026-05-28T17:31:13.282534Z`, `finished_at=null`, `active_only=1`, `stale_only=0` (user-provided prior evidence had `stale_only=1` at `210000 / 420594`). Cancelled through existing operator path `POST /api/jobs/{job_id}/cancel` at `2026-05-28T17:38:20Z`; response `status=cancelled`, `cancel_requested_at=2026-05-28T17:38:22.114980+00:00`, `finished_at=2026-05-28T17:38:22.115015+00:00`, `already_terminal=false`. Final verification at `2026-05-28T17:38:39Z`: job `status=cancelled`, `locked_at=null`, `active_only=0`, `stale_only=0`. No retry was started by Lane D. Monmouth release comes from the Master Planning decision above, not from cleanup alone.

### 2026-05-27

- **MERGE+VERIFY** PR #119 `fix(pipeline): contain overlay commit session failure` merged as `4a081ce429cb1c139d21f55f31fc3c6b88bcdc34`; Railway `/health.pipeline_version` reports `4a081ce429cb`. Lane A. B6 remains pending validation by Nassau County NY only. Monmouth remains paused until Nassau validates past `run_overlays`.
- **PATCH IN PROGRESS** B6 expanded post-overlay/run_overlays commit/session reliability. Lane A. Nassau job `d98324cc-6c78-4e2f-a6ab-d6fb15f92835` on `/health.pipeline_version=99500040e341` completed `download_parcels` 420,594 and `ingest_parcels` 420,577 / 17 dedupe, cleared B8/B10/B7 on Nassau, then failed `2026-05-27T21:03:09.172494Z` at `pipeline.py:1785 await db.commit()` during `run_overlays`; final `active_only=0`, `stale_only=0`. This confirms B6 expanded with Westchester's post-overlay `db.commit()` class. Patch scope is only post-overlay commit/session containment; no retries run by Lane A.
- **CLEANUP** stale Nassau County NY job `91bb9444-377a-4a3e-a3fb-45d7b63ba18e`. Lane D. Verified before cleanup via `GET /api/admin/jobs/{job_id}` plus `GET /api/admin/jobs?active_only=true&limit=500` and `GET /api/admin/jobs?stale_only=true&limit=500`: status `ingesting_parcels`, attempts `3`, mapping `150000 / 420594`, upserted `0`, `locked_at=2026-05-27T17:27:53.882342Z`, `finished_at=null`, `active_only=1`, `stale_only=1`. Cancelled through existing operator path `POST /api/jobs/{job_id}/cancel` at `2026-05-27T17:46:09Z`; response `status=cancelled`, `cancel_requested_at=2026-05-27T17:46:11.394103+00:00`, `finished_at=2026-05-27T17:46:11.394136+00:00`, `already_terminal=false`. Final verification at `2026-05-27T17:46:28Z`: job `status=cancelled`, `locked_at=null`, `active_only=0`, `stale_only=0`. Lane B can retry Nassau County NY only; no retry was started by Lane D.
- **CLASSIFY** B8. Lane A. Latest Nassau validation job `91bb9444-377a-4a3e-a3fb-45d7b63ba18e` is not B7/B10: attempt 2 became active/stale during `ingesting_parcels` at `320000 / 420594` mapped and `0` upserted with no traceback, after two completed `download_parcels` steps for the same 420,594-feature Nassau endpoint. At 2026-05-27 17:22 UTC the watchdog had auto-recovered it to attempt 3 (`downloading_parcels`, `locked_at=2026-05-27T17:21:22.865101Z`). This matches the Middlesex `110b0a01` and Fairfield `30997930` large-county mapping plateau family rather than a Nassau-specific source issue. No narrow code patch made; wait for Nassau `91bb9444` terminal state before any new retry, then retry Nassau County NY only if needed.

### 2026-05-26

- **MERGE+VERIFY** PR #111 `fix(pipeline): refresh coverage in fresh session` merged as `7411a2fa934e6fea8e80efcf1fa333ece0c8b4a5`; Railway `/health.pipeline_version` reports `7411a2fa934e`. Lane A. B10 cleared for validation retry: Nassau County NY only. Monmouth remains paused until Nassau validates past B10; B6 Westchester and B8 Middlesex/Fairfield remain separate.
- **PATCH IN PROGRESS** B10 Nassau coverage-refresh session boundary. Lane A. Evidence: Nassau job `7cda9f3e-eff5-403f-b345-ba083e359e9d` on deployed `3e39a47a3c2d` completed `download_parcels` with 420,594 features and `ingest_parcels` with 420,577 rows / 17 dedupe, then failed at `pipeline.py:1737 await refresh_jurisdiction_coverage_level(...)` -> `spatial_backfill.py:152 result = await db.execute(...)`. B9 did not recur; old B7 hard failure did not recur on Nassau, but B7 is not fully validation-cleared because B10 stopped the run. Monmouth remains paused.
- **MERGE+VERIFY** PR #109 `fix(pipeline): skip parcel cache count for forced jobs` merged as `0afa78a07579bd9d7c78b2f529d0519b8b2b893e`; Railway `/health.pipeline_version` reports `0afa78a07579`. Lane A. B9 cleared for validation retry: Nassau County NY first, then Monmouth County NJ for B7 validation. Keep B6 Westchester and B8 Middlesex/Fairfield separate.
- **PATCH IN PROGRESS** B9 Nassau forced-retry cache preflight bypass. Lane A. Evidence: Nassau job `3c7ce534-ce81-461e-bab5-76eb64e0105f` failed `2026-05-26T22:42:16.689936Z` during `download_parcels` at `pipeline.py:1229 existing_count = await db.scalar(...)`; `discover_layers` completed, `download_parcels` failed against `https://services6.arcgis.com/a523XM128lX5Nsff/arcgis/rest/services/Nassau_parcels/FeatureServer/6`, progress had only `jurisdiction_id`, and job `force=true`. Patch skips the existing parcel-count cache preflight for forced jobs. B7 is not validated cleared because Nassau did not reach matrix bootstrap.
- **MERGE+VALIDATE** PR #100 `feat(matrix): apply MA pattern batches and Highland review` merged as `6eb9eaf`. Lane E. Scope verified as three matrix scripts plus Lane E docs only; GitHub Backend Tests and Frontend Tests passed; local `py_compile` passed for `pattern_norfolk_ma_adjudication.py`, `pattern_middlesex_ma_adjudication.py`, and `highland_ut_matrix_adjudication.py`. E2 commit-hygiene blocker cleared.
- **MERGE+VERIFY** PR #106 `fix(pipeline): make matrix bootstrap non-fatal` merged as `ab88dba1ef6b6203f1752d078683be57696dadb4`; Railway `/health.pipeline_version` reports `ab88dba1ef6b`. Lane A. B7 cleared for validation retry: Nassau County NY and Monmouth County NJ first; keep B6 Westchester and B8 Middlesex/Fairfield separate.
- **OPEN** PR #106 B7 non-fatal zone-use matrix bootstrap containment. Lane A. Evidence: Monmouth job `08b0f866-5fe6-4efb-8403-ed331416f1ea` failed at `pipeline.py:1680` -> `bootstrap_zone_use_matrix` after `download_parcels` completed 251,486 features and `ingest_parcels` completed 251,486 parcels; no overlay step ran. Nassau job `80120217-61c2-4de7-9484-f43f2d4d5c7a` and New York job `557b3c44-92f3-402e-8275-c86c6a1712e6` show the same terminal bootstrap signature. Branch `fix/pipeline-nonfatal-zone-matrix-bootstrap` makes heuristic matrix bootstrap non-fatal.
- **CLASSIFY** B6 and B8. Lane A. B6 is Westchester job `886141e2-7ef3-4800-b635-20ecb8af2eaa`, a distinct post-overlay `db.commit()` failure at `pipeline.py:1752`; separate follow-up. B8 is Middlesex job `110b0a01-e723-43da-967c-bca50bba6848` plus Fairfield job `30997930-3a03-47ce-8411-730b688a4c6d`, both cancelled during large-county mapping plateau (`parcels_mapped` 114,000 / 122,000); parked separate follow-up.
- **APPLY+REFRESH** Highland, UT. Lane E. `highland_ut_matrix_adjudication.py` applied review metadata to `PD-1`; row remains unclear because Highland City Development Code Article 5 makes the adopted PD narrative the governing use regulation. Parcel delta: 0 unclear→classified. Refresh: partial, 4 remaining unclear rows, 937 remaining unclear-bound parcels.
- **APPLY+REFRESH** Middlesex County, MA. Lane E. `pattern_middlesex_ma_adjudication.py` applied Lowell batch 1 to 9 ordinance-cited rows (`NB`, `SMF`, `SMU`, `SSF`, `TSF`, `TTF`, `UMF`, `UMU`, `USF`). Parcel delta: 18,401 unclear→classified. Refresh: partial, 172 remaining unclear rows, 67,386 remaining unclear-bound parcels.
- **APPLY+REFRESH** Norfolk County, MA. Lane E. `pattern_norfolk_ma_adjudication.py` applied 12 ordinance-cited residential short-code rows (`G`, `GR`, `S`, `S-7`, `S1`, `S10`, `S15`, `S2`, `S25`, `S40`, `T-5`, `T-6`). Parcel delta: 16,489 unclear→classified. Refresh: partial, 88 remaining unclear rows, 14,638 remaining unclear-bound parcels.
- **MERGED** PR #95 `feat(matrix): Loudoun VA + Howard MD unclear-row cleanup` after Lane E correction/rebase and passing CI. Prod apply/refresh had already completed from the patched branch; branch deletion failed locally only because another worktree still held the source branch.
- **AUDIT** `backend/tmp/audit_post_truthfulness.json` generated after PR #98. Lane A. Verified 45 operational / 29 partial / 7 not_loaded / 81 total; zero operational jurisdictions have parcel zoning-code coverage below 70%. Same-audit old readiness logic would have reported 49 operational.
- **MERGE+VERIFY** PR #98 `fix(audit): require 70% parcel zoning coverage for operational` merged as `a29b86eeb301117138b4ca1e8fe0ebc347aa92f9`; Railway `/health.pipeline_version` reports `a29b86eeb301`. Lane A. Demoted Bergen County NJ, Draper City UT, Essex County NJ, and Montgomery County PA from operational to partial.
- **MERGE+VERIFY** PR #92 `fix(deploy): re-enable Vercel git deployments` merged as `ba7a9582d1207aa02849fbc3ebcf267be571257c`. Lane A. Vercel deploy workflow run `26466874832` completed successfully for the main push; production frontend returned HTTP 200 from Vercel.
- **MERGE+VERIFY** PR #94 `fix(pipeline): non-fatal flood + wetland overlays (match AADT containment pattern)` merged as `116dd4e1fc45f340649801fc02c4b608ed41e659`; Railway `/health.pipeline_version` reported `116dd4e1fc45` before subsequent main merges. Lane A. Historical overlay-fatal failures remain in the 14-day failed-job window; new retries should no longer fail the whole job on flood/wetland overlay errors.
- **APPLY+REFRESH** Somerset County, NJ. Lane E. `somerset_nj_matrix_adjudication.py` applied 13 ordinance-cited rows (`EP-250`, `G-B`, `LD`, `LD-1`, `LD-3`, `PAC`, `S-100`, `S-50`, `S-60`, `S-75`, `S-80`, `S-C-V`, `SMD`) via session-mode DB endpoint. Parcel delta: 10,567 unclear→classified. Refresh: operational, 66 remaining unclear rows, 2,194 remaining unclear-bound parcels.
- **APPLY+REFRESH** Loudoun VA + Howard MD cleanup. Lane E. PR #95 corrected before apply: `TOWNS` and `PUD-1` left unclear; `C1`, `PDCH`, `PUD` classified conditional with cited Loudoun ordinance sources. Loudoun parcel delta: 63 unclear→classified; operational did not flip (partial, high unclear share from `TOWNS`). Howard `2R0` and `OT` reviewed and left unclear; parcel delta 0; operational remains true.
- **RUNPATH** Railway CLI still unavailable locally (`invalid_grant` / no linked project). Lane E used the configured Supabase session-mode DB endpoint for apply/refresh because the transaction pooler rejects asyncpg prepared statements.
- **MERGED** PR #97 `feat(ops): queued-job watchdog cron` into `main` as `2e8d9e0`. Lane D. Main CI passed and Railway web `/health` + `/api/debug/env` report `pipeline_version: 2e8d9e09fcbf`; Railway cron service log verification is blocked locally because `railway logs` returns `invalid_grant` / `Unauthorized` until `railway login` is refreshed.
- **OPEN** PR #97 `feat(ops): queued-job watchdog cron`. Lane D. Adds `backend/scripts/queued_job_watchdog.py` with 0/1/2 exits and updates `backend/railway-cron.toml` so the queued-job watchdog runs every 10 minutes while the daily digest still runs during the 12:00 UTC hour.

### 2026-05-21 (Phase 1 close / Phase 2 sprint kickoff)

- **OPEN** PR #94 `fix(pipeline): non-fatal flood + wetland overlays (match AADT containment pattern)`. Lane A. KPI refs: Tier-2 #5 failed jobs/14d and Tier-2 #8 overlay correctness. Contains flood and wetland exceptions individually so one failed overlay emits a warning but does not fail the whole post-ingest job.
- **FOLLOW-UP** Stored job tracebacks are capped/truncated at 2048 chars for the overlay failure cluster. Logged for later operational diagnostics; not bundled with PR #94.
- **FOLLOW-UP** `POST /api/admin/jurisdictions/{id}/refresh-bbox` returns 404 on prod for Lane C bbox sweep. Separate investigation; not bundled with PR #94.
- **OPEN** PR #91 `feat(matrix): Somerset NJ adjudication — 13 unclear rows → prohibited/conditional`. Lane E. Adds `backend/scripts/somerset_nj_matrix_adjudication.py`; dry-run moves 10,567 parcels unclear→classified. No Railway run or coverage refresh yet.
- **VERIFY** Railway prod is running PR #89 commit `9fed01293aae` (`pipeline_version: 9fed01293aae` from `/health` and `/api/debug/env` at 2026-05-21 22:18 UTC). Lane A. B1 deploy verified; commit age was ~17 minutes at check time.
- **RESOLVE** Burlington County, NJ active failure cluster moved out of section 8. Latest forced rerun `9617a23c-330d-42f5-bacf-fb5a04a7c401` reached `ready` after PR #85; no duplicate boundary PR opened.
- **MERGE** PR #89 `fix(audit-cli): disable statement_timeout for full-sweep against prod-scale data` (`9fed012`). Lane A. Closes B1. Audit CLI now runs full-sweep against prod-scale.
- **MERGE** PR #90 `feat(allentown-2025): apply 2025 ordinance verdicts + ship vocabulary_aliases table`. Lane E. Allentown PA flipped operational (18/18 human-reviewed, 0 unclear, 100% zoned).
- **[DRIFT-LOG]** PR #90 introduced new `vocabulary_aliases` table. Underlying adjudication is in scope; the new table is an architectural addition that wasn't pre-flagged in plan. Logged for governance review at sprint close — not rolled back.
- **VERIFY** PR #85 (`3e104ad fix(pipeline): widen merge + coverage-refresh timeouts for large-county boundary`) verified in prod. Burlington job `9617a23c` reached `ready`, 174,852 parcels ingested in 13 minutes. Burlington failure loop closed.
- **BOOTSTRAP** docs/PHASE2_PROGRESS.md (this file). Master thread.
- **AUDIT** `tmp/audit_cli_after.json` generated post-PR-#89. New verified baseline: 48 op / 26 partial / 7 not_loaded / 81 total.
- **RECLASSIFY** Burlington County, NJ → Category B (structural coverage). 174,852 parcels ingested but only 1 has zoning_code. County has no county-level zoning layer; path is per-town ingest (Westampton pattern).
- **[DRIFT-LOG]** Hot Deals v2 (#79) + buybox maxTotalPrice (#84) shipped operator-surface features. Section 7 #4 violation. Logged for PR-template enforcement going forward.
- **[DRIFT-LOG]** alias_mappings framework (#86). Section 7 #3 violation. KPI move was real; logged.

### 2026-05-19/20 (pre-Phase-2; for context)

- Howard MD: 95.6% canonical coverage, NT FDP-container verdict, M-1/M-2 PERMITTED via §122.0.B.60. Lane E.
- Loudoun VA: 100% current-LCZO coverage, 1993→LCZO crosswalk of 18 legacy codes, reviewer Chrome corrections + sub_areas_eligible column. Lane E.
- NJ county registry expanded: Burlington/Ocean/Bergen/Somerset registered. Lane B.
- 0029 zone_matrix_soft_delete migration. Plan/structural.
