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
