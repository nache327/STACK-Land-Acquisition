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

## Per-window launch prompt (paste into each, edit the CAPS bits)
```
You are the <A/B/COUNTY> session in the parallel muni run. Working dir is this
worktree (C:/Users/nache_rl1pdne/zf-<county>), branch parcellogic/<county>-session.
Read docs/PARALLEL_SESSIONS_RUNBOOK.md and follow the per-muni auto-fetch loop for
<COUNTY> ONLY. My first task: <FIRST TASK FROM TABLE>. Ground verdicts with full
discipline (human_reviewed, verbatim citations, 2.3 guards, catch #58 sweep). Fetch
online ordinances yourself; escalate ONLY genuine ambiguities to
outputs/_exception_queue.md (top of OPEN, tag <SESSION>). Apply muni-scoped, open a
per-muni PR, do NOT re-score until the county batch is done — then ONE county re-score
+ `python scripts/postingest_gate.py --jurisdiction <jid>` (must PASS) + post the
distance-to-Loudoun delta. Never touch another county or the shared docs
(paste-kits/manifest/ledger) — those are integration-owned.
```

## Jurisdiction IDs (for the prompts)
- Middlesex MA: `18a11c2a-4d7d-4725-a643-e40ea2a4e171`
- Norfolk MA:   `6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5`
- Lake IL:      (session C: `SELECT id FROM jurisdictions WHERE name ILIKE '%lake%' AND state='IL'`)

## Your loop (the ceiling)
1. Watch `outputs/_exception_queue.md` — rule only the genuinely ambiguous cells.
2. Merge per-muni PRs (the throughput limit).
3. Own the shared docs; don't let sessions race them.

## Teardown when done
`git worktree remove ../zf-<county>` (after its branch is merged).
