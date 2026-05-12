# Bergen County Scale-Up Plan — Post-Paramus

**Date**: 2026-05-12
**Status**: Paramus end-to-end loop proven (115 districts, 8,619 overlays, 8,619 zoned parcels). Bergen is currently 3.1% zoned with `no_zoning_polygons` blocker cleared.

This plan covers the remaining 69 Bergen municipalities. **Do not auto-mass-ingest** — discovery alone has known false-positive failure modes that require operator review.

---

## What we learned from the 70-town sweep

A single `POST /_discover-municipal-zoning` over all 70 Bergen towns produced 350 candidate rows in `zoning_sources` (5 per town × 70 towns). After hand-classification, the actual signal-to-noise breakdown:

| Tier | Definition | Count | Action |
|---|---|---:|---|
| **A. Verified ingest-ready** | Paramus_Zoning, 80 confidence, 144 features, ingested with 8,619 spatial joins | 1 | Done |
| **B. Plausible per-town candidate** | Top hit has 5+ char exact-word match AND title not obviously another state | ~3 | Probe + verify + ingest |
| **C. False-positive Tier 1** | Top hit matches a substring but is a different jurisdiction entirely (e.g. Franklin Lakes → Franklin County Iowa, Garfield → Garfield County Utah) | ~12 | Reject, look elsewhere |
| **D. Generic "Zoning" top-hit** | A single generic `services3.../Zoning/FeatureServer/0` layer (339 features) appears as confidence-70 top-hit for 40 different Bergen towns | 40 | Reject — same layer, not real |
| **E. Substring false-positive** | "Cliffside Park" → "MontereyPark Zoning" pattern (8 occurrences for Park-suffixed towns), East/Fort/North/South/Lake substrings | ~14 | Reject |

**Net**: of 70 towns, only **1 town (Paramus) is verified ingest-ready** and **~3 towns (Edgewater, Oakland, possibly Hackensack) have plausible Tier-B candidates** worth manual verification.

For the remaining ~66 towns, ArcGIS Hub alone does not surface usable per-town zoning. The scale-up path requires *augmenting* the discovery service.

---

## Tier B: Probe + verify candidates (next sprint, 3 towns)

Each needs the operator to (1) probe the FeatureServer URL for layer metadata, (2) confirm the layer is the town's actual zoning (not "Proposed", not a different state), (3) verify, (4) ingest.

### B-1. Edgewater
- Source: `https://services.../Edgewater_Geodatabase/FeatureServer` (2,299 features, score 80)
- Probe checklist: confirm geometry_type=polygon for at least one layer; layers list contains "Zoning" or similar; jurisdiction owner in metadata references NJ.
- Risk: "Geodatabase" suggests this is a *bundle* of layers (could be parks, schools, zoning). `_ensure_layer_index` will pick the first polygon layer — may not be zoning.
- Expected delta if real: Edgewater has ~5,000 parcels; ingest delivers ~5k overlay rows.

### B-2. Oakland (NJ borough, not CA city)
- Source: `https://services1.arcgis.com/YZCmUqbcsUpOKfj7/.../Oakland_Proposed_Zoning_WFL1/FeatureServer` (54 features, score 95)
- Probe checklist: "Proposed" zoning is a draft that hasn't been adopted yet. Need to confirm whether this represents *current* zoning or a future overlay.
- Risk: 54 features is very small; may be a study-area subset, not full town coverage.
- Expected delta if real: ~3,500 parcels.

### B-3. Hackensack
- Source: `Hackensack_Hydro` (110 features) — this is *waterways*, not zoning. Reject as Tier B candidate.
- Status: drop from Tier B. Hackensack needs alternative discovery.

**Net Tier B realistic**: 2 towns (Edgewater + Oakland). Expected coverage gain: ~8.5k overlays = +3% Bergen coverage. Combined with Paramus, Bergen reaches ~6% county coverage.

---

## Tier C–E: Augmentation paths for the 66 remaining towns

ArcGIS Hub has no public per-town zoning service for these. The scale-up requires *new* discovery surfaces:

### 1. State-level NJ aggregator
- **NJ Office of GIS** publishes a statewide municipal-boundaries layer; check if they also have a statewide zoning aggregation (e.g. via NJDEP's iMapNJ).
- **NJ Department of Environmental Protection** publishes a Land Use Land Cover layer that's *zoning-adjacent* but not authoritative zoning.
- Action: add `nj_state_aggregator` to `zoning_sources.discovered_by` taxonomy. If a statewide layer exists with a `MUN` or `municipality_name` field, one ingest delivers all 70 Bergen towns at once.

### 2. Municipal-website scraping
- Each town's `.gov` website typically has a "Zoning Map" or "Land Use" page. Many publish a public ArcGIS embed at `arcgis.com/apps/.../{town}-zoning`.
- Pattern: `https://{town}nj.gov/zoning-map` or `https://{town}boronj.org/zoning`.
- Action: add a discovery service that scrapes the town website's HTML for embedded ArcGIS service URLs, then probes them through the existing pipeline.

### 3. State open-data portals
- `data.nj.gov` (Socrata) — search for "Bergen zoning" or "municipality zoning".
- Action: add a Socrata adapter to `zoning_discovery` that runs alongside the Hub adapter.

### 4. Manual operator entry
- For the long tail (~30+ towns), accept that discovery will miss them. Operator adds rows directly to `zoning_sources` via a new `POST /jurisdictions/{id}/_sources` (which we already have as a verify endpoint; extend it to support manual-add).
- Operator pastes a known URL + town name → row inserted with `discovered_by='manual'`, `confidence_label='verified'`, ready for ingest.

---

## Discovery-service hardening (priority for scale)

The Bergen sweep exposed two discovery bugs that will recur in every NJ county:

### Bug 1: Substring matching inflates false-positive confidence
Current `_name_tokens` accepts a town-name token that appears as a *substring* of any title word. So `Park` in "Cliffside Park" matches `MontereyPark` (one word). The fix: require **whole-word matching** (regex `\b{token}\b`) for the town-name bonus.

**Estimated impact**: removes 14 false Tier-1 boosts in Bergen alone.

### Bug 2: Generic "Zoning" layer dominates 40+ towns
A single `services3.arcgis.com/m3XdyJh55Jrxxk0l/.../Zoning/FeatureServer/0` (339 features) appears as the top hit for 40 different Bergen towns at confidence 70. It's not associated with any one town. The fix: **penalize layers whose title is exactly "Zoning" with no town-name component** by clamping their confidence to ≤ 50 unless the FeatureServer parent path contains a town-matching token.

**Estimated impact**: drops 40 Bergen towns from "discovered" to "discovered_low", which is the honest state.

Both fixes belong in `backend/app/services/zoning_discovery.py` and should be done **before** any other NJ county sweep (Morris, Hunterdon, or any new NJ county). Otherwise the operator's review queue is dominated by garbage.

---

## Recommended execution order

| Step | Action | Effort | Bergen delta |
|---|---|---|---:|
| 1 | Probe Edgewater FeatureServer metadata; if zoning layer exists, verify + ingest | 30 min | +5k overlays |
| 2 | Probe Oakland_Proposed_Zoning_WFL1; confirm current vs. draft + state | 30 min | +3k overlays (if real) |
| 3 | Implement Bug 1 fix (whole-word matching) + Bug 2 fix (penalize generic "Zoning") in zoning_discovery | 2-4 hrs | none direct; cleans review queue |
| 4 | Re-run full Bergen sweep with new scoring; expect Tier-1 count to drop to ~3 honest matches | 1 sweep | clarifies state |
| 5 | Add NJ-state-aggregator discovery adapter (probe iMapNJ / data.nj.gov / NJOGIS) | 4-8 hrs | potentially +60 towns if statewide layer exists |
| 6 | If statewide aggregator finds nothing, add municipal-website scraper for top-10 Bergen towns by parcel count | 8-16 hrs | +30-60k overlays |
| 7 | Operator manual-entry queue for the long tail | ongoing | +N as found |

**Do NOT** mass-verify the existing 350 Bergen `zoning_sources` rows. That would commit the false positives. The `confidence_label='verified'` gate is load-bearing — let operator approve each one with a probe.

---

## Concurrency + retry parameters

For sweeps over 30+ towns:
- **Concurrency**: keep `_PER_TOWN_CONCURRENCY = 4` (already in `nj_municipal_discovery.py`). Hub rate-limits at ~10 req/s per IP; 4 concurrent semaphore × ~3 req/town = ~12 req/s peak — within budget.
- **DB serialization**: with the asyncio.Lock fix (commit `4ea5ec2`), persist+commit serializes — no race.
- **Retry**: existing `_hub_search` doesn't retry on transient HTTP errors; for full-state sweeps add a 1-retry wrapper with 2s backoff.
- **Per-town timeout**: 20s (httpx default in `discover_municipal_zoning_for_county`). Towns that exceed it return `error="timeout"` and skip — sweep continues.

---

## Acceptance criteria for "Bergen scale-up done"

The scale-up is *complete* (not necessarily *exhaustive*) when:
1. Every Bergen town has at least one row in `zoning_sources` (already true: 70/70 after the full sweep).
2. Discovery bugs 1+2 fixed; re-sweep produces accurate confidence labels.
3. Every Tier-B candidate has been probed + verified-or-rejected by operator.
4. Bergen's coverage_snapshot shows `parcel_with_zoning_code_count / parcel_count >= 0.30` (a realistic ceiling for what Hub-only discovery can deliver; ~85k of 281k parcels).
5. The remaining ~70% of unzoned parcels are tracked in a `BERGEN_GAPS.md` file with each town categorized by next-action (state-aggregator-needed / scrape-needed / manual-entry-needed).

Pushing past 30% requires augmenting discovery with one of the alternative paths above — not blind verification of existing Hub candidates.

---

## Is the municipal loop production-ready?

**Yes, with caveats:**

✅ Discovery → verify → ingest → overlays → snapshot — proven end-to-end on Paramus
✅ Idempotent re-runs (ON CONFLICT)
✅ Operator-verified rows protected from re-discovery overwrite
✅ Concurrent multi-town persist no longer races (`4ea5ec2`)
✅ Field-name flexibility for NJ municipal layer shapes (`37dbc24`)
✅ Regression test in place

⚠️ Discovery returns too many false positives in counties where towns have substring-collision names — the substring-matching + generic-zoning bugs above. Live operator review currently compensates. Fix should land before sweeping additional NJ counties.

⚠️ Bergen's realistic ceiling via Hub-only is ~5-10 towns (~30% coverage). True 90%+ coverage requires non-Hub data sources (state aggregator or per-town municipal-site scrape) — those are out of scope for the current discovery service.

⚠️ Operator workflow is curl-only; a UI for batch-review/verify/ingest would unblock non-engineer operators. Out of scope for current sprint.
