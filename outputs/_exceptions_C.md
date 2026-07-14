# Exceptions / Findings — Session C — Fairfield County CT (Batch 1)

county_gis jid `66230887-aabe-4d62-aebb-856939ba77bb`. My file only.

## CRITICAL FINDING — the named targets can't produce wealth-gated needles yet (ring gap)
The instruction named Greenwich, Norwalk, Stamford, Westport, Darien. Reality from the DB:
- **Greenwich, Darien, Stamford, Westport, New Canaan, Wilton are SEPARATE jurisdictions**, NOT
  in the county_gis's 17 towns. And **all have 0 parcel_ring_metrics rows at every drive-time** →
  wealth-gated needle = 0 there regardless of grounding (can't clear the gate w/o ring data).
- **Norwalk IS in county_gis but has 0/21,607 ring coverage** → also 0 needles until ring precompute.
- The instruction's "34,026 clear the wealth gate" = the county_gis jid total (verified). Ring
  coverage is 131,240/192,361 there — but skips Norwalk (and the coastal cities).
→ **ACTION FOR COORDINATOR:** to make the named wealthy targets needle-capable, run the ring-metrics
  precompute on (a) the 6 separate town jids (Greenwich/Darien/Stamford/Westport/New Canaan/Wilton)
  and (b) Norwalk within county_gis. Until then I pivoted to ring-covered wealthy-with-industrial
  county_gis towns.

## GROUNDED THIS BATCH (county_gis, muni-scoped, human_reviewed, catch #42 verified)
| Town | layer | self-storage disposition | wealth-gated needles |
|---|---|---|---|
| **Monroe** | MetroCOG `maps.ctmetro.org/.../Monroe/Monroe_OpenGov/MapServer/14` (Zone) | NAMED special-exception in SB-2 + I-2 (Art.10 schedule); I-1/I-3 prohibited | **21** (I-2) |
| **Newtown** | MapXpress `gis.mapxpress.net/.../Newtown/Active/FeatureServer/23` (Zone_) | NAMED special-exception in M-2A/M-4/M-5; M-1/M-3 prohibited | **1** (M-5; industrial mostly outside wealth ring) |
| **Fairfield** | MetroCOG `maps.ctmetro.org/.../Fairfield/Fairfield_Landuse/MapServer/7` (ZONE) | ABSENT townwide (strict closed-list §2.4.A) → prohibited everywhere | **0** (honest no-op; DI has light-industrial by-right but no self-storage) |

## OPEN / ESCALATE
| # | Town | Blocker | Needed |
|---|---|---|---|
| CF1 | Ridgefield CT | No public zoning-polygon layer — town uses the AxisGIS proprietary viewer (no ArcGIS REST); Tighe&Bond host has only stormwater; WestCOG org has parcels but no zoning. Ordinance: self-storage ABSENT townwide (only "Storage warehouse" special-permit in B-2). | Ridgefield P&Z / WestCOG zoning shapefile OR digitize the zoning-map PDF. Low priority (self-storage near-absent anyway). |

## NOTE
- Newtown I-2 not grounded (code present in layer but not in the Art. V M-series use analysis — unverified; left no-verdict).
- Monroe & Newtown: light_industrial grounded (conditional in Monroe = manufacturing SEP; permitted in Newtown M-zones = by-right) but not a self-storage needle.
- Did NOT touch the 6 separate town jids or the in-app Verifier (frozen).

---
# BATCH 2 (2026-07-14) — 0 new grounded needles; county_gis needle-EXHAUSTED (recon+escalation batch)

**Finding: none of the batch-2 targets can yield wealth-gated needles.** The 6 named targets are
ring-COVERED but NOT wealthy enough — dt10 median HV is all BELOW the $475k gate, so their ≥1.5ac
wealth-gate pool = 0 (industrial-below-wealth-ring no-ops, per the coordinator's own "inside the
wealth ring" qualifier — none are):
  Bethel medHV $398k · Brookfield $366k · Trumbull $394k · Danbury $412k · Shelton $408k · Stratford $302k.
The towns that DO clear the gate (Redding $625k, Weston $888k, Easton $863k) are estate-residential:
- **Weston — NO-OP (confirmed).** Only 2 districts: R-2A + NSC (one 8,000-sf-capped neighborhood retail zone, exterior storage barred). Self-storage absent from closed-list Ch.240 → prohibited townwide.
- **Easton — NO-OP (confirmed).** All-residential (Residence A/B + Floodplain overlay); no commercial/industrial district at all. Self-storage absent (closed-list §1410).

## OPEN / ESCALATE (batch 2)
| # | Town | Blocker | Needed |
|---|---|---|---|
| CF2 | **Redding CT** | REAL GO but geometry-blocked. Redding **SB (Service Business) Zone permits "Self-service storage facility" BY RIGHT** (§4.3.2(a), named; excluded from BC §4.3.3(a)); clears the wealth gate (medHV $625k). BUT no public zoning-polygon REST layer: town CDM Smith service `gis3.cdmsmithgis.com/reddingct` is 404/dead; Redding is WestCOG (not MetroCOG — no folder); WestCOG MapGeo is proprietary; WestCOG Parcels FeatureServer carries no zoning attribute. | Redding SB-zone geometry — town/WestCOG zoning shapefile OR digitize the zoning-map PDF. Then rebind + ground SB self_storage=permitted → real needles (SB parcels ≥1.5ac in the $625k ring). **Highest-value Fairfield unblock.** |

## BATCH-2 BOTTOM LINE FOR COORDINATOR
county_gis groundable wealth-gated needles are **EXHAUSTED** after Batch 1 (Monroe 21 + Newtown 1 = 22). Remaining needle sources are all BLOCKED:
1. **Geometry-blocked GOs:** Redding (SB self-storage by-right, CF2), Ridgefield (CF1) — need town zoning shapefiles.
2. **Ring-precompute-blocked:** the marquee wealthy jids (Greenwich/Stamford/Darien/Westport/New Canaan/Wilton separate jids) + Norwalk (county_gis) — 0 ring metrics.
3. **True no-ops (correct, not gaps):** the 6 sub-$475k towns (Bethel/Brookfield/Trumbull/Danbury/Shelton/Stratford) + Weston + Easton + Fairfield-town.
Recommend Fairfield county_gis moves to a holding state pending (1) a ring-precompute run on the marquee jids+Norwalk and (2) sourcing Redding/Ridgefield zoning geometry. Did NOT grind 0-needle groundings (discipline: industrial-without-wealth-ring = correct no-op, not a gap).

---
# CHESTER PA — Batch 1 (2026-07-14) — 4 towns grounded, +390 wealth-gated needles

PA spatially bound → no rebind. All use tables via eCode360 print-endpoint (curl+UA). catch #38: I-codes confirmed INDUSTRIAL (not Institutional) in each town.
- West Goshen Twp: self_storage PERMITTED by right (NAMED "Miniwarehouse or self-storage facility") in I-1/I-2/I-3/I-2-R/I-C/MPD; C-4/C-5 prohibited. **+207 needles.**
- New Garden Twp: self_storage PERMITTED by right (NAMED §200-45.A(17)) in C/I; H/C/BP/ADZ prohibited. **+37.**
- East Goshen Twp: self_storage CONDITIONAL (NAMED §240-19C(2)) in I-1; BP EXPRESSLY prohibited (§240-21C(2)(b)); I-2/C-* absent. **+19.**
- Uwchlan Twp: self_storage CONDITIONAL in PI/PIC/PCID. **+127.**

## TRANSPARENCY FLAG (not a blocker — coordinator review)
CF-UW: **Uwchlan's 127 needles rest on the warehouse⇒conditional CONVENTION, not a named self-storage use.** Self-storage is UNNAMED townwide in Ch.265; PI/PIC/PCID permit "warehousing" by-right and the code is NOT a closed list (open conditional catch-all §509.5.f), so self_storage is reachable as a conditional use per the blessed convention (conf 0.65). This is weaker grounding than the other 3 towns (which name self-storage explicitly). Flagging for visibility; verdicts are conditional (not permitted), so they surface as conditional needles.

---
# CHESTER PA — Batch 2 (2026-07-14) — 4 towns grounded, +87 wealth-gated needles

PA spatially bound → no rebind; eCode360 print-endpoint. Discovery ranking (excl. 7 grounded).
- Upper Uwchlan Twp: LI self_storage PERMITTED by right (NAMED §200-44.A(10)); PI PROHIBITED (NB-Twp J25 — self-storage named only in LI under closed list, convention does NOT make PI conditional); C1/C3 prohibited. **+30 (LI)**.
- East Marlborough Twp: LI self_storage CONDITIONAL (NAMED §450-1002.B(12)); ESI=Institutional (catch #38, not industrial); MU/WMU/LMU/C-2 prohibited. **+33 (LI)**.
- Charlestown Twp: I/O self_storage CONDITIONAL (NAMED §27-1002.1.A(3)(h)); **"I" map code = INSTITUTIONAL (catch #38, §27-802 — NOT industrial)**; LI/B (misleading name, no storage)/B-1/H/NC prohibited. **+21 (I/O)**.
- West Whiteland Twp: I-1 self_storage CONDITIONAL (see CF-WW); TC/NC/O-L/O-R/O-C office/retail prohibited (Exton commercial core = correct no-op). **+3 (I-1)**.

## TRANSPARENCY FLAG (coordinator review)
CF-WW: **West Whiteland's 3 I-1 needles rest on the warehouse⇒conditional CONVENTION, not a named self-storage use.** Ch.325 has NO named self-storage anywhere; I-1 permits warehouse + light-mfg by right (§325-18B(3)/(4)) and does not exclude self-storage → conditional per the blessed convention (conf 0.65). Small (3 parcels). Same class as batch-1 CF-UW.

## CATCHES that PREVENTED false needles (kept honest)
- Charlestown "I" = Institutional (not Industrial) → the 4 wealth-ring "I" parcels correctly NOT grounded as a needle (catch #38).
- East Marlborough "ESI" = Educational/Scientific/Institutional → not an industrial needle (catch #38).
- Upper Uwchlan "PI" → prohibited (NOT convention-conditional) because self-storage is named only in LI under a closed list (NB-Twp J25 rule) — avoided ~15 false convention-needles.
