# Target Markets — 58 Wealth Pockets (KMZ) + Priority Queue

**CANONICAL — Nache-approved priority, 2026-06-16 (count reconciled 57 → 58).** This doc is the
single source of truth for the target universe (catch #24). The +1 vs the original KMZ rollup is the
**Burlington NJ wealth-tail (Moorestown / Medford / Mount Laurel), added to Phase 1**.

## Approved priority order — 58 wealth pockets
| Phase | States / metros | Polys | Why |
|---|---|---|---|
| **1** (now — NJ work) | NJ: Bergen, Morris, Somerset, Hunterdon, Monmouth, **Burlington** | 7 | Pilot region; Burlington wealth-tail (Moorestown/Medford/Mount Laurel) added |
| **2** (NJ-adjacent, same lat band) | Westchester NY, Fairfield CT, Nassau NY | 11 | Same drive-time catchment as NJ, ~1hr away |
| **3** (DC / Mid-Atlantic) | Loudoun VA, Fairfax VA, Montgomery MD, Howard MD, Montgomery PA | 8 | High polygon density, single regional team |
| **4** (Boston + Chicago North Shore) | Middlesex MA, Norfolk MA, Lake IL, Cook IL, DuPage IL | 10 | Two large metros; independent of NE-Corridor pipeline |
| **5** (South + Mountain West) | Williamson TN, Fulton GA, Mecklenburg NC, Wake NC, Douglas/Arapahoe CO | 10 | Growth markets, faster entitlement |
| **6** (Western + outliers) | Maricopa AZ, King WA, Multnomah OR, Hennepin MN, Oakland MI, Allegheny PA, Salt Lake UT, Contra Costa CA, Miami-Dade FL | 12 | One-offs; finish the map |
| | | **58** | |

**Coverage column** (below): `operational_readiness` / `parcel_zoning_code_coverage_pct` from Adam's May-31 close audit. "— not ingested" = not in that audit.

**Footprint.** 58 polygons · ~22 metros · ~17 states. Northeast Corridor is the heaviest cluster.

---

> The phase tables below predate the 2026-06-16 reconciliation and are kept for the per-county status
> detail; where they disagree with the approved order above (Burlington in Phase 1; Plymouth MA /
> Jefferson CO / Summit UT folded out of the named lists), **the approved table is authoritative.**

---

## Priority queue (the ordering you asked for)

Polygon-density-first, NJ-first per the pilot. Phase totals as stated in the source.

### Phase 1 — NJ (pilot site, Adam active) · 7 polygons
| County | Centers | Status (May-31 audit) |
|---|---|---|
| Bergen, NJ | Saddle River | partial · 3.1% |
| Morris, NJ | (Short Hills band) | partial · 0% |
| Somerset, NJ | — | **operational** · 100% |
| Hunterdon, NJ | — | partial · 0% |
| Monmouth, NJ | Marlboro, Holmdel | partial · 5.7% |
| **Burlington, NJ** | **Moorestown, Medford, Mount Laurel** | ingested + ringed (174,852 parcels); wealth-tail munis UNVERDICTED (0 per-muni rows) — verdict pass pending |

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

## Count reconciliation — RESOLVED 2026-06-16

The count is **58 polygons** (Nache-approved, see the table at the top). The original "57 vs 58 ±1"
ambiguity is resolved: the +1 is the **Burlington NJ wealth-tail (Moorestown / Medford / Mount Laurel),
now in Phase 1**. Phase totals: 1=7, 2=11, 3=8, 4=10, 5=10, 6=12 → **58**. The "parse the raw KMZ"
TODO is superseded by the approved priority table; treat that table as canonical.
