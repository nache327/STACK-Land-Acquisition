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
| _(none)_ | | | | |

## PARKED (coordinator-ruled, revisit-gated)
| # | Muni | Item | Coordinator ruling | Unblock condition |
|---|---|---|---|---|
| 1 | Hudson / Middlesex MA | Stale district scheme — parcels carry PRE-recodification codes (`C1–C13`/`M1–M7`/`SA5/7/8`/`SB*`/`LCI1`); current Nov-2023 bylaw uses `R15/R30/R40/R60/MR/MH/DB/NB/GB1/GB2/LCLI/IA/IB`. Rebind was DRY-RUN ONLY; **0 rows written, Hudson untouched.** | **HELD-parked, revisit at end of MA push (Nache 2026-07-09).** It's a *consolidating recodification, NOT a rename* (13 commercial→4 business, 7 industrial→3) → option-(b) crosswalk won't cleanly work (many-to-few, boundaries re-drawn) and hand-digitizing the PDF map = poison risk. Path = **spatial rebind against new polygons** (option a, Braintree pattern). No public queryable new-code layer (AGO "Hudson Zoning" = Hudson WI / NRPC-NH, catch #38). **Real yield — self-storage by-right in IA/IB/LCLI per amlegal — revisit-worthy, not a dead no-op.** | Obtain Hudson's **Nov-2023 zoning shapefile/geodatabase** from Town Planning/GIS (footer: "created by Hudson GIS – Nov 2023" → it exists). Then `rebind_configs/hudson.json` → town-GIS layer; `ordinance_districts` = {IA, IB, LCLI, DB, NB, GB1, GB2, R15, R30, R40, R60, MR, MH}; rebind → ground amlegal use table (codelibrary.amlegal.com/codes/hudson/latest) → re-score. Bylaw PDF: townofhudson.org DocumentCenter/View/325. |

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
| ex | Billerica | LM/Wholesale compound tokens `NSZ`/`SZY` (catch #56) | OCR cell-merge, not strikethrough; LM-in-C=SZ, Wholesale-in-I=SZ | 2026-07-08 |
| ex | Billerica | closed-list clause for ss prohibited-by-silence | "Any building or use of premises not specifically permitted is prohibited" — confirmed | 2026-07-08 |
| ex | Braintree | MAPC gate-b fail (no C1/C2/C3) | C123=Cluster I/II/III; route to town-GIS layer (field LAYER) | 2026-07-08 |
