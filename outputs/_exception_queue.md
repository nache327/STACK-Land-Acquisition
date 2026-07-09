# Exception Queue — parallel muni sessions

Purpose: keep Nache's attention on **genuine ambiguities only**. A session that hits something
it cannot self-verify (per the auto-fetch + self-verify loop) appends a row here instead of
guessing or blocking. Everything unambiguous proceeds to apply without a stop.

**Append rule (parallel-safe):** add your row at the TOP of the open table with your session tag
(`A`/`B`/`C`/`D`). Never edit another session's row. Nache clears items by moving them to Resolved
with the ruling. If two sessions somehow collide on this file, the per-muni `_apply_*.py` + PR are
the source of truth — this file is only the escalation signal.

Escalate ONLY these (from the plan): compound/OCR grid tokens needing a visual read (catch #56);
a missing or absent closed-list clause where a prohibited-by-silence verdict would otherwise rest
(catch #57/#58); a district-vocabulary mismatch the rebind can't resolve (route-to-town-GIS
decision); an ordinance with no online source (needs a paste). Do NOT escalate anything the 2.3
guards + source PDF already settle.

## OPEN
| # | Session | Muni / County | Item (what's ambiguous) | What's needed from Nache |
|---|---|---|---|---|
| _(none yet)_ | | | | |

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
| ex | Billerica | LM/Wholesale compound tokens `NSZ`/`SZY` (catch #56) | OCR cell-merge, not strikethrough; LM-in-C=SZ, Wholesale-in-I=SZ | 2026-07-08 |
| ex | Billerica | closed-list clause for ss prohibited-by-silence | "Any building or use of premises not specifically permitted is prohibited" — confirmed | 2026-07-08 |
| ex | Braintree | MAPC gate-b fail (no C1/C2/C3) | C123=Cluster I/II/III; route to town-GIS layer (field LAYER) | 2026-07-08 |
