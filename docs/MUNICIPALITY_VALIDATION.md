# Municipality operational validation

When a new municipality (or county-with-municipalities) is ingested,
this is the validation workflow that tells the operator whether it's
ready for sales conversations. Read-only primitives; no mutation.

Backed by `/api/jurisdictions/{id}/_municipalities-health` and
`scripts/municipality_health.py`.

## Trustworthiness bands

The classifier returns one of five labels per muni. The dashboard
filters by label; sales gates on `operational`.

| Band | Meaning | Operator action |
|---|---|---|
| `operational` | All thresholds met. Safe to surface to sales. | Use. |
| `partial` | Usable for general browsing but matrix-coverage or orphan-code gaps mean some parcels won't match buy-box filters | Acceptable; flag specific gaps. |
| `degraded` | Real flaws — duplicate polygons, too-few parcels, low zoning coverage | Investigate; consider re-ingest. |
| `broken` | Spatial join failed or districts cover the wrong location | Do NOT surface; re-ingest required. |
| `empty` | No parcels and no districts | Ingest hasn't started. |

## Operational thresholds

| Threshold | Default | Demote at |
|---|---:|---|
| Min parcel count | 50 | <50 → degraded |
| Parcel zoning-code rate (operational) | 80% | <80% → partial |
| Parcel zoning-code rate (partial) | 50% | <50% → degraded |
| Parcel zoning-code rate (broken) | 10% | <10% → broken |
| Parcel zone-class rate (partial) | 30% | <30% → partial |
| Min distinct districts | 3 | <3 → degraded |
| Max district overlap-sample ratio | 5% | >5% → degraded |
| Min parcel↔district extent overlap | 50% | <50% → broken |

`broken` outranks `degraded` outranks `partial`. Each band's `gaps`
list explains exactly which thresholds failed.

## Onboarding workflow

```bash
# 1. After ingest, look at every muni at once
python scripts/municipality_health.py <jurisdiction_id> --only-broken

# 2. If any broken, drill down
python scripts/municipality_health.py <jurisdiction_id> --muni "New Milford"

# 3. For root cause on a broken muni, the lower-level lenses still apply:
#    - `/_sources/{src_id}/_spatial-check` shows which source covered the wrong location
#    - `/_spatial-audit` shows the source × verdict cross-tab (iter 1)
#    - `/_score-health` shows whether re-scoring would shift the queue (iter 3)

# 4. Re-ingest if zoning_districts are wrong; re-run discovery if the right
#    source was never picked. Both are existing endpoints — this workflow
#    just tells you WHEN to use them.
```

## Anomaly signals decoded

| Symptom | Likely cause | Likely fix |
|---|---|---|
| `only N% of parcels carry zoning_code` (broken) | Zoning ingest hit wrong CRS, geometries don't intersect parcels | Re-run discovery + ingest; check `_spatial-check` verdict on the verified source |
| `parcel and district extents overlap only X%` (broken) | Wrong-jurisdiction source was verified (e.g. CT layer in NJ county) | Reject the source, re-discover |
| `M zoning_district rows have invalid PostGIS geometry` (broken) | Source layer published self-intersecting polygons | `make_valid` runs on ingest; this means it failed — inspect raw_attributes |
| `X% of sampled districts overlap a sibling` (degraded) | Two ingests of the same data into the same jurisdiction | Drop one set of districts (or one source); rerun ingest with `replace=true` |
| `only N parcels` (degraded) | Per-town parcel filter is dropping rows; or `parcels.city` mismatched | Check `parcels.city` distribution; backfill via `scripts/backfill_parcel_city.py` if NJ-style |
| `N zone codes on parcels not present on any district` (partial) | `parcel.zoning_code` was populated from parcel source (Regrid / county) instead of via spatial join | Either ingest authoritative zoning_districts, or accept the gap — matrix bind needs district codes |
| `only N distinct district polygons` (degraded) | Layer ingested fewer districts than published; downloader stopped early | Re-run ingest with debug logs; check ArcGIS pagination |

## What the framework does NOT promise

- **Source freshness.** We don't probe upstream extent on every read — that's
  the `_spatial-audit` lens (iter 1). Run it separately when investigating.
- **Matrix correctness.** `zone_class` coverage signals matrix bootstrap
  progress; the framework doesn't validate the matrix's semantic accuracy.
- **Per-parcel correctness.** The classifier looks at population-level
  ratios. A muni at 90% zoning coverage can still have specific outlier
  parcels; that's a per-record investigation, not a muni-band signal.

## Cost

Per jurisdiction, one call evaluates every muni in:
- 1 distinct-cities scan over `parcels` (indexed)
- 1 aggregate per muni over `parcels`
- 1 envelope-bounded count over `zoning_districts` per muni
- 1 bounded-sample overlap-pair count per muni (`OVERLAP_SAMPLE_LIMIT=200`)
- 1 orphan-zone-code EXCEPT query per muni

For Bergen (~70 munis, ~700k parcels): ~3–5 s end-to-end. Cheap enough for
a dashboard poll.
