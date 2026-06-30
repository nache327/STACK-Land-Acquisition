# Horsham Township (Montgomery PA) — eCode360 URL surface (for Nache grab, 2026-06-29)

eCode360 blocks automated fetch (403) → Nache grabs the use tables; Claude Code applies on paste.
Catch #38 verified: "Township of Horsham, PA, Montgomery County, Pennsylvania."

## Direct links
- **Township root:** https://ecode360.com/HO1764
- **Chapter 230 Zoning:** https://ecode360.com/44681314

### Needle-candidate INDUSTRIAL districts (grab these — the 58 SN-pass pool)
| zone | SN-pass | eCode360 |
|---|---|---|
| **I-1 Industrial** | 13 | https://ecode360.com/9954726 |
| **I-2 Industrial** (Art. XXVI) | 18 | https://ecode360.com/9954819 |
| **I-3 Industrial** | 19 | https://ecode360.com/9954846 |
| **PI Planned Industrial** | 8 | https://ecode360.com/9954772 |

Grab the USE-REGULATIONS section of each (the permitted/conditional/special-exception use list). What
matters for the verdict: (a) is self-storage / mini-warehouse / "mini storage" / self-service storage
named? (b) is warehouse/warehousing/storage/distribution by-right? → permitted (named) / conditional
(Cresskill: warehouse by-right + self-storage unnamed) / prohibited (explicit NP or silence).

### Optional (silence-rule prohibited coverage, secondary)
- **C-2 General Commercial:** https://ecode360.com/9954556 (reconcile GC-2/C-2 code gap first)
- Residential districts (R-1/R-2/R-3/R-4) — silence-prohibited if grabbed; not needles.

## On paste, Claude Code runs (fast):
1. Cross-check the grabbed zone codes vs parcels.zoning_code (I-1/I-2/I-3/PI confirmed present).
2. Apply muni-specific verdicts via direct UPSERT (`_apply_horsham_verdicts.py`), municipality='Horsham Township'.
3. Re-score vs SN (filter 72409acf-3712-4761-a156-50c2329ad35b) + harvest preview.
4. PR parcellogic/montgomery-pa-horsham-verdicts (review-gated).
