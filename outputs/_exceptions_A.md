# Session A exceptions / discovery notes — Middlesex MA (cumulative)

## OPEN — needs Nache
| Muni | Item | What's needed |
|---|---|---|
| **Newton** | **No auto-fetchable CURRENT source.** Chapter 30 Zoning is only at `newtonma.gov/home/showpublisheddocument/72882/...` — **Akamai-WAF-blocked** (curl → "Access Denied"; WebFetch → 403; no Wayback PDF snapshot; not on Municode/eCode360). Only freely fetchable copy is the **2014 DRAFT rezoning (never adopted)** — DO NOT ground from it (Hudson-class staleness trap). Wealthy, little industrial → likely modest yield. | **Paste** current Ch.30 §4.4.1 Use Table (M/Business/Mixed-Use rows: self-storage/warehouse/manufacturing/motor-vehicle-storage) + legend + closed-list clause. Then rebind (MAPC, muni='Newton') + ground. |
| **Hopkinton** | Identified in tail discovery (IA 27 + IB 7 large-lot wealth-ring parcels; Rt-495 biotech) but NOT yet grounded — deferred for time. Bylaw fetchable (town/eCode360). | Next pickup: fetch Hopkinton use table, check self-storage/warehouse in IA/IB, rebind if needed, ground. Likely a needle. |

## GROUNDED — tail3 batch (2026-07-14) — LAST Middlesex batch (tail drained)
| Muni | Result |
|---|---|
| Wakefield | GROUNDED (eCode360 Ch.190 WA1512, Appendix A Table of Use, curl+UA). **NEEDLE**: "Self-storage facility" (row 7) permitted **by-right** in LI + I; conditional (BA special permit) in B; li permitted LI/I. lgc prohibited (goods self-storage ≠ vehicle garage-condo; closed table). No rebind (parcels carry bylaw codes SSR/SR/GR/NB/LB/B/LI/I). |
| Boxborough | GROUNDED (town PDF View/1918, 2025, Table 4.1.3.d). **NEEDLE**: "Self-storage facility" permitted **by-right in IC** only. MAPC rebind confirmed assessor code **C→IC** spatially (C→IC:62, gates a/b/d PASS, layer vocab = AR/B/B1/IC/OP/R1/TC = bylaw Article 3). li permitted B/B1/OP/IC. lgc prohibited. |
| Pepperell | GROUNDED (town Zoning Bylaw View/2442, consolidated rev. 7/28/2014, Appendix A Table of Principal Uses; MRPC region). **NEEDLE**: "Self-storage facility" permitted **by-right in both C (Commercial) and I (Industrial)**; li permitted C/I. §3100 closed list. No rebind — parcel codes RUR/TNR/SUR/RCR/URR/COM/IND map by NAME to bylaw §2200 abbreviations RR/TR/RCR/SR/UR/C/I (verified against district-establishment list); verdicts keyed on parcel codes (COM→C, IND→I). lgc prohibited. |
| Natick | GROUNDED (CURRENT June-2025 Zoning Bylaws View/19928, Section III-A.1 Table of Use + §III-B..G). **MODEST NEEDLE**: self-storage is NOT a named use (only "self-service laundry" appears) → under §III-A.1.a closed list grounds to K6 "Warehouses for storage of personal property" = SP (conditional) in **INII + HMIa**; DM >1,000 sf SP. Prohibited elsewhere incl. INI (K6 INI=N — INI permits light-mfg by-right but excludes warehouses). li permitted INI/INII/HMIa; conditional CG/HM-II/HM-III/HPU (R&D). HM-II/III/HPU sections name office/R&D/retail but NO warehouse use. lgc prohibited. No rebind (verdicts keyed on parcel codes). |

## GROUNDED — tail2 batch (2026-07-13)
| Muni | Result |
|---|---|
| Hopkinton | GROUNDED (eCode360 Ch.210, §210-9/15 IA/IB permitted uses). NEEDLE: warehousing-for-distribution by-right IA/IB → ss/mw conditional (convention); li permitted IA/IB. |
| Acton | GROUNDED (town PDF §3.6.1 "Warehouse ... a personal self-storage facility or mini-warehouse"). NEEDLE: self-storage IS warehouse, by-right in OP-1/OP-2/PM/GI/LI/LI-1/SM/TD → ss/mw **permitted** there. |

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

## MIDDLESEX TAIL DRAINED (2026-07-14)
All industrial/commercial tail towns are now grounded. Remaining un-grounded parcels are either
correct no-ops (all-residential towns, see above) or the two held items:
- **Newton** = OPEN, awaiting Nache paste (Akamai-WAF-blocked current source; only stale 2014 draft freely fetchable).
- **Hudson** = PARKED (stale M-code consolidating recodification; coordinator-ruled — needs town shapefile → spatial rebind).
Middlesex is otherwise COMPLETE — next session pivots to a fresh county.
