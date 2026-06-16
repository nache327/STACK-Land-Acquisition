# Strategic docs reconciliation (catch-#24 follow-up) (2026-06-16, READ-ONLY)

## What actually exists in the repo
- ✅ **`docs/TARGET_MARKETS.md`** — the only canonical strategic doc present. 57 KMZ polygons, 6-phase
  priority queue. Phase-1 NJ = Bergen/Morris/Somerset/Hunterdon/Monmouth (**Burlington NOT listed**).
- ❌ **`outputs/57_KMZ_Wealth_Pockets_Priority_List.md`** — referenced in prompts, **does not exist** in repo.
- ❌ **`outputs/ParcelLogic_Strategic_Memo_WHY_HOW.md`** — referenced, **does not exist** in repo.

(There is no `outputs/` directory with these files. They live only in chat / Nache's local copy.)

## The delta (Burlington)
- Nache (this session): "Burlington IS in plan per the 57_KMZ list — Tier-1 #6."
- `docs/TARGET_MARKETS.md`: Burlington appears **nowhere** in the 6 phase tables or the scorecard.
- DB: Burlington NJ is ingested + precomputed (174,852 ringed) with 16 county-default human rows, but
  Moorestown/Medford/Mount Laurel (37,616 parcels) have **0 per-muni verdicts**.

→ The canonical doc and the authoritative KMZ list **disagree on Burlington** (and possibly the whole
Phase-1 NJ set — the doc's "representative centers" were estimates; see the doc's own "count
reconciliation" TODO admitting metro counts are ±1 and the KMZ was never parsed directly).

## Recommendation (DO NOT edit unilaterally — for Nache approval)
1. **Make `docs/TARGET_MARKETS.md` the single source of truth** (it's the doc-by-name, on origin/main).
2. **Reconcile it against the actual KMZ:** parse the 57-polygon KMZ directly to get exact pocket
   names + centroids (the doc's own outstanding TODO), replacing the representative-center estimates.
   That resolves Burlington and the ±1 count ambiguity definitively.
3. **Pending that parse,** add Burlington NJ (Moorestown/Medford/Mount Laurel) to the Phase-1 NJ table
   per Nache's confirmation it's Tier-1 #6 — with a note that it came from the KMZ list, not the
   original prose rollup.
4. If the `outputs/` memo + KMZ-list files exist on Nache's machine, commit them to the repo
   (`docs/` or `outputs/`) so the canonical universe isn't chat-only — root cause of the drift.

## Catch #24 (root cause of the alignment drift)
The strategic target universe lived in **multiple, partially-divergent docs** (one committed, two
chat-only), so audits anchored on whichever was in context — enabling both the out-of-plan UT drift
(#23) and the Burlington in/out ambiguity. Fix: ONE committed canonical doc, KMZ-derived, referenced
by every audit. (Logged to the ledger.)
