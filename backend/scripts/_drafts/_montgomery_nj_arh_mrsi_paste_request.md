# Montgomery Township NJ — ARH + MR/SI verdict correction: paste request (2026-06-12)

## Why
Two Somerset county-default verdicts are **heuristic guesses** (cites=None), and both zones exist
**only in Montgomery township** (Somerset). Blast radius today: 9 parcels score ≥70, **0 listed** —
so no false needle is in the digest yet; this is latent data-hygiene, not urgent.

| Zone | parcels (≥1.5ac) | current verdict | how it was set | suspicion |
|---|---|---|---|---|
| **ARH** (§16-4.13) | 206 (11) | self_storage = **conditional** | "Heuristic bootstrap from inferred zone_class=**agricultural**" | WRONG — ARH = **Age-Restricted Housing District** (residential). Expect **prohibited**. |
| **MR/SI** (§16-4.7) | 8 (8) | self_storage = **permitted** | "Heuristic bootstrap from inferred zone_class=**industrial**" | AMBIGUOUS — MR/SI = **Mountain Residential / Special Industrial**. The "Special Industrial" half *may* legitimately permit warehousing → permitted/conditional could be correct. MUST read the use list. |

## What's blocked
`fetch_from_url` (the pipeline's eCode360 playwright crawler) returns only the **definitions**
section for the Chapter 16 root node ([ecode360.com/34978977](https://ecode360.com/34978977)); the
per-district use lists are deeper nodes whose numeric IDs I don't have, and eCode360 search/WebFetch
are 403/JS-blocked. So the automated pipeline can't reach §16-4.7 / §16-4.13.

## Paste ask (Nache)
Open [ecode360.com/34978977](https://ecode360.com/34978977) (Montgomery Township NJ, Chapter 16:
Land Development) and copy the **Permitted Principal Uses + Conditional Uses + Accessory Uses** for:
1. **§16-4.7 — MR/SI Mountain Residential/Special Industrial District**
2. **§16-4.13 — ARH Age-Restricted Housing District**

**Specific question for each:** does the district name **warehouse / warehousing / self-storage /
mini-warehouse / "storage and distribution"** as a *permitted-by-right principal* use, a
*conditional* use, an *accessory* use, or **not at all**? (Per the convention: warehouse permitted
by-right → self_storage conditional; otherwise prohibited unless storage is expressly named.)

## Expected apply (after paste, via UPSERT, PR `parcellogic/montgomery-nj-arh-mrsi-correction`)
- **ARH → prohibited** (residential; removes 206 latent false-conditional parcels). High prior.
- **MR/SI →** depends on §16-4.7 text: if "Special Industrial" permits warehouse by-right → keep
  **permitted** but upgrade heuristic→`human_reviewed=true` with §16-4.7 citation; if warehouse is
  conditional → **conditional**; if MR/SI is residential-dominant with no warehouse-as-principal →
  **prohibited**. Then re-score Somerset vs SN and surface the needle delta.

No verdict applied yet — held for the paste (validate-before-apply / citation-grounding discipline).
