# Per-Muni Jurisdiction Wedge Analysis

**Date:** 2026-06-16
**Purpose:** Planning diagnostic after Lane A PR #267 found that King County's countywide denominator blocks an operational flip even when Bellevue/Mercer Island pass per-muni zoning gates. This checks whether the same county-denominator wedge applies to Maricopa AZ, Oakland MI, Hennepin MN, Fairfield CT, and Allegheny PA.
**Status:** Read-only diagnostic. No code, ingest, matrix authoring, or jurisdiction changes.

---

## Bottom line

| County | Total parcels | Wealth-muni parcels | Ratio | Recommended pattern | Expected operational flips |
|---|---:|---:|---:|---|---|
| Maricopa AZ | 1,742,671 | 196,639 | 11.3% | **Per-muni registration required** | Scottsdale + Paradise Valley direct 57-list flips; Carefree, Cave Creek, Fountain Hills optional adjacent flips |
| Oakland MI | 490,590 | 35,329 | 7.2% | **Per-muni registration required** | Birmingham + Bloomfield Hills direct 57-list flips; Beverly Hills likely add-on; Bloomfield Township/Franklin after source work |
| Hennepin MN | 445,965 | 96,539 | 21.7% | **Per-muni registration required** | Edina + Wayzata direct 57-list flips; Plymouth MN, Eden Prairie, Minnetonka adjacent flips if sourced |
| Fairfield CT | 261,652 | 66,730 | 25.5% | **Per-muni registration required** | Greenwich direct 57-list flip; Stamford/Westport/Darien/New Canaan adjacent/volume flips |
| Allegheny PA | 580,039 | 9,351 | 1.6% | **Per-muni registration required** | Fox Chapel direct 57-list flip only; O'Hara/Aspinwall/Sewickley optional corridor breadth |

**Verdict:** All five tested Tier 2/3 counties have the King WA wedge. None should be planned as county-level operational flips from target-muni ingest alone. Master should dispatch Lane A as **per-muni jurisdiction registration + per-muni zoning backfill + per-muni matrix sprint**, with county parcel adapters still useful as source plumbing.

**Threshold applied:** Ratio >=30% means county-level ingest can plausibly drive a county operational flip; ratio <30% means per-muni jurisdiction registration is required; 30-50% would be borderline. Every target set here is below 30%, including Fairfield CT at 25.5%.

---

## Method

- Primary inputs were the accepted acquisition specs and citation directories already merged under `docs/`.
- Live probes were limited to missing count values:
  - Maricopa parcel source: `https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Parcel_Data_View/FeatureServer/0`
  - Allegheny parcel source: `https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0`
- For counties not yet loaded in prod, "total parcels" means the canonical public parcel source count from the acquisition spec, not a prod `parcel_count`.
- For Fairfield CT, prod is already loaded and PR #228's `Town_Name -> parcels.city` re-derivation provides the target-muni parcel counts used by `docs/AUDIT_NOTES/fairfield_ct_citation_directory.md`.

Important interpretation: this analysis is denominator math only. It does not re-open Class A/Class B source feasibility, matrix readiness, or ordinance structure except where those affect the recommended per-muni target order.

---

## Maricopa County, AZ

| Input | Value |
|---|---:|
| County total parcels | 1,742,671 |
| Scottsdale | 150,207 |
| Paradise Valley | 10,071 |
| Carefree | 3,112 |
| Cave Creek | 17,033 |
| Fountain Hills | 16,216 |
| Target + adjacent total | 196,639 |
| County share | 11.3% |

Source basis:

- County total, Scottsdale, and Paradise Valley counts from `docs/MARICOPA_AZ_ACQUISITION_SPEC.md`.
- Carefree, Cave Creek, and Fountain Hills counts from live `PropertyCity` count probes against Maricopa `Parcel_Data_View/FeatureServer/0`.
- `docs/AUDIT_NOTES/maricopa_az_citation_directory.md` confirms Scottsdale + Paradise Valley are direct 57-list targets and Carefree/Cave Creek/Fountain Hills are adjacent wealth-band candidates.

Verdict: **per-muni jurisdiction registration required.** Scottsdale + Paradise Valley are only 9.2% of county parcels; even adding the adjacent northeast Valley band reaches only 11.3%. A county-level Maricopa jurisdiction would remain partial after the target proof.

Recommended per-muni targets:

| Per-muni target | Reason |
|---|---|
| `Scottsdale, AZ` | Direct 57-list polygon; best ordinance-side fit; must carry forward city-boundary/prefilter requirement because raw `PropertyCity='SCOTTSDALE'` bbox failed the primitive. |
| `Paradise Valley, AZ` | Direct 57-list polygon; simpler Class A path because town zoning bbox passed against county parcel bbox. |
| `Fountain Hills, AZ` | Largest adjacent add-on in this staged set, but PDF/code workflow until a live zoning layer is found. |
| `Cave Creek, AZ` | Adjacent add-on; parcel app was verified, zoning remains ordinance/PDF workflow. |
| `Carefree, AZ` | Small adjacent add-on; low denominator cost but manual zoning-source friction. |

Expected operational flips: **2 direct 57-list flips** if Scottsdale and Paradise Valley are registered separately. Up to **5 municipal flips** if Master also wants the adjacent northeast Valley band.

---

## Oakland County, MI

| Input | Value |
|---|---:|
| County total parcels | 490,590 |
| Birmingham | 9,786 |
| Bloomfield Hills | 1,833 |
| Bloomfield Township | 18,224 |
| Franklin | 1,312 |
| Beverly Hills | 4,174 |
| Target + adjacent total | 35,329 |
| County share | 7.2% |

Source basis:

- County total from `docs/OAKLAND_MI_ACQUISITION_SPEC.md`.
- Target and adjacent counts from `docs/AUDIT_NOTES/oakland_mi_citation_directory.md`, keyed by `CVTTAXDESCRIPTION`.
- Same doc confirms no verified SEMCOG carry and no Class C parcel zoning.

Verdict: **per-muni jurisdiction registration required.** Birmingham + Bloomfield Hills are only 2.4% of Oakland parcels. The full staged corridor reaches 7.2%, nowhere near the county-level 70% coverage gate.

Recommended per-muni targets:

| Per-muni target | Reason |
|---|---|
| `Bloomfield Hills, MI` | Direct 57-list polygon; strongest technical proof because the city layer carries `PIN` + `Zoning`. |
| `Birmingham, MI` | Direct 57-list polygon; strongest ordinance/use-table source via enCodePlus Appendix A. |
| `Beverly Hills, MI` | Best add-on because its zoning FeatureServer was verified and bbox matched in pre-stage. |
| `Bloomfield Township, MI` | Largest adjacent parcel count, but PDF/Clearzoning source friction. |
| `Franklin, MI` | Small adjacent add-on; American Legal + map/PDF workflow. |

Expected operational flips: **2 direct 57-list flips** first. Beverly Hills is a likely third flip if Lane A wants a live-layer add-on; Bloomfield Township and Franklin should not be promised in the first proof.

---

## Hennepin County, MN

| Input | Value |
|---|---:|
| County total parcels | 445,965 |
| Edina | 21,372 |
| Wayzata | 1,976 |
| Minnetonka | 20,971 |
| Plymouth, MN | 29,201 |
| Eden Prairie | 23,019 |
| Target + adjacent total | 96,539 |
| County share | 21.7% |

Source basis:

- County total from `docs/HENNEPIN_MN_ACQUISITION_SPEC.md`.
- Target and adjacent counts from `docs/AUDIT_NOTES/hennepin_mn_citation_directory.md`, keyed by MetroGIS `CTU_NAME`.
- Same docs confirm MetroGIS is parcel-only and does not carry Class C zoning.

Verdict: **per-muni jurisdiction registration required.** Edina + Wayzata are only 5.2% of Hennepin parcels. Even the expanded five-muni wealth band is 21.7%, below the planning threshold. The MetroGIS adapter remains valuable for parcel source reuse, but operational flips need city-scoped jurisdictions.

Recommended per-muni targets:

| Per-muni target | Reason |
|---|---|
| `Edina, MN` | Direct 57-list polygon; cleanest source-population proof because city zoning layer carries `PID` + `Zoning`. |
| `Wayzata, MN` | Direct 57-list polygon; likely manual/PDF-map zoning path, but small denominator makes per-muni jurisdiction realistic. |
| `Plymouth, MN` | Largest adjacent staged city; public zoning layers verified in pre-stage. Use full `Plymouth, MN` label to avoid Plymouth County MA ambiguity. |
| `Eden Prairie, MN` | Strong adjacent add-on with public zoning MapServer. |
| `Minnetonka, MN` | Useful adjacent add-on, but source-query hardening needed before it is as clean as Plymouth/Eden Prairie. |

Expected operational flips: **2 direct 57-list flips** after Edina + Wayzata, or **5 Hennepin municipal flips** if the adjacent band is included. Do not expect a Hennepin county operational flip from these munis.

---

## Fairfield County, CT

| Input | Value |
|---|---:|
| County total parcels | 261,652 |
| Greenwich | 18,042 |
| Westport | 9,947 |
| Darien | 5,831 |
| New Canaan | 7,386 |
| Stamford | 25,524 |
| Target + adjacent total | 66,730 |
| County share | 25.5% |

Source basis:

- County total from `docs/PHASE2_NY_CT_DIAGNOSTIC.md`.
- Target and adjacent counts from `docs/AUDIT_NOTES/fairfield_ct_citation_directory.md`, sourced from PR #228's `Town_Name -> parcels.city` re-derivation.
- Fairfield is already prod-loaded at the county level, but CT zoning remains municipal and PR #221 dropped the CT CAMA embedded-zoning/Class C premise.

Verdict: **per-muni jurisdiction registration required.** Fairfield is closest to the line, but 25.5% is still below the 30% threshold. Stamford's 25,524 parcels help, but the five staged towns still cannot drive a countywide operational flip.

Recommended per-muni targets:

| Per-muni target | Reason |
|---|---|
| `Greenwich, CT` | Direct 57-list polygon; should lead despite source friction. |
| `Stamford, CT` | Largest staged city and only verified live zoning MapServer. |
| `Westport, CT` | Strong ordinance-side fit; AxisGIS/source extraction still needed. |
| `New Canaan, CT` | Adjacent wealth band; PDF/web-GIS workflow. |
| `Darien, CT` | Adjacent wealth band; PDF workflow and smaller denominator. |

Expected operational flips: **Greenwich direct 57-list flip** plus Stamford/Westport/Darien/New Canaan as separate municipal flips. County-level Fairfield should remain a parent/source context, not the operational unit for this sprint lane.

---

## Allegheny County, PA

| Input | Value |
|---|---:|
| County total parcels | 580,039 |
| Fox Chapel | 2,179 |
| O'Hara | 4,348 |
| Aspinwall | 1,125 |
| Sewickley | 1,699 |
| Target + adjacent total | 9,351 |
| County share | 1.6% |
| Optional Sewickley Heights add-on | +452 parcels, 9,803 total / 1.7% |

Source basis:

- County total from live count probe against Allegheny `Parcels/MapServer/0`.
- Municipal counts from `docs/AUDIT_NOTES/allegheny_pa_citation_directory.md`, keyed by `MUNICODE`.
- `docs/ALLEGHENY_PA_ACQUISITION_SPEC.md` and the citation directory confirm no public Fox Chapel zoning FeatureServer and no Class C embedded zoning.

Verdict: **per-muni jurisdiction registration required.** This is the most extreme wedge in the set. Fox Chapel + adjacent candidates are 1.6% of Allegheny parcels, so a county-level Allegheny ingest cannot flip operational from the wealth-pocket proof.

Recommended per-muni targets:

| Per-muni target | Reason |
|---|---|
| `Fox Chapel Borough, PA` | Only direct 57-list polygon; clean `MUNICODE=868`; manual Class B zoning source. |
| `O Hara Township, PA` | Adjacent corridor breadth and highest staged parcel count. |
| `Aspinwall Borough, PA` | Compact add-on with eCode360 source. |
| `Sewickley Borough, PA` | Optional Ohio River wealth corridor add-on. |
| `Sewickley Heights Borough, PA` | Optional high-value enclave, but source-friction heavy and only 452 parcels. |

Expected operational flips: **1 direct 57-list flip** if Fox Chapel is registered separately. Additional Allegheny flips are optional and low-ROI.

---

## Plan revision recommendation

1. **Adopt per-muni jurisdiction registration as the default for Tier 2/3 counties where target munis are under 30% of county parcels.** King WA is not an isolated case; Maricopa, Oakland, Hennepin, Fairfield, and Allegheny all show the same denominator wedge.
2. **Keep county parcel adapters as source infrastructure, not the operational unit.** They remain useful for acquisition and standard fields, but the audit denominator should be municipal for these wealth-pocket sprints.
3. **Prioritize per-muni flips by direct 57-list impact and source cleanliness:**
   - Hennepin: Edina first; Wayzata second if Master accepts PDF/manual path.
   - Maricopa: Paradise Valley for clean spatial path, Scottsdale for highest value and best ordinance table.
   - Oakland: Bloomfield Hills + Birmingham.
   - Fairfield: Greenwich + Stamford.
   - Allegheny: Fox Chapel only unless a customer signal justifies adjacent add-ons.
4. **Do not forecast county-level operational count gains for these five counties from the staged target-muni work.** Forecast municipal operational gains instead.
