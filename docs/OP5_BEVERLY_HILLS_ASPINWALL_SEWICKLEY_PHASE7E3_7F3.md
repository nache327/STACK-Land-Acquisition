# Op-5 Phase 7E.3 + 7F.3 — Beverly Hills MI + Aspinwall PA + Sewickley PA all 5/5 PASS

**Owner:** Lane A
**Date:** 2026-06-22
**Sprint type:** Phase 7E.3 (Oakland MI) + 7F.3 (Allegheny PA) fires triggered by Diagnostic 2026-06-22 re-verification (`docs/AUDIT_NOTES/oakland_allegheny_source_reverification.md`).
**Verdict:** **3 MUNIS × 5/5 PASS @ 100 % cov**. Campaign's **9th + 10th + 11th consecutive 100 % ingest**.
**Predecessors:** PR #318 Oakland 7E.2 · PR #316 Allegheny 7F.2 · PR #321 Diagnostic re-verification.

---

## Beverly Hills MI — Oakland Phase 7E.3 — 5/5 PASS

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **100.0 %** (4,172 / 4,174) — PASS |
| GATE 2 near% | **0.9 %** (39 / 4,174) — PASS |
| GATE 3 raw_attributes empty | 0 — PASS |
| GATE 4 districts | 238 (after blank filter — source has 322 with 84 blank Zoning) — PASS |
| GATE 5 bbox | `[-83.275, 42.509, -83.204, 42.532]` — PASS |

- Source: `services5.arcgis.com/1PnnJue8khcujdxm/.../Zoning_Dissolved/FeatureServer/0`
- 12 distinct codes — **EXACT match** to Diagnostic's "12 nonblank" spec
- Top: R-2B 1,150 / R-1 1,112 / R-2A 829 / R-A 661 / R-3 121

**Note**: Lane A's prior 2026-06-19 ArcGIS Hub search did not surface this layer (Diagnostic re-verification 2026-06-22 found it). **Source-discovery lesson** — different search terms/timestamps surface different results. Always trust Diagnostic's fresh URL when conflict.

## Aspinwall PA — Allegheny Phase 7F.3 — 5/5 PASS

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **100.0 %** (768 / 768) — PASS |
| GATE 2 near% | **0.1 %** (1 / 768) — PASS |
| GATE 3 raw_attributes empty | 0 — PASS |
| GATE 4 districts | 1,242 (parcel-like source per Diagnostic) — PASS |
| GATE 5 bbox | `[-79.908, 40.487, -79.897, 40.500]` — PASS |

- Source: `services6.arcgis.com/Fm86weLSHlxbP80W/.../Aspinwall_Borough_Zoning_Map/FeatureServer/11`
- 9 distinct codes bound (vs Diagnostic spec 10 = -1 minor drift)
- Top: AR-3 326 / AR-2 179 / AR-1 112 / AR-S 49

**HALT-and-fix**: source uses `FID` not `OBJECTID` for OID field. First fire returned 0 features; corrected to `orderByFields=FID`, second fire clean.

## Sewickley PA — Allegheny Phase 7F.3 — 5/5 PASS

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **100.0 %** (1,115 / 1,115) — PASS |
| GATE 2 near% | **0.0 %** (0) — PASS |
| GATE 3 raw_attributes empty | 0 — PASS |
| GATE 4 districts | 26 — PASS |
| GATE 5 bbox | `[-80.193, 40.532, -80.156, 40.551]` — PASS |

- Source: `services1.arcgis.com/Ps1YVQiv5JQLIFu2/.../SW_ZONING_5-5-14/FeatureServer/0` (2014 vintage acceptable per Diagnostic)
- 9 distinct codes — **EXACT match** to Diagnostic spec
- Top: R-1A 635 / R-1 217 / R-2 102 / C-1 90

Same FID-not-OBJECTID fix as Aspinwall.

## Master's "Beverly Hills" call vindicated

Master's 2026-06-19 dispatch mentioned Birmingham + Beverly Hills as HIGH Path A. Lane A's prior probe missed Beverly Hills. Diagnostic re-verification 2026-06-22 confirmed Beverly Hills source LIVE. Lesson: **trust Diagnostic's fresh probes over Lane A's recent probe when conflict** — different search vectors surface different layers.

## Patterns carried forward

- **PR #285 Pierce Task E** — WKT-via-PostGIS via `ST_Multi(ST_MakeValid(...))`
- **PR #303 Eden Prairie** — degenerate-ring skip
- **PR #261** — inline jurisdictions.bbox UPDATE
- **PR #253** — skip prod ROLLBACK preflight at Class A scale
- **Stamford-shape adapter** (PR #308 precedent)
- **Source-freshness verification at fire time** (PR #319 Maricopa lesson — applied here for all 3 sources)
- **Halt-and-fix on field-name drift** (FID vs OBJECTID — caught + fixed in 5 min)

## What's in this PR

- `backend/scripts/perm_muni_beverly_hills_mi_zoning.py` (new)
- `backend/scripts/perm_muni_aspinwall_pa_zoning.py` (new)
- `backend/scripts/perm_muni_sewickley_pa_zoning.py` (new)
- `docs/OP5_BEVERLY_HILLS_ASPINWALL_SEWICKLEY_PHASE7E3_7F3.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate)
- MI/PA case discipline preserved (Beverly Hills retains "VILLAGE OF BEVERLY HILLS" in parcels.city; Aspinwall/Sewickley retain LABEL "Aspinwall Borough"/"Sewickley Borough")
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's 8fe33e5 + d7a0c7a pre-stages cover)
- Halt-and-report on field-name drift

## Next dispatch

1. Orchestrator applies 12 + 10 + 9 = 31 rows for 3 munis HIGH Path A (~10 min clean)
2. **3 munis flip operational** → count +3
3. Allegheny 7F.1 pagination retry still queued (separate)
4. Fox Chapel + O'Hara LOW Path B orchestrator-authored at apply-time
5. Bloomfield Township + Franklin LOW Path B orchestrator-authored at apply-time

## Campaign trajectory update

Confirmed gains:
- Edina + Plymouth + Eden Prairie + Stamford + Minnetonka + Greenwich + Birmingham + Bloomfield Hills + Beverly Hills + Aspinwall + Sewickley = **11 consecutive 100 % ingests** (campaign best streak)

Per Master's updated ceiling:
- Scottsdale + Birmingham + Bloomfield Hills applies + Beverly Hills + Aspinwall + Sewickley = 6 ops to land
- Plus LOW Path B Bloomfield Township + Franklin + Fox Chapel + O'Hara via orchestrator authoring
- Realistic ceiling: 37-40 ops
- Hard ceiling: 41 (Sewickley Heights + Wayzata + Maricopa 4 + Westport/Darien/New Canaan all deferred)
- Stretch +5-8 with Vessel Tech B2B unlock

## Sibling waves status

- **Maricopa**: Scottsdale (#313 amended) ; PV/CC/FH/Carefree DEFERRED (#319) → 1/5 ops
- **Fairfield**: Stamford applied + Greenwich (#311) → 2/5 ops
- **Oakland MI**: Birmingham + Bloomfield Hills (#320) + Beverly Hills (this PR) → 3/5 ops Path A locked; Bloomfield Twp + Franklin LOW Path B orchestrator-authored
- **Allegheny PA**: 7F.2 cohort (#316) + Aspinwall + Sewickley HIGH Path A (this PR) → 2/5 HIGH Path A locked; Fox Chapel + O'Hara LOW Path B orchestrator-authored; Sewickley Heights deferred; 7F.1 pagination retry queued
