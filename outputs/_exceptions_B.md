# Session B — exceptions (Norfolk MA county_gis)

Per-session escalation file (NOT the shared queue). Genuine ambiguities only; coordinator triages.

## OPEN
| # | Muni / County | Item (what's ambiguous) | What's needed |
|---|---|---|---|
| B4 | Westwood / Norfolk MA | **Current bylaw not machine-accessible; only a stale copy is.** Town site (townhall.westwood.ma.us) is Cloudflare-blocked (403/430 to curl, all paths) and hosts the current "Zoning Bylaw 2025". The only fetchable copy (IQM2 `westwoodtownma.iqm2.com/Citizens/FileOpen.aspx?Type=4&ID=5814`) is "adopted 1961, **amended through Nov 13 2017**" — ~8yr stale, missing MBTA-Communities + any post-2017 use changes. Not on eCode360 (zoning absent from WE2841 code) or Municode. Declined to ground human_reviewed off the stale copy (currency discipline). | Paste the current (2025) Westwood Table of Use Regulations (districts I/IO/LBA/LBB/HB/GR/SR/SRA-E/ARO — MAPC layer 2 rebind is READY), or confirm the 2017 industrial-use rows (I/IO/LBA/LBB warehouse/storage) are unchanged in 2025. Then rebind + ground. |
| B3 | Needham / Norfolk MA | **Undecodable assessor code `C` (20 parcels).** Needham grounded verdict-only (MAPC is STALE — lacks the current Route-128 corridor districts HC-128/MU-128/NEBC/HC-1, and no public current town-GIS layer found, so no clean rebind). 18 assessor codes mapped confidently to current §3.2 bylaw districts and were applied `human_reviewed`; `C` (20 parcels) does not map to any §2 district abbreviation (not CB/CSB/CS). `FP` (4, Flood-Plain overlay) intentionally left ungrounded (overlay → no base verdict). | Decode `C` (town assessor legend) or supply a current Needham zoning GIS layer (with HC-128/MU-128/NEBC/HC-1) for a spatial rebind. 20 parcels held. Source: needhamma.gov DocumentCenter/View/16644 (Nov 2025 bylaw). |

## BLOCKED (no machine-readable source — carried from shared queue, tag B)
| # | Muni | Item | Unblock |
|---|---|---|---|
| B1 | Millis / Norfolk MA | Ordinance is a scanned-image PDF (no text layer); no OCR/renderer available; not on eCode360 (MI3159=Millvale PA) or Municode. | Paste/OCR the Table of Use Regs (districts C-V/I-P/R-S/R-T/R-V; I-P = Industrial Park needle). Source: aptg.co/9n7GvH. |
| B2 | Plainville / Norfolk MA | Bylaw auto-fetchable (eCode360 Ch. 500 §500-17) but MAPC returns 0 (SRPEDD region) → no polygon layer to fill 91%-NULL parcels. | Town/SRPEDD zoning GIS layer, or OK a verdict-only pass on the ~270 coded parcels. Source: ecode360.com/11814987. |

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
