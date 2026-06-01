# Target Markets — 57 Wealth Pockets (KMZ) + Priority Queue

**Source.** A KMZ map of **57 wealth-pocket polygons** across the US, with a coworker analysis (geographic rollup + 6-phase priority queue). Recorded here 2026-06-01 so it stops living only in chat. The KMZ polygon count (57) is authoritative; see the [count reconciliation](#count-reconciliation) note for a +1 discrepancy in the prose rollup.

**Coverage column.** `operational_readiness` / `parcel_zoning_code_coverage_pct` are pulled from Adam's May-31 close audit (`backend/tmp/audit_may31_close.json`, on `origin/main`). "— not ingested" = the county does not appear in that audit at all.

**Footprint.** 57 polygons · 22 distinct metros · ~17 states. Northeast Corridor is the heaviest cluster (NY metro + NJ = ~17 polygons). The strategy has a real second half beyond the East Coast (Detroit, Twin Cities, Phoenix, Raleigh, Charlotte, Miami, Seattle, Portland, SF Bay, Park City).

---

## Priority queue (the ordering you asked for)

Polygon-density-first, NJ-first per the pilot. Phase totals as stated in the source.

### Phase 1 — NJ (pilot site, Adam active) · 6 polygons
| County | Centers | Status (May-31 audit) |
|---|---|---|
| Bergen, NJ | Saddle River | partial · 3.1% |
| Morris, NJ | (Short Hills band) | partial · 0% |
| Somerset, NJ | — | **operational** · 100% |
| Hunterdon, NJ | — | partial · 0% |
| Monmouth, NJ | Marlboro, Holmdel | partial · 5.7% |

### Phase 2 — NJ-adjacent, same lat band (~1hr drive) · 11 polygons
| County | Centers | Status |
|---|---|---|
| Westchester, NY | Scarsdale, Rye | partial · 0% (ingest retry pending) |
| Fairfield, CT | Greenwich | partial · 0% (ingest retry pending) |
| Nassau, NY (Long Island) | Garden City | partial · 0% (ingest retry pending) |

> **Phase-2 gate:** these three are the largest single chunk (11 polygons, ~19% of the map) and are blocked on the large-county ingest plateau (see B8) + zoning-depth. Open question for Adam: does the per-city pattern + a NY/CT NJDCA-equivalent (Westchester/Nassau/Suffolk publish municipal ordinances) close the depth gap? If yes, Phase 2 runs at NJ velocity; if no, it needs a structural sprint first (+1–2 wk).

### Phase 3 — DC / Mid-Atlantic (high density, half-done) · 8 polygons
| County | Centers | Status |
|---|---|---|
| Loudoun, VA | Great Falls | partial · 100% (partial by design) |
| Fairfax, VA | McLean | **operational** · 99.9% |
| Montgomery, MD | Bethesda, Potomac | **operational** · 95.3% |
| Howard, MD | — | **operational** · 91.5% |
| Montgomery, PA | Main Line (Philly suburb) | partial · 2.2% |

> **Tactical reorder worth considering:** Fairfax/Montgomery MD/Howard are already operational. Finishing Montgomery PA (+ verifying Loudoun) is low marginal cost — could interleave into Phase 1 to close the corridor, lifting Phase 1 from 6 → ~9 polygons.

### Phase 4 — Boston + Chicago North Shore · 10 polygons
| County | Centers | Status |
|---|---|---|
| Middlesex, MA | Weston, Newton | partial · 92.3% |
| Norfolk, MA | Wellesley | partial · 74.9% (gaps: high-unclear self-storage + no zoning polygons) |
| Plymouth, MA | Hingham | — not ingested |
| Lake, IL | Lake Forest, Highland Park | **operational** · 100% |
| Cook, IL | Winnetka | not_loaded · 0% |
| DuPage, IL | Hinsdale | partial · 0% |

### Phase 5 — South + Mountain West (growth markets, faster entitlement) · 10 polygons
| County | Centers | Status |
|---|---|---|
| Williamson, TN | Brentwood, Franklin | not_loaded · 0% |
| Fulton, GA | Sandy Springs, Buckhead | partial · 0% |
| Mecklenburg, NC | South Charlotte | partial · 0% |
| Wake, NC | Cary, N Raleigh | partial · 0% |
| Douglas, CO | Highlands Ranch | partial · 0% |
| Arapahoe, CO | Cherry Hills | partial · 0% |
| Jefferson, CO | Golden | — not ingested |

### Phase 6 — Western + outliers (one-offs, finish the map) · ~12 polygons
| County | Centers | Status |
|---|---|---|
| Maricopa, AZ | Scottsdale, Paradise Valley | — not ingested |
| King, WA | Bellevue, Mercer Island | — not ingested |
| Multnomah / Clackamas, OR | Lake Oswego | — not ingested |
| Hennepin, MN | Edina, Wayzata | — not ingested |
| Oakland, MI | Birmingham, Bloomfield Hills | — not ingested |
| Allegheny, PA | Fox Chapel | — not ingested |
| Salt Lake / Summit, UT | Park City corridor | **see note** |
| Contra Costa, CA | Lafayette, Walnut Creek | — not ingested |
| Miami-Dade, FL | Pinecrest | — not ingested |

> **Park City caveat:** the SLCo work (Salt Lake City operational, ~397k parcels) covers the *western* pockets (Holladay-style). The eastern wealth corridor — **Park City / Deer Valley / Promontory — is in Summit County**, a separate ingest the SLCo work does not activate. Cheap follow-up if a deal surfaces.

---

## Strategic anchor

- **Phase 1–3 (≈25–33 polygons, NE + Mid-Atlantic) is enough to physically fit the 115-site plan** at the ~4.6 sites/polygon average. Phases 4–6 are expansion runway, not infrastructure dependency.
- NJ activation is high-leverage but only ~11% of the universe (6 polygons), not the dominant share.
- NY metro (11 polygons / ~19%) is the structural-zoning-depth decision point — resolve the Phase-2 gate above before committing.

## Coverage scorecard (audit-grounded)

- **Operational now:** Somerset NJ, Fairfax VA, Montgomery MD, Howard MD, Lake IL, Salt Lake City UT, Allentown PA. (~7 polygons live)
- **Partial / needs matrix or coverage work:** Bergen/Morris/Monmouth/Hunterdon NJ, Westchester/Nassau NY, Fairfield CT, Loudoun VA, Montgomery PA, Middlesex/Norfolk MA, DuPage IL, Fulton GA, Mecklenburg/Wake NC, Douglas/Arapahoe CO.
- **Not loaded / not ingested:** Cook IL, Williamson TN, Plymouth MA, Jefferson CO, Oakland MI, Hennepin MN, Maricopa AZ, Allegheny PA, King WA, Multnomah/Clackamas OR, Contra Costa CA, Miami-Dade FL, Summit UT.

## Count reconciliation

The KMZ is **57 polygons** (authoritative). The prose geographic rollup sums to **58** (likely one double-counted polygon — e.g., a Hinsdale-type pocket split across Cook/DuPage). The phase queue as written totals 57 (Phase 6 stated as 12; the county list above enumerates 13 — same ±1 ambiguity). Treat metro-level counts as ±1 until reconciled against the raw KMZ. **TODO:** parse the KMZ directly to get the exact 57 polygon names + centroids and replace the representative-center estimates here.
