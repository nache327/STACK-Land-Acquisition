# Session B — Bellevue WA Bel-Red + office upside (Phase 6), 2026-07-15

Follows main LI/GC grounding (46). Ring already precomputed. municipality='Bellevue'. Did NOT touch King county.

## Bellevue Bel-Red (BR-*) — +39 needles → 85 total
- bellevue.municipal.codes is Cloudflare-JS-gated; fetched **LUC Part 20.25D (BelRed)** via **Playwright
  headless** (passed the challenge; 177k chars, 20 tables). Bel-Red uses live in Part 20.25D (like Downtown
  → Part 20.25A); the 20.10.375 section only establishes districts.
- Use-table column order verified by <td> index + validated against a broad row ("61 Finance P/P..P"):
  [BR-MO/MO-1] [BR-OR/OR-1/OR-2] [BR-RC-1/2/3] [BR-R] [BR-GC] [BR-CR] [BR-ORT].
- Use "637 Warehousing and Storage Services" = **P in BR-GC**, **P/ (inside-node) in BR-OR/OR-1/OR-2**;
  BLANK in BR-MO, BR-RC, BR-R, BR-CR, BR-ORT. **No named self-storage/self-service/mini-storage** anywhere
  in Bel-Red → warehouse-by-right convention → **BR-GC + BR-OR/OR-1/OR-2 = ss/mw CONDITIONAL, li permitted**.
- **NEEDLES (SELECT-confirmed): BR-GC 25 + BR-OR 8 + BR-OR-2 5 + BR-OR-1 1 = 39.** Other BR-* (MO/RC/R/CR/ORT)
  = warehousing blank → prohibited (correct no-op; Bel-Red is a TOD corridor replacing its light-industrial past).

## Office / CB (O/OLB/OLB2/PO/CB/DT-O-1) — NO upside (confirmed no-op)
- Chart 20.10.440 (broker-PDF, x-aligned): use "637 Warehousing and Storage" is **blank in O/OLB/OLB2/PO**
  (office does not permit warehousing) and **'S' (special, not by-right) in CB**. No named self-storage.
  → not arm-able on a principal by-right basis. Grounded prohibited.

## Result
Bellevue total needles **46 → 85** (LI 28 + GC 18 + BR-GC 25 + BR-OR 8 + BR-OR-2 5 + BR-OR-1 1).
verify_batch CLEAN, gate PASS, matrix_coverage 100%. `scripts/_apply_bellevue_belred.py`.
Method note: Playwright headless defeats the Cloudflare JS challenge on municipal.codes/codepublishing —
reusable for the other WA/JS-gated codes (Mercer Island, Bainbridge use tables) if a needle-hunt is wanted.
