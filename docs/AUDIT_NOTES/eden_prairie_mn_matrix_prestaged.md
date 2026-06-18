# Eden Prairie (Hennepin MN) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-author 28 zone codes for Eden Prairie. Fourth Hennepin per-muni in chain. NO ROWS APPLIED.
**Pattern:** Per-district narrative ordinance (Eden Prairie Chapter 11 Land Use Regulations). Bergen catchall × 4.

---

## Direct ArcGIS verification

Source: `https://gis.edenprairie.org/mapsb/rest/services/Public/Zoning/MapServer/7` paginated.

**Result: 19,824 features, 28 distinct ZONING codes** — exact Diagnostic PR #255 match.

---

## 28 zone codes — full inventory

| Code | Polys | Category |
|---|---:|---|
| **R1-13.5** | 8,589 | Single Family 13,500 sqft min (dominant) |
| **RM-6.5** | 4,432 | Residential Multifamily 6.5 acres min |
| **R1-9.5** | 3,007 | Single Family 9,500 sqft min |
| **R1-22** | 1,846 | Single Family 22,000 sqft min |
| RURAL | 378 | Rural |
| P-PARK AND OPEN SPACE | 370 | Park/Open Space |
| RM-2.5 | 323 | Residential Multifamily 2.5 acres min |
| **I-2** | 241 | **Industrial 2 — cleanup candidate** |
| OFC | 162 | Office |
| C-REG-SER | 116 | Regional Commercial Services |
| PUB | 92 | Public |
| GC | 49 | Golf Course |
| Please Call City 952-949-8485 | 43 | **DATA-QUALITY** |
| **I-5** | 31 | **Industrial 5 — cleanup candidate** |
| C-COM | 28 | Commercial Community |
| N-COM | 26 | Neighborhood Commercial |
| **I-GEN** | 24 | **General Industrial — cleanup candidate** |
| R1-44 | 18 | Single Family 44,000 sqft min |
| C-REG | 14 | Regional Commercial |
| C-HWY | 10 | Commercial Highway |
| RIGHT-OF-WAY | 9 | **DATA-QUALITY (non-zoned)** |
| WATER | 5 | **DATA-QUALITY (water body)** |
| A-C | 4 | Airport-Commercial |
| TOD-R | 3 | Transit-Oriented Residential |
| A-O | 1 | Airport-Office |
| FS | 1 | **DATA-QUALITY (unknown)** |
| TC-C | 1 | Town Center Commercial |
| TC-MU | 1 | Town Center Mixed-Use |

**Distribution:** 5 base residential (R1-9.5 through R1-44 + RURAL) + 2 multifamily + 6 commercial + 3 industrial + 2 airport + 2 Town Center + 1 PUD-style + 1 OFC + 1 GC + 1 PUB + 1 P-PARK + 4 data-quality.

---

## Cleanup candidates

**Industrial (substrate-first catchall × 4 stays):**
- **I-2** (241 polys), **I-5** (31), **I-GEN** (24) = 296 total industrial polys. Sixth set in cleanup queue (after Bellevue LI / Bainbridge B/I / Mill Creek BP / Gig Harbor ED / Edina PID / Plymouth I-1/2/3).

**Data-quality (default-prohibition stands by default; spot-check at apply-time):**
- `Please Call City 952-949-8485` (43 polys) — placeholder text in data; likely indicates unzoned/pending parcels
- `RIGHT-OF-WAY` (9), `WATER` (5), `FS` (1) — non-zoned natural/transport features

These DQ codes will either:
- Be filtered out by Lane A's ingest (if ingest validates zone_code format)
- Get bound to default-prohibition matrix rows (if Lane A's ingest accepts as-is)

Either way, catchall × 4 is the correct verdict — these aren't permissive zones.

---

## Citations

URL: `https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances?nodeId=CH11LAUSREZO`

Eden Prairie Chapter 11 Land Use Regulations — per-district narrative. Citation pair:
1. Chapter 11 General Provisions (default-prohibition)
2. Per-district section (R-1 family for R1-X variants; RM family for RM-X; C family for commercial; I family for industrial)

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations from Diagnostic directory + Municode
- ✅ Bias against unclear (0 unclear; all 28 → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY ("Eden Prairie", per MetroGIS CTU_NAME)
- ✅ NO ROWS APPLIED

## Pre-stage artifacts

- `/tmp/op5_eden_prairie_prestage.py`
- `/tmp/op5_eden_prairie_prestage_rows.json` (28 rows ready)
