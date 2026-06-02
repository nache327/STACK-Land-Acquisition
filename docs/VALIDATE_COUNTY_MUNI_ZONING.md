# Validation runbook — county→municipality zoning fix (Phase 1A/1B)

Use this to prove the fix works against the real DB (Supabase) + deployed pipeline
before building further phases on top of it. Branch: `feat/county-municipality-zoning-fix`.

## 0. Apply migration 0038 (additive; safe)

```
alembic upgrade head   # adds municipality_aliases table; no behavior change yet
```
Confirm: `\dt municipality_aliases` exists; head revision is `0038`.

## 1. Run a Salt Lake County ingest through the deployed pipeline

Submit "Salt Lake County, UT" (force a fresh run so the new county-only stages
fire). Watch the job `progress` for the new stages in order:

```
... zoning_backfill → sibling_zoning_backfill → crosswalk_cities → zone_matrix_bootstrap ...
```

`sibling_zoning_backfill` is skipped (correctly) only if zero parcels are unzoned.

## 2. zoning_code coverage jumped

```sql
SELECT
  COUNT(*) AS total,
  COUNT(zoning_code) AS with_code,
  ROUND(100.0 * COUNT(zoning_code) / NULLIF(COUNT(*),0), 1) AS pct_coded
FROM parcels
WHERE jurisdiction_id = :slco_id;
```
Expect `pct_coded` to rise from ~0 toward the share covered by sibling cities.

## 3. zone_use_matrix has per-city (municipality-tagged) rows

```sql
SELECT municipality, COUNT(*) AS rows, classification_source
FROM zone_use_matrix
WHERE jurisdiction_id = :slco_id AND deleted_at IS NULL
GROUP BY municipality, classification_source
ORDER BY municipality NULLS FIRST;
```
Expect rows for multiple cities (Sandy, Draper, …), not just `municipality IS NULL`.
`classification_source` should show `crosswalk` (copied from siblings) and
`inherited_pending` (stub-seeded cities with no sibling matrix).

## 4. Parcels resolve to their CITY-SPECIFIC verdict (the core proof)

For a handful of parcels in different cities, confirm the LATERAL join picks the
city row over the county default:

```sql
SELECT p.id, p.city, p.zoning_code, zum.municipality, zum.self_storage
FROM parcels p
LEFT JOIN LATERAL (
    SELECT municipality, self_storage
      FROM zone_use_matrix
     WHERE jurisdiction_id = p.jurisdiction_id
       AND zone_code = p.zoning_code
       AND (municipality IS NULL OR municipality = p.city)
       AND deleted_at IS NULL
     ORDER BY (municipality IS NULL) ASC
     LIMIT 1
) zum ON true
WHERE p.jurisdiction_id = :slco_id AND p.zoning_code IS NOT NULL
LIMIT 25;
```
Expect `zum.municipality = p.city` on cities that have a matrix (not NULL).

**Cross-municipality bleed check:** find the same `zone_code` used in two cities and
confirm each parcel gets its OWN city's verdict, not the neighbor's:

```sql
SELECT p.city, p.zoning_code, zum.municipality, zum.self_storage, COUNT(*)
FROM parcels p
LEFT JOIN LATERAL ( /* same LATERAL as above */
    SELECT municipality, self_storage FROM zone_use_matrix
     WHERE jurisdiction_id = p.jurisdiction_id AND zone_code = p.zoning_code
       AND (municipality IS NULL OR municipality = p.city) AND deleted_at IS NULL
     ORDER BY (municipality IS NULL) ASC LIMIT 1
) zum ON true
WHERE p.jurisdiction_id = :slco_id
  AND p.zoning_code IN (SELECT zoning_code FROM parcels
                        WHERE jurisdiction_id = :slco_id AND zoning_code IS NOT NULL
                        GROUP BY zoning_code HAVING COUNT(DISTINCT city) > 1)
GROUP BY p.city, p.zoning_code, zum.municipality, zum.self_storage
ORDER BY p.zoning_code, p.city
LIMIT 40;
```

## 5. Dashboard / verifier smoke test

- Open the Salt Lake County dashboard: Hot Deals / Worth a Look should now surface
  matches (non-zero), where before they were empty.
- Open the zoning verifier for the county: the City column appears, rows group by
  zone with per-city entries, and editing a city row scopes the override to that
  `?municipality=`.

## 6. Unmatched cities (what still needs attention)

The `crosswalk_cities` stage logs `unmatched_cities`. Any city there has parcels but
no sibling jurisdiction matched by name — candidates for a `municipality_aliases`
row (Phase 1C will auto-propose these). Until then those cities show
`inherited_pending` stubs (honest "unclear"), not fabricated verdicts.
```
