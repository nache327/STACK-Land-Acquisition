# Discipline-Catch Ledger — ParcelLogic

Canonical reference for caught-before-damage operational failures. Each was a pipeline layer that
**looked done but wasn't audited**; a direct check (usually a `SELECT` or a source-of-truth query)
surfaced the gap before it shipped. This doc is the institutional-knowledge version of the running
ledger in agent memory (`feedback_discipline_catch_ledger`).

## The two standing rules (what every catch distills to)
1. **Audit every new layer before calling it production-complete.** After any deploy/fix, verify the
   *effect* at the source of truth (query the rows that changed, the timestamp that moved) — not just
   that code merged. For multi-service infra (web + worker + cron), confirm EACH service deployed.
2. **Verify assumed state against actual state before generating creation actions.** Before any
   INSERT / register / "create X" / "start a sprint", run a `SELECT` first. Prefer ALTER/UPSERT over
   INSERT. Extends to: verify *all* stages (zoning AND listings), and the right *entity* (zoning
   municipality, not postal city).

## Layer progression (the shape of the failures)
schema → mapping → seeding → coverage → sequencing → idempotency → type system → naming →
migration-auto-apply → **multi-service-deploy** → **existing-state-check** → **full-stage-check**.

Catches **#1–#9** are the early layers (schema/mapping/seeding/coverage/sequencing/idempotency/
type-system/naming) — surfaced during the initial NJ/UT build-out and folded into the progression
above; not individually re-documented here. Catches **#10 onward** are individually recorded below.
(#14, #15, #19 numbers were not individually logged — gaps, not omissions.)

---

## #10 — Separate Railway ops-cron deploy gap
**Layer:** multi-service deploy. The digest SQL fix (PR #213) deployed to the web service, but the
digest fires from a SEPARATE Railway cron service (`backend/railway-cron.toml`, `*/10`,
`restartPolicyType=NEVER`) with its own deploy — which kept running stale crashing code.
**Would have shipped wrong:** digest dark 2 days while we believed it fixed. Symptom: frozen
`buybox_filters.last_email_sent_at`. **Where:** `project_phase2_gate_and_precompute_gap` memory.

## #11 — Westchester already registered
**Layer:** existing-state check. Jurisdiction `3e706886` + 257,914 parcels already existed from a
prior session. **Would have shipped wrong:** a duplicate jurisdiction INSERT. **Caught by:**
`SELECT … WHERE name ILIKE '%westchester%'` before generating the register action.

## #12 — Wrong execution mode for long ingest jobs
**Layer:** job execution. Ring-metrics precompute via the public endpoint runs as a FastAPI
BackgroundTask on the WEB dyno; a web restart/deploy kills it silently, orphaning Redis job-state at
`status=running, parcels_written=0` (Bergen stalled 65+ min). **Fix:** run >5-min ingest on the
Dramatiq WORKER path (later: the `_precompute-ring-metrics-worker` HTTP endpoint). **Where:**
`_precompute_worker_trigger.md`.

## #13 — Hand-verdict-over-factory apply direction
**Layer:** idempotency / write-direction. `factory_safe_write` protects the forward direction; the
reverse (hand verdict over a factory row) has a footgun — `create_zone` POST 409s, and
`INSERT … ON CONFLICT DO NOTHING` silently SKIPS, leaving the wrong verdict live. **Fix:**
`ON CONFLICT DO UPDATE … SET human_reviewed=true` (or PATCH-on-409). **Where:**
`_coordination_reverse_direction_check.md`.

## #16 — Precompute tract coverage: presence ≠ completeness
**Layer:** coverage. `ensure_census_tracts` short-circuited on `if existing > 0: return`, but
`existing` counted NEIGHBORING-county tracts already loaded → Westchester loaded 14/~223 tracts
(only 36,588/257,914 parcels ringed). **Would have shipped wrong:** the Maryland statewide bbox would
intersect thousands of pre-loaded tracts and silently skip → partial coverage. **Fix:** always fetch
full bbox set + upsert (PR `parcellogic/precompute-tract-coverage-fix`, +2 tests). Validated on
Howard MD (59/59 tracts). **Where:** `_wc_precompute_coverage_bug.md`.

## #17 — SELECT-before-sprint (MD already ingested)
**Layer:** existing-state check. The Maryland plan scoped a 2–3 week from-scratch ingest sprint; one
`SELECT` showed Howard + Montgomery MD already registered, 91–95% zoned, scored, and (Howard)
36-rows human-verdicted. **Would have shipped wrong:** a redundant multi-week sprint. The real gap
was just precompute. **Where:** `_md_county_crosscheck.md`.

## #18 — Zone-code false-friend (PM ≠ Manufacturing)
**Layer:** naming / semantics. Tewksbury `PM` reads like "Planned Manufacturing" but is the
**Piedmont CONSERVATION district** (§710.2). **Would have shipped wrong:** a manufacturing/storage
verdict on a 5-acre-residential conservation zone. **Rule:** never infer use-class from a letter
code; verify against the ordinance purpose + use list. Same family as Westchester Rye B-5
(generalized class ≠ ordinance grant).

## #20 — SELECT-before-sprint must verify Stage 2 (listings), not just Stage 1
**Layer:** full-stage check. Montgomery MD = 281k parcels + 95% zoned + 29,766 heuristic needles but
**0 CoStar listings** → `requireListed=true` ⇒ 0 digest surfacing. **Would have shipped wrong:** a
~1-day verdict+precompute sprint that harvests nothing. **Sprint-ready now requires:** (a) human
matrix path, (b) precompute-ready, (c) **CoStar listings ingested+matched**, (d) wealth tier.
**At-scale audit (2026-06-16, `_catch20_audit.md`):** Farmington/Spanish Fork/Pleasant Grove UT are
verdicted+ringed but CoStar-empty (catch-#20 unlocks); St. George/Highland UT need precompute first.

## #21 — Postal city ≠ zoning municipality
**Layer:** naming / entity-resolution. Hunterdon "Flemington I-2" needles carry listing.city=
'Flemington' (postal) but parcel.city='Raritan township' — zoned by Raritan Township (I-2 §296-123),
not Flemington Borough (which has no I-2). **Would have shipped wrong:** a verdict bound to the wrong
municipality's ordinance. **Rule:** ground verdicts against `parcels.city` (zoning jurisdiction),
never the listing's postal city; confirm the muni actually has the zone before fetching its ordinance.

## #23 — Recommendation systems must respect the strategic target universe, not just in-system metrics
**Layer:** strategic alignment (above Stage-1/2/3 sprint-readiness). The catch-#20 audit ranked
CoStar-pull candidates by **raw needle-parcel count** — surfacing Spanish Fork UT (720) and Davis/
Farmington UT as top picks. Both are **out-of-plan** (the 57-pocket plan's only Utah is "Salt Lake/
Summit Park City corridor"), and Spanish Fork isn't even a wealth pocket (HHI ~$83k). **Would have
shipped wrong:** continued CoStar pulls + Nache time on jurisdictions that don't support the
LuxeLocker premium thesis (and indeed yielded 0 wealth-qualified needles). **Fix:** pre-filter audit
recommendations to **IN-PLAN** jurisdictions (per `docs/TARGET_MARKETS.md`) AND wealth-tier-screen
BEFORE ranking. The at-scale audit (`_57_pocket_alignment_audit.md`) also surfaced broad drift: ~45 UT
jurisdictions, NYC (857k), extra NJ counties, Philadelphia, WA spillover — data stays, but
recommendations anchor on the 57. Next in-plan action ≠ biggest in-system number.

## #26 — `git checkout main -- .` to stage off a STALE local main = silent code loss + teammate-file deletion
**Layer:** git/release hygiene. Several PRs this session were committed with a
`git checkout main -- .` prefix (intended to "clean the tree" before `git add`) while **local main
was 31 commits behind origin/main**. Two failures: (a) it **reverted the actual code edits** to
tracked files (jurisdictions.py + job_queue.py) *before* `git add`, so the listing-matcher PR merged
**EMPTY** — only its new test file + ledger doc landed, leaving a **red CI on origin/main** (test
imports an endpoint that doesn't exist) and the prod endpoint 404ing; (b) the stale base meant the
branch's diff vs origin/main showed **7,470 deletions of Adam's files** (WA/Contra Costa ingest,
census.py, OP5 docs) — a merge would have wiped teammate work. **Would have shipped wrong:** broken
main + deleted coordination work, masked as "PR merged." **Fix:** NEVER `git checkout <ref> -- .` to
stage; `git add` only the specific files you edited. **Base every branch on `origin/main`**
(`git fetch && git checkout -b X origin/main`), not stale local HEAD. Verify `git diff --cached --stat
origin/main` shows ONLY your files + zero unexpected deletions before pushing. Recovery: re-applied the
matcher endpoint+actor + factory chokepoint on a fresh origin/main branch (6 files, +293/-1).

## #25 — Web-dyno BackgroundTask wrong mode generalizes beyond precompute (→ listing_matcher)
**Layer:** execution mode (same family as #12, new job class). The listing match+alert cascade runs
in a FastAPI `BackgroundTask` on the WEB dyno (`listings.py::_bg_match_and_alert`). On the Montgomery
MD ingest it **silently stalled** — 224 listings, **0 geocoded/0 matched for 8+ min** under session
load, and even a `_debug-rematch` (also BackgroundTask) didn't execute. **Would have shipped wrong:**
a county ingested but permanently unmatched → 0 harvest, with no error surfaced. **Fix:** built the
worker-path mirror **`POST /jurisdictions/{id}/_match-listings-worker`** + Dramatiq actor
`process_listing_match` + `enqueue_listing_match` (PR `parcellogic/listing-matcher-worker-endpoint`,
+3 regression tests). **Rule: when a >5-min job is found on a web BackgroundTask, build its worker-path
equivalent on first encounter — don't wait for the third.** (Precompute was #12; matcher is #25; the
next job class should ship worker-path from day one.)

## #24 — Single canonical source-of-truth for the strategic target universe
**Layer:** strategic alignment / docs governance. The 57-pocket universe lived in **three
partially-divergent docs** — `docs/TARGET_MARKETS.md` (committed) + two chat-only files
(`outputs/57_KMZ_Wealth_Pockets_Priority_List.md`, `ParcelLogic_Strategic_Memo_WHY_HOW.md`, neither
in the repo). Audits anchored on whichever was in context. **Would have shipped wrong:** the
out-of-plan drift (#23) AND the Burlington in/out ambiguity (committed doc omits it; Nache says it's
Tier-1 #6 per the KMZ list). **Fix:** ONE committed canonical doc, **derived by parsing the 57-polygon
KMZ directly** (the doc's own open TODO), referenced by every audit. Commit the chat-only files so the
universe isn't context-dependent. See `_strategic_docs_reconciliation.md`.

---

## How to use this doc
Before declaring any of these "done", run the source-of-truth check:
- "fix deployed" → query the changed rows / moved timestamp on EVERY service that runs the code.
- "register/create X" → `SELECT` for X first.
- "county is sprint-ready" → check zoning AND matrix AND rings AND **listings** (catch #20).
- "ground a zone verdict" → confirm the **zoning municipality** (parcels.city), not the postal city (#21).
- "presence implies completeness" → count vs the expected total (#16).
