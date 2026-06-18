# Plymouth MN (Hennepin) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Full pre-author 24 zone codes for Plymouth MN. Third Hennepin per-muni in the chain after Edina (commit bc1852c). Per Master's chain-pre-author directive.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** Per-district narrative ordinance (Plymouth Chapter XXI Zoning). Bergen catchall × 4.

**Note on muni naming:** This is Plymouth, **Minnesota** (Hennepin County), NOT Plymouth, Massachusetts. `municipality` field uses bare `"Plymouth"` matching MetroGIS `CTU_NAME`; doc/display name is `"Plymouth, MN"` per Diagnostic recommendation.

---

## Direct ArcGIS verification

```
GET https://plymap.plymouthmn.gov/webgis/rest/services/ParcelViewer/MapServer/2/query
    ?where=1=1
    &outFields=ZONING
    &returnGeometry=false
    (paginated × 10 pages: ~3000 features each → 29,366 total)
```

**Result: 29,366 features, 24 distinct ZONING codes** (Diagnostic predicted 23 — close enough; 1 blank/null code surfaced as the 24th).

---

## 24 zone codes — full inventory

| Code | Polys | Category |
|---|---:|---|
| **RSF-1** | 8,669 | Residential Single Family 1 (dominant) |
| **RSF-2** | 6,071 | Residential Single Family 2 |
| **PUD** | 3,710 | Planned Unit Development |
| **RSF-3** | 3,213 | Residential Single Family 3 |
| RMF-2 | 1,936 | Residential Multifamily 2 |
| RMF-1 | 1,448 | Residential Multifamily 1 |
| RMF-4 | 1,349 | Residential Multifamily 4 |
| RSF-4 | 1,010 | Residential Single Family 4 |
| RMF-3 | 725 | Residential Multifamily 3 |
| P-I | 214 | Public/Institutional |
| **I-2** | 210 | **Industrial — cleanup candidate** |
| FRD | 208 | Future Restricted Development |
| (blank) | 192 | NULL zone designation — spot-check at apply-time |
| O | 88 | Office |
| CC | 81 | City Center |
| **I-1** | 72 | **Industrial — cleanup candidate** |
| C-3 | 64 | Commercial |
| C-2 | 31 | Commercial |
| C-4 | 26 | Commercial |
| B-C | 23 | Business/Commercial Transitional |
| C-5 | 18 | Commercial |
| **I-3** | 6 | **Industrial — cleanup candidate** |
| CC-P | 1 | City Center Public |
| CC-R&E | 1 | City Center Retail/Entertainment |

**Distribution:** 8 residential (RSF-1 through RMF-4) + 4 City Center variants + 6 commercial (B-C, C-2 through C-5, O) + 3 industrial (I-1, I-2, I-3) + 1 PUD + 1 FRD + 1 P-I + 1 blank.

---

## Industrial cleanup candidates

Three industrial codes flagged for Somerset-style verdict-truth review (substrate-first catchall × 4 stays default per Master's bias-against-unclear):

- **I-1** (72 polys) — Industrial District
- **I-2** (210 polys) — Industrial District (largest industrial)
- **I-3** (6 polys) — Industrial District

Plymouth has the LARGEST industrial footprint of the WA + MN pre-stages so far (288 industrial polys total vs Edina's 132 PID / Gig Harbor's 1 ED / Bainbridge's 8 B/I + WD-I / Mill Creek's 68 BP / Bellevue's 61 LI parcels). Verdict-truth pass post-ingest may convert several I-codes to `permitted` for self_storage / mini_warehouse / light_industrial.

---

## Citations

URL: `https://library.municode.com/mn/plymouth/codes/code_of_ordinances?nodeId=CICO_CHXXIZOOR`

Chapter XXI Zoning Ordinance — per-district narrative pattern (each district has own use list); citation template grounded in:
1. Chapter XXI General Provisions (default-prohibition clause)
2. Per-district section (RSF-1 = Sec. 21355; RSF-2 = Sec. 21360; RSF-3 = Sec. 21365; PUD = Sec. 21655; P-I = Sec. 21650; FRD = Sec. 21350; RMF-2 = Sec. 21380 family)

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations from Diagnostic directory + Municode
- ✅ Bias against unclear (0 unclear; all 24 → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY ("Plymouth", per MetroGIS CTU_NAME)
- ✅ NO ROWS APPLIED until Lane A's Hennepin Phase 7A.2 ingest lands

## Pre-stage artifacts

- `/tmp/op5_plymouth_prestage.py`
- `/tmp/op5_plymouth_prestage_rows.json` (24 rows ready)
