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
| D5 | D | Bridgeport Boro / Montgomery PA | No auto-fetchable source (eCode360 + town CivicPlus uploads both 403) **and** Ch. 560 rewritten 11-11-2025 (Ord 2025-002)+amended 2026 → parcel codes (LIC/GC/GIC/NC/MUR/TO) may predate rewrite | Paste current Ch. 560 LIC + GC/GIC + commercial use tables; confirm codes still match parcels. Needle = LIC 50 + GC 31. URLs in `_drafts/_montgomery_pa_ecode360_paste_surface.md` |
| D4 | D | Hatfield Boro / Montgomery PA | eCode360-only (403 to automation), no town PDF | Paste I Industrial (Part 18) + CC/C commercial use tables. Needle = I 60. URLs in paste-surface draft |
| D3 | D | Hatfield Twp / Montgomery PA | eCode360-only (403 to automation), no town PDF. LI preview shows "Warehousing" + "Truck terminal" by-right (likely self-storage conditional) | Paste LI (Art XX, ecode360.com/10507615) + C/BB/BA use tables. Needle = LI 404. URLs in paste-surface draft |
| D2 | D | Pottstown Boro / Montgomery PA | eCode360-only (403 to automation), no town PDF; needle industrial district code not yet decoded (KOZ/general-industrial) | Paste industrial district use list + downtown/commercial (D/DG/GE). URLs in paste-surface draft |
| D1 | D | Hatboro Boro / Montgomery PA | eCode360-only (403 to automation), no town PDF. **Biggest eCode360-only industrial pool (LI 86 + HI 47 + HI-MU 17 = 150)** | Paste LI + HI + HI-MU use lists + HB/O commercial. URLs in `_drafts/_montgomery_pa_ecode360_paste_surface.md` |

## PARKED (coordinator-ruled, revisit-gated)
| # | Muni | Item | Coordinator ruling | Unblock condition |
|---|---|---|---|---|
| 1 | Hudson / Middlesex MA | Stale district scheme — parcels carry PRE-recodification codes (`C1–C13`/`M1–M7`/`SA5/7/8`/`SB*`/`LCI1`); current Nov-2023 bylaw uses `R15/R30/R40/R60/MR/MH/DB/NB/GB1/GB2/LCLI/IA/IB`. Rebind was DRY-RUN ONLY; **0 rows written, Hudson untouched.** | **HELD-parked, revisit at end of MA push (Nache 2026-07-09).** Consolidating recodification, NOT a rename (13 commercial→4 business, 7 industrial→3) → crosswalk option won't cleanly work (many-to-few, boundaries re-drawn) and hand-digitizing the PDF map = poison risk. Path = spatial rebind against new polygons (Braintree town-GIS pattern). No public queryable new-code layer (AGO "Hudson Zoning" = Hudson WI / NRPC-NH, catch #38). **Real yield — self-storage by-right IA/IB/LCLI per amlegal — revisit-worthy.** | Obtain Hudson's **Nov-2023 zoning shapefile/geodatabase** from Town Planning/GIS. Then `rebind_configs/hudson.json` → town-GIS layer; `ordinance_districts`={IA,IB,LCLI,DB,NB,GB1,GB2,R15,R30,R40,R60,MR,MH}; rebind → ground amlegal use table → re-score. Bylaw PDF: townofhudson.org DocumentCenter/View/325. |

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
| ex | Billerica | LM/Wholesale compound tokens `NSZ`/`SZY` (catch #56) | OCR cell-merge, not strikethrough; LM-in-C=SZ, Wholesale-in-I=SZ | 2026-07-08 |
| ex | Billerica | closed-list clause for ss prohibited-by-silence | "Any building or use of premises not specifically permitted is prohibited" — confirmed | 2026-07-08 |
| ex | Braintree | MAPC gate-b fail (no C1/C2/C3) | C123=Cluster I/II/III; route to town-GIS layer (field LAYER) | 2026-07-08 |
