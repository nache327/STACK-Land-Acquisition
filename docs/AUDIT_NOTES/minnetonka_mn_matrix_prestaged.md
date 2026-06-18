# Minnetonka (Hennepin MN) Matrix Pre-Stage — RISK-FLAGGED

**Date:** 2026-06-16
**Purpose:** Pre-author 14 zone codes (10 ArcGIS-observed + 4 ordinance-supplemented) for Minnetonka. Fourth Hennepin per-muni in chain. NO ROWS APPLIED.
**Pattern:** Per-district narrative ordinance (Minnetonka Chapter 3 Zoning Regulations). Bergen catchall × 4.

**⚠️ PATH B RISK**: Service rejects pagination per Diagnostic PR #255 ("public zoning app/service lead but needs query hardening"). Only first 1000 features observable. This pre-stage is best-effort; high probability of code-set mismatch at apply time.

---

## ArcGIS observation limitation

```
GET https://utility.arcgis.com/usrsvcs/servers/94ae6a63554048f1a0ae99174eaab529/rest/services/Minnetonka/MI_City_Zoning/MapServer/5/query?where=1=1
→ 1000 features (exceededTransferLimit=true)
→ error 400 "Pagination is not supported" on resultOffset
→ OBJECTID-batched query also returned 0 (dotted field name issue)
```

10 distinct codes surfaced from the 1000-feature sample. Likely undercounting — Diagnostic's ordinance scan suggests "R-1 through R-5, B-1 through B-3, I-1, PUD, overlays, and hybrid PURD forms" = ~12-15 codes minimum, potentially more with overlays.

---

## 14 codes — 10 observed + 4 ordinance-supplemented

### ArcGIS-observed (10)

| Code | Polys (in 1000-sample) | Category |
|---|---:|---|
| R-1 | 497 | Low-Density Residential |
| PUD | 294 | Planned Unit Development |
| R-3 PURD | 163 | Residential PURD overlay |
| **I-1** | 30 | **Industrial — cleanup candidate** |
| R-2 | 5 | Low-Density Residential |
| R-4 | 5 | Medium-Density Residential |
| B-2 | 2 | Limited Business |
| PURD | 1 | Planned Unit Residential Development standalone |
| R-1 PURD | 1 | R-1 with PURD overlay |
| R- | 1 | (stub/malformed designation — DQ flag) |

### Ordinance-supplemented (4 — not observed in sample but in Chapter 3)

| Code | Category | Anchor |
|---|---|---|
| R-3 | Residential | Sec. 300.12 R-3 |
| R-5 | Residential | Sec. 300.14 R-5 |
| B-1 | Limited Business | Sec. 300.17 B-1 |
| B-3 | Business | Sec. 300.19 B-3 |

### Possibly missing (not in pre-stage; flag at apply-time)

- R-3 PUD variants (R-3 PUD-x families)
- Overlay districts (TOD, environmental, shoreland)
- Special districts not surfaced by sample

---

## Industrial cleanup candidate

- **I-1** (30 observed polys) — Industrial District. Same Somerset-style flag as the WA wave cleanup candidates. Substrate-first catchall × 4 holds.

---

## Apply procedure with Path B amplified

**Step 0 — Mandatory verification at apply time** (vs other pre-stages):
1. Pull live uncovered-zone-codes from Lane A's Hennepin ingest for Minnetonka jid
2. Cross-reference vs this 14-code pre-stage:
   - **Matches**: apply pre-stage row directly
   - **Unobserved code surfaces** (e.g., R-3, R-5, B-1, B-3, R-3 PUD variants): apply ordinance-supplemented row OR author fresh from Chapter 3 anchors
   - **Pre-stage code NOT in uncovered**: drop from apply batch (like PCD-NB drop in Gig Harbor)

Expect more re-author than Edina/Plymouth/Eden Prairie. Time estimate: 30-60 min for Minnetonka vs 5-10 min for others.

---

## Citations

URL: `https://codelibrary.amlegal.com/codes/minnetonka/latest/minnetonka_mn/0-0-0-20634` (American Legal Publishing)

Citation pair: Chapter 3 General Provisions + per-district section (Sec. 300.10-300.22).

---

## Pre-stage artifacts

- `/tmp/op5_minnetonka_prestage.py`
- `/tmp/op5_minnetonka_prestage_rows.json` (14 rows; `_source` field tags `arcgis` vs `ordinance`)
