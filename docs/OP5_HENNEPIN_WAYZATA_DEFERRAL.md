# Op-5 Hennepin Wayzata Phase 7A.3 — DEFERRAL (Option B)

**Owner:** Lane A
**Date:** 2026-06-18
**Status:** Polygon-serviceable but **not formally operational pending GeoPDF tooling**. Same shape as Loudoun VA TOWNS deferral.
**Predecessors:** PR #294 Phase 7A.2 (Wayzata jurisdiction `1729467c-…` registered, 1,992 parcels moved from Hennepin umbrella) · Diagnostic PR #300 (GeoPDF path verdict, merged 2026-06-18T21:36:38Z).

---

## TL;DR

Wayzata Phase 7A.3 zoning ingest is deferred per Master's Option B: accept partial-with-residual state for now, queue GeoPDF extraction tooling as a separate Lane A track. Hennepin wave closes at 4/5 munis operational (Edina + Plymouth + Eden Prairie + Minnetonka; count 26→29 when applies land). Wayzata reopens when bandwidth permits.

## Why deferred (not blocked)

Wayzata is the only Hennepin wealth-band muni without a machine-readable zoning Feature Service:

| Probe | Result |
|-------|--------|
| ArcGIS Hub search | No Wayzata-published zoning Feature Service |
| Municode | Code of ordinances loads at `library.municode.com/mn/wayzata/codes/code_of_ordinances` (Chapter 937, Ordinance 811) |
| Diagnostic PR #300 | March 2025 Wayzata zoning map is Esri ArcMap GeoPDF with `Layers_Zoning_Designation1` extractable vector layer |

Diagnostic PR #300's verdict: **GeoPDF vector extraction + style-to-zone-code QA** is the primary path. Diagnostic explicitly rejected broad-stroke parcel classification as a production fallback.

## Master's Option B (chosen 2026-06-18)

Two paths surfaced:

**Option A**: Build GeoPDF extraction tooling as a future dispatch (~1-2 days separate Lane A track).
**Option B (CHOSEN)**: Accept Wayzata partial-with-residual for now. Phase 7A.2 jurisdiction registered. Phase 7A.3 deferred. Document as "polygon-serviceable but not formally operational pending GeoPDF tooling."

Rationale: Adding GeoPDF extraction primitive mid-Hennepin-wave violates one-thing-at-a-time discipline. Master picked B; spike not required (Lane A confirmed agreement — no disagreement-triggered 30-min spike on `pdf2geojson` / `vector-tile-extractor` libs needed).

## Current state

- Jurisdiction registered: `1729467c-4efa-4b21-98fd-1a20281b4296` (Phase 7A.2 PR #294)
- 1,992 parcels with `jurisdiction_id` = Wayzata, `city` = 'Wayzata'
- bbox UPDATED (Phase 7A.2's bbox subroutine touched this)
- `zoning_code` column NULL on all 1,992 parcels (no Phase 7A.3 substrate)
- Audit verdict: SUB-GATE on parcel_zoning_code_coverage_pct (0 / 1,992 = 0 %)
- Operational status: **NOT operational** (count 26 → 29 ceiling for this wave, would be 30 if Wayzata flipped)

## Comparable precedent — Loudoun VA TOWNS

Same deferral shape:
- Loudoun VA jurisdiction registered, parcels loaded
- Per-town zoning ingest deferred (no machine-readable per-town publisher)
- Reopened when bandwidth permitted

Loudoun precedent confirms this is a valid in-flight state, not a halt.

## Reopen criteria

Reopen Wayzata Phase 7A.3 as separate sprint when:
1. **GeoPDF tooling primitive built**: validated `pdf2geojson` or equivalent extraction lib added to Lane A's toolbox
2. **Manual polygon authoring approved**: ~15 hand-drawn polygons from Wayzata's PDF map authoritative for the 15-code matrix (~3-4h manual digitization per orchestrator's brief)
3. **Wayzata publishes a Feature Service**: ArcGIS Hub or municode adds GIS layer (unlikely near-term but watch)
4. **Master changes priority**: Wayzata flip becomes worth burning the tooling sprint

## What's in this PR

- `docs/OP5_HENNEPIN_WAYZATA_DEFERRAL.md` (this file)

No code changes. Wayzata jurisdiction remains registered with `zoning_code` NULL on all 1,992 parcels.

## Hard rules honored

- Don't build GeoPDF extraction tooling mid-wave (Master's Option B verbatim)
- Halt-and-report — documented deferral, not silent partial state
- One-thing-at-a-time discipline preserved

## Hennepin wave final operational impact

When orchestrator's 4 pending matrix sprints apply (Edina 37 ✓ already applied, Plymouth 24, Eden Prairie 28, Minnetonka 14):

| Muni | Status | Operational delta |
|------|--------|------------------:|
| Edina | ✓ Applied 2026-06-18T22:32:13Z | +1 (25 → 26) |
| Plymouth | DB-level 5/5 PASS — awaiting apply | +1 (26 → 27) |
| Eden Prairie | DB-level 5/5 PASS — awaiting apply | +1 (27 → 28) |
| Minnetonka | DB-level in flight at PR commit time | +1 (28 → 29) |
| Wayzata | Deferred per Option B | 0 |

**Final Hennepin wave count: 25 → 29** (4 operational flips, 1 deferred).
