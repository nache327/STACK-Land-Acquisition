# Wedge Cohort Apply Runbook

**Date:** 2026-06-18
**Purpose:** Operator-handoff consolidated reference for the 25-muni wedge cohort (WA/MN/AZ/CT/MI/PA per-muni Op-5 substrate). Single source of truth for apply commands, endpoint-truth checks, refresh patterns, case discipline, cleanup candidate queue, and Diagnostic re-engagement triggers. Replaces the need to cross-reference 20+ per-muni pre-stage docs at apply time.
**Scope:** This runbook covers the 5 wedge cohort counties (King WA + Hennepin MN + Maricopa AZ + Fairfield CT + Oakland MI + Allegheny PA) — 25 munis, 659 pre-authored rows.

---

## Table of contents

1. [Apply checklist (per-muni)](#1-apply-checklist-per-muni)
2. [25-muni jurisdiction inventory](#2-25-muni-jurisdiction-inventory)
3. [19-item cleanup candidate queue](#3-19-item-cleanup-candidate-queue)
4. [Case discipline patterns (6 observed)](#4-case-discipline-patterns)
5. [Ordinance pattern shapes (4 observed)](#5-ordinance-pattern-shapes)
6. [Diagnostic re-engagement triggers](#6-diagnostic-re-engagement-triggers)
7. [Audit refresh strategy (HTTP vs direct Python)](#7-audit-refresh-strategy)
8. [Pre-stage doc index](#8-pre-stage-doc-index)

---

## 1. Apply checklist (per-muni)

For each muni, execute in sequence:

1. **Verify Lane A's ingest landed** — pull `/api/admin/op5/uncovered-zone-codes?jurisdiction_id={jid}` and confirm code count matches pre-stage prediction (Path A) OR document the mismatch (Path B)
2. **Verify case discipline** — confirm `prod_city_value` from endpoint matches expected pattern (see §4); compare exact spelling vs pre-stage `municipality` field
3. **Filter pre-stage rows** — drop pre-stage codes not in Lane A's uncovered set (e.g., PCD-NB drop in Gig Harbor; SewickleyHts predicted rows verify-first)
4. **Apply via `_upload-matrix-rows`** — POST per batch of ≤15 rows; `replace_existing=false`
5. **Endpoint-truth check** — re-pull `uncovered-zone-codes` to confirm `uncovered_count=0`
6. **Fire ONE refresh** — see §7 for current strategy
7. **Watch for flip** — poll `/api/admin/coverage` until captured_at advances and `operational_readiness=operational` + `blocking_gaps=[]`
8. **Update tracker** — `coordination/lane_state.json` `current_api_truth += 1` + `PHASE2_PROGRESS.md §15` flip entry

**Time estimate (Path A perfect match):** 5-10 min apply + 10-15 min refresh land = ~15-25 min wall-clock per muni.

**Time estimate (Path B mismatch):** 30-60 min apply + 10-15 min refresh land = ~40-75 min wall-clock per muni.

---

## 2. 25-muni jurisdiction inventory

### King WA (FLIPPED — 5/5)
| muni | jid | status |
|---|---|---|
| Bellevue | `71a53bba-8697-4b8d-93e9-e3de091b8706` | OPERATIONAL |
| Mercer Island | `bdf769db-4150-45da-baa5-529995e7246f` | OPERATIONAL |
| Bainbridge Island | `c6af2bd5-6ecb-4c4a-a9af-d51345c615c0` | OPERATIONAL |
| Mill Creek | `ebdcf222-8e47-46f0-88fa-384ef4141bfa` | OPERATIONAL |
| Gig Harbor | `a2987841-4fe9-4dd3-833e-548bb4fe0cbc` | OPERATIONAL |

### Hennepin MN (1/5 FLIPPED)
| muni | jid | status |
|---|---|---|
| Edina | `2b08fa13-bc49-489d-9735-bfff7f297352` | OPERATIONAL |
| Plymouth, MN | `7cc5f175-6218-4a7d-b196-70f043652968` | registered; Phase 7A.3 pending |
| Eden Prairie | `455b6dac-f915-4707-a109-880712b884fb` | registered; Phase 7A.3 pending |
| Minnetonka | `3267204b-fa88-45c5-bddd-3162cea4eb41` | registered; Phase 7A.3 pending |
| Wayzata | `1729467c-4efa-4b21-98fd-1a20281b4296` | registered; Phase 7A.3 pending |

### Maricopa AZ (0/5 — Lane A Phase 7B pending)
| muni | jid | status |
|---|---|---|
| Scottsdale | TBD | not yet registered |
| Paradise Valley | TBD | not yet registered |
| Carefree | TBD | not yet registered |
| Cave Creek | TBD | not yet registered |
| Fountain Hills | TBD | not yet registered |

### Fairfield CT (0/5 — Lane A Phase 7C pending; head-start via PR #228)
| muni | jid | status |
|---|---|---|
| Stamford | TBD | not yet registered (parcels.city populated via PR #228) |
| Greenwich | TBD | not yet registered |
| Westport | TBD | not yet registered |
| Darien | TBD | not yet registered |
| New Canaan | TBD | not yet registered |

### Oakland MI (0/5 — Lane A Phase 7E pending)
| muni | jid | status |
|---|---|---|
| Birmingham | TBD | not yet registered |
| Bloomfield Hills | TBD | not yet registered |
| Beverly Hills | TBD | not yet registered |
| Bloomfield Township | TBD | not yet registered |
| Franklin | TBD | not yet registered |

### Allegheny PA (0/5 — Lane A Phase 7F pending)
| muni | jid | status |
|---|---|---|
| Fox Chapel Borough | TBD | not yet registered |
| O Hara Township | TBD | not yet registered |
| Aspinwall Borough | TBD | not yet registered |
| Sewickley Borough | TBD | not yet registered |
| Sewickley Heights Borough | TBD | not yet registered |

---

## 3. 19-item cleanup candidate queue

All 19 carry **substrate-first Bergen catchall × 4 prohibited**. Flagged for **verdict-truth Somerset-style sprint** post-ingest (the prohibited verdict may convert to `permitted` for self_storage / mini_warehouse / light_industrial where industrial/manufacturing districts permit storage by right).

### WA wave (4)
| muni | code | WAZA designation | parcels/polys |
|---|---|---|---:|
| Bellevue | LI | Light Industrial | 61 parcels |
| Bainbridge Island | B/I | Business/Industrial (INDLHT) | 6 polys |
| Bainbridge Island | WD-I | Water-Dependent Industrial (INDPORT) | 2 polys — **catchall HOLDS** (water-dependent ≠ self-storage) |
| Mill Creek | BP | Business and Industrial Park (INDHVY/Heavy Industrial) | 68 polys |
| Gig Harbor | ED | Employment District (INDLHT) | 1 poly |

### Hennepin MN (4)
| muni | code | designation | polys |
|---|---|---|---:|
| Edina | PID | Planned Industrial District | 132 |
| Plymouth | I-1 | Industrial | 72 |
| Plymouth | I-2 | Industrial | 210 |
| Plymouth | I-3 | Industrial | 6 |
| Eden Prairie | I-2 | Industrial 2 | 241 |
| Eden Prairie | I-5 | Industrial 5 | 31 |
| Eden Prairie | I-GEN | General Industrial | 24 |
| Minnetonka | I-1 | Industrial (observed) | 30 |

### Maricopa AZ (2 + overlay variants)
| muni | code | designation | polys |
|---|---|---|---:|
| Scottsdale | I-1 + 4 overlay variants (I-1 ESL (HD), I-1 (C), I-1 PCD, I-1 PCD ESL (HD)) | Industrial | various |
| Scottsdale | I-G + 2 overlay variants (I-G + I-G (C)) | General Industrial | various |
| Fountain Hills | IND-1 | Industrial 1 | TBD |

### Fairfield CT (5 — Stamford)
| muni | code | designation | polys |
|---|---|---|---:|
| Stamford | HT-D | High Technology District | 1 |
| Stamford | IP-D | Designed Industrial Park | 1 |
| Stamford | M-D | Designed Industrial | 2 |
| Stamford | M-G | General Industrial | 13 |
| Stamford | M-L | Light Industrial | 9 |

### Oakland MI (2)
| muni | code | designation | polys |
|---|---|---|---:|
| Bloomfield Hills | I-1 | Industrial | 26 |
| Bloomfield Township | I-1 | Industrial (ordinance-derived; polys TBD) | TBD |

### Allegheny PA (2)
| muni | code | designation | polys |
|---|---|---|---:|
| O Hara Township | SM | Suburban Manufacturing | TBD |
| Aspinwall Borough | AI-1 | Limited Industrial | TBD |

**TOTAL: 19 distinct cleanup candidates** (Scottsdale + overlay variants counted once each).

---

## 4. Case discipline patterns

6 distinct patterns observed across the cohort. Always verify `prod_city_value` matches at apply time — mismatch causes silent matrix-row miss.

| # | pattern | examples | state(s) | source |
|---|---|---|---|---|
| 1 | **Title-case bare** | `Bellevue`, `Edina`, `Stamford` | WA, MN, CT | WAZA Jurisdiction / MetroGIS CTU_NAME / CT PR #228 town derivation |
| 2 | **UPPERCASE bare** | `SCOTTSDALE`, `PARADISE VALLEY` | AZ (Maricopa) | Maricopa parcel `PropertyCity` |
| 3 | **UPPERCASE + political-entity prefix** | `CITY OF BIRMINGHAM`, `VILLAGE OF FRANKLIN`, `CHARTER TOWNSHIP OF BLOOMFIELD` | MI (Oakland) | Oakland parcel `CVTTAXDESCRIPTION` |
| 4 | **Title-case + Borough/Township suffix + apostrophe-to-space** | `Fox Chapel Borough`, `O Hara Township` (← `O'Hara`) | PA (Allegheny) | Allegheny `MUNICODE` joined to municipal-boundary layer |
| 5 | **Burlington NJ title-case** | `Moorestown` | NJ | per nache parallel work |
| 6 | **Pierce WA City Limits spatial join derivation, mixed-case** | TBD | WA (Pierce post-Task E) | Pierce parcel city derived via spatial join (per Lane A Task E) |

**Mismatch cost**: matrix row authored with wrong municipality string → silent miss at audit → blocking_gap firing → flip blocked. Always pull `prod_city_value` from endpoint before apply.

---

## 5. Ordinance pattern shapes

4 distinct ordinance structural patterns observed. Citation template differs by shape:

### Master use table (single Table N.NN.A)
- **Examples**: Bainbridge BIMC Table 18.09.020 / Wayzata Chapter 937 / Scottsdale Article XI Table 11.201.A
- **Citation template**: Citation 1 grounds Table N.NN.A default-prohibition; Citation 2 references zone_code's row in the same table

### Per-district narrative (each district = own chapter with own use list)
- **Examples**: Mill Creek MCMC Title 17 / Gig Harbor GHMC Title 17 / Edina Chapter 36 / Plymouth Chapter XXI / Eden Prairie Chapter 11 / Minnetonka Chapter 3 / Stamford Section 4+5 / Birmingham Article 2 / Bloomfield Hills Articles 4/5/6 / Beverly Hills Chapter 46 / O Hara Chapter 455 / Aspinwall Chapter 27 / Sewickley Chapter 330
- **Citation template**: Citation 1 grounds general-provisions chapter default-prohibition; Citation 2 references per-district section anchor

### Pure ordinance/PDF (no machine-readable layer)
- **Examples**: Wayzata (later — original was Chapter 937 master use table) / Maricopa 4 (PV/Carefree/CaveCk/FtnHills) / Fairfield 4 (Greenwich/Westport/Darien/New Canaan) / Oakland 2 (Bloomfield Twp / Franklin) / Allegheny 4 (O Hara/Aspinwall/Sewickley/Sewickley Hts)
- **Citation template**: identical to per-district narrative, but Path B risk amplified because Lane A's ingest source (PDF digitize / hand polygons / hidden GIS endpoint) may surface different codes
- **Apply discipline**: spot-check first; re-author if mismatch

### Mixed
- **Examples**: Fairfield CT split — Stamford (per-district + Section 4 master use) is full pre-author, but Greenwich/Westport/Darien/New Canaan are citations-only because PDF/web-map sources
- **Citation template**: use full pre-author template for ArcGIS-verified munis; defer per-code authoring for ordinance-only

---

## 6. Diagnostic re-engagement triggers

When apply-time surfaces a condition outside the pre-stage, escalate to Diagnostic. Common patterns:

| trigger | example | escalation path |
|---|---|---|
| Source pagination blocked | Minnetonka MI_City_Zoning/5 rejects `resultOffset` | Diagnostic to find alt query strategy (OBJECTID batching, distinct values, geometry-server alt endpoint) |
| Source token-locked | Paradise Valley AZ ArcGIS error 499 | Diagnostic to request auth or find public alt source |
| Source 403 to WebFetch | Code Publishing platforms (Bainbridge BIMC, Mill Creek MCMC, Gig Harbor GHMC) | Use WebSearch as verification primitive (validated 4/4 URLs cleanly in PR #270) |
| Source PDF-only | Wayzata MN, Allegheny 4 munis | Diagnostic for PDF polygon source planning |
| Ordinance recently amended | Darien CT Amendment 104 (May 2026), Wayzata Chapter 937 (June 2022 Ord. 811) | Verify citation template still aligns with current adopted version |
| Adopted-vs-update split | New Canaan CT 2025 update materials | Cite ADOPTED regs only; use update PDFs as extraction hints unless ratified |
| WAZA-vs-city-layer mismatch | Bellevue (resolved: WAZA-legacy authoritative per PR #264) | Diagnostic to verify which layer drives prod ingest |
| Long-tail PUD codes | Edina 19 PUD project-specific codes (1-poly each), Scottsdale 79 single-poly overlay codes | Apply all if Lane A preserves raw values; drop tail if Lane A normalizes |
| Data-quality flags | Eden Prairie "Please Call City 952-949-8485" (43 polys), "RIGHT-OF-WAY", "WATER", "FS" | Default-prohibition catchall stands; spot-check at apply-time |
| Numeric-zero vs letter-O typography | Birmingham layer uses `0-1`/`0-2` (numeric zero) for offices; ordinance uses `O1`/`O2` | Match LAYER spelling per Diagnostic PR #260 |
| Apostrophe-to-space transform | `O'Hara Township` → `O Hara Township` in Allegheny municipal-boundary layer | Match LAYER spelling without apostrophe |

---

## 7. Audit refresh strategy

### Current state (2026-06-18)

- **PR #280 NOT YET MERGED** (per `gh pr view 280` — state=OPEN) — CTE-scoping fix that closes Mercer 502 pathology not yet deployed
- HTTP refresh via `POST /api/admin/coverage/refresh?jurisdiction_id={jid}` hits Railway 240s edge timeout (HTTP_CODE=000); backend processes server-side; captured_at advances ~10-15 min after fire (Bellevue/Edina precedent)

### Refresh patterns

1. **HTTP refresh (current default until PR #280 deploys)** — fire-and-forget via `nohup curl ... &`; wait 10-15 min for captured_at advance via watcher
2. **Direct Python audit invocation (Mercer pattern)** — Lane A's workaround for stuck audit snapshot; invoke `app.services.coverage_audit.refresh_all_snapshots` (or equivalent) directly; bypasses Railway proxy. Used for Mercer when 75+ min HTTP refreshes failed.
3. **Post-PR-#280 HTTP refresh** — projected ~5-sec response time once CTE-scoping fix deploys

### Watcher pattern

For each per-muni flip, spawn background watcher polling `/api/admin/coverage` at 45s intervals; exit when `operational_readiness=operational`. Used successfully for all 6 confirmed flips this session.

---

## 8. Pre-stage doc index

All 20 audit-notes pre-stage docs created this session:

### King WA (5 munis)
- `docs/AUDIT_NOTES/bainbridge_island_matrix_prestaged.md` (commit f99fb2c) — 15 rows
- `docs/AUDIT_NOTES/mill_creek_citation_anchors_prestaged.md` (0a6ef78) — citations-only later upgraded
- `docs/AUDIT_NOTES/gig_harbor_matrix_prestaged.md` (156b0ed) — 20 rows
- Bellevue/Mercer Island in `docs/OP5_KING_WA_MATRIX_SPRINT.md` (PR #266 addendum) — 62 rows

### Hennepin MN (5 munis)
- `docs/AUDIT_NOTES/edina_mn_matrix_prestaged.md` (bc1852c) — 39 rows ✓ APPLIED + FLIPPED
- `docs/AUDIT_NOTES/plymouth_mn_matrix_prestaged.md` (528a21d) — 24 rows
- `docs/AUDIT_NOTES/eden_prairie_mn_matrix_prestaged.md` (dfea670) — 28 rows
- `docs/AUDIT_NOTES/minnetonka_mn_matrix_prestaged.md` (5287ee4) — 14 rows
- `docs/AUDIT_NOTES/wayzata_mn_matrix_prestaged.md` (3ec7a9c) — 15 rows

### Maricopa AZ (5 munis)
- `docs/AUDIT_NOTES/scottsdale_az_matrix_prestaged.md` (20dacfc) — 249 rows
- `docs/AUDIT_NOTES/maricopa_az_4_remaining_matrix_prestaged.md` (9af5827) — 52 rows (PV + Carefree + Cave Creek + Fountain Hills)

### Fairfield CT (5 munis)
- `docs/AUDIT_NOTES/fairfield_ct_matrix_prestaged.md` (9c5cee9) — Stamford 42 rows + 4 citations-only

### Oakland MI (5 munis)
- `docs/AUDIT_NOTES/oakland_mi_matrix_prestaged.md` (8fe33e5) — 65 rows

### Allegheny PA (5 munis)
- `docs/AUDIT_NOTES/allegheny_pa_matrix_prestaged.md` (d7a0c7a) — 26 rows

### Diagnostic citation directories (pre-existing — base of pre-stages)
- `docs/AUDIT_NOTES/hennepin_mn_citation_directory.md` (PR #255)
- `docs/AUDIT_NOTES/maricopa_az_citation_directory.md` (PR #262)
- `docs/AUDIT_NOTES/fairfield_ct_citation_directory.md` (PR #257)
- `docs/AUDIT_NOTES/oakland_mi_citation_directory.md` (PR #260)
- `docs/AUDIT_NOTES/allegheny_pa_citation_directory.md` (PR #263)
- `docs/AUDIT_NOTES/puget_sound_wealth_muni_citation_directory.md` (PR #270)

---

## Quick-reference: by status

### OPERATIONAL (6 munis flipped this campaign-week)
Bellevue, Mercer Island, Bainbridge Island, Mill Creek, Gig Harbor, Edina

### ROW-READY (15 munis pre-staged + jurisdiction registered or pending)
Plymouth MN, Eden Prairie, Minnetonka, Wayzata (registered), Scottsdale, Paradise Valley, Carefree, Cave Creek, Fountain Hills, Stamford, Greenwich (citations only), Westport (citations only), Darien (citations only), New Canaan (citations only), Birmingham, Bloomfield Hills, Beverly Hills, Bloomfield Township, Franklin, Fox Chapel Borough, O Hara Township, Aspinwall Borough, Sewickley Borough, Sewickley Heights Borough (citations + predicted)

### NEXT 4 IMMEDIATE DISPATCHES
1. **Plymouth, MN** — apply 528a21d (24 rows) when Lane A Phase 7A.3 fires
2. **Eden Prairie, MN** — apply dfea670 (28 rows) when Lane A Phase 7A.3 fires
3. **Minnetonka, MN** — apply 5287ee4 (14 rows) when Lane A ZoneCo-source PR opens
4. **Wayzata, MN** — apply 3ec7a9c (15 rows) when Diagnostic PDF planning verdict lands

After Hennepin closes: Maricopa wave → Fairfield wave → Oakland wave → Allegheny wave.

---

## Closing notes

This runbook is the operator handoff doc for the verdict-truth Somerset-style sprint and for scaling beyond the 5 wedge counties. Maintain as new munis flip or new patterns surface. Track jurisdiction_id additions in §2 as Lane A registers them.

When the 19-item cleanup candidate queue fires for verdict-truth review, prioritize by parcel/poly count (most impactful first): Plymouth I-2 (210), Eden Prairie I-2 (241), Edina PID (132), Mill Creek BP (68), Bellevue LI (61 parcels). Light-industrial / heavy-industrial / business-park codes most likely to convert to `permitted` for self-storage. Pure-industrial-zone municipal ordinances vary widely — research per code at time of cleanup.
