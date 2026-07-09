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
| C3 | C | Bannockburn, Lake IL | Only public zoning-polygon layer (GHA `gis.gha-engineers.com/.../Bannockburn/Zoning/MapServer/2`, ZONECLASS) returns HTTP 500 on every query — can't rebind. Wealthy (100% wealth-gate) but tiny; self-storage only special-use in Office District (low yield). | A working geometry pull (paginated export / retry window) or a town shapefile. Fine to skip given low yield. |
| C2 | C | Vernon Hills, Lake IL | No PUBLIC zoning-polygon layer: village runs a PRIVATE AGOL org (vernonhills.maps.arcgis.com; zoning service not shared). Marginal anyway — only 11.7% of parcels clear the wealth gate; O-R&D "Storage facilities" = special use. | Village GIS zoning shapefile / data request, then Municode content-API use table + rebind. |
| C1 | C | Libertyville, Lake IL | No PUBLIC zoning-polygon layer yet: GIS-Consortium `ags.gisconsortium.org/.../VLV/*` is token-gated. Real industrial districts (I-1/I-3, M1) but only 37% of parcels clear the wealth gate. NOTE: Buffalo Grove + Lincolnshire (same Consortium block) were UNBLOCKED via the `utility.arcgis.com/usrsvcs/servers/<guid>/rest/services/VLV/AGOL_VLV_Project/...` anonymous proxy — Libertyville almost certainly has the same proxy; just need its usrsvcs GUID (from the Libertyville community-map-viewer network calls). | Either find Libertyville's usrsvcs proxy GUID, or credentialed Consortium access / town shapefile. Lower priority (37% gate). |

## PARKED (coordinator-ruled, revisit-gated)
| # | Muni | Item | Coordinator ruling | Unblock condition |
|---|---|---|---|---|
| 1 | Hudson / Middlesex MA | Stale district scheme — parcels carry PRE-recodification codes (`C1–C13`/`M1–M7`/`SA5/7/8`/`SB*`/`LCI1`); current Nov-2023 bylaw uses `R15/R30/R40/R60/MR/MH/DB/NB/GB1/GB2/LCLI/IA/IB`. Rebind was DRY-RUN ONLY; **0 rows written, Hudson untouched.** | **HELD-parked, revisit at end of MA push (Nache 2026-07-09).** Consolidating recodification, NOT a rename (13 commercial→4 business, 7 industrial→3) → crosswalk option won't cleanly work (many-to-few, boundaries re-drawn) and hand-digitizing the PDF map = poison risk. Path = spatial rebind against new polygons (Braintree town-GIS pattern). No public queryable new-code layer (AGO "Hudson Zoning" = Hudson WI / NRPC-NH, catch #38). **Real yield — self-storage by-right IA/IB/LCLI per amlegal — revisit-worthy.** | Obtain Hudson's **Nov-2023 zoning shapefile/geodatabase** from Town Planning/GIS. Then `rebind_configs/hudson.json` → town-GIS layer; `ordinance_districts`={IA,IB,LCLI,DB,NB,GB1,GB2,R15,R30,R40,R60,MR,MH}; rebind → ground amlegal use table → re-score. Bylaw PDF: townofhudson.org DocumentCenter/View/325. |
| 2 | Randolph / Norfolk MA | 3 undecodable parcel codes GPOD/HA/C (~20 parcels); Session B kept the 11 decodable districts grounded verdict-only. | **Low-priority park (Nache 2026-07-09).** GPOD is almost certainly a Groundwater Protection OVERLAY — overlays correctly get no base verdict (not a gap). HA/C are 2 codes over ~20 parcels — not worth a session's time now. | Decode HA/C from the Randolph bylaw, or a town-GIS rebind pass — opportunistic. |

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
| D1 | Hatboro Boro (MontPA) | eCode360-blocked escalation | UNBLOCKED via curl+browser-UA (Session B method). Ch. 27: LI/HI/HI-MU conditional (§27-1402.J 'Storage buildings and warehouses' by-right); O/RC-1/RC-2/HB prohibited. 150 armed. | 2026-07-09 |
| D2 | Pottstown Boro (MontPA) | eCode360-blocked; industrial code undecoded | UNBLOCKED. §300 chart decoded (HM/FO/HB). HB permitted ('Rental storage'); HM+FO conditional (Warehouse by-right); downtown/gateway prohibited. 194 armed. | 2026-07-09 |
| D3 | Hatfield Twp (MontPA) | eCode360-blocked escalation | UNBLOCKED. Ch. 282: LI+LIRC conditional (§282-145.B 'Warehousing' by-right + SE catch-alls); C/LC/SC/LPO/IN/TD prohibited. 408 armed. | 2026-07-09 |
| D4 | Hatfield Boro (MontPA) | eCode360-blocked escalation | UNBLOCKED. Ch. 27: I PERMITTED (§27-1802.1.N 'Self-storage developments' by-right); CC prohibited (§27-2106.1.I); C prohibited. 60 armed. | 2026-07-09 |
| D5 | Bridgeport Boro (MontPA) | eCode360-blocked + Ch.560 rewrite version-mismatch risk | UNBLOCKED. Version check RESOLVED — parcel codes match current §560-402 scheme 1:1. LIC+GIC PERMITTED (§560-1202 '(u) Storage facility (self-service)' by-right); GC conditional; NC/MUR prohibited. 82 armed. | 2026-07-09 |
| ex | Billerica | LM/Wholesale compound tokens `NSZ`/`SZY` (catch #56) | OCR cell-merge, not strikethrough; LM-in-C=SZ, Wholesale-in-I=SZ | 2026-07-08 |
| ex | Billerica | closed-list clause for ss prohibited-by-silence | "Any building or use of premises not specifically permitted is prohibited" — confirmed | 2026-07-08 |
| ex | Braintree | MAPC gate-b fail (no C1/C2/C3) | C123=Cluster I/II/III; route to town-GIS layer (field LAYER) | 2026-07-08 |
