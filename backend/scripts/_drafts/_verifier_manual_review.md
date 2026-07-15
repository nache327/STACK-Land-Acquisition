# Verifier NULL-municipality — rows needing a MANUAL town ruling

These human verdicts are scoped `municipality=NULL` on a MULTI-TOWN county jurisdiction, so
each currently fans out county-wide. The intended town is NOT derivable from the row (generic
in-app Verifier note, or a terse note with no town named), so the automated backfill left them
untouched. For each, tell me the town it was meant for and I'll re-scope it (exact `parcels.city`
casing) + re-score — OR confirm it's a deliberate county-wide default and I'll leave it.

## ⚠️ MATERIAL — RESOLVED-PENDING-GO (2026-07-15 analysis) — needs Nache's explicit approval to execute

Re-audited with the town-scoped rows for comparison. Findings (script:
`scripts/_demote_monmouth_null_verifier.py`, dry-run only — the --apply was auto-mode-blocked as a
material shared-prod change to this escalated row, awaiting go):

| Zone | NULL verdict | fanned needles NOW | town-scoped rows that exist | Recommendation |
|---|---|---|---|---|
| **LI** | permitted ("Permitted", bare) | **67** (Manalapan 28, Aberdeen 14, Neptune 14, Shrewsbury 8, Freehold 3) | Marlboro §220-92 = **conditional**; Red Bank §490-150 = **permitted** | **DEMOTE.** #38 DECISIVE: the two verified towns DISAGREE, so a county-wide "permitted" is factually wrong. NJ home-rule = no county UDO to justify NULL. Marlboro(31)+RedBank(2)=33 verified LI needles KEPT via their own rows. |
| **IOR** | permitted ("Permitted", bare) | **35** | none | **DEMOTE.** No #37 verbatim basis (bare "Permitted"), no town-scoped IOR verdict, 56 home-rule towns — indefensible as county-wide. |
| **CIR** | conditional ("…I think we should consider this") | **0** | none | **DEMOTE.** Note is a speculative musing, not a grounded verdict (#37 fail). |

**Net if executed: Monmouth 141 → 39 needles (−102 UNVERIFIED, false-confidence leads removed).**
The 33 verified LI needles (Marlboro conditional + Red Bank permitted) are preserved. **Follow-up to
recover GENUINE needles:** a proper per-town grounding pass for Monmouth LI/IOR towns on a verbatim
basis — Manalapan (347 LI parcels) is the strongest candidate.

**Correction to prior note:** IOR arms **35** needles (not 0 as first stated) — it is material, not
hygiene. Earlier draft was stale.

## Low / zero needle impact — correctness hygiene (prohibited on codes that arm nothing)

In-app Verifier rows (generic note "Verified via Site Scout Zoning Chat … user session") — all
prohibited, so they can only over-suppress towns lacking their own row, on codes where
self-storage wouldn't arm anyway:

| County | Zones (all prohibited, NULL) | # towns fanned |
|---|---|---|
| Burlington | A-1, C-1, NC-1, NC-2 | 41 |
| Monmouth | R-80 (ecode360 source) | 56 |
| Somerset | AH-1, CF, I-2, LD, MDR, MH, NBH, O, OL, U, VB, VR | 28 |

## Left ALONE (correct as-is — NOT the bug)

- **Lake County IL — II, LI (permitted, NULL):** genuine county-wide Unified Development Ordinance
  (Ch. 151) — NULL is correct by design.
- **Bergen NJ — CEM, CR, GOV (prohibited, NULL):** deliberate tombstone markers ("zone code not in
  any verified Bergen municipality ordinance").
- **Middlesex MA (18) + Norfolk MA (23) — prohibited, NULL:** script-applied per-town verdicts
  written NULL (notes name Lowell/Somerville/Reading/Brookline/Norwood/Needham/Bellingham/Melrose).
  All prohibited on residential/business codes → ~zero needle impact. Technically mis-scoped; scope
  opportunistically only if we ever see a same-code industrial district collision.
- **Single-place jurisdictions (Loudoun, Fairfax, Montgomery MD, Howard MD, all UT cities, Allentown
  PA, etc. — 336 rows):** `parcels.city` is unpopulated (all NULL), so `municipality IS NULL` is the
  ONLY value that scores. Backfilling would BREAK them. Correct as-is.

## Done in this pass (Somerset — Franklin, derivable from verbatim notes)

- **G-B** — NULL conditional row DEMOTED (tombstoned): Franklin already has an authoritative
  town-scoped `prohibited` verdict (§220-10M); the NULL row only fanned a stale conditional to the
  other 27 towns.
- **PAC, S-C-V** — scoped NULL → `Franklin township` (planned-adult-community / senior-village
  district codes named "Franklin …" in the notes).
- Somerset re-scored under the advisory lock (117,387 parcels). **Needle delta: 0** — these codes
  clear no wealth-gated parcels, so the fix is pure correctness (removed false county-wide
  application), not a yield change.
