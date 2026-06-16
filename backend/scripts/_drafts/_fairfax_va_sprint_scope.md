# Fairfax VA verdict-pass scope + reviewer table (2026-06-16)

Jurisdiction `6421e666-f306-47d1-8656-c54af95599b5`. **SELECT-before-sprint:** 369,267 parcels,
99.9% zoned, 74 matrix rows **all `classification_source='unclear'` (heuristic), 0 human, 0 rings,
0 listings.** Adam lane: clear (no op5/human rows). Precompute FIRED (worker endpoint, ~90 min).

## Ordinance source (authoritative)
Fairfax County zMOD (adopted 2021), downloaded `zmod-adopted-ordinance-footnotes.pdf` (13.75MB) →
pdftotext. **Self-Storage** is a distinct use under category "Freight Movement, Warehousing &
Wholesale Distribution", use-specific standards **§4102.6.C**. Two use tables:
- **TABLE 4101.1** (Residential/Commercial/Industrial): districts R-A…R-30, C-1…C-8, I-I, I-2, I-3,
  I-4, I-5, I-6.
- **TABLE 4101.2** (Planned Development): PDH, PRC, PDC, PRM, PTC, PCC. Self-Storage shows `/SE`
  (permitted-if-on-final-development-plan, else special exception).
- **Footnote 341 (verbatim):** "This carries forward permissions for current use 'mini-warehousing
  establishment,' except the use is changed from **SE to allowed, subject to conditions, in the I-3
  District**." ("allowed, subject to conditions" = permitted-by-right with use-specific standards
  §4102.6.C → `permitted` in our schema.)
- **Footnote 335:** a vehicle use is SE in I-4 "when in association with a self-storage use" →
  confirms self-storage operates in I-4.

## Extraction limitation (why most verdicts are HELD)
Tables 4101.1/4101.2 use a **diagonal/rotated district-column header**; pdftotext flattens the P/SE/SP
cell markers so they can't be aligned to districts with confidence, and `pdftoppm` is unavailable to
render the matrix visually. So only the footnote-grounded I-3 verdict is verbatim-verifiable now.

## Reviewer table (26 needle-candidate zones)
| Zone | parcels(1.5-15ac) | heuristic | PROPOSED | conf | basis |
|---|---|---|---|---|---|
| **I-3** | 132 | permitted | **permitted** ✅APPLY | 0.95 | FN341 verbatim: mini-warehousing → allowed in I-3 (§4102.6.C) |
| I-4 | 264 | permitted | permitted? | HOLD | FN335 implies self-storage in I-4; matrix marker unverified |
| I-5 | 507 | permitted | permitted? | HOLD | heavy-industrial ≥ I-3 (structural inference, NOT verbatim) |
| I-6 | 134 | permitted | permitted? | HOLD | same |
| I-2 / I-I / M | 5/5/4 | permitted | ? | HOLD | light/limited-industrial — verify |
| C-8 | 196 | conditional | conditional? | HOLD | commercial; matrix shows SE in C-block (which C unclear) |
| C-3/C-6/C-7/C-4/C-2/C-5/C-1/CS/CP/CC/CO | 105/162/70/43/42/26/0/18/4/0/3 | conditional | ? | HOLD | verify per-C-district SE marker |
| PDC | 1,672 | prohibited | conditional? | HOLD | Table 4101.2 Self-Storage `/SE` in PD block (which PD unclear — PDC vs PRM) |
| PRM/PTC/RTC | 265/96/18 | prohibited/unclear | ? | HOLD | planned/transit — verify |
| AE/AC/AW (agricultural) | 4/4/1 | conditional | likely prohibited | HOLD | ag districts — verify |

**Applying now (verbatim-grounded):** I-3 = permitted. **Held for use-table confirm:** the other 25,
incl. the big pools I-5 (507) / PDC (1,672) / I-4 (264). To finish: a 2-minute visual read of Table
4101.1/4101.2 Self-Storage row (or a Municode/Encode use-table screenshot) resolves every marker.

## Catch-#20 note
Fairfax has **0 CoStar listings** → even fully verdicted + ringed, it surfaces 0 needles until a
**Fairfax CoStar pull**. Verdict + precompute = infrastructure; the pull is the harvest trigger
(same as Howard, which had 94 listings → 4 wealth-qualified needles).
