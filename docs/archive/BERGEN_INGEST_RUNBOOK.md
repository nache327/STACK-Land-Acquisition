# Bergen Municipal Ingest Runbook

**Date**: 2026-05-16
**Lane**: Discovery + Coverage Expansion
**Purpose**: copy-paste commands for Adam to land each of the operationally-validated Bergen sources end-to-end. Each block is independent; run in any order.

**Prerequisites:**
- `backend/data/zoning_source_tenants.json`, `backend/data/bergen_zoning_directory.json`, `backend/data/nj_mun_code_map.json` are on `origin/main` (cold-merge from this session).
- `backend/scripts/onboard_municipality.py` is on `origin/main` (cold-merge from this session).
- Op-1 hot wiring (per `BERGEN_OP1_HOT_WIRING.md`) is OPTIONAL for these ingests — operator-driven verify still works without it.

**Conventions:**
- `BERGEN=4bf00234-4455-4987-a067-b22ee6b6aa1f`
- `API=https://capable-serenity-production-0d1a.up.railway.app`
- Each muni block is named `# MUNI-{rank} {Name}` so the operator can grep them and run in priority order.

---

## Tier 1 — NJSEA Meadowlands (10 Bergen towns in ONE ingest)

**Source**: `https://services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/20200609_Zoning/FeatureServer/0`
**Publisher**: Rutgers University tenant (Center for Urban Policy Research) — hosting NJ Sports & Exposition Authority Meadowlands District zoning
**Geometry**: 163 polygons, esriGeometryPolygon, WGS84 reprojectable
**Fields**: `MUN_CODE`, `QUALIFIER` (MD/OMD/MD-OMD), `ZONE_CODE` (RRR, EC, LIA, LIB, RA, LDR, CP, …)
**Bergen towns covered (10)**: Carlstadt, East Rutherford, Little Ferry, Lyndhurst, Moonachie, North Arlington, Ridgefield, Rutherford, South Hackensack, Teterboro
**Expected delta**: +10,000–20,000 parcels with zoning_code populated (conservative)

### Option A — single ingest using onboard script (RECOMMENDED)

```bash
# From the Railway container (or local with prod DATABASE_URL):
python -m scripts.onboard_municipality \
  --jurisdiction-id 4bf00234-4455-4987-a067-b22ee6b6aa1f \
  --source-url "https://services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/20200609_Zoning/FeatureServer/0" \
  --where "MUN_CODE LIKE '02%'" \
  --label "NJSEA Meadowlands Zoning (Bergen 10 munis)" \
  --auto-verify
```

The script will:
1. spatial-check the source vs Bergen bbox (expect `verdict: good` since the Meadowlands sits inside Bergen)
2. insert a `zoning_sources` row with `validation_status=pending`, then auto-flip to `verified`
3. invoke `backfill_zoning` with `where=MUN_CODE LIKE '02%'` → 163 polygons → `zoning_districts` → spatial-join to `parcels.zoning_code`
4. report final coverage delta

### Option B — equivalent curl sequence

```bash
# 1. spatial-check
curl -sS "${API}/api/jurisdictions/${BERGEN}/_spatial-check?zoning_url=https%3A//services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/20200609_Zoning/FeatureServer/0"

# 2. seed source via _manual-source (if endpoint exists) OR direct DB upsert via Op-1's _discover-tenant-services (or a fresh _discover-municipal-zoning sweep)
# (Skipped curl shape — Adam should use Option A which handles upsert idempotently.)

# 3. ingest with bbox-filtered backfill
curl -sS -X POST "${API}/api/jurisdictions/${BERGEN}/_backfill-zoning?zoning_url=https%3A//services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/20200609_Zoning/FeatureServer/0&where=MUN_CODE+LIKE+%2702%25%27&replace=false&spatial_join=true"

# 4. verify coverage
curl -sS "${API}/api/admin/coverage" | jq '.[] | select(.county=="Bergen") | {parcel_with_zoning_code_count, parcel_zoning_code_coverage_pct}'
```

---

## Tier 1 — Westwood (Paramus vendor tenant)

**Source**: `https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Westwood_Zoning_2019/FeatureServer/0`
**Publisher**: Same vendor as verified Paramus (auto-grow catalog entry)
**Expected delta**: ~3,300 parcels (full town coverage if service is complete)

### Pre-flight: probe service metadata to confirm shape

```bash
curl -sS "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Westwood_Zoning_2019/FeatureServer/0?f=json" | jq '{name, geometryType, fields: [.fields[] | {name, type}]}'

curl -sS "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Westwood_Zoning_2019/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json"
```

Expected: `esriGeometryPolygon`, ~50-200 features, has a `Zone` / `ZONE_CODE` / `Zoning` field.

### Onboard

```bash
python -m scripts.onboard_municipality \
  --jurisdiction-id 4bf00234-4455-4987-a067-b22ee6b6aa1f \
  --source-url "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Westwood_Zoning_2019/FeatureServer/0" \
  --muni "Westwood" \
  --label "Westwood vendor (Paramus consultant)" \
  --auto-verify
```

---

## Tier 1 — Paramus revision refresh (optional)

**Sources**:
- `https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning_Rev2023/FeatureServer/0` (likely current revision)
- `https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning_Rev2020/FeatureServer/0` (alt revision)

**Why optional**: the existing `Paramus_Zoning` (no rev suffix) is already verified + ingested (8,619 parcels). The revisions may be newer/cleaner; ingest as `replace=true` only if operator confirms the revision is newer.

### Probe both

```bash
for u in Paramus_Zoning Paramus_Zoning_Rev2020 Paramus_Zoning_Rev2023; do
  echo "--- $u"
  curl -sS "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/${u}/FeatureServer/0?f=json" | jq -r '"name=\(.name)  features=?"'
  curl -sS "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/${u}/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json"
done
```

### Onboard Rev2023 only if newer

```bash
python -m scripts.onboard_municipality \
  --jurisdiction-id 4bf00234-4455-4987-a067-b22ee6b6aa1f \
  --source-url "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning_Rev2023/FeatureServer/0" \
  --muni "Paramus" \
  --label "Paramus Zoning 2023 revision (vendor refresh)" \
  --auto-verify \
  --replace
```

---

## Tier 2 — PDF-only towns (blocked on Op-5 PDF georeference pipeline)

These are listed for record-keeping. Each has a published PDF zoning map URL (in `backend/data/bergen_zoning_directory.json`) but NO ArcGIS service. **Do NOT onboard yet.** Awaiting Op-5 build-out.

| Town | Map URL | Operator action today |
|---|---|---|
| Hackensack | `https://ecode360.com/attachment/HA0454/HA0454-175g%20Zoning%20Map.pdf` (581 KB, OK) | Queue for Op-5 |
| Fort Lee | `https://www.fortleenj.org/DocumentCenter/View/417/Zoning-Map-PDF` (969 KB, OK) | Queue for Op-5 |
| Garfield | `https://www.garfieldnj.org/_Content/pdf/zoning.pdf` (679 KB, OK) | Queue for Op-5 |
| Teaneck | directory URL broken (S3 403). Re-hunt later. | Queue for re-hunt |
| Fair Lawn | directory URL broken (404). Re-hunt later. | Queue for re-hunt |

**Coverage gap from these 5**: ~58,300 parcels (~21% of Bergen) sitting on the wrong side of the PDF barrier.

---

## Coverage measurement (post-ingest, every block)

```bash
# Bergen overall
curl -sS "${API}/api/admin/coverage" | jq '.[] | select(.county=="Bergen") | {
  parcel_with_zoning_code_count,
  parcel_zoning_code_coverage_pct,
  zoning_district_count,
  source_count_verified,
  source_count_pending
}'

# Per-muni breakdown (works only if Op-6 parcels.city backfill has been run)
curl -sS "${API}/api/admin/coverage?include_breakdown=true&jurisdiction_id=${BERGEN}" \
  | jq '.[] | select(.county=="Bergen") | .municipality_breakdown'
```

Expected end-state after running Tier-1 ingests:

| Metric | Before | After |
|---|---:|---:|
| `parcel_with_zoning_code_count` | 8,619 | **22,000 – 27,000** |
| `parcel_zoning_code_coverage_pct` | 3.1% | **7.8% – 9.6%** |
| `zoning_district_count` | 366 | **520 – 650** |
| `source_count_verified` | 1 | **3 – 5** |

---

## Rollback / safety

Every ingest writes to `zoning_districts` additively (default `replace=false`). To roll back a botched Tier-1 ingest:

```sql
-- Identify the offending zoning_districts rows (by source URL or insertion time)
SELECT id, jurisdiction_id, city, zone_code, source_url, inserted_at
FROM zoning_districts
WHERE jurisdiction_id = '4bf00234-4455-4987-a067-b22ee6b6aa1f'
  AND inserted_at > now() - interval '1 hour'
ORDER BY inserted_at DESC LIMIT 200;

-- Drop them
DELETE FROM zoning_districts
WHERE jurisdiction_id = '4bf00234-4455-4987-a067-b22ee6b6aa1f'
  AND source_url = '<the bad source url>';

-- Re-run spatial_backfill to clear parcels.zoning_code for affected rows
-- (use existing /api/debug/fix-zoning/{jurisdiction_id} endpoint)
```

---

## What this runbook deliberately omits

- Tier 2/3 onboarding via PDF pipeline (Op-5 deferred per user direction)
- Generic muni-website CSE probing (Op-3 — superseded for Bergen by the
  Municipal_Zoning directory)
- Mass-rerun of stale-scored sources (the other lane's `_rescore-stale-sources`
  endpoint handles that separately)
- Any migration. Zero migrations are needed for this runbook.

---

## Per-muni cheat sheet (NJSEA Meadowlands, for verification queries)

After Tier-1 NJSEA ingest, you can grep per-town directly via the
`nj_mun_code_map.json` mapping:

```bash
# Example: how many features did NJSEA contribute for Carlstadt (0205)?
python3 -c "
import json
m = json.load(open('backend/data/nj_mun_code_map.json'))['codes']
for code in ['0205','0212','0230','0232','0237','0239','0249','0256','0259','0262']:
  print(f\"  {code}: {m[code]['muni']}\")"
```
