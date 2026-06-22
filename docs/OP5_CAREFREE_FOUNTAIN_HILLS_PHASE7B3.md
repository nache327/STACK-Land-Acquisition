# Op-5 Maricopa Phase 7B.3 — Carefree PASS + Fountain Hills HALT (heavy-QA verdict)

**Owner:** Lane A
**Date:** 2026-06-22
**Sprint type:** Phase 7B.3 retry after Diagnostic PR #324 resurrected both munis from deferred pile (PR #319). Per Master's directive: Carefree clean Path A, Fountain Hills Path A with heavy-QA whitelist.
**Verdict:** **Carefree 5/5 PASS @ 99.7 % cov** + **Fountain Hills HALT @ 55.9 % cov** (Master HALT threshold triggered).

---

## Carefree 5/5 PASS

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **99.7 %** (2,983 / 2,991) — PASS |
| GATE 2 near% | 6.9 % (207 / 2,991) — PASS |
| GATE 3 raw empty | 0 — PASS |
| GATE 4 districts | 13 (18 source - 5 blank filtered) — PASS |
| GATE 5 bbox | `[-111.99, 33.79, -111.86, 33.86]` — PASS |

- Source: `services6.arcgis.com/clPWQMwZfdWn4MQZ/.../TOC_Zoning/FeatureServer/104`
- 11 distinct codes: C, GO, L (Resort), R-3, R1-10, R1-18, R1-35, RUPD, Rural-190, Rural-43, Rural-70
- Promoted from PR #319 deferral by Diagnostic PR #324 fresh probe

Top: R1-35 598 / Rural-70 476 / Rural-43 405 / R-3 349 / R1-18 304

## Fountain Hills HALT @ 55.9 % cov

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **55.9 %** (8,831 / 15,810) — **SUB — Master HALT trigger** |
| GATE 2 near% | 8.8 % (1,384 / 15,810) — PASS |
| GATE 3 raw empty | 0 — PASS |
| GATE 4 districts | 118 — PASS |
| GATE 5 bbox | `[-111.79, 33.57, -111.59, 33.73]` — PASS |

### QA whitelist results

- **Source 993 polygons → whitelist accepted 118 (12 %)** → noise 872 (88 %)
- Master's >10 % rejection threshold = HALT (88 % is 8.8× the threshold)

### Noise breakdown (top 10 rejected types)

Source field `TEXTSTRING` carries a mix of valid codes + heavy noise:
- CAD escape strings (`\\pxqc;{\\fArial CE...`) — font/formatting from CAD ancestry
- Ordinance numbers (`ORD 23-08`, `ORD00-02`, `ORD99-14`)
- Special use case IDs (`S.U. 01-13`, `S.U. Z79-62`, ~40 distinct values)
- Zone amendment numbers (`Z02-12` through `Z18-02`, ~25 distinct)
- Special-use descriptors (CELL TOWER, COLUMBARIUM, DRIVE THRU, EXERCISE AREA, GROUP HOME, etc.)
- Raw numbers (1, 9, 20-50, 15a, 5b, 6b)
- Blank values

### Coverage distribution (whitelisted only)

Top: OSR 1,584 / R-3 1,238 / R-2 845 / R.U.P.D. 719 / R1-35 596 / R1-8 561

29 distinct codes bound to 8,831 parcels. The other 6,979 parcels fall in source polygons whose TEXTSTRING is metadata, not zoning.

## Master HALT decision required

Master's prior directive: "if >10% noise, halt and surface". 88 % noise triggers HALT. Three options:

**(a) Accept 55.9 % partial coverage**
- Below 70 % gate but above SUB threshold for valuable data
- Orchestrator gets 29 real zoning codes for ~9k parcels
- Doesn't pass quality gates for "formally operational"
- ~6.9k parcels remain unbound (in source noise areas)

**(b) Defer Fountain Hills per Wayzata pattern**
- Source too noisy for reliable zoning attribution per established discipline
- Wait for cleaner source or PDF/ordinance ground-truth
- Maricopa wave stays at 2/5 (Scottsdale + Carefree only)

**(c) Expand whitelist to capture S.U./Z prefixes as catch-alls**
- Risk: assigns non-zoning codes to parcels (data integrity issue)
- Master's discipline: "don't fabricate placeholder zoning_code" (PR #319 codified)
- Not recommended

**Lane A recommendation**: Option (b) — defer. The 2005 layer ancestry + CAD format = unreliable zoning attribution. Real Fountain Hills zoning needs current ordinance source.

## What's in this PR

- `backend/scripts/perm_muni_carefree_az_zoning.py` (new) — Carefree clean Path A
- `backend/scripts/perm_muni_fountain_hills_az_zoning.py` (new) — Fountain Hills whitelist QA
- `docs/OP5_CAREFREE_FOUNTAIN_HILLS_PHASE7B3.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate)
- UPPERCASE AZ case-discipline (parcels.city)
- Inline jurisdictions.bbox per muni (PR #261)
- Skip prod ROLLBACK preflight (PR #253)
- Don't fabricate placeholder zoning_code (PR #319)
- Halt-and-surface on heavy-QA threshold breach (Master directive)
- Source-freshness verified at fire time (both probed 2026-06-22)
- Don't author matrix (orchestrator handles)

## Maricopa wave update

- Scottsdale (PR #313) ✓
- Paradise Valley ✗ (token-gate, PR #319)
- Cave Creek ✗ (no source per Diagnostic PR #324)
- Carefree ✓ (this PR — promoted from defer)
- Fountain Hills ⚠ (this PR — HALT awaiting Master verdict)

If Master accepts (a): Maricopa = 3/5. If (b): Maricopa = 2/5.

## Sibling status

- Allegheny 7F.1 retry in flight (PID 18753, 41 % complete at PR commit time)
- Beverly Hills + Aspinwall + Sewickley (PR #322) at orchestrator apply
- LOW Path B deferrals (PR #323) for Fox Chapel + O'Hara + Bloomfield Twp + Franklin
