# Oakland MI Wealth Munis Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-author 65 rows across 5 Oakland MI wealth munis (Birmingham + Bloomfield Hills + Beverly Hills + Bloomfield Township + Franklin). Forward-velocity push during Hennepin wave refresh-wait per Master's 2026-06-16 dispatch.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** Mixed — 3 ArcGIS-direct + 2 ordinance-derived. Per-district narrative for all 5 (MI muni standard).

**⚠️ CASE-DISCIPLINE NOTE (NEW PATTERN)**: Oakland County `CVTTAXDESCRIPTION` field uses **UPPERCASE with political-entity prefixes**:
- `CITY OF BIRMINGHAM`
- `CITY OF BLOOMFIELD HILLS`
- `CHARTER TOWNSHIP OF BLOOMFIELD`
- `VILLAGE OF FRANKLIN`
- `VILLAGE OF BEVERLY HILLS`

Different from WA/MN (title-case bare names), Maricopa AZ (UPPERCASE bare names), or CT (title-case bare names). **Fourth case discipline pattern in the wedge cohort.**

---

## Per-muni summary

| muni | parcels (Oakland src) | scope | rows | source | industrial flag |
|---|---:|---|---:|---|---|
| Birmingham | 9,786 | **Full pre-author** (ArcGIS direct) | **21** | maps.bhamgov.org/.../Zoning/MapServer/0 | none |
| Bloomfield Hills | 1,833 | **Full pre-author** (ArcGIS direct) | **13** | services9.arcgis.com/.../Zoning_BloomfieldHills | I-1 (1) |
| Beverly Hills | 4,174 | **Full pre-author** (ArcGIS direct) | **12** | services5.arcgis.com/.../Zoning_Dissolved | none |
| Bloomfield Township | 18,224 | Ordinance-derived | 11 | bloomfieldtwp.org Clearzoning PDF | I-1 (1) |
| Franklin | 1,312 | Ordinance-derived | 8 | American Legal | none |
| **Total** | **35,329** | mixed | **65** | — | **2** |

---

## Birmingham (21 codes — ArcGIS direct)

### Caveat per Diagnostic PR #260

**Layer uses `0-1` and `0-2` (zero) for office districts; ordinance text uses `O1`/`O2` (letter O).** Matrix rows in this pre-stage use the LAYER spelling `0-1`/`0-2` so they match Lane A's ingest output exactly. This is the strictest case discipline yet — character literally `0` not `O`.

### Code distribution

**Residential (9)**: R1, R1-A, R2, R3 (Single Family) + R4 (Two Family) + R5/R6/R7/R8 (Multifamily)

**Business (5)**: B-1, B-2, B-2B, B-3 (Office Residential), B-4 (Business Residential)

**Office (2)**: 0-1 (Office), 0-2 (Office Commercial) — note: layer uses zero, not letter O

**Mixed Use + Public + Transitional (5)**: MX, P, PP, TZ-1, TZ-3

NO explicit industrial. Birmingham is residential/business-heavy wealth pocket.

### Citation source

- enCodePlus: `https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx`
- Article 2 Zoning Districts and Regulations + Appendix A Land Use Matrix

---

## Bloomfield Hills (13 codes — ArcGIS direct)

### Code distribution

**Residential A-x family (6)**: A-1, A-2, A-3, A-3-1, A-4, A-6 + RR (Rural Residential) = 7 residential codes (1,684 of 1,853 polys = 91%)

**Business/Commercial/Office (4)**: B-1, C-1, O-1, O-2

**Industrial (1 — cleanup candidate)**: **I-1** (26 polys)

**Parking (1)**: P-1

### Industrial flag

**I-1** — Industrial — Somerset-style cleanup candidate. Substrate-first catchall × 4; verdict-truth review post-ingest.

### Citation source

- City zoning ordinance page: `https://www.bloomfieldhills.gov/241/Zoning-Ordinance`
- Articles 4 (residential), 5 (commercial/office), 6 (industrial)

---

## Beverly Hills (12 codes — ArcGIS direct; 2 NULL/blank excluded)

### Code distribution

**Single-Family Residential (6)**: R-1, R-1A, R-2, R-2A, R-2B, R-3 (R-2B is largest at 72 polys = 23%)

**Multifamily (2)**: R-A (Attached), RM (Multifamily)

**Business/Office (2)**: B (Business), O-1 (Office)

**Public (2)**: P (Park), PP (Public Property)

NO industrial. Beverly Hills is pure residential/wealth-pocket village.

### Citation source

- Beverly Hills Municode Chapter 46: `https://library.municode.com/mi/beverly_hills/codes/code_of_ordinances?nodeId=PTIICOOR_CH46ZO`
- Chapter 46 Zoning — per-district sections

---

## Bloomfield Township (11 codes — ORDINANCE-DERIVED)

Per Diagnostic PR #260: no live machine-readable layer; uses Clearzoning PDF + zoning-map PDF workflow.

### Code list (ordinance-derived)

| Code | Category |
|---|---|
| R-1, R-2, R-3, R-4 | Single Family Residential (4 density variants) |
| R-M | Multifamily Residential |
| B-1, B-2 | Business |
| O-1 | Office |
| **I-1** | **Industrial — cleanup candidate** |
| OS | Open Space |
| PUD | Planned Unit Development |

### Citation source

- Township zoning page: `https://www.bloomfieldtwp.org/clerk/zoning-ordinance/`
- Zoning map PDF: `https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf`

PATH B AMPLIFIED — Lane A's ingest source (PDF digitize or hidden GIS endpoint) may surface different codes.

---

## Franklin (8 codes — ORDINANCE-DERIVED)

Per Diagnostic PR #260: American Legal-hosted code; no live zoning layer.

### Code list (ordinance-derived)

| Code | Category |
|---|---|
| R-1A, R-1, R-2 | Single Family Residential variants |
| B-1, B-2 | Business |
| OS | Open Space |
| P | Park |
| PUD | Planned Unit Development |

NO industrial — Franklin is small village wealth pocket (1,312 parcels).

### Citation source

- American Legal: `https://codelibrary.amlegal.com/codes/franklin/latest/overview`
- Village Code Title XV Land Usage

PATH B AMPLIFIED.

---

## Cleanup candidate queue update

**Oakland additions (2):**
- Bloomfield Hills: I-1 (26 polys, Industrial)
- Bloomfield Township: I-1 (polys TBD, Industrial — ordinance-derived)

**Campaign total cleanup queue now: 17 items** (WA 4 + Hennepin 4 + Maricopa 2 + Stamford 5 + Oakland 2).

---

## Apply procedure (when Lane A's Oakland Phase 7C ingest lands)

### Path A (Birmingham + Bloomfield Hills + Beverly Hills)

Apply pre-stage rows; ~5-10 min each. Expected high Path A confidence given ArcGIS-direct sources.

### Path B (Bloomfield Township + Franklin)

Verify code list at apply-time; re-author surfaced codes using ordinance citation template. 30-60 min each.

---

## Operational count forecast (Oakland wave when Lane A dispatches)

| outcome | count |
|---|---:|
| current (after Hennepin + Maricopa + Fairfield waves) | 40 |
| + Birmingham flip | 41 (direct 57-list) |
| + Bloomfield Hills flip | 42 (direct 57-list) |
| + Beverly Hills flip | 43 |
| + Bloomfield Township flip | 44 |
| + Franklin flip | 45 |

Then Allegheny PA remains as the last wedge county.

---

## Pre-stage artifacts

- `/tmp/op5_oakland_prestage.py` — authoring script for all 5
- `/tmp/op5_oakland_city_of_birmingham_prestage_rows.json` (21 rows)
- `/tmp/op5_oakland_city_of_bloomfield_hills_prestage_rows.json` (13 rows)
- `/tmp/op5_oakland_village_of_beverly_hills_prestage_rows.json` (12 rows)
- `/tmp/op5_oakland_charter_township_of_bloomfield_prestage_rows.json` (11 rows)
- `/tmp/op5_oakland_village_of_franklin_prestage_rows.json` (8 rows)
- Raw ArcGIS responses cached at `/tmp/birmingham_raw.json`, `/tmp/bloomfield_hills_raw.json`, `/tmp/beverly_hills_raw.json`

**Combined Oakland pre-stage: 65 rows across 5 munis.**

---

## Case-discipline patterns recap (wedge cohort)

| state | convention | example |
|---|---|---|
| WA | title-case bare | `Bellevue`, `Bainbridge Island` |
| MN | title-case bare | `Edina`, `Plymouth` |
| CT | title-case bare | `Greenwich`, `Stamford` |
| AZ (Maricopa) | UPPERCASE bare | `SCOTTSDALE`, `PARADISE VALLEY` |
| **MI (Oakland)** | **UPPERCASE + political-entity prefix** | `CITY OF BIRMINGHAM`, `VILLAGE OF FRANKLIN`, `CHARTER TOWNSHIP OF BLOOMFIELD` |

5 distinct case-discipline patterns observed. Allegheny PA pre-stage (not yet done) may surface a 6th.
