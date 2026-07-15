# 58-Pocket Completion Ledger — the REAL path to 100% (2026-07-15)

**Supersedes the "≈20 not-ingested pockets" framing in RECALIBRATION_58_pockets.md.** A live
per-jid audit (parcels / zoned% / dt10 ring / human verdicts / wealth-gated needles) shows that
framing was badly stale. **The path to 100% is NOT a Stage-0 ingest project.** Nearly every one of
the 58 pockets already has parcels ingested. The remaining work is the pipeline we've run dozens of
times: **ring-metrics precompute → (bind where needed) → discovery-rank → ground → verify.**

## The finding — where the un-finished pockets actually sit

Two consistent situations across every un-finished pocket:

1. **Wealthy per-city jids are already zoning-bound but have NO ring metrics, NO verdicts.**
   Scottsdale 127k · Edina 21k · Brentwood 17k · Franklin 32k · Sandy Springs 30k · Buckhead 25k ·
   Bellevue 28k · Snyderville/Promontory + Park City ~31k · Birmingham · Bloomfield Hills · Fox Chapel ·
   Pinecrest · Winnetka · Hingham · South Charlotte · Mercer Island · Bainbridge · Greenwood Village.
   → **need: ring-precompute + ground.** (Zoning already present.)

2. **County jids are mostly zoning-UNBOUND (zoned=0).** Maricopa · Arapahoe · Douglas · Miami-Dade ·
   Fulton · Cook · DuPage · Oakland · Hennepin · Mecklenburg · Williamson · Allegheny · King.
   Exceptions: **Wake NC & Nassau NY have ring metrics DONE (435k/403k) but no zoning** — need bind + ground;
   **Contra Costa CA is zoned (277k)** — needs ring + ground.

**The universal blocker is ring-metrics precompute (Stage 3a).** The needle gate requires dt=10
`parcel_ring_metrics` (median_home_value ≥ 475k AND median_hhi ≥ 100k); with ring=0, needles are
structurally 0 regardless of zoning or verdicts. Trigger: `POST /jurisdictions/{jid}/_precompute-ring-metrics`
(async; status via `GET .../_precompute-ring-metrics-status/{job_id}`). Tract-cached, Mapbox-backed —
so **precompute the small wealthy per-city jids (few tracts, cheap); do NOT fire it on giant county jids
(Maricopa 1.5M, Cook 1.9M) 4-way in parallel — Mapbox cost/rate risk.**

## Per-pocket sequence to a needle
For each pocket: **(1) bind zoning if county jid & zoned=0** → **(2) ring-precompute** →
**(3) discovery-rank** (in-ring ≥1.5ac industrial/flex parcels per zone/town — the
`_<county>_ring_rank.py` pattern) → **(4) ground ONLY the in-ring-industrial towns** (pure-residential
wealth towns — Paradise Valley, Cherry Hills, Bloomfield Hills, Wayzata, Mercer Island — will be
correct no-ops, same lesson as Greenwich/Hudson) → **(5) verify_batch + gate**.

## Session clusters (geographic, tract-cache-coherent)

**A — Mountain West + Upper Midwest:** Denver (Greenwood Village, Cherry Hills Village, Douglas/
Highlands Ranch — Douglas county needs bind), Park City UT (Park City + Snyderville/Promontory, bound),
Minneapolis (Edina, Wayzata, Minnetonka, Eden Prairie — Hennepin county needs bind for coverage).

**B — Southeast + South:** Nashville (Brentwood, Franklin — bound), Atlanta (Sandy Springs, Buckhead —
bound; Fulton county needs bind), Charlotte (South Charlotte — bound; Mecklenburg county needs bind),
**Wake NC** (ring DONE — just bind + ground, high-value), Miami (Pinecrest — bound).

**C — West + Southwest:** Phoenix (Scottsdale bound; Paradise Valley/Cave Creek/Fountain Hills; Maricopa
county heavy — per-city only), Seattle (Bellevue, Mercer Island, Bainbridge — bound; King county heavy),
Contra Costa CA (zoned — ring + ground), Portland (Lake Oswego — bound).

**D — Rust Belt + NE finish-in-place:** Chicago (Winnetka bound; Cook/DuPage — Hinsdale has no jid, needs
bind), Detroit (Birmingham, Bloomfield Hills, Bloomfield Twp — bound; Oakland county), Pittsburgh (Fox
Chapel, Sewickley, O'Hara — bound; Allegheny county), Boston-Plymouth (Hingham — bound), **Nassau NY**
(ring DONE — bind + ground, Phase-2 priority). PLUS the NE finish-in-place: Darien CT, South Brunswick NJ,
Burlington NJ wealth-tail verdict pass, Westchester NY batch-2 + Hastings gate-fix.

## Coordinator-held (this session)
- Essex NJ A+B reconcile re-score (owed).
- Ring-precompute traffic control (stagger county-scale jobs; per-city first).
- 58-pocket ledger tracking; one county re-score per pocket at batch end.

## True Stage-0 gaps (genuinely 0 parcels — small)
Miami-Dade *county* jid (but pocket = Pinecrest ✓ bound), Jefferson/Golden CO (folded out of 58),
Summit *county* jid (but pocket = Park City ✓ bound). **No 58 wealth pocket requires new parcel ingest.**
