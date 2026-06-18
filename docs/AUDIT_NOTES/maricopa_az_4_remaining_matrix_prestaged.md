# Maricopa AZ Remaining 4 Wealth Munis Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-author 52 zone codes for the 4 remaining Maricopa AZ wealth munis (Paradise Valley + Carefree + Cave Creek + Fountain Hills) after Scottsdale (commit 20dacfc). Combined Maricopa wealth muni pre-stage now totals **301 codes across 5 munis**.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** All 4 are **ordinance-derived** (no live machine-readable zoning layers verified per Diagnostic PR #262, except Paradise Valley whose ArcGIS source returned token-required 499 error). Bergen catchall × 4. UPPERCASE municipality per Maricopa PropertyCity convention.

**⚠️ PATH B RISK AMPLIFIED** for all 4 vs Scottsdale (which is ArcGIS-direct). Ordinance-derived code lists may not match Lane A's actual ingest source codes — expect re-author at apply time more often than for Scottsdale or Hennepin ArcGIS-direct pre-stages.

---

## Per-muni summary

| muni | rows | source | confidence | industrial flag | data-source path |
|---|---:|---|---|---|---|
| Paradise Valley | 10 | Ordinance + accepted spec ZONECLASS sample | LOW (token-locked ArcGIS) | none | `https://www.paradisevalleyaz.gov/281/Town-Code` |
| Carefree | 8 | American Legal Chapter 16 | LOW (no live layer) | none | `https://codelibrary.amlegal.com/codes/carefree/latest/carefree_az/0-0-0-1` |
| Cave Creek | 10 | Cave Creek Chapters 2/3/4 | LOW (app is parcel-only) | none | `https://www.cavecreekaz.gov/336/Ordinances-Guidelines` |
| Fountain Hills | 24 | Town Codes ZO Chapter 2 | LOW (no live layer) | **IND-1 (1)** | `https://fountainhills.town.codes/ZO` |

---

## Paradise Valley (10 codes)

Per Diagnostic PR #262: ZONECLASS field has 427 nonblank rows from town zoning layer; codes include R-43, R-35, R-18, OSP-Open Space Reserve, Public School. ArcGIS source `https://gis.paradisevalleyaz.gov/.../Planning_and_Zoning/MapServer/7` returned token-required error 499 during this session; ordinance + accepted-spec sample-derived only.

| Code | Category |
|---|---|
| R-43 | Single-Family Residential, 43,000 sqft min |
| R-35 | Single-Family Residential, 35,000 sqft min |
| R-18 | Single-Family Residential, 18,000 sqft min |
| R-43A | Single-Family Residential, 43A suffix |
| R-35A | Single-Family Residential, 35A suffix |
| R-18A | Single-Family Residential, 18A suffix |
| OSP-Open Space Reserve | Open Space Reserve |
| Public School | Public/Institutional |
| SUP | Special Use Permit district |
| Resort | Resort district |

NO industrial districts — Paradise Valley is a pure residential/estate wealth pocket (10,071 parcels per spec).

---

## Carefree (8 codes)

Per Diagnostic PR #262: Chapter 16 Zoning, Article IV district boundaries, Section 5.01 permitted uses. Codes: R1-70, R1-35, R1-18, GO, C + standard PUD/OS additions.

| Code | Category |
|---|---|
| R1-70 | Single-Family, 70,000 sqft min lot |
| R1-35 | Single-Family, 35,000 sqft min lot |
| R1-18 | Single-Family, 18,000 sqft min lot |
| R1-10 | Single-Family, 10,000 sqft min lot |
| GO | Garden Office |
| C | Commercial |
| OS | Open Space |
| PUD | Planned Unit Development |

NO industrial districts.

---

## Cave Creek (10 codes)

Per Diagnostic PR #262: Chapter 2 Residential Zones; Chapter 3 Commercial Zones; Chapter 4 Open Space Zones. Codes: DR-x family + CB, GC + standard OS/PUD.

| Code | Category |
|---|---|
| DR-190 | Desert Rural, 190,000 sqft min |
| DR-89 | Desert Rural, 89,000 sqft min |
| DR-70 | Desert Rural, 70,000 sqft min |
| DR-43 | Desert Rural, 43,000 sqft min |
| DR-35 | Desert Rural, 35,000 sqft min |
| DR-18 | Desert Rural, 18,000 sqft min |
| CB | Commercial Buffer |
| GC | General Commercial |
| OS | Open Space |
| PUD | Planned Unit Development |

NO industrial districts. Cave Creek is desert-rural wealth pocket; Cave Creek public app FeatureServer is parcel-only (not zoning).

---

## Fountain Hills (24 codes — only Maricopa per-muni with industrial)

Per Diagnostic PR #262: Town Codes ZO Chapter 2 Districts. Largest of the 4 ordinance-derived (after Scottsdale's 249 ArcGIS-direct).

### Open Space (2)
| Code | Category |
|---|---|
| OSR | Open Space Recreational |
| OSC | Open Space Conservation |

### Single-Family Residential (6)
| Code | Category |
|---|---|
| R1-43 | 43,000 sqft min |
| R1-35 | 35,000 sqft min |
| R1-18 | 18,000 sqft min |
| R1-10 | 10,000 sqft min |
| R1-8 | 8,000 sqft min |
| R1-6 | 6,000 sqft min |

### Multifamily (4)
| Code | Category |
|---|---|
| R-2 | Multifamily 2 |
| R-3 | Multifamily 3 |
| R-4 | Multifamily 4 |
| R-5 | Multifamily 5 |

### Commercial (4)
| Code | Category |
|---|---|
| C-C | Common Commercial |
| C-1 | Commercial 1 |
| C-2 | Commercial 2 |
| C-3 | Commercial 3 |

### Lodging + Town Center (5)
| Code | Category |
|---|---|
| L-1 | Lodging 1 |
| L-2 | Lodging 2 |
| TC-RES | Town Center Residential |
| TC-COM | Town Center Commercial |
| TCC-D | Town Center Commercial Downtown |

### Industrial + Public + PUD (3)
| Code | Category |
|---|---|
| **IND-1** | **Industrial 1 — cleanup candidate** |
| PI | Public/Institutional |
| PUD | Planned Unit Development |

---

## Cumulative Maricopa cleanup candidates (8 = Scottsdale 7 + Fountain Hills 1)

| muni | industrial codes |
|---|---|
| Scottsdale | I-1, I-G, I-1 ESL (HD), I-1 (C), I-G (C), I-1 PCD, I-1 PCD ESL (HD) |
| Fountain Hills | IND-1 |

All get Bergen catchall × 4 substrate-first; verdict-truth review post-ingest per Bellevue LI / WA wave / Edina PID / Plymouth I-x / Eden Prairie I-x precedent.

---

## Apply procedure (when Lane A's Maricopa Phase 7B ingest lands)

### Per-muni Path A vs Path B

| muni | Path A confidence | likely action |
|---|---|---|
| Scottsdale (separate doc) | HIGH (ArcGIS direct, 249 codes) | apply 249 in batches; ~15 min |
| Paradise Valley | LOW (token-locked) | apply 10 + re-author surfaced codes; 15-30 min |
| Carefree | LOW (no live layer) | apply 8 + re-author surfaced codes; 15-30 min |
| Cave Creek | LOW (no live layer) | apply 10 + re-author surfaced codes; 15-30 min |
| Fountain Hills | LOW (no live layer) | apply 24 + re-author surfaced codes; 30-60 min |

---

## Pre-stage artifacts

- `/tmp/op5_maricopa_remaining_prestage.py` — authoring script for all 4
- `/tmp/op5_paradise_valley_prestage_rows.json` (10 rows)
- `/tmp/op5_carefree_prestage_rows.json` (8 rows)
- `/tmp/op5_cave_creek_prestage_rows.json` (10 rows)
- `/tmp/op5_fountain_hills_prestage_rows.json` (24 rows)

Scottsdale (commit 20dacfc): `/tmp/op5_scottsdale_prestage_rows.json` (249 rows)

**Combined Maricopa pre-stage: 301 rows across 5 munis.**

---

## Operational count forecast (Maricopa wave when Lane A lands Phase 7B)

| outcome | count |
|---|---:|
| current (after Hennepin wave completes) | 30 |
| + Scottsdale flip | 31 (largest single-muni; 150k parcels per spec) |
| + Paradise Valley flip | 32 |
| + Carefree flip | 33 |
| + Cave Creek flip | 34 |
| + Fountain Hills flip | 35 |

Then 3 more wedge counties to go (Oakland MI, Fairfield CT, Allegheny PA) per Diagnostic plan.
