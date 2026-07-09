# Parallel Launch Card — 2026-07-09

Steps 1–2 GREEN (post-deploy verified + sibling linter live). Worktrees scaffolded.
Open 3 Claude Code windows; in each, `cd` to its worktree and paste its mandate.
**One county per session.** Sessions post ambiguities to `outputs/_exception_queue.md`
(shared) and open per-muni PRs; you clear exceptions + merge. Do NOT run two sessions
on the same county.

## Worktrees (already created, each with its own .env incl. REDIS_URL)
```
C:/Users/nache_rl1pdne/zf-middlesex   [parcellogic/middlesex-session]
C:/Users/nache_rl1pdne/zf-norfolk     [parcellogic/norfolk-session]
C:/Users/nache_rl1pdne/zf-lake        [parcellogic/lake-session]
```

## Assignment + first tasks
| Session | County | Open in | First task | Then |
|---|---|---|---|---|
| **A** | Middlesex MA | `C:/Users/nache_rl1pdne/zf-middlesex` | **Warm-up:** wire `scripts/_apply_middlesex_ma_wilmington.py` a `main()` (data module → executable apply, Dedham template; DB already matches, so it's idempotent) → then **Woburn** + **Hudson** (deferred rebinds; add `rebind_configs/<muni>.json` if needed, dry-run→eyeball→apply, Stage-4 paste) | Holliston/Framingham/Tewksbury/Chelmsford tail |
| **B** | Norfolk MA | `C:/Users/nache_rl1pdne/zf-norfolk` | **Norwood** (169) — MAPC rebind-before-paste: add `rebind_configs/norwood.json`, dry-run→eyeball→apply, then auto-fetch use table | **Walpole** (150), then Foxborough/Quincy/Randolph/Sharon/Medfield |
| **C** | Lake IL | `C:/Users/nache_rl1pdne/zf-lake` | **Lake sequence:** `scripts/reclassify_sentinel_codes.py --jurisdiction <lake-jid> --apply INC` (catch #51) → stamp cities via WABBoundaries/1 (`backfill_city_from_boundaries.py`) → county-UDO paste kit (honest yield **LI 148 + II 3**) | Class-B North Shore recon manifest (greenlight-gated) |

## Ready-to-paste per-window prompts (launched 2026-07-09)

### Window A — open in `C:/Users/nache_rl1pdne/zf-middlesex`
```
You are Session A in the parallel muni run. Working dir is this worktree
(C:/Users/nache_rl1pdne/zf-middlesex), branch parcellogic/middlesex-session. Read
docs/PARALLEL_SESSIONS_RUNBOOK.md and follow the per-muni auto-fetch loop for
MIDDLESEX MA ONLY (jid 18a11c2a-4d7d-4725-a643-e40ea2a4e171). Warm-up task: wire
scripts/_apply_middlesex_ma_wilmington.py an idempotent main() (data module ->
executable apply, Dedham template; DB already matches so it just proves the pattern).
Then Woburn and Hudson: add rebind_configs/<muni>.json if needed, dry-run ->
eyeball diff -> apply, then auto-fetch the use table. Ground verdicts with full
discipline (human_reviewed, verbatim citations, 2.3 guards, catch #58 sweep). Fetch
online ordinances yourself; escalate ONLY genuine ambiguities to
outputs/_exception_queue.md (top of OPEN, tag A). Apply muni-scoped, open a per-muni
PR, do NOT re-score until the Middlesex batch is done -- then ONE Middlesex re-score +
`python scripts/postingest_gate.py --jurisdiction 18a11c2a-4d7d-4725-a643-e40ea2a4e171`
(must PASS) + post the distance-to-Loudoun delta. Never touch another county or the
shared docs (paste-kits/manifest/ledger) -- those are integration-owned.
```

### Window B — open in `C:/Users/nache_rl1pdne/zf-norfolk`
```
You are Session B in the parallel muni run. Working dir is this worktree
(C:/Users/nache_rl1pdne/zf-norfolk), branch parcellogic/norfolk-session. Read
docs/PARALLEL_SESSIONS_RUNBOOK.md and follow the per-muni auto-fetch loop for
NORFOLK MA ONLY (jid 6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5). First task: Norwood (169) --
MAPC rebind-before-paste: add rebind_configs/norwood.json, dry-run -> eyeball diff ->
apply, then auto-fetch the use table. Then Walpole (150), then Foxborough/Quincy/
Randolph/Sharon/Medfield. Ground verdicts with full discipline (human_reviewed,
verbatim citations, 2.3 guards, catch #58 sweep). Fetch online ordinances yourself;
escalate ONLY genuine ambiguities to outputs/_exception_queue.md (top of OPEN, tag B).
Apply muni-scoped, open a per-muni PR, do NOT re-score until the Norfolk batch is done --
then ONE Norfolk re-score + `python scripts/postingest_gate.py --jurisdiction
6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5` (must PASS) + post the distance-to-Loudoun delta.
Never touch another county or the shared docs -- those are integration-owned.
```

### Window C — open in `C:/Users/nache_rl1pdne/zf-lake`
```
You are Session C in the parallel muni run. Working dir is this worktree
(C:/Users/nache_rl1pdne/zf-lake), branch parcellogic/lake-session. Read
docs/PARALLEL_SESSIONS_RUNBOOK.md. Work LAKE COUNTY IL ONLY (jid
10d01284-829b-4b03-b416-54bc452b8e70). Lake sequence: (1) reclassify INC placeholders --
`python scripts/reclassify_sentinel_codes.py --jurisdiction
10d01284-829b-4b03-b416-54bc452b8e70 --apply INC` (catch #51); (2) stamp cities via
WABBoundaries/1 (`python scripts/backfill_city_from_boundaries.py` with the Lake IL
source from _lake_il_task86_recon_manifest.md); (3) build the county-UDO paste kit
(honest yield LI 148 + II 3 -- ground, don't inflate). Full discipline (human_reviewed,
verbatim citations, 2.3 guards, catch #58 sweep). Escalate ambiguities to
outputs/_exception_queue.md (tag C). Do NOT re-score until the batch is done -- then ONE
Lake re-score + `python scripts/postingest_gate.py --jurisdiction
10d01284-829b-4b03-b416-54bc452b8e70` (must PASS). Class-B North Shore recon is
greenlight-gated -- stop and ask before it. Never touch another county or shared docs.
```

## Jurisdiction IDs (resolved)
- Middlesex MA: `18a11c2a-4d7d-4725-a643-e40ea2a4e171`
- Norfolk MA:   `6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5`
- Lake IL:      `10d01284-829b-4b03-b416-54bc452b8e70`  (Lake County, IL)

## Your loop (the ceiling)
1. Watch `outputs/_exception_queue.md` — rule only the genuinely ambiguous cells.
2. Merge per-muni PRs (the throughput limit).
3. Own the shared docs; don't let sessions race them.

## Teardown when done
`git worktree remove ../zf-<county>` (after its branch is merged).
