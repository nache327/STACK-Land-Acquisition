# 58-Pocket Recalibration — Path to 100% (2026-07-14 EOD)

Program state: **≈5,100 wealth-gated needles across ~14 counties.** NJ Tier-1 just closed (+375).
Coverage of the 58-pocket map: **~28 pockets substantially DONE (~48%)**; the rest split between
finish-in-place (cheap) and not-yet-ingested (the real remaining lift). Precise bound%/ring% per pocket
to be confirmed next session when the shared DB is uncontended (today's audit query timed out under load).

## Bucket 1 — DONE (grounded + wealth-ring measured)
NE Corridor + DC + eastern-PA + Chicago-North-Shore, in needle order:
- **MA:** Norfolk 1,331 · Middlesex 1,191 (both past Loudoun 1,153)
- **PA:** Chester 710 · Bucks 380 · Montgomery 208 · Delaware 67 · Allentown (Lehigh) harvesting
- **NJ:** Morris 354 · Essex 144 · Middlesex 93 · Union 90 · Passaic 48 · + Bergen/Somerset/Monmouth/
  Hunterdon/Burlington (Phase-1, prior)
- **IL:** Lake 267
- **NY:** Westchester 122
- **CT:** Fairfield-county 22 + Stamford 72 (marquee; Greenwich/Westport/New Canaan = correct no-ops)
- **DC-metro (prior):** Loudoun VA, Fairfax VA, Montgomery MD, Howard MD
- **UT (prior):** Salt Lake cluster

Calibration learned: suburban wealth counties land **~90–360 needles** each; the number tracks
*industrial-that-permits-storage inside the wealth ring*, NOT raw wealth-pass or raw industrial acreage
(Fairfield NJ 315 lots → 9 needles; Hudson 3,712 wealth parcels → 0). Purest-wealth pockets zone storage
out entirely (Greenwich, Hudson Gold Coast) — correct no-ops.

## Bucket 2 — BLOCKED, finish-in-place (ingested; cheap incremental yield)
- **Stage-2 CoStar (armed-but-waiting):** the entire NJ Tier-1 (Essex/Middlesex/Union/Passaic) has
  on-needle=0 — needles are grounded but no CoStar listings matched. **A CoStar pull per county turns
  ~375 grounded needles into digest-ready deals.** Also refresh Chester/Bucks/Morris. → biggest cheap win.
- **Paste/source-gated (8 items):** White Plains NY (Municode LI:134), Redding CT (self-storage by-right,
  needs shapefile), Newton MA (Akamai), **Monmouth LI (67-needle NULL ruling)**, Upper Dublin PA, Westwood
  MA, Tinicum PA (2021 rebind), Port Chester NY (re-stamp). Each = one paste/ruling → grounds.
- **Stage-1 residual town-binds:** Darien CT, South Brunswick NJ (Municode), a handful of single towns —
  the Atlas/UCNJ/county-GIS bind pattern (now hardened) applies; low effort each.
- **Rural NJTPA tail:** Sussex/Warren NJ — bindable via the Atlas but low-wealth → likely near-no-op.
  Deprioritize (anti sprint-volume).

## Bucket 3 — NOT INGESTED (the real gap to 100% — Stage-0 lift)
These pockets have no parcels/zoning in the system yet; nothing above applies until they're ingested:
- **Phase 2:** Nassau NY (recon'd NO-GO — no county zoning composite; per-village PDFs).
- **Phase 4:** Plymouth MA, Cook IL, DuPage IL.
- **Phase 5 (South + Mtn-West):** Williamson TN, Fulton GA, Mecklenburg NC, Wake NC, Douglas CO,
  Arapahoe CO, Jefferson CO.
- **Phase 6 (West + outliers):** Maricopa AZ, King WA, Multnomah/Clackamas OR, Hennepin MN, Oakland MI,
  Allegheny PA, Contra Costa CA, Miami-Dade FL.
≈ **20 pockets at 0%** — this is the majority of the remaining distance to 100%, and it's an **ingest
project** (parcel + zoning acquisition, Adam's automation lane per memory), not a grounding-session task.

## Sequenced path to 100%
1. **NOW / cheapest, highest-ratio:** CoStar pulls for the 4 NJ Tier-1 counties (Nache-supplied reports →
   `/api/listings/upload` + `_match_listings_direct.py`) — converts ~375 grounded needles to live deals.
   Then clear the 8-item paste queue (each a one-shot ground). This closes the *ingested* map to full.
2. **NEXT / medium:** residual Stage-1 town-binds (Darien, South Brunswick, etc.) via the hardened bind
   template; optional Sussex/Warren if a slow day.
3. **THE 100% GAP / the real lift:** Stage-0 ingest of the ~20 Southern/Western pockets, one metro at a
   time. Once a metro's parcels+zoning are in, the proven pipeline applies unchanged: ring-precompute →
   Atlas/county-GIS bind → discovery-rank → ground in-ring towns → CoStar. Recommend piloting ONE Phase-5
   metro (Wake NC or Williamson TN — growth markets, cleaner entitlement) to time the ingest + prove the
   template travels outside the NE corridor, then scale.

## Standing infra (all shipped this run — reusable for every new pocket)
- `bind_nj_atlas082025.py` — hardened Stage-1 bind (orderByFields paging + UNNEST batching + bad-code
  filter); template for any NJTPA/county-GIS county.
- `verify_batch.py` — one-command batch verification (casing + needle tally + on-needle + gate).
- `_match_listings_direct.py` — reliable CoStar matcher (bypasses the stalling Railway worker).
- `CLAUDE.md` — auto-loaded playbook so sessions don't re-derive.
- Gate is a true signal again (Hastings + Mine Hill stubs cleaned).

## Owed / open
- Essex A+B reconcile re-score (post-merge; Union/Passaic/Middlesex already re-scored solo).
- Merge the open PRs (Essex ground A/B, Middlesex #535 [conflict resolved], Passaic, Union batch2, CT,
  Chester, coordinator cleanup/handoff branches).
- 8-item paste queue — Nache-gated.
