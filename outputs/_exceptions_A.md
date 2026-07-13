# Session A exceptions / discovery notes — Middlesex MA (cumulative)

## OPEN — needs Nache
| Muni | Item | What's needed |
|---|---|---|
| **Newton** | **No auto-fetchable CURRENT source.** Chapter 30 Zoning is only at `newtonma.gov/home/showpublisheddocument/72882/...` — **Akamai-WAF-blocked** (curl → "Access Denied"; WebFetch → 403; no Wayback PDF snapshot; not on Municode/eCode360). Only freely fetchable copy is the **2014 DRAFT rezoning (never adopted)** — DO NOT ground from it (Hudson-class staleness trap). Wealthy, little industrial → likely modest yield. | **Paste** current Ch.30 §4.4.1 Use Table (M/Business/Mixed-Use rows: self-storage/warehouse/manufacturing/motor-vehicle-storage) + legend + closed-list clause. Then rebind (MAPC, muni='Newton') + ground. |
| **Hopkinton** | Identified in tail discovery (IA 27 + IB 7 large-lot wealth-ring parcels; Rt-495 biotech) but NOT yet grounded — deferred for time. Bylaw fetchable (town/eCode360). | Next pickup: fetch Hopkinton use table, check self-storage/warehouse in IA/IB, rebind if needed, ground. Likely a needle. |

## GROUNDED — tail batch (2026-07-09)
| Muni | Result |
|---|---|
| Lexington | GROUNDED (eCode360 Ch.135 Table 1 via curl+UA attachment). **0-NEEDLE correct no-op**: no self-storage use + closed-list; only mover-storage/distribution by-right (not generic warehouse). li permitted CM/CRO; lgc conditional CS/CSX (named auto-storage SP). NOTE: GC = "Government Civic" (not commercial) — discovery false signal. |
| Ayer | GROUNDED (eCode360 Ch.320 Table via curl+UA; §320-4 confirmed DB=DPSFBC, MT=MUT). Needle: ss/mw conditional (SP) in LI + MUT; li permitted LI/I; **self-storage = N in the heavier Industrial (I)** — confined to LI/MUT. lgc prohibited. No rebind (MRPC town, codes clean). |
| Bedford | GROUNDED (MAPC rebind split assessor IND→IP/I/IC). Needle: no named self-storage but Warehouse by-right in Commercial + Industrial A/B/C → ss/mw conditional (convention); li permitted there. Great Road GB/LB recorded prohibited (Table 4.3-2 not machine-parsed, conservative). Closed-list §2.3. Adopted March 2025 (not the Jan-2025 draft). |

## CORRECT NO-OPS — discovery-ranked but all-residential / no wealth-ring industrial (recorded, not forced)
Wealthy towns whose high large-lot-in-ring count is RESIDENTIAL (single-letter A/B/C/D codes = residence districts), with no real self-storage-eligible industrial in the ring:
- **Carlisle** ("B"=Residence-B, 2-acre residential), **Weston** (A/B/C/D=residence), **Lincoln**, **Sherborn**, **Sudbury**, **Wayland**, **Concord** (mostly AA/A residence; only I(16)+IPA(13) tiny industrial), **Reading** (S20/S15/S40 residential + tiny IND), **Belmont** (dense residential), **Groton/Stow/Dunstable** (rural residential).
These are correct no-ops per the thesis (wealth without self-storage-eligible industrial ≠ gap). Revisit only if a specific blocked deal surfaces.

## Remaining un-grounded with SOME industrial (lower priority, next pickup)
Acton (LI/OP1/LB), Boxborough (OP 54 + C 50), Wakefield (I 48), Pepperell (IND 49, MRPC), Natick (large commercial, mostly retail). Hudson = PARKED (stale M-code scheme, coordinator-ruled).
