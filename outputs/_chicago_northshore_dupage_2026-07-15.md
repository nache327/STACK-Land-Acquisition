# Chicago North Shore + DuPage hole (Phase 6) — outcome (2026-07-15)

## 1. Winnetka IL [d1c50553] — GROUNDED-REACHABLE → verified correct NO-OP
Ring already done (5,194 dt10, 100% clear the $475k gate — ultra-wealthy). **amlegal Cloudflare-JS wall
BEATEN** via the ordinance fetcher's Playwright path (`app.services.ordinance_fetcher.fetch_from_url` →
headless chromium; 36 Title-17 sections crawled where curl+UA only got the SPA shell). Verdict: **0-needle
no-op**, verified from the ordinance + DB:
- **#38 catch: Winnetka B-1 (§17.32) and B-2 (§17.36) are "Multifamily Residential Districts", NOT business.**
  So the 102 in-ring "B2" + 2 "B1" parcels are RESIDENTIAL — not a needle (Tarrytown M-1/2/3 pattern).
- Districts (§17.08.010): R-1..R-5 single-family, B-1/B-2 multifamily, **C-1/C-2 commercial, OF office, IN
  institutional, A** — **NO industrial district anywhere.**
- C-1 (65) / C-2 (201) commercial have **0 in-ring ≥1.5ac** parcels. Self-storage is not a named use (the
  only "storage" text is an accessory-use restriction: no outdoor storage of commercial trucks/boats).
- ⇒ zero in-ring ≥1.5ac parcels in any self-storage-eligible district → structural 0 needles. Not grounded
  (no needle possible; consistent with Darien no-op handling). **Reusable win: amlegal-JS is beatable via
  the Playwright fetcher — supersedes the "amlegal paste-gated" note in [[project_finish_in_place]].**

## 2. Cook North Shore villages (Kenilworth/Glencoe/Wilmette/Northfield) — BLOCKED on bind; unblock path below
Parcels sit in the **Cook County jid [1726fc6f]** (1,865,823 parcels, **city = NULL for ALL**, ring=0, zoning
unbound). Two blockers:
- **Identify the village parcels:** Cook raw has `CITYNAME` (mailing city, e.g. 'PALATINE') + `township_name`
  → backfill `parcels.city` from `raw->>'CITYNAME'` (Nassau MUNI_NAME pattern) to scope the 4 villages.
  (Mailing-city ≈ village for these incorporated North Shore towns; verify against village boundary.)
- **Zoning source (the real blocker):** Cook County's zoning layer is **UNINCORPORATED-only**
  (`hub-cookcountyil.opendata.arcgis.com` Unincorporated Zoning Districts) — the incorporated villages have
  their OWN zoning, NOT in it. **UNLOCK: the villages are GIS-Consortium members** (public.gisconsortium.org)
  → per CLAUDE.md, reach their token-gated layers via the anonymous proxy
  `utility.arcgis.com/usrsvcs/servers/<guid>/rest/services/<F>/AGOL_<F>_Project/MapServer` (guid from each
  village's community-map-viewer). Verify #38 (layer IS in IL + dry-run coverage%) before --apply.
- **Then:** tract-batched ring for just those villages' tracts (NOT the 1.9M county) → ground via
  amlegal-Playwright.
- **Prior (high):** likely residential no-ops. Kenilworth + Glencoe are famously pure-residential (0 industrial);
  Wilmette + Northfield have small commercial cores (Northfield has a Willow Rd office/light-industrial strip —
  the only plausible needle). Same North Shore pattern as Winnetka.

## 3. Hinsdale / DuPage [8e748965] — BLOCKED (no polygon layer + parcels unidentifiable) — paste-spec below
DuPage County jid = **336,715 parcels, city=NULL, NO `raw` at all, ring=0, zoning unbound.** Hinsdale
village parcels are **not identifiable in the DB** (no city, no raw to backfill from). DuPage County GIS
`gis.dupageco.org/.../Zoning` has only **`UnincorporatedZoningData`** — Hinsdale (incorporated) is NOT in it.
No CMAP regional parcel-zoning layer exists (CMAP publishes land-USE inventory, not municipal zoning). See
paste-spec in outputs/_exceptions_A.md.

## Handoff to coordinator
- **Winnetka [d1c50553] = 0 needles, verified no-op** (amlegal-Playwright reached; B=multifamily #38; no
  industrial). Grounded needles this session = 0.
- **Cook villages [1726fc6f]** = Stage-1 bind project — city-backfill from raw CITYNAME + GIS-Consortium
  proxy zoning bind + tract-ring + amlegal-Playwright ground. Likely no-ops (residential North Shore).
- **Hinsdale/DuPage [8e748965]** = blocked: parcels unidentifiable (city=NULL, no raw) + no municipal zoning
  polygon layer. Needs a spatial village-boundary scope + a Hinsdale zoning source. Paste-spec filed.
- No re-score / CoStar. County jids untouched (no county-scale bind/ring fired).
