# Session B — Salt Lake cluster human-review (2026-07-15)

## Structure (confirmed) — ring + needles live on the COUNTY jid
The SLCo county-model holds: **ring metrics (dt10) + all machine-era needles are on the Salt Lake County
jid `d79e9029` (city-filtered)**, NOT the per-city jids. Ring dt10 rows: County 249,613 · Draper (own jid)
25,515 · South Salt Lake 8,650 (but zoned=0) · Salt Lake City 5,311 · Midvale 4. The other **12 per-city
jids are ring=0** (Sandy/West Jordan/South Jordan/West Valley/Millcreek/Murray/Holladay/Cottonwood
Heights/Taylorsville/Herriman/Bluffdale/North Salt Lake) → they cannot produce needles; the county jid is
the needle source. **Coordinator confirmed: write human_reviewed rows on the county jid, municipality=<city>.**
Human-confirmed needles were 0 everywhere (predates the discipline); machine-era = **731 (county) + 106 (Draper own jid)**.

## Machine-era needle breakdown (county jid, by city × zone)
- **South Jordan ~350**: P-C 148c, C-F 55c, P-O 35c, C-C 32c, BH-MU 25c, I-F 19p, MU-CITY/SOUTH/TOD/COMM/V/TC ~30c, C-N 3c
- **Herriman ~114**: LPMPC 53c, C-2 42c, AMSD 9c, TM 5c, C-1 3c, M-1 2p
- **West Valley City 99**: M 99p ✅ DONE
- **Draper (county-jid rows) ~100** + **Draper own jid `6e618f70` 106**: CBP 43c, M1 15p, M2 13p, CG 9c, "A5;M1"/"M2;OS"/"CC;CG" composite-code artifacts — **DRAPER DOUBLE-JID DEDUP needed**
- **West Jordan ~26**: P-C 14c, C-M 8c, M-1 4p
- **Sandy ~25**: SD(EH) 6c, SD(Magna)(CC) 5c, SD(H) 5c, SD(PO/R) 2c … — SD=Sandy overlay; **"SD(Magna)" suspect (Magna is a separate township — possible miscode)**
- **Cottonwood Heights ~5**: **RR-1-21 (ZC) 3c** ⚠ Rural Residential — machine #58 error, DEMOTE; MU 2c
- **Millcreek 2**: C-1 2c

## DONE this session
- **West Valley City M = self_storage PERMITTED (human_reviewed)** — verbatim §7-7-122 "Self-Storage
  Facilities are only allowed in the Manufacturing (M) Zone" (Playwright on westvalleycity.municipal.codes).
  Confirms the machine M verdict → **99 needles brought to human standard.** Self-storage confined to M
  (all other WVC zones stay prohibited). `scripts/_apply_slco_westvalley.py`.

## Source-access finding (important for the hand-back)
The SLCo Municode content-API is **walled cluster-wide** — all SLCo Municode clients (South Jordan 4400,
Sandy 4222, Herriman 13004, Cottonwood 17877, Millcreek 19874) return product IDs in the 41xxx range with
**empty Jobs/latest** (newer-instance wall; SPA-interception on library.municode.com also yielded no API
calls). BUT the cities are ALSO on `{city}.municipal.codes` (General-Code platform) which is **Cloudflare-JS
but Playwright-fetchable** (proven on West Valley + Bellevue/Snyderville). → **Per-city path = Playwright on
`{city}.municipal.codes`** (e.g. southjordan.municipal.codes, sandy.municipal.codes, cottonwoodheights.municipal.codes).

## HAND-BACK — remaining cities (proven approach, county jid, muni=<city>)
Each is a verify-and-confirm/demote against the CURRENT ordinance via Playwright on `{city}.municipal.codes`.
Prioritized by count: **South Jordan (350) → Draper+dedup (200) → Herriman (114) → West Jordan (26) →
Sandy (25) → Cottonwood Heights (demote RR-1-21) → Millcreek (2).** South Jordan/Herriman use a use-matrix
(per-zone alignment needed); West Valley-style named-confinement clauses are faster where present.
Not rushed this session (verbatim #37 over speed; ~632 county + 106 Draper machine needles still pending
review). Net delta so far: **+99 human-confirmed** (West Valley); machine-era count unchanged elsewhere.

## GATE FLAG (pre-existing county-jid poison — NOT from this session's grounding)
County-jid verify_batch = CLEAN casing, West Valley 99 needles, but **postingest_gate FAILs** on **30
distinct over-length / URL-shaped parcel `zoning_code`s** (machine-era artifacts): e.g. "Bingham Junction -
Subarea 1", "Bingham Junction - Subarea 6", "Bingham Junction Zone", composite "CBP; CR; CSD-KMAC; RM2",
descriptive "CI Civic Institutional", etc. These are pre-existing SLCo-ingest data-quality issues on
parcels.zoning_code (same class as the Middlesex/Dunellen Atlas phrase-artifacts), independent of the West
Valley human row. NOT fixed here — it is a broad shared-data cleanup (30 codes × 397k parcels) that needs
coordinator authorization and is a distinct task. Recommend: NULL/normalize the over-length codes (they are
not real district codes) as a scoped cleanup, then re-gate. Flagged for coordinator.
