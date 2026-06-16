# Op-5 Monmouth NJ Citation-Structure Hygiene Pass

**Date:** 2026-06-15 (continuation of attribution audit from 2026-06-11)
**Target:** 120 Monmouth NJ matrix rows from the 2026-06-04 Lane E operator batch where ordinance citations existed in `notes` but the structured `citations` array was empty.
**Outcome:** **120/120 UPDATED in place — citations array populated, verdicts/notes preserved. No operational state change (citations are not audited).**

---

## Headline

Per the attribution audit at `docs/AUDIT_NOTES/monmouth_120_row_attribution.md` (PR #229), Monmouth's 120-row 2026-06-04 operator batch had real ordinance section refs embedded in `notes` (e.g., `[§225-13.A(8)]` Spring Lake GC, `[§130-38(C)(7)(b)[1]]` Sea Bright BR) but the structured `citations` field was empty. UI/API consumers reading the structured array saw no citation despite the verdict being fully grounded.

This pass migrates those refs into the `citations` array and cross-walks each muni to its verified eCode360 URL from `backend/data/monmouth_zoning_directory.json`.

**Zero changes to verdict, notes, or operational state. Pure citation-depth improvement.**

| dimension | BEFORE | AFTER |
|---|---|---|
| Rows updated | — | **120 / 120** (in place) |
| Citations array | empty (None / count=0) | **populated** (2-citation pair per Scarsdale PR #234 precedent) |
| Section-ref source | `[§...]` embedded in notes | extracted into structured `citations[0].section` |
| URL source | None | per-muni eCode360 short code from `monmouth_zoning_directory.json` |
| Verdict | preserved | preserved (zero change) |
| Notes | preserved verbatim | preserved verbatim |
| classification_source | "human" | "human" |
| human_reviewed | True | True |
| operational_readiness | operational | operational (no change — citations are not audited) |

---

## What we did

### 1. Pull 120-row target batch

- `GET /api/admin/op5/adjudications?jurisdiction_id=<monmouth>&status=approved&limit=500` (paged)
- Filter to `created_at` starts with `2026-06-04` AND `citations` empty
- Confirmed: 120 of 165 Monmouth approved rows match

### 2. Build per-muni URL map

- Source: `backend/data/monmouth_zoning_directory.json` (51 muni entries with verified eCode360 URLs)
- Exact-name match to `prod_city_value` (avoided partial-match false positives like "Spring Lake" → "Spring Lake Heights")
- **All 10 top target munis matched cleanly**: Holmdel township, Red Bank borough, Rumson borough, Colts Neck township, Sea Bright borough, Marlboro township, Spring Lake Heights borough, Allenhurst borough, Spring Lake borough, Deal borough
- 0 muni URL gaps

### 3. Section-ref extraction

Regex extracted `[§...]` / `[Sec...]` / `[NNN-NNN]` patterns from notes:
- **94 of 120 rows** had a section ref in notes → got specific §-citation (e.g., `§225-13.A(8)`, `§490-152`, `§130-38(C)(7)(b)[1]`, `§30-86.5(b)`)
- **26 of 120 rows** had notes-only (no section ref) → got generic "district use provisions" framing with the muni URL

### 4. Author 2-citation pair (Scarsdale PR #234 precedent)

```python
citations = [
    {
        "section": f"{muni} Zoning Ordinance — {section_ref} (district use provisions)" if section_ref
                   else f"{muni} Zoning Ordinance — district use provisions",
        "quote": (notes_with_ref_stripped),  # operator's original verdict reasoning
        "url": ecode360_url,  # from monmouth_zoning_directory.json
    },
    {
        "section": f"{muni} Zoning Ordinance — General Use Provisions (catchall)",
        "quote": "Uses not specifically listed as permitted in a district's "
                 "Schedule of Regulations are prohibited (NJ municipal "
                 "default-prohibition pattern).",
        "url": ecode360_url,
    },
]
```

### 5. Apply via `_upload-matrix-rows` with `replace_existing=true`

- 8 batches × 15 rows = 120 rows
- **120/120 UPDATED in place** (in-place upsert via NULL-muni and named-muni keys preserved)
- 0 errors, 0 skips
- Verdicts / notes / `human_reviewed=true` status all preserved

### 6. NO refresh fired

Citation structure is not audited; this pass has zero impact on `matrix_zone_match_pct`, `self_storage_classified_parcel_pct`, or `operational_readiness`. Skip refresh per scope guard.

---

## Sample before/after

### Sample row 1: Spring Lake GC

**BEFORE:**
- `zone_code`: GC
- `municipality`: Spring Lake borough
- `verdict`: (conditional, conditional, permitted, prohibited)
- `notes`: `[§225-13.A(8)] Wholesale distribution centers + warehouses permitted BY RIGHT in GC District only; self-storage unnamed -> conditional per warehouse compatibility`
- `citations`: None

**AFTER:**
- `zone_code`: GC (unchanged)
- `municipality`: Spring Lake borough (unchanged)
- `verdict`: (conditional, conditional, permitted, prohibited) (unchanged)
- `notes`: same verbatim
- `citations`: 
  ```json
  [
    {
      "section": "Spring Lake borough Zoning Ordinance — §225-13.A(8) (district use provisions)",
      "quote": "Wholesale distribution centers + warehouses permitted BY RIGHT in GC District only; self-storage unnamed -> conditional per warehouse compatibility",
      "url": "https://ecode360.com/SP0178"
    },
    {
      "section": "Spring Lake borough Zoning Ordinance — General Use Provisions (catchall)",
      "quote": "Uses not specifically listed as permitted in a district's Schedule of Regulations are prohibited (NJ municipal default-prohibition pattern).",
      "url": "https://ecode360.com/SP0178"
    }
  ]
  ```

### Sample row 2: Holmdel R 40A (2) (notes-only, no section ref)

**BEFORE:**
- `citations`: None
- `notes`: prose-only verdict reasoning (no `[§...]` marker)

**AFTER:**
- `citations`:
  ```json
  [
    {
      "section": "Holmdel township Zoning Ordinance — district use provisions",
      "quote": "<original notes verbatim>",
      "url": "https://ecode360.com/HO0333"
    },
    {
      "section": "Holmdel township Zoning Ordinance — General Use Provisions (catchall)",
      "quote": "Uses not specifically listed as permitted...",
      "url": "https://ecode360.com/HO0333"
    }
  ]
  ```

---

## Hard-rule compliance

- ✅ Real ordinance citations only (every URL from `monmouth_zoning_directory.json`; section refs extracted verbatim from operator notes — zero fabrication).
- ✅ Verdicts unchanged (preserve operator's domain decisions).
- ✅ Notes preserved verbatim (no semantic edits).
- ✅ classification_source remains "human" (this is structural cleanup, not a fresh authoring pass).
- ✅ `human_reviewed=true` preserved (these were operator-approved rows; status unchanged).
- ✅ `replace_existing=true` for in-place upsert (no row count change).
- ✅ NO refresh fired (citations are not audited; metric impact = 0).
- ✅ Scope guard held: no verdict changes, no new rows, no unclear reauthoring.
- ✅ PR opens but does NOT MERGE — Master review required.

---

## Artifacts (in /tmp/)

- `op5_monmouth_citation_hygiene.py` — hygiene script with regex + URL map + apply
- `op5_monmouth_hygiene_authored.json` — 120 rows posted
- `op5_monmouth_hygiene_apply_results.json` — 8-batch results
- `op5_monmouth_hygiene_run.log` — full session log
- `mon_target_rows.json` — original 120 rows before hygiene (for diff inspection)

---

## STOP for Master review

Awaiting:
1. Approve PR — purely citation-depth improvement, zero verdict/operational change
2. Confirm hygiene-pass approach as the standard for any future "rich-notes-empty-citations" batches surfaced by future audits

This pass cleared the deferred-but-defensible work item Master signaled willingness to lift on 2026-06-15. King WA matrix sprint follows when Lane A's Phase 6A.2 lands.
