# Session C — Passaic NJ prep (parcellogic/passaic-nj-prep)

## Passaic County NJ (jid 7a9ed95d-df89-4864-a203-f831a987b562) — PREP ONLY, HELD
County-model jurisdiction, 125,785 parcels, 16 municipalities (Paterson/Clifton/Wayne/West
Milford/Passaic/Hawthorne/Ringwood/Wanaque/Totowa/Woodland Park/Pompton Lakes/Little Falls/
North Haledon/Bloomingdale/Haledon/Prospect Park). Doubly-blocked at recon:
`parcel_ring_metrics` dt=10 = 0 (Stage 3) AND `zoning_code` NULL on 100% (Stage 1).
**After prep: Stage 3 CLOSED (ring complete); Stage 1 bind DRY-READY (apply held).**

**NOTHING grounded, NOTHING bound.** Prep to make Passaic fire-ready the instant A's Essex
distribution confirms suburban-NJ yields + coordinator/Nache go.

### Task 1 — ring precompute (Stage 3): ✅ COMPLETE
`POST /api/jurisdictions/7a9ed95d…/_precompute-ring-metrics-worker` (X-Admin-Secret) → **HTTP 202
enqueued** to the Dramatiq worker path. Landed within ~2 min (tract demographics already available,
so a fast spatial-join + batch UPSERT). Verified: **125,785 dt=10 rows, 100% with non-null
median_home_value + median_hhi, and 25,687 wealth-pass** (HV≥475k AND HHI≥100k). Stage 3 done —
Passaic now has a real wealth-ring pool to gate needles against.

### Task 2 — NJTPA Atlas bind (Stage 1): DRY-RUN READY (no writes)
Script: `backend/scripts/_bind_passaic_njtpa_atlas.py` (replicates the proven Essex bind:
Atlas MapServer 082025, `County='Passaic'` filter, centroid-within EPSG:4326, replace=false,
provenance `njtpa_atlas_082025`/`njtpa`, overlays excluded from base bind). **DRY by default;
writes gated behind `APPLY=1` — do NOT set without the greenlight.**

Dry-run result: **county centroid match = 123,645 / 125,785 = 98.3%.** Per-town match:
Wayne 100%, North Haledon 100%, Wanaque 97.6%, Ringwood 99.9%, Pompton Lakes ~100%, Totowa ~100%,
Woodland Park ~100%, Little Falls 100%, Hawthorne 100%, West Milford 99.1%, Bloomingdale 99.9%.
(~1.7% unmatched county-wide = expected slivers/water — West Milford lakes, edge centroids.)

**#38 spot-check — Atlas codes match town ordinances (clean):**
- Wayne: R-15 / R-30 / RC-2.5 / PUD / GA / **I (Industrial)** / **B (Business)** — real Wayne
  district vocabulary; "I" = Industrial (correct, not Institutional), 315 parcels — a live needle
  candidate once grounded.
- North Haledon: RA-1/RA-2/RA-3 / B-1/B-2 / AHTD townhouse / RDZ — matches (residential-heavy
  wealthy borough, no heavy industrial, as expected).
- Wanaque: R-10/R-15/R-40 / B / IR-1 (Industrial/Research) / AAH — matches.
- Ringwood: R-20/R-40/R-80V / I-60 (Industrial/Office/Research) / CS-40 — matches.
- Little Falls: R-1A/B/C / B-1/B-2/B-3 / LI (Light Industrial) / TV-CBD — matches.
- Hawthorne: R-1/R-2/R-3 / B-1/B-2/B-3 / I-1 (Light Industrial) — matches.
- Bloomingdale: R-10/R-20/R-40 / B-1 / M-1 (Light Industrial) — matches.
Each code carries an Atlas `Full_District_Name` (affirmative basis for later grounding). No
mislabeled-family (#38) red flags. Atlas `Jurisdic_1` town spellings are Title-Case ("Wayne
Township") vs parcels.city lowercase-suffix ("Wayne township") — irrelevant to the spatial bind,
but the grounding session must set `municipality` = exact parcels.city.

### HOLD (both gated)
- Bind apply (`APPLY=1`) — HELD pending Essex-yield confirmation + coordinator/Nache go.
- All grounding — HELD until bound + ring-complete + go. No verdict rows written this session.
