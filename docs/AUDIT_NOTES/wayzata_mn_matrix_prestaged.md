# Wayzata (Hennepin MN) Matrix Pre-Stage — ORDINANCE-DERIVED

**Date:** 2026-06-16
**Purpose:** Pre-author 15 zone codes for Wayzata. Fifth and final Hennepin per-muni in chain. NO ROWS APPLIED.
**Pattern:** **Master use table** ordinance (Wayzata Chapter 937 — closer to Bainbridge BIMC's pattern than the per-district narratives of Edina/Plymouth/Eden Prairie/Minnetonka). Bergen catchall × 4.

**⚠️ DATA-SOURCE NOTE**: No live machine-readable zoning layer found per Diagnostic PR #255. Codes derived from:
- Wayzata Code of Ordinances Part IX Zoning + Chapter 937 master use table (Ordinance No. 811 June 2022 consolidation)
- WebSearch confirmation of district list
- March 2025 official zoning map PDF (https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025)

PATH B risk amplified vs ArcGIS-direct pre-stages (Edina/Plymouth/Eden Prairie). Lane A's ingest source (PDF digitize / city GIS handoff / hand-digitized polygons) may surface different codes.

---

## 15 zone codes — ordinance-derived

### Residential (8)

| Code | Category |
|---|---|
| R-1A | Low-Density Single Family Estate District |
| R-1 | Low-Density Single Family Residential District |
| R-2A | Single Family Residential District |
| R-2 | Medium-Density Single Family Residential District |
| R-3A | Single and Two Family Residential District |
| R-3 | Single and Two Family Residential District |
| R-4 | Medium-Density Multiple Residential |
| R-5 | Average-Density Multiple Residential District |

### Commercial (6)

| Code | Category |
|---|---|
| C-1 | Office and Limited Commercial |
| C-1A | Neighborhood Office |
| C-2 | Commercial |
| C-3 | Commercial |
| C-3A | Service District (Chapter 977.5) |
| C-4 | Commercial |

### PUD (1)

| Code | Category |
|---|---|
| PUD | Planned Unit Development |

### NO INDUSTRIAL ZONES

Wayzata is a Lake Minnetonka shore wealth pocket; ~1,976 parcels total. No industrial districts in the ordinance — first muni in the wave with zero industrial cleanup candidates.

---

## Apply procedure with PATH B amplified

When Lane A's Hennepin Phase 7A.2 ingests Wayzata:

1. **Determine Lane A's source path**:
   - If they manually digitized the PDF map: codes likely match this 15-code list directly
   - If they extracted from Hennepin county-level layer: codes may use Hennepin county classification (different)
   - If they have city GIS handoff: codes may include suffix variants or overlays not in ordinance summary

2. **Cross-reference pre-stage rows**:
   - Apply matching codes from `/tmp/op5_wayzata_prestage_rows.json` (strip `_*` fields)
   - Drop pre-stage codes NOT in Lane A's uncovered set
   - For any NEW codes Lane A surfaced: author fresh using Chapter 937 master use table citation template

3. **Citation template** is straightforward because Wayzata uses a master use table (like Bainbridge BIMC, unlike Edina/Plymouth/Eden Prairie/Minnetonka):
   - Citation 1: Chapter 937 master use table (default-prohibition framing)
   - Citation 2: Per-district section anchor (R-1A = Chapter 951; R-1 = Chapter 952; R-2A = Chapter 953; R-5 = Chapter 959; C-3A = Chapter 977.5; PUD = Chapter 933)

Time estimate: 30-60 min vs 5-10 min for ArcGIS-direct pre-stages, due to higher mismatch probability.

---

## Citations

URLs:
- Master ordinance index: `https://library.municode.com/mn/wayzata/codes/code_of_ordinances`
- Chapter 937 master use table: `https://library.municode.com/MN/Wayzata/codes/code_of_ordinances?nodeId=CD_ORD_PTIXZO_CH937ZODIUSTAPEST`
- Zoning map PDF (March 2025): `https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025`

---

## Pre-stage artifacts

- `/tmp/op5_wayzata_prestage.py`
- `/tmp/op5_wayzata_prestage_rows.json` (15 rows; `_source = ordinance_pdf` on each)
