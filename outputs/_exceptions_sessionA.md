# Session A exceptions — Middlesex MA

Per-session escalation file (2026-07-09). Hudson is already coordinator-PARKED in the shared
queue (`_exception_queue.md` PARKED #1) — not duplicated here.

## OPEN / DEFERRED
| Muni | Item | Status / what's needed |
|---|---|---|
| Littleton | **Use table not yet grounded — DEFERRED, not blocked.** Zoning = eCode360 Ch.173 (pub code `LI1092`). eCode360 IS reachable via curl+browser-UA, but Littleton's use regs are in **section bodies (per-district list format)**, not a single use-table attachment PDF like Chelmsford's — its only attachment is `173a Intensity of Use Schedule` (dimensional, not uses). Needs node-by-node section fetch (extract Article V child `data-guid`s → curl each). Rebind source = MAPC layer 2 (Littleton is MAPC territory, not NMCOG). | **Next pickup:** fetch Littleton Article V use sections via curl+UA node walk (or `/attachment/` if a use-table PDF exists), build `rebind_configs/littleton.json` (MAPC, muni='Littleton'), rebind → ground → apply. No paste needed (source reachable). |

## RESOLVED this session
| Muni | Item | Resolution |
|---|---|---|
| Chelmsford | Earlier flagged "eCode360 blocked" (premature) | UNBLOCKED + GROUNDED via curl+browser-UA at `ecode360.com/attachment/332663/CH1747-195a Use Regulations.pdf`. 16 districts applied; needle (ss/mw cond in CB + IA). Supersedes the stale `parcellogic/middlesex-chelmsford-held` branch. |

## Superseded branches (do NOT merge — stale base, off pre-fix main)
- `parcellogic/middlesex-chelmsford-held` (escalation #2/#3 into the shared queue — obsolete; Chelmsford now grounded, Littleton tracked here).
- `parcellogic/middlesex-hudson-blocked` (Hudson now coordinator-PARKED #1).
- The 5 per-muni verdict branches (`middlesex-framingham|tewksbury-ma|tyngsborough|westford|chelmsford`) are consolidated into `parcellogic/middlesex-batch-tier1` (off latest main + rebind-assert fix); merge the batch branch, not the per-muni ones.
