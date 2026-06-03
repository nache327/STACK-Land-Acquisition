# Op-5 Proof Decision — GO WITH RASTER CARVE-OUT

**Owner:** Master Planning Thread
**Decided:** 2026-06-04
**Source artifacts:** `docs/OP5_PROOF_PLAN.md`, `docs/OP5_DISPATCH_J_AND_O.md`, `/tmp/op5_proof/dispatch_p/cp3_final_gate.md`

---

## Decision

**GO WITH RASTER CARVE-OUT.**

Authorize the 25-agent factory build for vector-class NJ municipalities. Route raster-class municipalities (where vector linework + color-segmentation + vision-LLM georef all fall short) to operator-assisted Op-5 (manual GCPs in QGIS) until a non-vision georef approach lands.

Per the `docs/OP5_PROOF_PLAN.md` decision tree, this is the "2/3 PASS" branch:
- ✅ Fort Lee — vector-class — passes coverage + accuracy gates with nearest-fallback applied
- ✅ Garfield — vector-class — passes coverage + accuracy gates
- ❌ Hackensack — raster-class — vision-LLM georef cannot localize landmarks to sufficient pixel precision (RMS 162m vs <30m target). Carved out.
- (Fair Lawn was carved out earlier as text-only-legend class.)

---

## Evidence base

### Dispatch P final 2×4 gate (2026-06-04)

| Town | Coverage contained | Coverage +50m | Coverage +200m | Spot-check 50m mixed | Spot-check bound-only |
|---|---:|---:|---:|---:|---:|
| Fort Lee | 57.6% | 67.8% | 84.1% | 9/10 | **9/9 (100%)** |
| Garfield | 40.9% | 75.0% | 93.2% | 8/10 | **8/8 (100%)** |
| Hackensack | 50.7% | (carved) | (carved) | 4/10 (CP3 v1) | — |

**The critical finding:** every bound parcel — contained or nearest-fallback — was correctly classified. 17/17 across both vector-class towns. The mixed-sample "failures" are unbound parcels (no district within fallback radius), which is the audit gate correctly declining to assign a verdict, not a wrong verdict.

### Cumulative proof artifacts

- `/tmp/op5_proof/dispatch_p/cp3_final_gate.md` — Dispatch P 2×4 gate doc
- `/tmp/op5_proof/dispatch_p/fort_lee_p_summary.md`
- `/tmp/op5_proof/dispatch_p/garfield_p_summary.md`
- `/tmp/op5_proof/hackensack/cp3_v3_summary.md` — Dispatch O failure analysis (Mapbox geocoding worked; vision-LLM landmark localization did not)
- PR #172 (84d8263) — spatial_backfill nearest_within_meters fallback (merged 2026-06-02)
- PR #170 — NJ municipal vendor lists (merged earlier)

---

## Decisions on the 4 open questions

### 1. Production default radius: 100m with per-jurisdiction override

Spot-check accuracy on bound parcels was 100% at every radius tested (50m, 200m). The choice is pure coverage trade-off, not accuracy trade-off.

- 50m: Fort Lee 67.8% (below 70% gate), Garfield 75.0%
- 100m: Fort Lee est. ~78-80%, Garfield est. ~85-88%
- 200m: Fort Lee 84.1%, Garfield 93.2%

100m default gives reliable buffer above the 70% operational gate for typical NJ Bergen-class munis. Per-jurisdiction override via `nearest_within_meters` kwarg lets operators tighten (dense urban munis) or widen (sparse exurban munis) without code changes.

### 2. Binding-method transparency in v1 customer UI: yes

Add a small badge to `frontend/components/ParcelDrawer.tsx` displaying:
- "Zone: B1 (within district)" for `binding_method='contained'`
- "Zone: B1 (nearest, ~30m)" for `binding_method='nearest_<N>m'`

Customer-trust scales with transparency. Buyers can apply their own confidence threshold. Minimal UI work; reads from existing `parcels.zone_binding_method` field added in PR #172.

### 3. Raster-class classification — Phase 0 of factory

Empirical baseline from Bergen archive: ~10-15% of munis are raster-class (Hackensack-style). Across the 5 NJ factory counties (Bergen 70 + Essex 22 + Middlesex NJ 25 + Monmouth 53 + Burlington 40 = 210), expect ~21-32 raster-class munis routed to operator-assisted Op-5.

Phase 0 of the factory: discovery-classify all 210 munis before extraction begins. Output `{muni: {class: vector|raster|text_only_legend|absent, source_url, ordinance_url}}`. Vector + text-only-with-color-legend → automated factory. Raster + text-only-no-color → operator queue.

### 4. PR #172 merge status

Already merged 2026-06-02 as commit `84d8263`. The orchestrator's question is informational only. `backend/app/services/spatial_backfill.py::backfill_parcel_zoning_from_districts` now accepts `nearest_within_meters: float | None = None`.

---

## Carve-out class

The following PDF classes route to operator-assisted Op-5 (manual QGIS georef + manual zone-code assignment), not the factory:

1. **Raster PDFs with no exposed vector layer AND no automatable georef** — Hackensack class. Vision-LLM landmark-pixel localization fails at RMS <30m. Operator does the QGIS step.
2. **Text-only-legend PDFs with no color-to-zone mapping** — Fair Lawn class. The polygon extraction works but zone codes cannot be confidently assigned without operator pairing.

Estimated combined: 12-18% of NJ Tier-S munis. Operator throughput per archive precedent: 55-80 min per town. At ~30 carve-out munis, total operator labor: 28-40 hours, schedulable in parallel with the factory.

---

## What ships from this decision

Three deliverables, three branches:

1. **This file** (`docs/OP5_PROOF_DECISION.md`) — record of decision
2. **`docs/OP5_FACTORY_72H_PLAN.md`** — factory build specification (this PR)
3. **Coordination updates** — `coordination/lane_state.json` + `coordination/dispatch_queue.json` reflect factory authorization

Following PRs author:
- 25-agent factory pre-build (factory orchestrator stand-up, discovery-classify Phase 0)
- ParcelDrawer binding-method badge (small UI PR)
- Operator-assisted Op-5 runbook for carve-out class (docs)

No backend code changes in this decision PR — the platform fix (PR #172) already shipped.
