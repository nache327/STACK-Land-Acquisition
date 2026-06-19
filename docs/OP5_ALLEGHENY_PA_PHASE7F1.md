# Op-5 Allegheny PA Phase 7F.1 — county parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Wave 5 final-wedge dispatch. Closes the 25-muni wedge cohort.
**Verdict:** **DB-LEVEL IN FLIGHT.** Allegheny County, PA jurisdiction `2a6a5d52-58c4-4e36-a5bd-45fc8d3e76c7` registered. Parcel ingest fetching 580,039 features from WPRDC OPENDATA Parcels at PR commit time. 130 Allegheny muni labels pre-loaded for in-script city derivation.
**Predecessors:** Diagnostic acquisition spec (`docs/ALLEGHENY_PA_ACQUISITION_SPEC.md`) · Phase 7E.1 Oakland pattern (PR #314).

---

## TL;DR

Allegheny County publishes parcels at the WPRDC stack — 580,039 features. **Parcels layer carries MUNICODE (integer) only — no city/municipality string.** Adapter fetches all 130 Allegheny muni boundaries at fire start, builds MUNICODE→LABEL dict, joins in-script during ingest. LABEL is title-case + Borough/Township suffix + apostrophe-stripped per Allegheny convention.

This is the final wedge wave. After Allegheny closes, the campaign trajectory locks to **~46 operational jurisdictions**.

## What's in this PR

- `backend/scripts/ingest_allegheny_pa_parcels.py` (new) — county parcel ingest with in-script MUNICODE→LABEL join + jurisdiction registration
- `backend/data/allegheny_pa_zoning_directory.json` (new) — 5-muni directory (all LOW Path B ordinance-derived per orchestrator's d7a0c7a)
- `docs/OP5_ALLEGHENY_PA_PHASE7F1.md` (this file)

## Source — Allegheny County WPRDC OPENDATA

```
https://gisdata.alleghenycounty.us/arcgis/rest/services/
OPENDATA/Parcels/MapServer/0
```

- Publisher: **Allegheny County / WPRDC (Western Pennsylvania Regional Data Center)**
- Layer: `Parcel`
- SR: PA State Plane South (wkid=102729); server-side reprojected via `outSR=4326`
- maxRecordCount: 1,000 (smaller than other waves — paginated more aggressively)
- Total: **580,039 parcels**
- Fields: OBJECTID, PIN, MAPBLOCKLOT, MUNICODE, CALCACREAGE + metadata

## Muni boundary join (Pierce-Task-E-style)

Companion source for city derivation:
```
https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services/
AlleghenyCountyMunicipalBoundaries/FeatureServer/0
```

130 muni rows fetched once at fire start. Adapter builds `MUNICODE → LABEL` dict in memory, used during `_map_row` to set `parcels.city`. No spatial join required (parcels source already carries MUNICODE integer key).

## PA case discipline — title-case + suffix + apostrophe-stripped

**Critical pattern flag**: Allegheny LABEL field carries the canonical format:

| MUNICODE | NAME (raw) | LABEL (canonical) |
|---------:|------------|-------------------|
| 868 | FOX CHAPEL | **Fox Chapel Borough** |
| 931 | O'HARA | **O Hara Township** (apostrophe → space) |
| 801 | ASPINWALL | **Aspinwall Borough** |
| 851 | SEWICKLEY | **Sewickley Borough** |
| 869 | SEWICKLEY HEIGHTS | **Sewickley Heights Borough** |

Per Master's Wave 5 dispatch: **PRESERVE LABEL VERBATIM**. Don't strip suffix. Don't reinsert apostrophes. Phase 7F.2 per-muni registration uses exact-equality `city='Fox Chapel Borough'` joins.

Different from:
- MN title-case ('Edina') — no suffix
- WA mixed ('Bellevue') — no suffix
- AZ UPPERCASE-bare ('SCOTTSDALE') — no suffix
- MI UPPERCASE + political-entity prefix ('CITY OF BIRMINGHAM')

## Pre-flight check ✓

```
Muni map loaded: 130 codes
  868: 'Fox Chapel Borough'
  931: 'O Hara Township'
  801: 'Aspinwall Borough'
  851: 'Sewickley Borough'
  869: 'Sewickley Heights Borough'

features fetched : 1,000
geom_skipped     : 0
apn_skipped      : 1
mappable rows    : 999
distinct city in sample: 107 (Penn Hills 45, Mount Lebanon Twp 25, …)

5 wealth-band target munis in 1k sample:
  Fox Chapel Borough            9
  O Hara Township               9
  Aspinwall Borough             3
  Sewickley Borough             2
  Sewickley Heights Borough     1
```

All 5 wealth-band targets present in first 1k sample. Pipeline shape validated.

## Fire process

Started 2026-06-19T13:48:09Z. Process PID 89084, `nohup ... & disown`. Log `/tmp/allegheny_parcels_fire.log`. Estimated wall-clock: 1-2h based on Hennepin's 448k throughput at clean rate.

## Class C / Zoning verdict — Class B/manual

Per acquisition spec: **no public countywide municipal zoning FeatureServer found**. Each muni likely needs PDF-source or per-borough ordinance work. Orchestrator's d7a0c7a pre-stage (26 rows total) covers all 5 munis at Path B — apply-time authoring.

## Next dispatch — sequence within Allegheny wave

1. **Parcel ingest completes** (~1-2h)
2. **Inline bbox UPDATE** fires automatically
3. **Phase 7F.2** per-muni registration via UPDATE jurisdiction_id pattern:
   - Fox Chapel Borough (jid TBD by registration)
   - O Hara Township
   - Aspinwall Borough
   - Sewickley Borough
   - Sewickley Heights Borough
4. **Phase 7F.3** per-muni zoning ingest (all 5 LOW Path B):
   - Orchestrator authors at apply-time from ordinance (no Lane A polygon authoring required)
   - Sewickley Heights flagged for Ordinance No. 294 PDF parsing per orchestrator's d7a0c7a notes

## Expected outcome

**+5 → count 46 (WEDGE COHORT COMPLETE)**

After Allegheny closes, the 25-muni wedge plan is fully executed:
- WA (5 ops): Bellevue + Mercer + Bainbridge + Mill Creek + Gig Harbor
- Hennepin (4 + 1 deferred): Edina + Plymouth + Eden Prairie + Minnetonka + Wayzata (Option B GeoPDF deferred)
- Fairfield (2 + 3 deferred): Stamford + Greenwich + Westport/Darien/New Canaan (Vessel Tech token-gated)
- Maricopa (5): Scottsdale + Paradise Valley + Cave Creek + Fountain Hills + Carefree
- Oakland MI (5): Birmingham + Beverly Hills + Bloomfield Hills + Bloomfield Twp + Franklin
- Allegheny (5): Fox Chapel + O Hara + Aspinwall + Sewickley + Sewickley Heights

Plus existing operational base (~20). Theoretical ceiling **46-49** depending on deferred resolution.

## Hard rules honored

- raw_attributes preserved verbatim, bounded passthrough (Norfolk gate)
- LABEL preserved verbatim (PA case discipline: title-case + suffix + apostrophe-stripped)
- No zoning data written (Phase 7F.3 separate)
- Inline jurisdictions.bbox UPDATE (PR #261 codified)
- Skip ROLLBACK preflight at scale (PR #253)
- `--start-offset` resume flag for silent-hang recovery
- One refresh per phase

## Sibling waves status

- **Maricopa**: PV (#310) + 4-muni (#313) → 5/5 registered, Scottsdale 7B.3 spatial backfill in flight
- **Fairfield**: Stamford applied + Greenwich (#311) 5/5 → 2/5 ops
- **Oakland MI**: parcel ingest 490k completing (Phase 7E.1, ~99.998% done — last batch landing)
- **Allegheny PA**: parcel ingest in flight (this PR)

## Vessel Tech informational note

Per Master 2026-06-19: Diagnostic PR #312 verdict to pursue B2B/tokened access for KX6JS016gWFWiY6Y org (47 deduped zoning Feature Service titles, 32 CT + 15 NJ). 58-list overlap: Mount Laurel NJ + Westport CT + New Canaan CT. Potential 6th wave AFTER wedge cohort closes. Bookmarked.
