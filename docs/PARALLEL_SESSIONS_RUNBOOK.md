# Parallel Muni Sessions — Runbook

How to run 3–4 Claude Code sessions on different municipalities at once **without collisions**.
Grounded in the 2026-07-08 concurrency audit. Companion to the velocity plan
(`~/.claude/plans/i-need-help-making-golden-globe.md`).

## Why this works (and where the limits are)
- **Safe in parallel:** per-muni `zone_use_matrix` writes (upsert key includes `municipality`),
  different-*county* re-scores, new per-muni files.
- **Contended → isolate:** same-county re-score (now guarded by an advisory lock, but still
  county-partition), the working tree/branch/`.env`, and the shared docs (paste-kits, rebind
  manifest, ledger). The `CONFIGS` conflict is GONE (now per-muni JSON in `rebind_configs/`).
- **Real ceiling:** Nache's exception-review + PR-merge cadence. Sessions clear the unambiguous
  majority; Nache handles exceptions (`outputs/_exception_queue.md`) + merges. Expect ~2.5–3.5×,
  not 5×.

## One-time setup per session (worktree isolation)
```bash
# from the main checkout, once per session/county:
git worktree add ../zf-middlesex -b parcellogic/middlesex-batch origin/main
cp backend/.env ../zf-middlesex/backend/.env      # .env is git-ignored; same Supabase DB
# repeat: ../zf-norfolk, ../zf-lake, ../zf-billerica
git worktree list                                  # confirm independent trees
```
Each session opens its own worktree dir. No two sessions share a working tree → no branch thrash.

## County partition (assign disjoint counties)
| Session | Worktree | County | Munis |
|---|---|---|---|
| A | `zf-middlesex` | Middlesex MA | Woburn, Wilmington(wire SQL), Hudson, then Holliston/Framingham/Tewksbury/Chelmsford |
| B | `zf-norfolk` | Norfolk MA | Norwood, Walpole, then Foxborough/Quincy/Randolph/Sharon/Medfield |
| C | `zf-lake` | Lake IL | reclassify INC → stamp cities → county-UDO kit → North Shore recon (gated) |
| D | `zf-billerica` | Middlesex MA | Billerica tail (mostly grounded); fold into A if idle |

Rule: **one session = one county at a time.** Never two sessions on the same county
(re-score + county-scoped scans).

## Per-muni loop (each session runs this, no paste unless it must escalate)
1. **Fetch** the ordinance (eCode360/Municode/town PDF; Playwright/DocumentCenter). No source → escalate (paste).
2. **Rebind** if MA assessor-mismatch: add `backend/scripts/rebind_configs/<muni>.json` (see that
   dir's README), then `python scripts/backfill_zoning_from_districts.py --muni <MUNI>` dry-run →
   eyeball diff → `--apply` on gates a/b/d pass; else point the JSON `url` at town GIS.
3. **Parse** the use table under the 2.3 guards (already in `ordinance_parser.py`).
4. **Self-verify** vs the source PDF: column alignment, closed-list clause, named-use definitions;
   apply the catch #58 closed-list sweep across inferred uses.
5. **Escalate** genuine ambiguities to `outputs/_exception_queue.md` (top of OPEN, tag your session);
   everything else proceeds.
6. **Apply** muni-scoped verdicts (human_reviewed, verbatim citations) → verify rows (catch #42) →
   commit `_apply_<muni>.py` → open PR. **Do NOT re-score yet.**
7. When the county's batch is done: **one** re-score of that county → run
   `python scripts/postingest_gate.py --jurisdiction <jid>` (must PASS) → post the distance-to-Loudoun delta.

## Shared-file discipline (the remaining conflict surface)
Sessions write ONLY per-muni files (`_apply_<muni>.py`, `rebind_configs/<muni>.json`,
`_drafts/_<muni>_*.md`, `_rebind_diff_<muni>_*.json`). The shared docs — `_ma_stage4_paste_kits.md`,
`_ma_district_rebind_manifest.md`, the discipline ledger — are edited by **one integration owner**
(Nache or a designated coordinator session), never raced.

## Guardrails (non-negotiable — speed must not erode the bar)
- Every verdict stays `human_reviewed` with a verbatim citation. No session lowers the bar to go faster.
- `postingest_gate.py` must PASS per county post-batch (CI can run it too).
- CI green on every PR (2.3 guard tests + gate tests are the net).
- Merge-gated as always; nothing auto-merges.
