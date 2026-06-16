# Puget Sound Wealth-Muni Citation Directory (Pre-Stage)

**Date:** 2026-06-16
**Purpose:** Pre-stage citation URLs for upcoming Pierce + Snohomish + Kitsap per-muni matrix sprints after Lane A's Phase 6B.2 PIVOT lands per-muni jurisdiction registration.
**Pattern:** Same shape as PR #248 (King WA wealth-muni pre-stage) and PR #235 (Westchester pre-stage). Becomes part of the standard pre-sprint habit Master codified for the new 20-30 muni-sprint normal.

---

## Why pre-stage NOW

Per Master's 2026-06-16 plan-revision: King WA's county-level coverage-math failure forced a structural pivot. Bellevue + Mercer Island re-register as their own jurisdictions; Pierce / Snohomish / Kitsap follow the same per-muni pattern. Each wealth-muni becomes its own small matrix sprint (~1-3h per muni per Diagnostic PR #247 forecast).

URLs are **deterministic** (independent of Lane A's adapter shape — same as PR #248 Bellevue/Mercer URLs held through Phase 6A.2). 30-45 min spent now saves ~30 min/muni on each sprint's hot path.

---

## Wealth-muni roster (3 target munis)

| target | county | est. parcels | platform | URL | chapter |
|---|---|---:|---|---|---|
| **Gig Harbor** | Pierce | small-medium (~7-9k per Tier 4 forecast) | Code Publishing | https://www.codepublishing.com/WA/GigHarbor/ | Title 17 Zoning; Chapter 17.14 permitted uses by district |
| **Mukilteo** | Snohomish | small (~8-10k) | Code Publishing | https://www.codepublishing.com/WA/Mukilteo/ | Title 17 Zoning (multi-chapter); Chapter 17.20 districts; Title 17B Shoreline |
| **Mill Creek** | Snohomish (alt to Mukilteo) | small (~7k) | Code Publishing | https://www.codepublishing.com/WA/MillCreek/ | Title 17 Zoning |
| **Bainbridge Island** | Kitsap | small-medium (~12-15k) | Code Publishing | https://www.codepublishing.com/WA/BainbridgeIsland/html/BainbridgeIsland18/BainbridgeIsland18.html | Title 18 Zoning; Chapter 18.06 districts; Chapter 18.09 use regulations |

**All 4 munis on Code Publishing platform.** Pattern continues from PR #258 (Contra Costa) where Code Publishing was the dominant CA suburban platform. WA + CA both lean heavily on Code Publishing for suburban/wealth-muni zoning.

---

## Note on Snohomish target ambiguity

Master's dispatch flagged "Mukilteo OR Mill Creek" — both are Snohomish wealth-bracket munis. Lane A's per-muni ingest will determine which one gets registered first. Pre-stage covers BOTH so either can fire as the next sprint without further research delay.

---

## Citation-construction pattern (PR #234 / PR #240 / PR #258 / PR #266 precedent)

```python
citations = [
    {
        "section": f"{prod_city_value} Municipal Code Title 17 (or 18) — General Use Provisions",
        "quote": "Uses not specifically listed as permitted in a district's "
                 "use-table / permitted-use chart are prohibited "
                 "(WA municipal default-prohibition pattern).",
        "url": ordinance_url,
    },
    {
        "section": f"{prod_city_value} Municipal Code — Zone {zone_code} District Use Provisions",
        "quote": f"Self-storage facility, mini-warehouse, light industrial, and "
                 f"luxury garage condominium uses are not enumerated in the "
                 f"{zone_code} district's permitted-use chart.",
        "url": ordinance_url,
    },
]
```

Same shape as King WA matrix sprint (PR #266). WA municipal default-prohibition language; Code Publishing platform URLs.

---

## Matrix-sprint follow-up checklist (when Lane A's per-muni ingest lands)

1. **Re-pull** `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={muni-jurisdiction-id}` for the newly registered muni
2. **Verify per-muni codes** against the muni's actual use-table (Code Publishing has searchable HTML)
3. **Bias against unclear** per Master's brief — `prohibited × 4` catchall liberally
4. **`municipality` matches `prod_city_value` EXACTLY** — WA case discipline (PR #264 lesson; "Gig Harbor" not "GIG HARBOR")
5. **Spot-check 10%** before applying
6. **ONE refresh** at sprint end
7. **Expected**: each muni flips operational individually if its own parcel-coverage clears 70% gate (per-muni shape per Master's plan revision)

---

## Known unknowns / risks

- **Per-muni jurisdiction registration shape**: Lane A's adapter may register each muni differently (e.g., separate `jurisdiction_id` per muni vs nested under county). Verify the registration shape before authoring matrix rows.
- **WA case discipline**: per PR #264 lesson, `prod_city_value` may be UPPERCASE in some adapter outputs. Spot-verify before authoring.
- **Code Publishing platform stability**: same as eCode360's anti-bot 403 pattern — WebFetch may fail; humans/operators can browse the URLs fine. Use WebSearch as the verification primitive (this pre-stage validated 4/4 URLs cleanly via WebSearch).
- **Wealth-muni LI/industrial codes**: King WA Bellevue surfaced an LI (Light Industrial) code with 61 parcels — Bergen catchall × 4 may be overly conservative for genuine industrial zones. Flag for Somerset-style cleanup follow-up if industrial codes appear.

---

## Status

**Pre-stage. Lane A's Phase 6B.2 PIVOT (per-muni re-jurisdictioning + ingest) has not yet landed; this directory captures the verified URLs so the matrix sprints can move faster when it does.**

When Lane A's per-muni adapter lands:
- Gig Harbor sprint fires (~1-3h per Diagnostic PR #247 estimate)
- Mukilteo OR Mill Creek sprint fires (Master / Lane A picks which)
- Bainbridge Island sprint fires

Each adds ~1 to operational count per Tier 4 forecast (assuming per-muni cov clears 70% gate, which is the explicit point of the per-muni structural pivot).
