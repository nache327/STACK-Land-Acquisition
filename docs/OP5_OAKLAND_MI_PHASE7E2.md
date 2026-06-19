# Op-5 Oakland MI Phase 7E.2 — wealth-band per-muni registration

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Wave 4 cohort after Phase 7E.1 (PR #314).
**Verdict:** **DB-LEVEL DONE. 5/5 munis registered.** 35,321 parcels moved (Birmingham 9,778 + Bloomfield Hills 1,833 + Bloomfield Township 18,224 + Franklin 1,312 + Beverly Hills 4,174). All counts exact match to expected.
**Predecessors:** PR #314 Phase 7E.1 (Oakland parcel ingest, 490,581 parcels) · PR #294 Hennepin Phase 7A.2 pattern.

---

## 5-muni summary

| Muni (jurisdictions.name) | jid | parcels.city filter | Parcels |
|---------------------------|-----|---------------------|--------:|
| Birmingham, MI | `97474794-c0c8-4903-9fae-51fb8fc795bc` | `'CITY OF BIRMINGHAM'` | 9,778 |
| Bloomfield Hills, MI | `e914f6d4-9dfd-467a-a0a6-0e6b02c28691` | `'CITY OF BLOOMFIELD HILLS'` | 1,833 |
| Bloomfield Township, MI | `15ecf7aa-e9d4-4804-a64c-282f8b172701` | `'CHARTER TOWNSHIP OF BLOOMFIELD'` | 18,224 |
| Franklin, MI | `ec91da85-6cf3-4243-bbff-5d7f71017c44` | `'VILLAGE OF FRANKLIN'` | 1,312 |
| Beverly Hills, MI | `53edb548-7359-4e9d-9ff0-ec81fadb8c5d` | `'VILLAGE OF BEVERLY HILLS'` | 4,174 |

**Total moved**: 35,321. **Oakland residual**: 455,260.

## 5/5 gates PASS per muni

| Gate | Status |
|------|:------:|
| Parcels moved = expected (exact) | **PASS** (5/5) |
| `raw_attributes` preserved (Norfolk) | **PASS** (5/5, 0 empty) |
| `parcels.geom` non-null | **PASS** (5/5, 100 %) |
| `jurisdictions.bbox` populated inline (PR #261) | **PASS** (5/5, valid Oakland envelope) |
| MI case discipline UPPERCASE + political-entity prefix | **PASS** (5/5 verbatim) |

## Per-muni bboxes

| Muni | bbox |
|------|------|
| Birmingham | `[-83.250, 42.531, -83.186, 42.566]` |
| Bloomfield Hills | `[-83.266, 42.559, -83.225, 42.597]` |
| Bloomfield Township | `[-83.325, 42.529, -83.207, 42.621]` |
| Franklin | `[-83.321, 42.507, -83.286, 42.530]` |
| Beverly Hills | `[-83.275, 42.509, -83.204, 42.532]` |

## What's in the PR

- `backend/scripts/perm_muni_oakland_cohort.py` (new) — 5-muni cohort registration
- `docs/OP5_OAKLAND_MI_PHASE7E2.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches jurisdiction_id + updated_at only
- CVTTAXDESCRIPTION verbatim UPPERCASE + political-entity prefix (MI discipline)
- Inline jurisdictions.bbox per muni (PR #261 codified)
- Per-muni atomic transaction (insert + UPDATE + bbox)
- Skip ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's 65-row pre-stage 8fe33e5 covers all 5)

## Phase 7E.3 next dispatch

Per Master 2026-06-19:
- **Birmingham + Beverly Hills** HIGH Path A (orchestrator's 8fe33e5 — 21 + 12 = 33 rows ready)
  - Birmingham caveat: 0-1/0-2 numeric ZERO codes (not letter O) per Diagnostic PR #260
- **Bloomfield Hills + Bloomfield Township + Franklin** LOW Path B (orchestrator authors at apply-time per Greenwich precedent, ~15-25 min per muni)

Phase 7E.3 zoning adapters fire next.

## Expected outcome

**+5 → count step depending on what's already applied**

Per Master's trajectory: Oakland Birmingham + Beverly Hills → 38-39, then Bloomfield Hills + Twp + Franklin → 40-42.

## Sibling waves status

- **Maricopa**: PV (#310) + 4-muni (#313); Scottsdale 7B.3 PASS (86.0% cov via Pass 1, Pass 2 hung killed); PV/CC/FH/Carefree 7B.3 firing next
- **Fairfield**: Stamford applied + Greenwich (#311) → 2/5 ops; Westport probe in flight
- **Oakland MI** (this PR): 5/5 registered, Phase 7E.3 next
- **Allegheny PA**: 7F.1 parcel ingest in flight; 7F.2 cohort PR #316 READY (gated on 7F.1 completion)
