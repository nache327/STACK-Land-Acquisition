# Fairfield CT Wealth Munis Matrix Pre-Stage (Risk-Adjusted)

**Date:** 2026-06-16
**Purpose:** Pre-author Fairfield CT wealth munis ahead of Lane A's Fairfield CT per-muni wave dispatch. **Stamford gets full pre-author (42 codes ArcGIS-verified)**; Greenwich + Westport + Darien + New Canaan get **citations + chapter anchors only** per Master's risk-adjusted scope (their sources are PDF-only / web-map / AxisGIS UI — high Path B mismatch risk).
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** Per-district narrative ordinance (CT muni standard; CGS Chapter 124 home rule). Bergen catchall × 4.

**⚠️ CASE-DISCIPLINE NOTE**: CT uses **TITLE CASE** per PR #228 city re-derivation (`Greenwich`, `Westport`, `Darien`, `New Canaan`, `Stamford`). Same as WA/MN convention; different from Maricopa AZ UPPERCASE.

**HEAD-START vs Hennepin/Maricopa**: Fairfield's `parcels.city` is already populated via PR #228 (261,652 parcels Town_Name → city). When Lane A's Fairfield per-muni wave fires, the Phase shape is 7A.2-equivalent (register per-muni jurisdictions + UPDATE jurisdiction_id) WITHOUT needing Phase 7A.1 (parcel ingest). Faster path to wave-open.

---

## Per-muni summary

| muni | parcels (PR #228) | scope | rows | source confidence | industrial flag |
|---|---:|---|---:|---|---|
| **Stamford** | 25,524 | **Full pre-author** (ArcGIS direct) | **42** | HIGH | HT-D, IP-D, M-D, M-G, M-L (5) |
| Greenwich | 18,042 | Citations + chapter anchors only | — | LOW (PDF/web-map) | TBD |
| Westport | 9,947 | Citations + chapter anchors only | — | LOW (AxisGIS UI + enCodePlus) | TBD |
| Darien | 5,831 | Citations + chapter anchors only | — | LOW (PDF-only) | TBD |
| New Canaan | 7,386 | Citations + chapter anchors only | — | LOW (eCode360 + PDF) | TBD |

**Total Fairfield target parcels: 66,730** (25.5% of Fairfield county per PR #228).

---

## Stamford (FULL PRE-AUTHOR — 42 codes)

### Direct ArcGIS verification

`https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3` — 377 features, 42 distinct ZoningDistrict codes (verified per Diagnostic PR #257; exact match).

### Code inventory (42)

**Residential (18):** R-5, R-6, R-7 1/2, R-10, R-10/R-D, R-20, R-20/R-D, R-H, R-HD, R-MF, RA-1, RA-1/R-D, RA-2, RA-2/R-D, RA-3, RM-1, NX-D

**Commercial (10):** B-D, C-B, C-D, C-G, C-I, C-L, C-N, CC, CSC-D, V-C

**Industrial (5 — cleanup candidates):** **HT-D** (High Technology), **IP-D** (Designed Industrial Park), **M-D** (Designed Industrial), **M-G** (General Industrial), **M-L** (Light Industrial)

**Waterfront/Special (5):** CW-D, DW-D, MR-D, MX-D, HCDD

**Park/Public (1):** P

**Special districts (3):** P-D, SRD-N, SRD-S, TCDD

### Citation pattern

URLs:
- Primary: `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations`
- Municode: `https://library.municode.com/ct/stamford`

Citation pair: Section 4 Use Regulations and Standards (default-prohibition) + Section 5 Districts and District Regulations (per-zone-code).

### Apply-time procedure

Path A: Apply 42 rows via `_upload-matrix-rows` to Stamford per-muni jid; ~5-10 min (3 batches of 15 + 12).

---

## Greenwich (CITATIONS-ONLY — defer per-code authoring)

**Direct 57-list wealth pocket.** No verified public zoning FeatureServer. Greenwich Building Zone Regulations is sectioned/PDF; Division 9 Use Regulations + Division 21 area/height/bulk.

### Sources

- Ordinance: `https://www.greenwichct.gov/442/Building-Zone-Regulations`
- Maps: `https://www.greenwichct.gov/440/Resource-Maps`
- Town Zoning Map PDF: `/DocumentCenter/View/14293/Town-Zoning-Map-PDF`
- Business Zone Maps PDF: `/DocumentCenter/View/42917/Business-Zone-Maps-PDF`
- Interactive app: `https://greenwichgis.maps.arcgis.com/apps/instant/lookup/index.html?appid=dd08394df7544ef7862d946a2ad5d7a5` (did NOT expose public zoning layers in pre-stage probe)

### Chapter anchors (citation template ready)

- **Division 9 Use Regulations** — chapter-level default-prohibition framing
- **Section 6-100 Use Groups for Business Zones**
- **Sections 6-103 through 6-108** — per-business-zone use regulations (LBR, LB, GB, GBO, WB, BEX-50)
- **Division 21** — schedule of open spaces/heights/bulk (area/dimensional)

### Likely codes (per Diagnostic; verify at apply-time)

Residential: RA-4, RA-2, RA-1, R-20, R-12, R-7, R-6
Business: LBR, LB, GB, GBO, WB, BEX-50

Estimated ~25-35 codes. Path B re-author at apply time: ~4-6h.

---

## Westport (CITATIONS-ONLY — defer per-code authoring)

**Best ordinance-side fit (enCodePlus exposes district chapters with permitted-use subsections).** Source path is AxisGIS UI — no REST verified.

### Sources

- enCodePlus regulations: `https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx`
- Town regulations page: `https://www.westportct.gov/government/departments-a-z/planning-and-zoning-department/zoning-and-subdivision-regulations`
- AxisGIS map: `https://www.axisgis.com/WestportCT/`

### Chapter anchors

- **Section 14-2 Residence AAA District permitted uses**
- **Sections 21-2, 24-2, 24A-2, 24B-2, 24C-2** — district-specific permitted uses
- **Section 32-7 Prohibited Uses** (default-prohibition framing)
- **Section 42** — map/amendment procedures

### Likely codes (per Diagnostic; verify at apply-time)

Residential: AAA, AA, A, B, C
Business: GBD, GBD/S, RBD, BCD

Estimated ~25-35 codes.

---

## Darien (CITATIONS-ONLY — defer per-code authoring)

**Smallest wealth muni (5,831 parcels).** PDF-only zoning regs/map. Current through Amendment 104 effective May 10, 2026.

### Sources

- Ordinance page: `https://www.darienct.gov/301/Zoning-Regulations`
- Regulations PDF: `https://www.darienct.gov/DocumentCenter/View/6613`
- Zoning map PDF: `https://www.darienct.gov/DocumentCenter/View/6126`
- Municode: `https://library.municode.com/ct/darien/codes/code_of_ordinances`

### Chapter anchors

- **Zoning Regulations PDF** — primary use-table reference
- **Residential district sections** — `R-2`, `R-1`, `R-1/2`, `R-1/3`, `R-1/5`
- **Central Business District section** — `CBD`
- **Municode town code** — secondary reference

### Likely codes (per Diagnostic; verify at apply-time)

Residential: R-2, R-1, R-1/2, R-1/3, R-1/5
Business: CBD + others
Estimated ~15-25 codes.

---

## New Canaan (CITATIONS-ONLY — defer per-code authoring)

**Adopted-source vs 2025-update-source split is a citation risk.** Current adopted regs are PDF/eCode360; 2025 update materials are work-product only.

### Sources

- Ordinance page: `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regulations.php`
- eCode360: `https://www.ecode360.com/NE0075?needHash=true`
- eCode360 PDF: `https://ecode360.com/NE0075/laws/LF2192955.pdf`
- Zoning map PDF (03.01.23): `https://www.newcanaan.info/Departments/Land%20Use/Zoning%20Map%2003.01.23.pdf`
- Tighe & Bond web GIS: `https://hosting.tighebond.com/NewCanaanCT/` (UI only)
- 2025 update materials: `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regs_update_2025.php` (WORK-PRODUCT; do not cite for adopted rows)

### Chapter anchors

- **Section 3.5 Residence Zones**
- **Section 4.8 Business Zones**
- **Section 5 Special Zones**

### Likely codes (per Diagnostic; verify at apply-time)

Residential: A Residence, B Residence, 1/3 Acre Residence + others
Business: Retail A, Business A, Business B
Estimated ~25-35 codes.

**CITATION DISCIPLINE**: Use adopted regs (Section 3.5/4.8/5) for final rows. 2025 update PDFs only as extraction hints unless adopted.

---

## Apply procedure when Lane A's Fairfield CT per-muni wave fires

### Path A (Stamford)

1. Apply 42 pre-staged rows; ~5-10 min
2. Endpoint truth + refresh
3. Expected flip with 100% Path A confidence

### Path B (Greenwich + Westport + Darien + New Canaan)

For each:
1. Pull live uncovered codes from Lane A's ingest
2. Author per-code rows using this doc's citation template + chapter anchors
3. Time estimate: 4-6h per muni (vs full pre-author 4-6h each — citations-only saves the **research time**, not the authoring time)

Net total: ~16-25h for the 4 PDF-only munis + ~10 min Stamford = ~16-25h post-ingest authoring vs the original Diagnostic estimate of 14-28h.

**Savings**: Stamford's 42 rows fire instantly (saved 5-8h authoring). 4 PDF-only munis still need authoring but with citation framework ready.

---

## Cleanup candidate queue update

**Fairfield additions (5+ pending):**
- Stamford: HT-D (High Technology), IP-D (Designed Industrial Park), M-D (Designed Industrial), M-G (General Industrial), M-L (Light Industrial)
- Greenwich: TBD (Diagnostic doesn't surface industrial codes; Greenwich is residential/commercial-heavy)
- Westport/Darien/New Canaan: likely no/minimal industrial (wealth pockets)

**Campaign total cleanup queue now: 15 items** (WA 4 + Hennepin 4 + Maricopa 2 + Stamford 5).

---

## Operational count forecast (Fairfield wave when Lane A dispatches)

| outcome | count |
|---|---:|
| current (after Hennepin + Maricopa waves) | 35 |
| + Stamford flip | 36 (largest by parcels, but lowest Path A risk) |
| + Greenwich flip | 37 (direct 57-list polygon) |
| + Westport flip | 38 |
| + Darien flip | 39 |
| + New Canaan flip | 40 |

Then Oakland MI + Allegheny PA remain in the wedge cohort. Plus optional carry-county work post-MetroGIS (6 MN counties).

---

## Pre-stage artifacts

- `/tmp/op5_stamford_prestage.py` — Stamford full authoring script
- `/tmp/op5_stamford_prestage_rows.json` — 42 Stamford rows ready
- `/tmp/stamford_raw.json` — 377 raw features from ArcGIS query
- This doc — citations + chapter anchors for Greenwich + Westport + Darien + New Canaan
