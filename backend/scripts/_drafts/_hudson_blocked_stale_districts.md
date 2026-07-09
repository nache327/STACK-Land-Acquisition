# Hudson MA — BLOCKED: stale district scheme (Session A, 2026-07-09)

## Verdict: HELD. Escalated to `outputs/_exception_queue.md` OPEN #1 (tag A).

## What happened
Ran the per-muni loop for Hudson (Middlesex jid `18a11c2a-4d7d-4725-a643-e40ea2a4e171`).
Rebind **dry-run** passed all gates (a vocab clean, b count 29 in [27,31], d no-unaccounted;
4.4% changed, 9 orphans, transitions clean). Then fetched the **current** ordinance to ground
verdicts and found a fundamental mismatch — so I did **not** run `--apply` and applied **no verdicts**.

## The mismatch
| Source | District codes |
|---|---|
| Our parcels + MAPC Zoning Atlas layer (what `hudson.json` was reconned from) | `C1–C13`, `M1–M7`, `SA5/7/8`, `SB/SB1–4`, `LCI1` |
| **Current Town of Hudson bylaw (Nov 20 2023)** — §5.0 Establishment of Districts, Appendix B Table of Use Regs, Appendix C Intensity | `R60`, `R40`, `R30`, `R15`, `MR`, `MH`, `DB`, `NB`, `GB1`, `GB2`, `LCLI`, `IA`, `IB` |

The legacy `C/M/SA/SB/LCI` codes appear **nowhere** in the current bylaw. Hudson recodified
its districts (map "dated November 2023"). MAPC's Hudson layer still carries the old scheme,
so the rebind gates passed trivially (config vocab ⊆ MAPC vocab because both are the stale source).

## Why this blocks grounding
Verdicts must key to the zone_code the parcels carry. Appendix B (the authoritative current use
table) is keyed to `R60…/IA/IB`. There is no way to attach a grounded, verbatim-cited verdict to
`C1`/`M1`/`SA8` etc. without an authoritative **old→new crosswalk**, which I could not locate in
the bylaw or town materials. Guessing a crosswalk would violate the grounding bar.

## What the current Appendix B DOES say (for when Hudson is unblocked)
Industrial / Light-Industrial uses, columns `LCLI / IA / IB` (Y=by-right, N=prohibited, ZBA/PB=special permit):
- **Self-storage facility**: `DB`=ZBA, `NB`=N, `GB1`=ZBA, `GB2`=ZBA, `LCLI`=Y, `IA`=Y, `IB`=Y (N in all residential).
- **Warehouse and distribution center** (also Standard/Transload/Crossdocking/Fulfillment): `LCLI`=Y, `IA`=Y, `IB`=Y; N elsewhere.
- **Light Manufacturing**: `GB1`=ZBA, `GB2`=ZBA, `LCLI`=Y, `IA`=Y, `IB`=Y; N elsewhere.
- **Manufacturing**: `LCLI`=Y, `IA`=Y, `IB`=Y.
Note: unlike Wilmington/Woburn (self-storage prohibited), Hudson's current bylaw **PERMITS self-storage
by-right in LCLI/IA/IB and by ZBA special permit in DB/GB1/GB2** — i.e. Hudson likely HAS needles once
the parcels are rebound to the current scheme. This raises the stakes on getting the source right.

## Recommended unblock (see exception queue for the ask)
(a) Re-point `hudson.json` `url` at the town's current Nov-2023 zoning GIS layer (codes `R60…/IA/IB`)
    and re-recon `ordinance_districts` to the current bylaw; rebind → then verdicts from Appendix B; **or**
(b) obtain/confirm the official old→new recodification crosswalk (`SA/SB/C/M → R/DB/NB/GB/LCLI/IA/IB`).

## State left behind
- Hudson parcels: **untouched** (dry-run only, never `--apply`).
- `zone_use_matrix` Hudson rows: **0**.
- `hudson.json`: notes updated to STALE/BLOCKED with the pointer above.
- Dry-run diff artifact: `_drafts/_rebind_diff_hudson_dry.json`.
