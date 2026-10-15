# Op-5 Hennepin MN Phase 7A.2 — wealth-band per-muni registration

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7A.2 PIVOT — pre-authorized by Master after PR #293 Phase 7A.1 numbers landed clean.
**Verdict:** **DB-LEVEL DONE. 5 / 5 munis registered + parcels moved + bbox populated.** All gates pass cleanly. Awaits Phase 7A.3 (per-muni zoning publisher discovery + ingest) + orchestrator's matrix pre-stage to flip operational.
**Predecessors:** PR #293 Phase 7A.1 (Hennepin umbrella + 448,084 parcels live) · PR #271 Bellevue/Mercer (PATH 1 transparent re-jurisdictioning pattern) · PR #261 inline bbox codified.

---

## TL;DR

Master pre-authorized Phase 7A.2 after Phase 7A.1 cleared all 5 gates. Same PATH 1 pattern as Bellevue/Mercer (PR #271): register each wealth-band muni as own prod jurisdiction, move parcels from Hennepin umbrella → per-muni jurisdiction via `UPDATE jurisdiction_id`, inline bbox UPDATE per muni.

**5 / 5 munis registered.** All counts match Phase 7A.1 preflight exactly:

| Muni | jid | Parcels moved | bbox |
|------|-----|--------------:|------|
| Edina | `2b08fa13-bc49-489d-9735-bfff7f297352` | 21,343 | `[-93.402, 44.860, -93.319, 44.931]` |
| Wayzata | `1729467c-4efa-4b21-98fd-1a20281b4296` | 1,992 | `[-93.548, 44.951, -93.477, 44.982]` |
| Minnetonka | `3267204b-fa88-45c5-bddd-3162cea4eb41` | 20,911 | `[-93.523, 44.891, -93.399, 44.979]` |
| Plymouth | `7cc5f175-6218-4a7d-b196-70f043652968` | 29,204 | `[-93.523, 44.978, -93.401, 45.066]` |
| Eden Prairie | `455b6dac-f915-4707-a109-880712b884fb` | 22,956 | `[-93.521, 44.799, -93.398, 44.892]` |
| **Total** |  | **96,406** | |

Hennepin umbrella residual: **351,678 parcels** (unincorporated + non-cohort munis like Minneapolis 128,750, Bloomington, etc.) — still under Hennepin jurisdiction for future per-muni dispatches.

## 5 Quality gates — PASS per muni

For each muni, verified at fire-end inside the atomic transaction:

| Gate | Threshold | All 5 munis |
|------|-----------|:-----------:|
| Jurisdiction registered | 1 row per muni | **PASS** (5 / 5) |
| Parcels moved | matches expected count | **PASS** (5 / 5 exact-count) |
| `with_geom` | 100 % | **PASS** (100 % each) |
| `raw_attributes` preserved (Norfolk) | 0 empty | **PASS** (0 empty per muni) |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + in Twin Cities range | **PASS** (5 / 5 within lon -93.85 to -93.15, lat 44.75 to 45.30) |

Per-muni transaction (atomic for jurisdiction insert + parcel UPDATE + bbox UPDATE) — any failure rolls the whole muni back.

## What's NOT done in this PR

This dispatch registers jurisdictions + moves parcels + sets bbox. To **flip operational**, each muni still needs:

1. **Phase 7A.3 — per-muni zoning publisher discovery + ingest** (Lane A follow-up, ~1-2h per muni). Each Hennepin wealth muni publishes their own city zoning layer (Edina via ZoneCo consultant + city portal; Wayzata, Minnetonka, Plymouth, Eden Prairie via each city's GIS). Discovery + WAZA-equivalent Class A ingest per muni mirrors King WA Phase 6A.2 pattern.
2. **Spatial backfill** to populate `parcels.zoning_code` from the new districts (contained + nearest_50m + nearest_100m escalation per Westchester Group A precedent).
3. **Orchestrator's matrix sprint** for each muni's distinct codes (Edina's 39 codes already pre-staged per Master's brief).
4. **Audit recompute** via PR #280's scoped CTE (5-sec direct-python on the fix-merged path).

Once 1-4 land: each muni flips → count **25 → 30** if all 5 land cleanly.

## What's NOT done — multi-county MetroGIS carry

Per Master's bonus check request: NOT a clean clone pattern. Verified probe results:

| Source | Status |
|--------|--------|
| MetroGIS `Parcels2023*` per-county layers (Hennepin, Anoka, Carver, Ramsey, Scott, Washington, Dakota) | **ALL 7 return "Service not started"** — server-wide outage of the 2023 dataset; NOT a Hennepin-specific issue |
| MetroGIS aggregator parent folder | **499 Token Required** |
| `gis2.metc.state.mn.us/.../plan_regional_parcels` (Twin Cities Parcels) | **Connection timeout** (unreachable) |
| Direct per-county portals | Mixed: Dakota 200 OK, Carver 404, Ramsey discoverable via ArcGIS Hub but layer URL TBD, others DNS-unresolved from this network |

**Carry verdict**: Each of the 6 non-Hennepin counties needs separate adapter port (per-county portal probing + field map). Time to discover all 6 = several hours per county. Not a Pierce/Snohomish/Kitsap-style 1-clone unlock. Documented in PR #293 + this PR.

## What changed in the repo

- `backend/scripts/perm_muni_hennepin_cohort.py` (new) — standalone Hennepin 5-muni per-muni adapter (clone of `rejurisdiction_bellevue_mercer.py` pattern, scaled to 5 munis)
- `docs/OP5_HENNEPIN_MN_PHASE7A2.md` (this file)

No backend code changes.

## Hard rules honored

- `raw_attributes` preserved verbatim (Norfolk gate — UPDATE only touched `jurisdiction_id` + `updated_at`; raw column untouched)
- `municipality matches prod_city_value EXACTLY` (PR #233 title-case discipline — `'Edina'` not `'EDINA'`, verified via exact-count match preflight = expected)
- Inline `jurisdictions.bbox` per muni (PR #261 codified) — sanity-checked against Twin Cities envelope before writing
- Per-muni transaction for atomicity
- Halt-and-report discipline (0 HALTs this dispatch)
- ONE refresh per phase (audit recompute deferred to PR #280 merge + nightly sweep — direct-python audit per muni would be slow against the un-scoped CTE prod build)
- Don't author matrix (orchestrator's chain-pre-author covers all 5 munis)

## Stack note

This branch is **stacked on PR #293** (Phase 7A.1). After PR #293 merges, this PR rebases trivially onto main.

## Next dispatch (deferred to Master)

**Phase 7A.3** — per-muni zoning publisher discovery + Class A ingest:
1. Edina — research city zoning publisher (likely edinamn.gov or city GIS portal); verify codes match orchestrator's 39-code pre-stage
2. Wayzata, Minnetonka, Plymouth, Eden Prairie — same shape
3. Each muni: WAZA-equivalent INSERT zoning_districts → spatial backfill → audit recompute
4. Orchestrator's matrix applies per muni
5. Each muni flips operational
