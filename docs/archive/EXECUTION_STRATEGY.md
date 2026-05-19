# Parallel Claude Code Execution Strategy — Zoning Intelligence Platform

**Drafted:** 2026-05-14 · **Reframed:** answers the actual question — how should one principal operator (Adam) run multiple parallel Claude Code sessions against this repo?
**Assumption baseline:** Adam is sole integration owner. Claude sessions are disposable workers. No autonomous deploy. Adam reviews every diff before merge.

---

## Context

The audit shows the platform is at a complexity where the bottleneck has shifted from "what to build" to **"how fast Adam can dispatch + review work."** Single sequential Claude sessions are leaving capacity on the table because:

- Each session that touches a different surface (`zoning_discovery.py` vs `frontend/app/admin/*` vs `scripts/`) blocks none of the others.
- Long-running Claude sessions degrade as the context fills with old tool output — quality drops 30k tokens in.
- The roadmap has at least 6 discrete in-flight workstreams (NYC matrix, NJ aggregator, Discovery Bugs 1/2, Phase 2/3 cherry-pick, admin UI, coverage-snapshot bug) — most are file-isolated from each other.

The prior plan was rejected for treating Claude as a teammate-with-identity. Correct mental model: **Claude sessions are jobs, not employees.** Spawn one per discrete task with a tight scope, let it work in an isolated worktree, review its diff, merge or discard, then dispose of it.

---

## Section 1 — Is parallel Claude execution actually warranted?

**Yes — moderately, not aggressively.**

Signals from the audit that support parallel execution:

1. **6+ workstreams sit in non-overlapping files.**
   - NYC matrix mapping → new data files + `matrix_zones` table writes
   - NJ state aggregator → net-new file under `backend/app/services/`
   - Discovery Bugs 1/2 → confined to `zoning_discovery.py::_name_match_signals`
   - Phase 2/3 cherry-pick → `pipeline.py` + `ingestion.py` (one session)
   - Admin UI → greenfield under `frontend/app/admin/*`
   - Coverage-snapshot zero-population bug → single function in coverage refresh

2. **Hot files are concentrated and identifiable.** `jurisdictions.py` (13/100 commits), `zoning_discovery.py` (9), `pipeline.py` (6), dashboard page (7). The conflict surface is small and well-bounded — easy to enforce "one session at a time on these."

3. **Migration writes are the only true serialization point.** Everything else can parallelize with hygiene.

4. **Frontend admin UI is pure greenfield.** Zero conflict with any backend session, ever. This is a "free" lane.

5. **Adam already has a Mac that ran the audit cleanly** + a working `~/.claude` agent infrastructure (worktree support, plan mode, subagents). The mechanics are in place.

Signals **against** going aggressive (5+ sessions):

1. **Adam's review bandwidth is the real ceiling.** Three sessions producing PRs faster than he can read them creates the same drift as the 0017 incident — just on a smaller scale. Don't generate more diff than you can audit same-day.
2. **The 0023 alembic collision** happened with only 2 concurrent contributors. Add 3 parallel Claude sessions touching migrations and the collision rate goes superlinear.
3. **Context-window cost**: parallel sessions also cost cache-budget. A session per task means 5x cache misses vs. one long session — but quality-wise that's a feature, not a bug.

**Verdict:** Run **2-3 concurrent sessions max**, with strict rules about which surfaces overlap. Single-thread for hot-backend work; parallel for cold-backend + frontend + docs.

---

## Section 2 — Optimal Claude lane structure

Lanes are **work shapes**, not identities. At any moment, up to 3 sessions can be live:

| Slot | Shape | Max concurrent | Owns (writable surface) |
|---|---|---:|---|
| **Slot 1** | Hot Backend (serialized) | 1 | `backend/app/api/jurisdictions.py`, `backend/app/services/pipeline.py`, `backend/app/services/zoning_discovery.py`, `backend/app/services/ingestion.py`, `backend/app/services/zoning_system.py`, `backend/app/services/spatial_backfill.py`, `backend/alembic/versions/*` |
| **Slot 2** | Cold Backend (parallel-safe) | 1-2 | Net-new files under `backend/app/services/`, `backend/scripts/*`, `backend/app/api/debug.py` (with care), `backend/app/data/*`, isolated functions in `backend/app/services/coverage_*` |
| **Slot 3** | Frontend (parallel-safe) | 1 | `frontend/app/admin/*` (greenfield), `frontend/components/admin/*`, new pages, additive types in `frontend/lib/api.ts` |
| **Slot 4 (optional)** | Doc / Status (lightweight) | 1 | `STATUS.md`, `ORPHAN_BRANCH_AUDIT.md`, `BERGEN_SCALE_UP.md`, `MIGRATION_RESERVATIONS.md`, plan files |

**Rules for the slots:**

1. **Slot 1 is single-threaded.** Never run two sessions that touch hot-backend files at the same time. Queue them.
2. **Slot 2 can have two sessions** only if their target files are truly non-overlapping (e.g. one writes `backend/app/services/nj_state_aggregator.py`, the other writes `backend/scripts/build_nyc_matrix.py`).
3. **Slot 3 is always safe** to run alongside any backend session because `frontend/app/admin/*` doesn't exist yet — pure greenfield.
4. **Slot 4 is for short bursts** (10-30 min) — STATUS.md regen, audit refresh, plan drafting. Doesn't block anything.

**Worktree isolation is mandatory.** Each session runs in its own `git worktree` so file-system level conflicts are impossible:

```bash
# spawn pattern
git fetch origin
git worktree add ~/work/zoning/wt-nyc-matrix -b feat/nyc-matrix-mapping origin/main
cd ~/work/zoning/wt-nyc-matrix && claude
# (work happens; Adam reviews; merge to main; push)
git worktree remove ~/work/zoning/wt-nyc-matrix
git branch -D feat/nyc-matrix-mapping  # optional cleanup
```

**Every session starts in plan mode.** Hard rule. The first prompt to each session is the scoped task description ending with `/plan`. Adam reviews the plan, then approves via ExitPlanMode. Plans become the contract between Adam and the disposable session.

**Execution after plan approval is synchronous within the session.** Don't let a session sit idle between plan and execution — it'll burn cache and forget context.

---

## Section 3 — Hot-file conflict analysis

Based on `git log --oneline | head -100` from the audit:

### Hot zone — single-session-at-a-time

| File | Edits / last 100 commits | Why it's hot |
|---|---:|---|
| `backend/app/api/jurisdictions.py` | 13 | Every new operator endpoint lands here |
| `backend/app/services/zoning_discovery.py` | 9 | Scoring v2 + Bug 1/2 + bbox + denylist all funnel here |
| `frontend/app/dashboard/[jobId]/page.tsx` | 7 | Primary user surface; lots of features attach |
| `backend/app/services/pipeline.py` | 6 | Ingest orchestration; cherry-pick target |
| `backend/app/api/parcels.py` | 6 | Parcel-drawer / value-density work |
| `backend/app/api/debug.py` | 6 | Diagnostic endpoint creep |
| `backend/app/services/buybox_scoring.py` | (medium) | Listings + value-density both write here |
| `backend/alembic/versions/*` | n/a | **Serialize absolutely** — one collision already (commit `8767150`) |

### Cold zone — safe to parallelize

- `backend/app/services/<new_adapter>.py` — new files
- `backend/scripts/*` — isolated execution scripts
- `backend/app/data/*` — data files (matrix definitions, denylists)
- `backend/app/services/coverage_*.py` — narrow surface
- `frontend/app/admin/*` — does not exist yet
- `frontend/components/admin/*` — does not exist yet
- All `*.md` documentation
- All `tests/*` (with care — if two sessions are testing the same module, they can collide on test files)

### Workstream collision matrix

| Workstream A | Workstream B | Collide? |
|---|---|:---:|
| NYC matrix mapping | NJ state aggregator | No (different files) |
| NYC matrix mapping | Discovery Bug 1/2 | No |
| NYC matrix mapping | Phase 2/3 cherry-pick | **Possibly** (both write `pipeline.py` if matrix work touches ingestion) |
| Discovery Bug 1/2 | NJ state aggregator | No (different functions in same module — but **same file** — still collides) |
| Discovery Bug 1/2 | Admin UI | No |
| Admin UI | Anything backend | No |
| coverage_snapshot bug fix | NYC matrix | No |
| Phase 2/3 cherry-pick | Anything in pipeline.py/ingestion.py | **Yes** |
| Any migration | Any other migration | **Yes always** — serialize |

**Operational rule:** before spawning a session, grep its declared scope against the hot-zone list. If any hot file appears, check Slot 1 is free.

---

## Section 4 — Recommended execution cadence

### Daily rhythm

| Time | Action |
|---|---|
| Morning (5 min) | `git fetch origin && git worktree list` — verify clean state. Spawn Doc slot 4 session: "regenerate STATUS.md from live probes." Review diff, merge, push. |
| Morning + 0:05 | Decide today's workstreams. Spawn up to 3 sessions in their own worktrees with `/plan`-first prompts. |
| Continuous | Review plans as they land. ExitPlanMode → session executes. Review final diff before merge. |
| Per-merge | Push to main. Check Railway/Vercel deploy. Re-verify `/health.pipeline_version` matches the merge SHA within 15 min. |
| End-of-day | List open worktrees: `git worktree list`. Any worktree older than 24h gets a "ship or kill" decision. |

### Weekly rhythm

| Day | Action |
|---|---|
| Monday | Orphan sweep — `git worktree prune`, `git branch -D` the empty `claude/*` branches, audit `git branch -r --merged main` for delete candidates. Pull origin/main into local main checkout to keep it as a reference. |
| Wednesday | Cache-budget check — if multiple sessions are running for >2 hours each, consider shorter scopes next time. |
| Friday | Roadmap reset — read STATUS.md, check `/admin/coverage`, decide next week's queue. |

### Plan mode discipline

- **Every session opens with a scoped prompt + `/plan` at the end** OR Adam types `/plan` immediately to enter plan mode.
- Plan files live at `~/.claude/plans/*.md` and are reviewed before ExitPlanMode is approved.
- A session that doesn't enter plan mode first is treated as a fast turn-around — short, single-edit kind of work only (e.g. "fix this typo," "add this log line").

### Merge strategy

- One PR-equivalent per session. Don't pile multiple session outputs into a single merge.
- Squash-merge to main with the session's primary commit message.
- Push immediately. Railway redeploys backend; Vercel redeploys frontend via the GH Action.
- **Never `railway up` from a worktree.** Reinforced in every session prompt.

### Deploy strategy

- Only one active "deploying" merge at a time. If two sessions finish within 5 minutes of each other, merge them sequentially, with a `/health` check between. (Concurrent merges into main are still fine — but verify deploy completed between them.)
- Each merge gets a 15-min post-deploy verification window before the next merge: `/health`, `/api/debug/alembic-status`, `/api/admin/jobs?stale_only=true`.

### Migration discipline (the one real serialization point)

- A `MIGRATION_RESERVATIONS.md` file in repo root tracks the next available number.
- Before spawning a session that will write a migration, Adam claims the number in that file as a single-commit change (could itself be a Doc-slot session).
- The session's plan file explicitly references the reserved number.
- After the migration lands, the reservation row is closed out.

This prevents the `0023` collision pattern: even if two sessions are alive in parallel, only one is "in flight" for a given migration slot.

### Branch hygiene

- Branch naming: `feat/<short-task>`, `fix/<short-task>`, `chore/<short-task>` — same pattern as existing PRs.
- **No `claude/*` branches.** Those drift and accumulate. Delete the 4 stale ones from prior sessions.
- **No long-lived branches.** If a session needs more than a day, the scope was wrong — split it.
- **Always rebase before merge** to confirm no parallel session moved the target file out from under you.

---

## Section 5 — Fastest path to roadmap completion

### Current bottlenecks ranked by leverage × parallelizability

| # | Bottleneck | Leverage | Slot | Parallel-safe right now? |
|---|---|---|---|---|
| 1 | **NYC zone-use matrix mapping** | 856k parcels unblock | Cold Backend (new data files + scripts) | **Yes** |
| 2 | **NJ state aggregator adapter** | Unlocks all NJ municipal zoning in one source | Cold Backend (new file) | **Yes** |
| 3 | **Discovery Bugs 1+2 (whole-word matching + generic-Zoning penalty)** | Gates every future NJ county sweep | Hot Backend (zoning_discovery.py) | **No** — serial |
| 4 | **Operator admin UI for `/_sources` review** | Multiplies operator throughput | Frontend (greenfield) | **Yes** |
| 5 | **Phase 2/3 county handler cherry-pick** | ~1.5M parcels (Westchester/Nassau/Fairfield/Fairfax/Loudoun/MontMD/HowardMD/MontPA) | Hot Backend (pipeline.py + ingestion.py) | **No** — serial |
| 6 | **coverage_snapshot.source_count_* bug** | Operator dashboard shows zero source counts despite real data | Cold Backend (snapshot refresh fn) | **Yes** |
| 7 | **Cook IL / Wake NC / Williamson TN one-shot ingests** | T0 → T2 unblock | Cold Backend (just submit jobs) | **Yes** (mostly job submission, not code) |
| 8 | **Spatial observability endpoint** | Measures whether pyproj/bbox work landed in prod | Cold Backend (new debug endpoint) | **Yes** |
| 9 | **STATUS.md regen script** | Eliminates daily stale-status risk | Doc / Cold Backend | **Yes** |

### What to parallelize TODAY

**Day-1 simultaneous spawn (3 sessions):**

| Worktree | Slot | Task |
|---|---|---|
| `wt-nyc-matrix` | Cold Backend | Build NYC zone-use matrix from MapPLUTO codes + DCP zoning resolutions. Output: `backend/app/data/matrix/nyc.yaml` + matrix-loader script. No edits to `pipeline.py` or `jurisdictions.py`. |
| `wt-admin-sources-ui` | Frontend | Build `frontend/app/admin/sources/[jurisdictionId]/page.tsx` against existing `/_sources` + `/_review` endpoints. No backend changes. |
| `wt-coverage-snapshot-fix` | Cold Backend | Fix `source_count_*` zero-population in coverage refresh function. Verify Bergen shows real counts. Single file. |

These three do not collide on any file. All three start in plan mode; Adam reviews each plan; each executes independently; merge as they finish.

**Day-2 / next slot (after Day-1 hot-backend slot frees):**

| Worktree | Slot | Task |
|---|---|---|
| `wt-discovery-bugs` | Hot Backend (Slot 1) | Verify and/or fix Bugs 1+2 in `_name_match_signals`. Tight scope: only `zoning_discovery.py` + tests. |
| `wt-nj-aggregator` | Cold Backend | New file `backend/app/services/nj_state_aggregator.py`. Doesn't touch hot files yet; integration happens later. |
| `wt-admin-coverage-ui` | Frontend | Continue admin UI — `frontend/app/admin/coverage/page.tsx`. |

**Day-3:**

| Worktree | Slot | Task |
|---|---|---|
| `wt-phase23-cherrypick` | Hot Backend (Slot 1, sequential after discovery-bugs ships) | Cherry-pick Phase 2/3 ingestion intelligence from `claude/agitated-khayyam-58c0d9`. Land Westchester/Nassau/Fairfield CT ingests. |
| `wt-spatial-stats` | Cold Backend | New `/api/debug/spatial-stats/{id}` debug endpoint. Doesn't conflict with pipeline.py. |
| `wt-admin-jobs-ui` | Frontend | `frontend/app/admin/jobs/page.tsx`. |

### What stays serialized

- **Anything touching `pipeline.py`, `ingestion.py`, `jurisdictions.py`, `zoning_discovery.py`** — one at a time, queued through Slot 1.
- **All alembic migrations** — reserve number in `MIGRATION_RESERVATIONS.md` first.
- **Deploy + verification** — only one merge "deploying" at a time; verify `/health` between.

### Realistic 30-day delta with this cadence

- NYC matrix shipped + verified → `operational_readiness=operational` for NYC.
- 3 NY/CT counties (Westchester, Nassau, Fairfield) ingested.
- 2-4 NJ counties materially zoned via state aggregator.
- 3-4 admin UI pages live (sources, coverage, jobs, progression).
- Bergen re-swept with cleaner scoring; FP rate drops from 40% to <20%.
- STATUS.md is daily-regenerated and trustworthy.
- No new orphan branches; no migration collisions; no deploy drift.

---

## Section 6 — Concrete recommendation

**If this were my repo, I'd run the next 30 days like this:**

### Exact session structure

- **2-3 concurrent Claude Code sessions, max.**
- Each in its own `git worktree`.
- Each starts in plan mode.
- Adam approves plans before execution.
- Adam reviews diffs before merging to main.
- Single-thread the Hot Backend slot; parallelize Cold Backend + Frontend freely.

### Exact merge strategy

- One session = one branch = one PR-equivalent.
- Squash-merge to main.
- Rebase before merge if the session has been alive >4 hours.
- Never `--force` to main.
- Delete worktree + branch immediately after merge.

### Exact deploy strategy

- `git push origin main` is the **only** path to production.
- Railway auto-deploy on main push; Vercel via `.github/workflows/deploy-vercel.yml`.
- Investigate why PRs #28/#29 didn't deploy. Until fixed, treat origin-deploy lag as a recurring risk: check `/health.pipeline_version` after every push.
- Never `railway up` from any worktree.

### Exact integration cadence

- **Per-session:** plan-mode review → execute → diff review → merge → push → 15-min deploy verify.
- **Daily:** morning `git fetch + STATUS.md regen + worktree list audit`. End-of-day "ship or kill" any session older than 24 hours.
- **Weekly:** Monday orphan/branch sweep + roadmap reset.

### Direct answer: "How would you run the next 30 days?"

**Week 1 — clear the foundation**
1. Day 1 — spawn 3 parallel sessions:
   - `wt-status-regen-script` (Cold Backend, small) — write `scripts/regenerate_status.py` that pulls live probes; run it
   - `wt-coverage-snapshot-fix` (Cold Backend) — fix `source_count_*` zero-population
   - `wt-admin-sources-ui` (Frontend) — scaffold the operator review page
2. Day 2 — Discovery Bugs 1+2 in Slot 1 (Hot Backend); continue admin UI; NJ aggregator scaffolding in Cold Backend.
3. Day 3-5 — NYC matrix work in Cold Backend; admin UI second page; lane Slot 1 cycles through Phase 2/3 cherry-pick.
4. Day 6-7 — submit Cook IL / Wake NC / Williamson TN ingests; clean up orphan branches; verify Week 1 deliverables.

**Week 2 — coverage push**
- Slot 1 (Hot Backend): NYC matrix integration into ingestion path; Westchester/Nassau/Fairfield ingest using cherry-picked Phase 2/3 handlers.
- Slot 2 (Cold Backend): NJ state aggregator MVP shipping; spatial observability endpoint.
- Slot 3 (Frontend): admin/coverage page + progression view.

**Week 3 — NJ scaling**
- Slot 1: NJ muni-loop runs powered by state aggregator — Hudson, Morris, Union, Passaic.
- Slot 2: Discovery scoring v2.1 polish based on re-swept Bergen data.
- Slot 3: admin/jobs page (kill/retry/force-rerun UI).

**Week 4 — polish + verify**
- Slot 1: long-tail jurisdictions (Hunterdon, Monmouth tail, MA counties).
- Slot 2: edge-case fixes from operator feedback.
- Slot 3: dashboard polish + retrospective.

**Throughput math:** 3 sessions × ~5 working days/week × 4 weeks ≈ 60 session-units of work. Realistic completion rate is 0.5-1 task per session (some take multiple sessions). Expect ~30-50 substantive code changes in 30 days. That is **3-5× single-thread velocity** at the cost of Adam reviewing ~3 PRs/day instead of 1.

### Hard rules — non-negotiable

1. **No `railway up`** from any worktree. Push-to-main is the only deploy.
2. **No two sessions touching hot files simultaneously.** Slot 1 is serial.
3. **No migration writes without `MIGRATION_RESERVATIONS.md` claim.**
4. **No worktree lives > 7 days.** Ship or kill.
5. **Every session starts in plan mode.** No exceptions for non-trivial work.
6. **Pull origin/main into your reference checkout daily.** The current 47-commit local drift is the cautionary tale.

---

## Critical files referenced

| Purpose | Path |
|---|---|
| Hot backend surface (Slot 1) | `backend/app/api/jurisdictions.py`, `backend/app/services/{pipeline,ingestion,zoning_discovery,zoning_system,spatial_backfill}.py` |
| Migration directory | `backend/alembic/versions/` |
| Migration reservations (proposed new file) | `MIGRATION_RESERVATIONS.md` |
| Cold backend surface (Slot 2) | `backend/app/services/<new_files>`, `backend/scripts/*`, `backend/app/data/*` |
| Frontend greenfield (Slot 3) | `frontend/app/admin/{sources,coverage,jobs}/` |
| Status + audit files (Slot 4) | `STATUS.md`, `ORPHAN_BRANCH_AUDIT.md`, `BERGEN_SCALE_UP.md` |
| CI / deploy | `.github/workflows/ci.yml`, `.github/workflows/deploy-vercel.yml` |
| Health probes | `https://capable-serenity-production-0d1a.up.railway.app/{health,api/debug/alembic-status,api/admin/jobs}` |
| Frontend URL | `https://zoning-finder.vercel.app` |

---

## Example session prompts (copy-paste templates)

### Slot 1 (Hot Backend) — Discovery Bugs 1+2

```
You are working in a fresh git worktree at ~/work/zoning/wt-discovery-bugs.

Task: Verify whether Bug 1 (substring matching) and Bug 2 (generic Zoning layer dominating)
documented in BERGEN_SCALE_UP.md are still present in
backend/app/services/zoning_discovery.py::_name_match_signals and
_score_candidate. If present, fix them:

- Bug 1: replace substring `token in word` with whole-word regex `\b{token}\b`
- Bug 2: clamp confidence ≤ 50 for layers whose normalized title is exactly "Zoning"
  unless the FeatureServer parent URL contains a token from the jurisdiction's
  name_tokens.

Constraints:
- Only edit zoning_discovery.py and its test file backend/tests/test_zoning_discovery_scoring.py
- Do not touch pipeline.py, jurisdictions.py, ingestion.py
- Do not write migrations
- Run existing tests; add tests for both fixes

Begin in plan mode (/plan).
```

### Slot 2 (Cold Backend) — coverage_snapshot fix

```
You are working in a fresh git worktree at ~/work/zoning/wt-coverage-snapshot-fix.

Task: Fix the coverage_snapshot.source_count_* zero-population bug. The
GET /api/admin/coverage endpoint returns source_count_total/verified/rejected/pending
as 0 for every jurisdiction, but GET /jurisdictions/{id}/_sources returns real rows
(Bergen has 200 sources with 81 rejected). The refresh function isn't joining
zoning_sources properly.

Investigate the refresh path (likely in backend/app/services/coverage_*.py or
similar). Fix the join. Verify via:
  curl https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage
showing nonzero source_count_* for Bergen (jurisdiction_id=4bf00234-...).

Constraints:
- Only edit the coverage refresh function and its tests
- Do not touch pipeline.py, jurisdictions.py, zoning_discovery.py
- No migrations

Begin in plan mode (/plan).
```

### Slot 3 (Frontend) — admin/sources UI

```
You are working in a fresh git worktree at ~/work/zoning/wt-admin-sources-ui.

Task: Build frontend/app/admin/sources/[jurisdictionId]/page.tsx that calls
GET /api/jurisdictions/{id}/_sources, renders a table of sources with their
confidence_score, confidence_label, confidence_breakdown, and offers
per-row verify/reject actions via POST /_sources/{sid}/_review.

Also support bulk-review via POST /_sources/_bulk-review.

Constraints:
- ONLY edit files under frontend/app/admin/sources/ or frontend/components/admin/
- May add types in frontend/lib/api.ts by addition only — no breaking changes
- No backend code changes. If a backend bug is found, write it down in a follow-up note.
- Use the existing shadcn/ui components in frontend/components/ui/ where possible.

Begin in plan mode (/plan).
```

### Slot 4 (Doc) — STATUS.md regen

```
You are working in the main checkout. Quick task — no worktree needed.

Task: Regenerate STATUS.md from live probes. Pull:
- `git rev-parse HEAD` and `git rev-parse origin/main`
- `git rev-list --left-right --count main...origin/main`
- curl https://capable-serenity-production-0d1a.up.railway.app/health
- curl https://capable-serenity-production-0d1a.up.railway.app/api/debug/alembic-status
- curl https://capable-serenity-production-0d1a.up.railway.app/api/admin/jobs?stale_only=true&limit=20
- ls backend/alembic/versions/

Rewrite STATUS.md with current snapshot. Keep the historical incident notes from
the prior version. Commit + push.

You can skip plan mode for this — it's a single file with clear inputs.
```

---

## Verification — operational tests for this plan

1. **End of week 1:** at least 4 distinct branches merged to main via this workflow. `git worktree list` shows ≤ 3 active. No `claude/*` orphans accumulated.
2. **End of week 2:** Discovery scoring v2.1 deployed; Bergen re-sweep shows FP rate < 20%. Admin UI sources page is live at `https://zoning-finder.vercel.app/admin/sources/{id}`.
3. **End of week 3:** NYC `matrix_zone_count > 0` in `/api/admin/coverage`. `/health.pipeline_version` always matches `origin/main` HEAD within 15 min of any push.
4. **End of week 4:** Two additional NJ counties at >30% zoning coverage. No migration collisions. No `railway up`-from-local events.
5. **Per-day audit:** `git worktree list` + check no worktree older than 24 hours. If something's lingering, ship or kill — don't let it become the next orphan branch.

---

## What NOT to do (the failure modes this avoids)

- ❌ Spawn 5+ sessions and watch review bandwidth saturate while diffs pile up unreviewed.
- ❌ Run two sessions both editing `zoning_discovery.py` (or any hot file) "in parallel" — they will collide.
- ❌ Skip plan mode "for speed" on a multi-file change — that's how scope creeps and quality drops.
- ❌ Let a worktree live for a week — it accumulates the same drift as a feature branch.
- ❌ Keep multiple plan files alive without acting on them — turn into stale `~/.claude/plans/*.md` litter.
- ❌ `railway up` from a worktree to "test in prod" — this is exactly what caused the 58-hour outage.
- ❌ Trust a session's "I'm done" without reading the diff. Disposable workers ≠ trusted owners.
