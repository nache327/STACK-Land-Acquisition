# Op-5 LOW Path B deferrals — Fox Chapel + O'Hara + Bloomfield Township + Franklin

**Owner:** Lane A
**Date:** 2026-06-22
**Sprint type:** Per-muni LOW Path B zoning ingest deferrals — orchestrator authors at apply-time per Greenwich precedent. Same pattern as Wayzata Option B (no Lane A polygon authoring).
**Verdict:** **4 munis DEFER Phase 7E.3/7F.3 zoning ingest to orchestrator apply-time authoring.** All 4 jurisdictions registered with parcels + bbox; `zoning_code` populated by orchestrator at apply-time.
**Predecessors:** PR #316 Allegheny 7F.2 · PR #318 Oakland 7E.2 · PR #321 Diagnostic re-verification.

---

## TL;DR

4 munis confirmed LOW Path B (no live machine-readable zoning Feature Server per Diagnostic PR #321). Lane A halts Phase 7E.3/7F.3 ingest for these; orchestrator authors zoning matrix at apply-time per Greenwich precedent (~25 min per muni).

This is the **established Greenwich pattern** (matrix authoring without per-muni Lane A ingest) — different from the **Wayzata Option B pattern** (deferred entirely pending GeoPDF tooling). The 4 munis here flip operational via orchestrator's apply, NOT via Lane A ingest.

## 4 munis deferred to orchestrator apply-time

| Muni | jid | Parcels | Reason for LOW Path B |
|------|-----|--------:|------------------------|
| Fox Chapel, PA | `c5e04fa4-08d7-464b-8b74-dd56fc1f3f17` | 1,485 (per 7F.1 partial ingest — see retry note) | No public FeatureServer (Diagnostic PR #317 + #321) |
| O'Hara, PA | `58e12865-5369-43e7-a727-8fea17627788` | 2,940 | No public FeatureServer (Diagnostic PR #317 + #321) |
| Bloomfield Township, MI | `15ecf7aa-e9d4-4804-a64c-282f8b172701` | 18,224 | No public FeatureServer; Oakland Composite Master Plan is land-use not zoning (Diagnostic PR #321) |
| Franklin, MI | `ec91da85-6cf3-4243-bbff-5d7f71017c44` | 1,312 | Same as Bloomfield Township |

## Orchestrator apply-time authoring pattern (Greenwich precedent)

For each muni:
1. Orchestrator authors `zone_use_matrix` rows from ordinance text + zoning map (~25 min/muni at apply-time)
2. Per-muni `parcels.zoning_code` populated via orchestrator's apply path (NOT spatial backfill from a Feature Server)
3. 5 quality gates evaluated post-apply

No Lane A code changes required for these 4 munis. They're flagged as "zoning-deferred-to-orchestrator" in the jurisdiction state.

## Why not full deferral (Wayzata-style)?

Wayzata's deferral was full because:
- No machine-readable source AND
- No orchestrator-authored matrix planned (Master deferred entire muni pending GeoPDF tooling sprint)

These 4 munis have orchestrator-authored matrices pre-staged:
- **Fox Chapel + O'Hara** — Allegheny pre-stage `d7a0c7a` (orchestrator authors ordinance-derived matrix at apply-time)
- **Bloomfield Township + Franklin** — Oakland pre-stage `8fe33e5` (similar)

So these flip operational via orchestrator's matrix authoring + parcels.zoning_code population (NOT via Lane A spatial backfill).

## Fox Chapel parcel count caveat

Allegheny 7F.1 retry is in flight (PAGE_SIZE=200 to work around Allegheny GIS pagination truncation). Fox Chapel currently shows 1,485 / spec 2,179 = -32 %. Retry verdict TBD:
- If retry brings Fox Chapel to ~2,179: original was pagination gap (resolved)
- If retry stays ~1,485: real spec drift (second source-freshness-drift example after Paradise Valley PR #319)

Either way, Fox Chapel still flips operationally via orchestrator's LOW Path B authoring. Parcel count caveat will be documented in retry verdict PR.

## Source-freshness verification at fire time

Per Master's Maricopa PR #319 lesson codification: **verify source freshness AT FIRE TIME, not trust pre-stage specs > 7 days old**. Applied here:
- Diagnostic PR #321 re-verified all 4 munis on 2026-06-22 — confirmed no live FeatureServer
- Lane A's prior probes confirmed same finding
- LOW Path B deferral is correct per fresh probes

## ArcGIS source field-name variance — lesson codified

**Apply-time field-name probe required.** Different ArcGIS source publishers use different OID field names:

| Field name observed | Examples |
|---------------------|----------|
| `OBJECTID` | Stamford (PR #308), Birmingham (PR #320), Maricopa Parcel_Data_View (PR #305) |
| `OBJECTID_1` | Greenwich Zone_Boundaries (PR #311) — CAD-source artifact |
| `OBJECTID_12` | Oakland MI Tax Parcel Plus (PR #314) |
| `FID` | Aspinwall + Sewickley (PR #322) |
| `objectid` (lowercase) | Birmingham `cloudgisdata.bhamsql.*` (PR #320) |

**Discipline**: Probe layer schema before `orderByFields` is hard-coded:
```bash
curl -s "$LAYER_URL?f=json" | python3 -c "import json,sys; print([f['name'] for f in json.load(sys.stdin).get('fields',[])])"
```

First fire with wrong OID returns 0 features — caught by 5-gate verdict `GATE 4 districts = 0 — FAIL`. Patch + re-fire is ~5 min recovery (Aspinwall + Sewickley precedent).

## What's in this PR

- `docs/OP5_LOW_PATH_B_DEFERRALS_BUNDLE.md` (this file)
- Allegheny 7F.1 retry log (in-flight, separate branch — PR follows)

No code changes for the 4 deferred munis. Their jurisdictions remain registered with parcels + bbox.

## Hard rules honored

- Don't fabricate placeholder zoning_code (wrong data per PR #319 discipline)
- Halt-and-report (this PR is the report)
- Source-freshness verified at fire time
- Don't author matrix at Lane A (orchestrator's domain for LOW Path B)
- Field-name variance lesson codified for future waves

## Sibling waves status update

| Wave | Phase 7N.3 status | Notes |
|------|-------------------|-------|
| Hennepin | 4/5 (Wayzata deferred) | All Phase 7A.3 ingests complete |
| Fairfield | 2/5 (3 Vessel Tech deferred) | Stamford + Greenwich Path A |
| Maricopa | 1/5 (PV + CC + FH + Carefree deferred per PR #319) | Scottsdale Path A only |
| Oakland MI | **3/5** (Bloomfield Twp + Franklin deferred via this PR) | Birmingham + Bloomfield Hills + Beverly Hills Path A |
| Allegheny PA | **2 + 2/5** (Sewickley Heights deferred; Fox Chapel + O'Hara deferred via this PR) | Aspinwall + Sewickley Path A |

Total wedge ops landing: 4 + 2 + 1 + 3 + 4 = **14 / 25 wedge munis** at HIGH Path A. Remainder (11) all defer to orchestrator (LOW Path B authoring) or full defer (Wayzata GeoPDF / Vessel Tech B2B).

Plus existing operational base (~25): theoretical campaign ceiling **39-42 ops** (depending on orchestrator's LOW Path B execution).
