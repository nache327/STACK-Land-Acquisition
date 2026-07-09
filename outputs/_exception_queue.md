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

## RESOLVED
| # | Muni | Item | Ruling | Date |
|---|---|---|---|---|
| ex | Billerica | LM/Wholesale compound tokens `NSZ`/`SZY` (catch #56) | OCR cell-merge, not strikethrough; LM-in-C=SZ, Wholesale-in-I=SZ | 2026-07-08 |
| ex | Billerica | closed-list clause for ss prohibited-by-silence | "Any building or use of premises not specifically permitted is prohibited" — confirmed | 2026-07-08 |
| ex | Braintree | MAPC gate-b fail (no C1/C2/C3) | C123=Cluster I/II/III; route to town-GIS layer (field LAYER) | 2026-07-08 |
