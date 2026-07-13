# Session D exceptions — Montgomery County PA (jid a59d956d) — batch-v3

Per-session file (not the shared queue). Batch-v3 targeted the strategic IN-list (default-deny).

## Grounded this batch (3 IN-list munis)
| Muni | Needle verdict | Basis | source |
|---|---|---|---|
| Conshohocken Borough | LI → **conditional** (0.72) | §27-1402.I same-general-character permitted catch-all + F "Warehouse, storage, or distribution center"; self-storage same-character as permitted storage use | eCode360 curl+UA |
| Springfield Township | I → **permitted** (0.95); LI → prohibited | §114-121 names "O. Self storage facility" by-right; LI §114-12C1 closed list omits it (catch #37 — the two industrial codes diverge) | eCode360 curl+UA |
| Whitpain Township | I → **conditional** (0.90) | §160-142.G(3) names "miniwarehousing ... ministorage facilities" as special exception | eCode360 curl+UA |

## OPEN escalations

### D-v3-1 — Upper Dublin Township: amlegal-hosted, not auto-fetchable
Upper Dublin's code (Chapter 255 Zoning) is on **American Legal Publishing** (codelibrary.amlegal.com),
NOT eCode360/Municode. Tried the banked + adjacent unlocks, all failed:
- eCode360: not present (amlegal muni).
- amlegal `files.amlegal.com/pdffiles/UpperDublin/UpperDublinALS.pdf` = 1-page 9KB STUB (not the code).
- amlegal codelibrary SPA: content behind a JS app; `/api/clients/...`, `/api/codes/...`, `/api/clients/.../products`, `export.amlegal.com/api/...` all HTTP 404.
- Municode content-API: `api.municode.com/Clients/name?name=Upper Dublin` → 404 (not a Municode client).
- Zoneomics: mirror only (non-authoritative for verbatim human_reviewed citations); CR-I content paginated, not surfaced.
Needle worth chasing: Upper Dublin is wealthy (Fort Washington / PA-309), needle district **CR-I** (23
parcels, Commercial-Restricted Industrial) + CR-L (67). **Need:** an amlegal content-API path / export
token, OR OK to ground from the Zoneomics mirror (§255 sections preserved), OR a town-site PDF from
upperdublin.net/township-code.

### D-v3-2 — Lower Merion Township: deferred no-op (no industrial district)
Catch #37 save: Lower Merion's IE1/2/3 = **Institutional Education**, IC1/3 = **Institutional Civic**
(NOT industrial). Lower Merion (elite Main Line, Chapter 155 form-based code) has **no industrial
district** — non-residential districts are commercial/town-center (VC/TC1/TC2/BMV), institutional
(IN/IC/IE), and mixed-use overlays. Per catch #52 this is an expected self-storage prohibition / honest
no-op with ~0 wealth-gated needles, and the form-based use-table parse is heavy for ~0 yield. DEFERRED —
low priority. If grounded later, expect all-prohibited.

### D-v3-3 — Bryn Athyn Borough: tiny, town-site-only source
Bryn Athyn (IN-list, flagged "small/very-high-wealth, review") is a 423-parcel borough with only LI:7.
Not on eCode360; ordinance would come from brynathynboro.org. Marginal yield (7 industrial parcels).
Low priority; ultra-wealth means those 7 could clear the wealth gate if grounded — opportunistic.

## ⚠ IN-list status: near-exhausted of easy (auto-fetchable) wins
Grounded IN munis to date: Upper Merion, Horsham, Plymouth, Whitemarsh, West Conshohocken (prior) +
Conshohocken, Springfield, Whitpain (this batch). Remaining IN-list: Upper Dublin (amlegal-blocked,
D-v3-1), Lower Merion (no industrial, D-v3-2), Bryn Athyn (tiny/town-site, D-v3-3). **All remaining
IN-list munis are blocked, no-op, or marginal.** Per the coordinator's standing offer: recommend
green-lighting a fresh county rather than reaching into OUT-list munis. (Do NOT self-decide OUT-list
munis in — catch #48.)

## Notes
- municipality = parcels.city EXACTLY (mixed case) on every write; case-sensitive join.
- eCode360 fetch: curl + browser-UA (WebFetch 403s). Confirmed working this batch.
- catch #34 GIS-vs-ordinance: Whitpain parcels carry S-C/AR/AR-1 (ordinance SC/A-R/A-R-1); Springfield
  B-1/B-2 (ordinance B1/B2). Verdicts keyed to parcel codes.
