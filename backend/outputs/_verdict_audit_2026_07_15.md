# Adversarial verdict spot-audit + remediation — 2026-07-15

**Method:** For each block I re-derived the `self_storage` verdict directly from the **current** ordinance
(Playwright / live use-table cell reads / PDF) **before** revealing the stored matrix, then compared. Needle
zones prioritized.

**Outcome:** 6 blocks audited → 4 CONFIRMED, **1 real mismatch corrected** (Scottsdale I-G), **1 escalation
withdrawn** (Bellevue BR-GC — the "absent" finding was an investigation-query artifact, not a real gap).

---

## Audit table

| # | Block | Zone | Current ordinance | Stored | Verdict |
|---|-------|------|-------------------|--------|---------|
| 1 | Concord CA `7ad622d4` | OBP/IBP/IMX | Self-Storage/Mini-Storage = **UP** (Ch. 18.50) | conditional | ✅ CONFIRMED |
| 1 | Concord CA | HI (4th UP col) | UP in table, **but no HI zone in Concord parcels** | (absent) | ✅ moot — 0 needles lost |
| 2 | Scottsdale AZ `8e31ce3a` | I-1 / C-3 / C-4 | "Internalized community storage" = **P** | conditional | ✅ CONFIRMED (green) |
| 2 | Scottsdale AZ | **I-G / I-G (C)** | "Internalized community storage" = **blank / not permitted** | conditional | 🔴 **MISMATCH → CORRECTED** |
| 3 | Franklin TN `307285f8` | LI / HI | "Self-Storage Facilities" named-use, allowed (§5.1.4) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA `71a53bba` | LI / GC | "Warehousing and Storage Services" = **P** (LUC 20.10.440) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA | BR-OR/OR-1/OR-2 | **P/** (LUC 20.25D.130) | conditional | ✅ CONFIRMED (green) |
| 4 | Bellevue WA | BR-GC | **P** (LUC 20.25D.130) | **conditional (already present)** | ✅ CONFIRMED — escalation withdrawn |
| 5 | Hingham MA `4208af9b` | 131I / 131IP / 131BB | 4.14 storage-warehouse=**P** + 6.2 light-industrial=**P** | conditional | ✅ CONFIRMED |
| 6 | Westchester — Yonkers | §43-36 | self-storage confined to BR/B/BA; mfg not listed | BR/B/BA cond.; mfg prohibited | ✅ CONFIRMED |

Benign level note (not a mismatch, left as-is): several zones read stored **conditional** where the ordinance
says **permitted** (Concord OBP/IBP/IMX, Scottsdale I-1/C-3/C-4, Bellevue LI/GC/BR-OR, Franklin LI/HI). Both are
needle-positive, so "conditional" is a conservative label that neither loses nor manufactures needles.

---

## CORRECTION APPLIED — Scottsdale I-G (over-permit → prohibited)

**Script:** `scripts/_apply_scottsdale_ig_demote.py` (muni-scoped, `human_reviewed=true`, idempotent).
**Change:** `I-G` and `I-G (C)` — `self_storage`/`mini_warehouse`/`luxury_garage_condo` **conditional → prohibited**;
`light_industrial` kept **permitted** (general warehouse/distribution IS permitted in I-G).

**Verbatim basis — Appendix B Zoning Ordinance, Art. XI Land Use Table §11.201.A (Municode, live read):**
- Row **"Internalized community storage"**: `C-1=P C-2=P C-3=P C-4=P PNC=P PCC=P I-1=P` — **`I-G` = (blank / not permitted)**.
- Row **"Wholesale, warehouse and distribution"**: `C-3=P C-4=P I-1=P **I-G=P**`.

**Verbatim definition — Art. III Definitions:**
> "Internalized community storage is an establishment that offers storage in an enclosed building, with access
> to storage units only from the interior of the building. The use may include a dwelling unit/office for
> on-site supervision, but may not include outdoor storage."

**Rationale (#37 verbatim, #58 closed-list, named-beats-convention):** self-storage IS a named use
("Internalized community storage" = miniwarehouse), permitted in I-1/C-1/C-2/C-3/C-4/PNC/PCC but **deliberately
omitted from I-G**, even though *general* warehouse/distribution IS permitted in I-G. The named-use exclusion
beats the warehouse-by-right convention → I-G self-storage is **prohibited**.

**Needle delta (SELECT-confirmed):** I-G wealth-gated needles **11 → 0**. Scottsdale total **302 → 291** (−11).
Re-scored via `scripts/_rescore_scottsdale.py` (147,886 parcels).

## ESCALATION WITHDRAWN — Bellevue BR-GC (audit finding #2 was a false alarm)

The audit initially flagged BR-GC as "absent from the matrix." On applying the remediation I SELECT-verified the
full (untruncated) BR-* set and found **`BR-GC` already present: `self_storage=conditional, light_industrial=permitted,
human_reviewed=true`, cited to LUC 20.25D**. The "absent" reading came from a `tail`-truncated investigation
query (BR-GC sorts alphabetically above BR-MO, where the earlier output was cut). BR-GC's 25 wealth-gated needles
were already counted. **No change made** — the stored value already matches the live LUC 20.25D.130
("Warehousing and Storage Services" = P in BR-GC). #42 verify-before-declare caught this before any write.

---

## Post-remediation verification (verify_batch.py)

```
Scottsdale, AZ (8e31ce3a): casing OK · needles=291 · gate=PASS · VERDICT: CLEAN
Bellevue, WA   (71a53bba): casing OK · needles=85  · gate=PASS · VERDICT: CLEAN
```

## Secondary observation (not actioned) — Scottsdale commercial breadth
"Internalized community storage" is also **P** in C-1/C-2/PNC/PCC per §11.201.A. If those zones carry in-ring
≥1.5 ac parcels they are additional needle-positive zones (a coverage *expansion*, not a correctness mismatch) —
flagged for a future pass, outside this audit's I-1/I-G/C-3/C-4 scope.

## Sources
- Scottsdale: [Land Use Tables §11.201.A](https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR_ARTXILAUSTA) + Art. III Definitions.
- Bellevue: LUC [20.10.440](https://bellevue.municipal.codes/LUC/20.10.440) + [20.25D.130](https://bellevue.municipal.codes/LUC/20.25D.130) (live).
- Concord Ch. 18.50 · Franklin TN [Zoning Ordinance §5.1.4 + Principal Use Table](https://web.franklintn.gov/FlippingBook/FranklinZoningOrdinance/) · Hingham [By-Law rev. 2025-04-29](https://hingham-ma.gov/DocumentCenter/View/2145/Hingham-Zoning-By-law-PDF) · Yonkers Zoning §43-36.
