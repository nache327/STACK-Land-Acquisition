# Session D exceptions — Montgomery County PA (jid a59d956d)

Per-session exceptions file (not the shared queue). Items are named-vs-inferred judgment calls or
residual ambiguities surfaced under the standing discipline (named-use grounds a verdict; inference
cannot sit in human_reviewed; #58 closed-list sweep is a hard gate).

## Discipline correction applied 2026-07-09 (warehouse-inference conditionals demoted)
Three districts were originally verdicted CONDITIONAL on the warehouse-by-right *convention* (inference).
Under the hard gate that inference cannot sit in human_reviewed, they were demoted to PROHIBITED,
grounded on closed-list silence / named-use classification. Re-applied + catch-#42 verified.

| Muni | Zone | was | now | grounding for the correction |
|---|---|---|---|---|
| Souderton Borough | LI | conditional | **prohibited** | Ordinance NAMES self-storage as a prohibited *commercial* use in C-1/C-2/C-3 -> classifies it commercial. §1001 LI permits "any lawful industrial purpose" + "commercial uses permitted in C-1/C-2" (which exclude self-storage), no unlisted-use SE catch-all -> not admissible. |
| Hatboro Borough | LI/HI/HI-MU | conditional | **prohibited** | §27-1402 CLOSED list ("and no other"); "Storage buildings and warehouses" (J) is distinct warehousing, self-storage not named, no unlisted-use SE catch-all -> #58 sweep -> prohibited. |
| Pottstown Borough | HM | conditional | **prohibited** | §338 closed enumerated A-H (H "Warehouse" distinct); §338 Conditional Uses = adult/solid-waste/utility only, no "same general character" catch-all -> #58 sweep -> prohibited. |

Conditional verdicts RETAINED because grounded on an EXPLICIT named catch-all clause (not inference):
- Lansdale I — §405-1503.D SE catch-all "any other trade, industry or use ... no more injurious than those listed."
- Hatfield Twp LI/LIRC — §282-145.U "Any use not listed as a permitted use in any other district ... allowed in the LI ... as a special exception."
- Pottstown FO — §336 conditional catch-all "Uses of the same general character as those listed ... same or lesser impact as determined by Borough Council" (Warehouse/Outdoor storage are listed permitted; self-storage is same general character).

## OPEN judgment calls for coordinator review

### D-ex1 — Hatboro LI/HI/HI-MU: does "Storage buildings and warehouses" name the self-storage cohort?
§27-1402.1.J permits "Storage buildings and warehouses" by-right in a closed list. A self-storage
facility is arguably a "storage building." I demoted to PROHIBITED under the strict #58 sweep (treating
"storage buildings/warehouses" as distribution/goods warehousing, NOT the self-storage cohort). If the
coordinator rules "storage buildings" DOES name the self-storage cohort, these flip to PERMITTED
(by-right). Low armed-impact either way: Hatboro is 0 wealth-gated needles (fails the ≥1.5ac + dt10
HV≥$475k + HHI≥$100k gate regardless of verdict).

### D-ex2 — Souderton LI: "any lawful industrial purpose" residual ambiguity
§1001 grants "any lawful industrial purpose." I read self-storage as a *commercial* use (per the
ordinance's own taxonomy — it names self-storage prohibited in C-1/C-2/C-3) and demoted LI to prohibited.
If the coordinator rules self-storage qualifies as "any lawful industrial purpose" (open grant),
LI would flip to permitted. Low armed-impact: Souderton is 0 wealth-gated needles (6 LI parcels, fail
the size/wealth gate).

## Needle-metric reconciliation (WEALTH-GATED needles, corrected 2026-07-09)
Reported ONLY as wealth-gated needles: self_storage∈{permitted,conditional} AND acres≥1.5 AND dt10
median_home_value≥$475k AND median_HHI≥$100k (NOT raw grounded coverage; NOT the looser score≥70/HNW
gate I used earlier, which over-reported "armed").

**All 8 Session-D corridor munis = 0 wealth-gated needles.** Ring metrics ARE present; this is a true
wealth-gate fail, not missing data — every muni's BEST needle parcel is below the $475k HV floor:
Lansdale max HV $427k · Hatfield Twp $382k · Hatfield Boro $373k · Norristown $295k · Pottstown $283k ·
Bridgeport $270k · Souderton 0 sized. These are the industrial/commercial CORRIDOR towns — real storage
zoning, but NOT wealth pockets. Textbook "industrial WITHOUT wealth-ring = correct no-op" (catch #52 /
needle-vs-coverage). Grounding is still valuable (complete honest coverage; each would arm if a
wealth-ring parcel ever lands), but the needle contribution is **0**.

Montgomery PA wealth-gated needle pool = **197** (89 permitted-tier + 108 conditional-tier), ALL in the
5 pre-grounded wealth towns (Upper Merion 113, Horsham 29, Plymouth 20, Whitemarsh 18, West Conshohocken
17). This batch did not change it. The "N armed" figures in the shared-queue RESOLVED D-rows used the
looser gate and are superseded by this wealth-gated reconciliation.

## Notes
- All Montgomery-PA verdicts use municipality = parcels.city EXACTLY (mixed case, e.g. "Municipality of
  Norristown", "Hatfield Township") — the m.municipality=p.city scoring join is case-sensitive; UPPERCASE
  would silently zero the armed count.
- eCode360 fetch method confirmed: curl + browser-UA (WebFetch 403s). All 5 previously-escalated munis
  auto-fetched + grounded this session.
