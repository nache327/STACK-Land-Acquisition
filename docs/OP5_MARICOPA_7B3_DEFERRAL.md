# Op-5 Maricopa Phase 7B.3 — Consolidated Deferral Report (PV + CC + FH + Carefree)

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** HALT-and-report per Master's Option (a) approval. Deferral pattern (Wayzata Option B precedent) applied to 4 Maricopa wealth munis after live source-freshness probe revealed Diagnostic PR #232's verdicts no longer hold.
**Verdict:** **DEFERRED.** Paradise Valley + Cave Creek + Fountain Hills + Carefree all defer Phase 7B.3 zoning ingest. Maricopa wave closes at **1/5 operational** (Scottsdale only).
**Predecessors:** PR #305 Phase 7B.1 · PR #310 PV 7B.2 · PR #313 4-muni 7B.2 + Scottsdale 7B.3 · Diagnostic PR #232 (acquisition spec, 2026-06-11).

---

## TL;DR

Live probes 2026-06-19 (8 days after Diagnostic PR #232) reveal the zoning sources Master expected are gone or never existed at all. Same shape as Wayzata Option B deferral (no machine-readable source). 4 jurisdictions registered with parcels + bbox but `zoning_code` unpopulated.

## Per-muni verdict

| Muni | PR #232 status (2026-06-11) | 2026-06-19 probe | Verdict |
|------|------------------------------|-------------------|---------|
| Paradise Valley | "Live zoning layer, 427 nonblank ZONECLASS" | **499 Token Required** at `gis.paradisevalleyaz.gov/.../Planning_and_Zoning/MapServer/7` | TOKEN-GATED since PR #232 |
| Cave Creek | LOW Path B ordinance-only | No AZ Feature Service in ArcGIS Hub (only Oregon namespace) | NO source |
| Fountain Hills | LOW Path B ordinance-only | Only result: `ToFH 2005 LandUse_Zoning` (21 years stale) | NO fresh source |
| Carefree | LOW Path B ordinance-only | Only result: 1988 static "zoning district map" PDF | NO source |

## Critical lesson codified — SOURCE FRESHNESS DRIFTS WEEK-TO-WEEK

**8 days** between Diagnostic PR #232 (2026-06-11) probe and Lane A fire-time probe (2026-06-19). Paradise Valley's previously-public zoning Feature Server became token-gated in that window. Future per-muni waves should:

1. **Verify source freshness AT FIRE TIME**, not trust acquisition specs > 7 days old
2. **Probe each muni's published GIS** before assuming Path A applicability
3. **Document token-gate state** explicitly when discovered
4. **Treat "live zoning layer per spec" + > 7 days = potentially-stale** until re-verified

This pattern previously caught Greenwich (LOW Path B → HIGH Path A promotion when Daniel.Clark_greenwichgis layer surfaced in 2026-06-19 probe). Same discipline catches PV's degradation in the other direction.

## What's deferred vs what's locked in

### Locked in (Phase 7B.1 + 7B.2 unaffected by 7B.3 defer)

| Muni | jid | Parcels | bbox | Phase 7B.3 status |
|------|-----|--------:|------|--------------------|
| Paradise Valley | `a79a7175-…` | 9,847 | `[-112.013, 33.508, -111.920, 33.583]` | DEFERRED |
| Cave Creek | `5b1227a1-…` | 16,521 | `[-112.138, 33.655, -111.822, 33.911]` | DEFERRED |
| Fountain Hills | `666dc28d-…` | 15,810 | `[-111.787, 33.568, -111.588, 33.727]` | DEFERRED |
| Carefree | `da313f75-…` | 2,991 | `[-111.963, 33.799, -111.874, 33.857]` | DEFERRED |

### Operational despite deferral

- Scottsdale: jurisdiction registered + Phase 7B.3 fired (PR #313, 86.0 % cov, 229 codes, 1,937 districts)
- Maricopa County umbrella jurisdiction retained

### Path B doesn't apply here

For Wayzata, Master accepted Option B "polygon-serviceable but not formally operational pending GeoPDF tooling". Same logic for PV/CC/FH/Carefree:
- Token-gated source for PV (orchestrator can't author 427-row matrix without seeing the source)
- No source for CC/FH/Carefree (orchestrator's `9af5827` LOW Path B pre-stage was ordinance-only — same as Wayzata's Ord. 294 PDF)

Lane A halts. Orchestrator handles per their pre-stage as-is or defers per Wayzata pattern.

## Sibling deferrals (same pattern)

| Muni | Reason | Reopen criteria |
|------|--------|-----------------|
| Wayzata MN | GeoPDF extraction tooling not built | GeoPDF tooling sprint |
| Westport CT | Vessel Tech token-gated | B2B unlock |
| Darien CT | Vessel Tech + Tighe-Bond + MapGeo token-gated | B2B unlock |
| New Canaan CT | Vessel Tech + Tighe-Bond + eCode360 token-gated | B2B unlock |
| Paradise Valley AZ (NEW) | PV town source went token-gated 2026-06-11 → 2026-06-19 | Direct outreach to Paradise Valley GIS / token negotiation |
| Cave Creek AZ (NEW) | No public Feature Service | Built ordinance-derived PDF flow |
| Fountain Hills AZ (NEW) | 2005 stale layer only | Town GIS update |
| Carefree AZ (NEW) | 1988 static map only | Direct outreach |
| Sewickley Heights PA (Allegheny per PR #317) | Ordinance No. 294 PDF only | Wayzata-style PDF sprint |

## Updated campaign ceiling

| Wave | Ops gained / 5 | Δ from theoretical 5/5 |
|------|---------------:|----------------------:|
| Hennepin MN | 4 (Wayzata defer) | -1 |
| Fairfield CT | 2 (Westport + Darien + New Canaan defer) | -3 |
| Maricopa AZ | 1 (PV + CC + FH + Carefree defer) | -4 |
| Oakland MI | TBD (Birmingham + Bloomfield Hills HIGH Path A confirmed; Bloomfield Twp + Franklin + Beverly Hills probing) | -? |
| Allegheny PA | 4 (Sewickley Heights defer per PR #317) | -1 |
| **Total** | **At least 11** | -9 |

Plus existing base (~25 ops):
- **Realistic ceiling**: 36-40 ops (depending on Oakland resolution)
- **Stretch with Vessel Tech B2B + PV token + Wayzata GeoPDF + Maricopa direct outreach**: 45-46

This is below Master's prior 46-49 ceiling estimate. The discrepancy is the Maricopa wave reduction from 5/5 → 1/5 — driven entirely by source-freshness-week findings.

## What's in this PR

- `docs/OP5_MARICOPA_7B3_DEFERRAL.md` (this file) — single consolidated deferral doc + source-freshness lesson codification

No code changes. PV/CC/FH/Carefree jurisdictions remain registered with parcels + bbox (from PR #310 and PR #313). `parcels.zoning_code` remains NULL for all 4 — same shape as Wayzata.

## Hard rules honored

- Don't fabricate placeholder zoning_code='UNZONED' (wrong data per discipline — confirmed by Master 2026-06-19)
- Halt-and-report (this PR is the report)
- Don't trust pre-stage specs > 7 days (lesson codified)
- One-thing-at-a-time discipline (not building Maricopa GeoPDF tooling mid-wave)

## Master's PR description handles the rest

PR #310 (PV 7B.2) and PR #313 (4-muni 7B.2) are unaffected. Those PRs documented registration; this PR documents the Phase 7B.3 deferral. Cleanly separable for Master's review queue.
