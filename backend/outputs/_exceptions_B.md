# Session B — Cook IL North Shore (Phase 4)

## (4a) Winnetka (jid d1c50553-1ec0-49b8-9e52-46186c200221) — RING DONE, grounding amlegal-blocked
- **Ring-precompute COMPLETE** (fired per-city, ledger-authorized solo): job ded5121c, 9 tracts,
  10.4s, parcels_written 20,776. This was the blocker — Winnetka was bound 94% (4,893/5,194) but had
  ring=0. **Now 239 wealth&1.5ac** measurable (was 0).
- Wealth&1.5ac by zone: **B2 102**, R2 75, R1 11, R4 8, R5 7, B1 2, R3 2. (C1/C2/D have 0 — sub-1.5ac.)
  Zones: R1-R5 residential, B1/B2 business, C1/C2 commercial, D. (Ordinance: 5 SF + 2 MF + 2 commercial
  + 1 industrial district.)
- **Grounding BLOCKED (paste-gate):** Winnetka's Title 17 zoning is on amlegal
  (codelibrary.amlegal.com/codes/winnetka), which serves district use-tables via a **Cloudflare JS
  challenge** (not the UA-only gate) — curl+UA gets only the SPA shell / "Just a moment...". Village site
  has no full-text ordinance PDF (only application packets + zoning map). Did NOT ground on a guess
  (#37 verbatim-basis). **Likely a Darien-style no-op** (wealthy North Shore residential village; the
  needle candidate B2 is the village-center business district, which almost certainly prohibits
  self-storage) — but needs the verbatim Title 17 use table for B1/B2/C1/C2/D to confirm.
  → HANDOFF: paste Title 17 commercial/industrial use tables, or fetch via a JS-capable path.

## (4b) Cook County North Shore (jid 1726fc6f-9927-413e-b20e-936ab438de10) — coordinator-gated
- Cook is ~1.9M parcels, mostly zoning-UNBOUND. The North Shore wealth towns other than Winnetka
  (Kenilworth, Glencoe, Wilmette, Northfield) sit in this county jid and need **county-scale bind +
  ring-precompute**. Per the 58-pocket ledger: "do NOT fire ring-precompute on giant county jids
  (Cook 1.9M) ... ping coordinator before any COUNTY-scale precompute." NOT run solo.
  → HANDOFF to coordinator: authorize/stage the Cook county bind + (tract-batched) ring-precompute,
  then discovery-rank the North Shore in-ring industrial and ground.
