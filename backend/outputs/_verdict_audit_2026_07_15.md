# Adversarial verdict spot-audit — 2026-07-15

**Method:** For each block I re-derived the `self_storage` verdict directly from the **current** ordinance
(Playwright / live use-table cell reads / PDF) **before** revealing the stored matrix, then compared. Needle
zones prioritized. Per instruction, **no silent fixes** — mismatches are escalated below with verbatim
citations; no DB writes and no re-score were performed. `verify_batch` is not run because no correction was
applied.

## Result — 4 CONFIRMED blocks, 2 blocks with a mismatch

| # | Block | Zone | Re-derived from current ordinance | Stored | Verdict |
|---|-------|------|-----------------------------------|--------|---------|
| 1 | Concord CA `7ad622d4` | OBP | Self-Storage/Mini-Storage = **UP** (Ch. 18.50 use table) | conditional | ✅ CONFIRMED |
| 1 | Concord CA | IBP | **UP** | conditional | ✅ CONFIRMED |
| 1 | Concord CA | IMX | **UP** | conditional | ✅ CONFIRMED |
| 1 | Concord CA | HI (4th UP col) | UP in table, **but no HI zone exists in Concord parcels** | (absent) | ✅ CONFIRMED — moot, 0 needles lost |
| 2 | Scottsdale AZ `8e31ce3a` | I-1 | "Internalized community storage" = **P** | conditional | ✅ CONFIRMED (green) |
| 2 | Scottsdale AZ | C-3 | **P** | conditional | ✅ CONFIRMED (green) |
| 2 | Scottsdale AZ | C-4 | **P** | conditional | ✅ CONFIRMED (green) |
| 2 | Scottsdale AZ | **I-G** | "Internalized community storage" = **blank / not permitted** | **conditional** | 🔴 **MISMATCH — over-permit** |
| 3 | Franklin TN `307285f8` | LI | "Self-Storage Facilities" named-use, allowed (§5.1.4 standards) | conditional | ✅ CONFIRMED (green) |
| 3 | Franklin TN | HI | allowed (§5.1.4 standards) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA `71a53bba` | LI | "Warehousing and Storage Services" = **P** (LUC 20.10.440) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA | GC | **P** (LUC 20.10.440) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA | BR-OR/OR-1/OR-2 | **P/** (LUC 20.25D.130) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA | **BR-GC** | "Warehousing and Storage Services" = **P** (LUC 20.25D.130) | **absent** | 🔴 **MISMATCH — missing / under-coverage** |
| 5 | Hingham MA `4208af9b` | 131I | 4.14 storage-warehouse = **P** + 6.2 light-industrial = **P** → convention | conditional | ✅ CONFIRMED |
| 5 | Hingham MA | 131IP | same (P/P) | conditional | ✅ CONFIRMED |
| 5 | Hingham MA | 131BB | 4.14 storage-warehouse = **P** | conditional | ✅ CONFIRMED |
| 6 | Westchester — Yonkers | §43-36 | self-storage confined to BR/B/BA; M/MG/I/IP/PMD not listed | BR/B/BA cond.; mfg prohibited | ✅ CONFIRMED |

Benign level note (not a mismatch): several stored zones are tagged **conditional** where the current ordinance
actually reads **permitted** (Concord OBP/IBP/IMX, Scottsdale I-1/C-3/C-4, Bellevue LI/GC/BR-OR, Franklin LI/HI).
Both permitted and conditional are needle-positive, so this is a **conservative** label that neither loses nor
manufactures needles. Left as-is.

---

## ESCALATION 1 — Scottsdale I-G: stored over-permits (false needles)

**Zone:** I-G (General Industrial). **Stored:** `self_storage = conditional` (conf 0.80, human_reviewed).
**Re-derived:** self-storage **PROHIBITED** in I-G.

**Verbatim basis — Appendix B Zoning Ordinance, Art. XI Land Use Table §11.201.A (Municode, live read):**
- Row **"Internalized community storage"**: `C-1=P  C-2=P  C-3=P  C-4=P  PNC=P  PCC=P  I-1=P` — **`I-G` = (blank / not permitted)**.
- Row **"Wholesale, warehouse and distribution"**: `C-3=P  C-4=P  I-1=P  **I-G=P**`.

**Verbatim definition — Art. III Definitions:**
> "Internalized community storage is an establishment that offers storage in an enclosed building, with access
> to storage units only from the interior of the building. The use may include a dwelling unit/office for
> on-site supervision, but may not include outdoor storage."

**Why it's a mismatch (#37 verbatim, #58 closed-list, named-beats-convention):** self-storage IS a **named use**
in Scottsdale ("Internalized community storage" = miniwarehouse). It is permitted in I-1/C-1/C-2/C-3/C-4/PNC/PCC
but **deliberately omitted from I-G**, even though *general* "Wholesale, warehouse and distribution" IS permitted
in I-G. The stored verdict applied the warehouse-by-right convention to I-G — but a named self-storage use that
excludes I-G **beats** the convention. I-G self-storage should be **prohibited**, not conditional.

**Materiality:** I-G has ~43 parcels (10 ≥1.5 ac) + "I-G (C)" ~33 (3 ≥1.5 ac). Any in-ring I-G parcel is a
**false needle** under the current stored value. **Recommend:** demote I-G → prohibited (do not delete the row),
verbatim cite the §11.201.A "Internalized community storage" blank-in-I-G cell, then re-score Scottsdale + gate.

## ESCALATION 2 — Bellevue BR-GC: missing from matrix (missed needles)

**Zone:** BR-GC (BelRed General Commercial). **Stored:** **no `self_storage` row exists.**
**Re-derived:** self-storage is a **permitted** use in BR-GC → should be conditional (needle-positive).

**Verbatim basis — LUC 20.25D.130 BelRed land-use chart (live, Playwright):** row
**"Warehousing and Storage Services, Excluding Stockyards"** → `BR-OR/OR-1/OR-2 = P/ , **BR-GC = P**`, all other
BelRed zones blank. (Cross-check: LUC 20.10.440 base chart — same use = `LI=P, GC=P`.)

**Why it's a mismatch:** the stored Bellevue matrix was built from a **broker-PDF reproduction** of the use chart
and contains 10 BR-* rows but **omits BR-GC entirely**. The live code shows Warehousing/Storage permitted in
BR-GC → self-storage conditional by the warehouse convention. The omission silently drops a whole needle-positive
zone.

**Materiality:** BR-GC has 75 parcels, **25 ≥1.5 ac** — the largest BelRed candidate zone. In-ring BR-GC parcels
are currently **invisible needles**. **Recommend:** add BR-GC = conditional (warehouse-convention, cite LUC
20.25D.130), then re-score Bellevue + gate. (BR-CR is also absent but its chart cell is blank → correctly
prohibited, no action.)

## Secondary observation (not escalated) — Scottsdale commercial breadth
"Internalized community storage" is also **P** in C-1, C-2, PNC, PCC per §11.201.A. If those zones carry in-ring
≥1.5 ac parcels they are additional needle-positive zones; outside this audit's I-1/I-G/C-3/C-4 scope. Flag for a
coverage pass, not a correctness mismatch.

## Sources
- Concord: Municipal Code Ch. 18.50 (Playwright).
- Scottsdale: [Land Use Tables §11.201.A](https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR_ARTXILAUSTA) + Art. III Definitions.
- Franklin TN: [Zoning Ordinance Principal Use Table pp. 87-89 + §5.1.4](https://web.franklintn.gov/FlippingBook/FranklinZoningOrdinance/).
- Bellevue: LUC [20.10.440](https://bellevue.municipal.codes/LUC/20.10.440) + [20.25D.130](https://bellevue.municipal.codes/LUC/20.25D.130) (live).
- Hingham: [Zoning By-Law rev. 2025-04-29, §III-A use table](https://hingham-ma.gov/DocumentCenter/View/2145/Hingham-Zoning-By-law-PDF).
- Yonkers: Zoning Ordinance §43-36.
