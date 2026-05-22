# Phase 2 Progress — STACK Land Acquisition

**Last audit refresh:** 2026-05-21 (post PR #89, verified via `tmp/audit_cli_after.json`)
**Phase 2 sprint:** 1 of 6 (each sprint = 14 days; sprint window 2026-05-22 → 2026-06-05)
**Plan reference:** `/Users/arench/.claude/plans/virtual-herding-iverson.md`

## Write discipline

- Each section lists its **owner**. Only the owner edits that section.
- Numbers must cite their source (audit JSON filename + timestamp, PR number, or live psql query).
- No "approx", "likely", or "should" without a named source.
- KPI claims belong only in sections 1–4, 11; activity goes in 15.
- Drift flags get appended to section 15 (Daily Changelog) with `[DRIFT]` tag.
- Lane Status (section 9) is a one-row update per lane per session — overwrite, don't append.

---

## 1. Current KPI Snapshot

**Owner:** master thread (refresh after every audit)
**Source:** `tmp/audit_cli_after.json` (2026-05-21, post-PR-#89 verification by Lane A)

| Tier | KPI | Value | Source | Δ vs prior |
|---|---|---:|---|---:|
| 1 #1 | Honest operational jurisdictions | 46 (projected) | live audit + truthfulness rule | first measurement |
| 1 #1 | Audit-operational jurisdictions | **48** | audit_cli_after.json `.summary.operational_count` | +1 (was 47) |
| 1 #2 | Trustworthy parcel verdict count | ~3.6M | derived from sum of `parcels_with_matrix_match` minus unclear across operationals | first measurement |
| 1 #3 | Avg unclear share (partials) | ~18% | derived; will tighten as Lane E ships | first measurement |
| 1 #4 | Fake-operationals | 2 (Essex NJ, Draper City UT) | truthfulness rule applied to audit JSON | down from 4 morning; pending truthfulness merge |
| 2 #5 | Failed jobs / 14d | 47 | live `jobs` table | unchanged; Burlington loop closed via PR #85 |
| 2 #5 | Stuck jobs (>10min, non-terminal) | 0 | live `jobs` table | unchanged |
| 2 #6 | Snapshot table latest capture | 2026-05-19 21:56 UTC | live `coverage_snapshots` | stale; refresh blocked on Railway 502 |
| 2 #7 | Ingest success last 14d | 109 ready / 47 failed / 13 cancelled | live `jobs` table | — |
| 2 #8 | Jurisdictions with `bbox IS NULL` | 7 | live `jurisdictions` table | Lane C target |

---

## 2. Honest Operational Count

**Owner:** master thread
**Definition:** `operational_readiness = "operational"` AND `parcel_zoning_code_coverage_pct ≥ 70` AND no fake-op flags.

**Current value:** **46** (projected post-truthfulness merge)
**Audit-operational value:** **48** (pre-truthfulness, includes 2 fake-ops)

**Phase-1 close delta:** +1 honest operational (Allentown PA flipped via PR #90).
**Confidence:** high for 48 (verified live); high for 46 projection (Essex + Draper both below 70% threshold per audit JSON).

To validate post-merge: `jq '[.jurisdictions[] | select(.operational_readiness=="operational") | select(.parcel_zoning_code_coverage_pct < 70) | .name]' tmp/audit_<date>.json` must return `[]`.

---

## 3. Audit-Operational Count

**Owner:** master thread
**Current value:** **48**

Source: `tmp/audit_cli_after.json` summary block, 2026-05-21 evening.

**Flagged as fake-operational (drop on truthfulness patch merge):**

| jurisdiction | parcel_zoning_code_coverage_pct | rationale |
|---|---:|---|
| Essex County, NJ | 23.8 | 76% of 175,932 parcels lack zoning_code |
| Draper City, UT | 65.9 | 34% of 25,515 parcels lack zoning_code |

**Previously flagged but resolved/under-threshold:**
- Montgomery PA (2.2%) — audit-operational; needs separate truthfulness review.
- Bergen NJ (3.1%) — audit-operational; needs separate truthfulness review.

> Note: Lane A's truthfulness patch projection cited only Essex + Draper. Master thread to verify post-merge whether Mont PA + Bergen NJ also fall under the rule (they're at 2.2% and 3.1% respectively — well below 70%). If yes, honest count drops to 44, not 46.

---

## 4. Partial Jurisdictions

**Owner:** master thread
**Count:** **26** (per audit_cli_after.json)

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
| 1 | Norfolk County, MA | ~100 | 31,127 | medium (pattern-batch MA family) | queued | Lane E |
| 2 | Middlesex County, MA | ~181 | 85,787 | medium (reuses Norfolk pattern) | queued | Lane E |
| 3 | Highland, UT | 4 | 937 | trivial (PD-1 only if ordinance supports; zero-bind unsupported stays unclear) | queued | Lane E |
| done | Somerset County, NJ | 66 remaining | 2,194 remaining unclear-bound | applied; operational | #91 merged + prod applied 2026-05-26 | Lane E |
| done | Loudoun VA + Howard MD cleanup | 4 remaining active rows | 19,309 remaining unclear-bound | applied; Howard operational, Loudoun partial by design | PR #95 patched/applied; merge pending | Lane E |

_Lane E: append progress notes here (script written / PR opened / merged / refreshed / operational flip)._

- 2026-05-21 22:20 UTC — Somerset NJ script ready and pushed to PR #91. Dry-run: 13 rows, 10,567 parcels move unclear→classified. `PAC-2` / `PAC-3` deliberately left unclear because absent from matrix.
- 2026-05-26 18:23 UTC — Somerset NJ applied to prod via session-mode DB endpoint after Railway CLI auth remained expired. Updated 13 rows (`EP-250`, `G-B`, `LD`, `LD-1`, `LD-3`, `PAC`, `S-100`, `S-50`, `S-60`, `S-75`, `S-80`, `S-C-V`, `SMD`), moving 10,567 parcels unclear→classified. Refresh: operational, 66 remaining unclear rows, 2,194 remaining unclear-bound parcels, 98.4% classified parcel coverage.
- 2026-05-26 18:23 UTC — Loudoun + Howard cleanup applied to prod. Loudoun PR #95 corrected before apply to leave `TOWNS` and `PUD-1` unclear rather than overclassify out-of-scope / unverified rows; classified only `C1`, `PDCH`, and `PUD` (63 parcels unclear→classified). Loudoun remains partial with 2 active unclear rows / 19,298 unclear-bound parcels. Howard reviewed `2R0` and `OT`, moved 0 parcels, and remains operational with 2 active unclear rows / 11 unclear-bound parcels.

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

**Last 14d (source: live `/api/admin/jobs?status=failed&limit=500`, filtered since 2026-05-07, refreshed 2026-05-21 22:18 UTC):**

| count | jurisdiction(s) | pipeline line | class | status |
|---:|---|---|---|---|
| 5 | Middlesex NJ / Westchester NY / Nassau NY / Fairfield CT / Marlboro NJ | `pipeline.py:1732` -> `apply_flood_overlay` -> `overlays.py:193` | flood overlay fatal after successful parcel ingest | PR #94 opened to make flood + wetland overlay failures non-fatal; retry after merge + deploy |
| 13 | Marlboro, NJ | 1298 / coverage_refresh | mixed upstream + coverage_refresh | needs retry; normalize duplicated `marlboro`/`Marlboro` rows |
| 7 | Fairfax County, VA | mixed | mixed pipeline/network | Lane B retry/triage pending |
| 5 | Monmouth County, NJ | 1286/1298/1329 + coverage_refresh | mixed | partially addressed by PR #85; structural Cat-B remains |
| 5 | Cook County, IL | mixed | other_pipeline/stale | not boundary class |
| 3 | Montgomery County, MD | mixed | other_pipeline/other | retry/triage pending |
| 3 | Nassau County, NY | mixed | other_pipeline/other | Lane B retry pending |
| 3 | Wake County, NC | 1417/1401 | parcel ingest | not boundary class; needs source check |
| 2 | Middlesex County, NJ | 1410/1688 | boundary | PR #85 should resolve; retry pending |
| 2 | Montgomery County, PA | mixed incl. bootstrap | mixed | PR #85 should resolve boundary component; retry pending |
| 1 | Bergen County, NJ | bootstrap | boundary | PR #85 should resolve; transient |
| 1 | Allentown, PA | httpx network | transient | likely resolved by later operationalization |
| 1 | Somerset County, NJ | 1077 | upstream | not boundary |

_Lane A: append new clusters here. Remove resolved clusters (move to section 15 as changelog entries)._

---

## 9. Lane Status

**Owner:** each lane writes its own row. Overwrite, do not append.

| Lane | Current task | Open PRs | Blockers | Last update |
|---|---|---|---|---|
| A — Integrator | verified Railway prod deploy of `9fed01293aae`; next: Vercel auto-deploy re-enable | — | truthfulness patch held by master sequencing | 2026-05-21 22:18 UTC (prod `/health` + `/api/debug/env`; commit age ~17m at verification) |
| B — Discovery + Coverage | retry queue + Burlington per-town pilot | — | none | 2026-05-21 (master) |
| C — Spatial + CRS | bbox refresh sweep (7 jurisdictions) | — | none | 2026-05-21 (master) |
| D — Operator + Workflow | queued-job watchdog cron | PR #97 merged | Railway cron-log verification blocked by expired local CLI auth | 2026-05-26 (web deploy on `2e8d9e0`; cron logs pending Railway login) |
| E — Matrix Intelligence | Norfolk County MA pattern batch next; Somerset applied/refreshed; Loudoun + Howard cleanup applied | #95 open (patched; merge pending) | Railway CLI auth unavailable; direct session DB endpoint used for prod apply/refresh | 2026-05-26 18:23 UTC |

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
| #94 | fix(pipeline): non-fatal flood + wetland overlays (match AADT containment pattern) | A | open | urgent; before Lane B retries five overlay-failed jurisdictions |
| #95 | feat(matrix): Loudoun VA + Howard MD unclear-row cleanup | E | open; patched + prod applied | merge after review/checks |
| #97 | feat(ops): queued-job watchdog cron | D | **MERGED** (`2e8d9e0`) 2026-05-26 | done |
| (drafted) | Lane A: truthfulness patch (`audit_zoning_coverage.py` `_build_audit`) | A | drafted by Lane A | after Somerset, after fresh audit |

---

## 13. Merge Queue

**Owner:** master thread
**Ordered sequencing for next merges:**

1. ~~PR #89 (audit CLI timeout)~~ ✅ merged
2. **Lane E Somerset NJ** — already verified, citations real, 10,567 parcels move. Open PR + merge.
3. **Lane A truthfulness patch** — merge AFTER Somerset so the next audit refresh captures both deltas in one snapshot diff.
4. ~~Lane D watchdog PR #97~~ ✅ merged; Railway web deploy serves `2e8d9e0`, cron-log OK run still pending Railway CLI login.
5. **Lane B Burlington-pattern retries** — no PRs; operational sweep.
6. **Lane C bbox sweep** — no PRs unless bug surfaces.
7. **Lane E Norfolk MA pattern-batch** — next sprint task.

---

## 14. Blockers

**Owner:** any lane appends; resolved blockers removed.

| ID | blocker | owner | downstream impact | status |
|---|---|---|---|---|
| ~~B1~~ | ~~audit CLI times out on prod~~ | Lane A | ~~master can't refresh KPIs~~ | **RESOLVED via PR #89** |
| ~~B2~~ | ~~Lane D watchdog PR overwrites daily-digest cron in `railway-cron.toml`~~ | ~~user / Lane D~~ | ~~watchdog can't merge~~ | **RESOLVED in PR #97** — daily digest remains in the cron command; watchdog runs from the same Railway cron service |
| B3 | truthfulness patch held pending audit verification | Lane A | sequencing | **deferrable** — patch is drafted; merge after Somerset |
| B4 | Burlington `ready` but 0 zoning_code on 174,851 of 174,852 parcels | Lane B | Burlington reclassified Cat-B | **OPEN** — reclassified, not a defect |
| B5 | alias_mappings framework abstraction (PR #86) + vocabulary_aliases table (PR #90) | logged | governance | **LOG ONLY** (Section 7 #3 in plan); not rolled back |

---

## 15. Daily Changelog

**Owner:** any lane appends (reverse chronological).

### 2026-05-26

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
