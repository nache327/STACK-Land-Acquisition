# Op-5 Operator Runbook (Bergen)

**Owner:** Operator-track lead
**Status:** Live as of 2026-06-10 (factory abandoned per `docs/OP5_FACTORY_ABANDONED.md`)
**Predecessor:** `docs/archive/BERGEN_PDF_OPERATIONALIZATION.md` (2026-05-16 MVP design — read it for the architecture rationale; this runbook is the operator-facing how-to)
**Toolkit reference:** `docs/OP5_OPERATOR_TOOLKIT.md`

This is the per-muni workflow operators use to ingest Bergen PDF-class zoning sources after the 25-agent factory was abandoned. The architecture is unchanged from the 2026-05-16 MVP plan: **operator runs QGIS for georef + polygon trace, backend's existing `_upload-zoning` endpoint does the ingest, review queue UI signs off matrix adjudications.** What's new here is sequencing the ~56 remaining Bergen PDF munis and slotting in the toolkit pieces that shipped 2026-06-04.

---

## Scope

| Track | Count | Throughput estimate |
|---|---:|---|
| Bergen ArcGIS direct ingests (immediate wins) | ~14 | minutes per muni; see `docs/archive/BERGEN_INGEST_RUNBOOK.md` |
| Bergen PDF / raster operator-assisted (THIS RUNBOOK) | ~56 | 55-80 min per muni |
| Non-Bergen NJ counties (Essex/Middlesex NJ/Monmouth/Burlington) | deferred | — |

Combined Bergen target: 70 munis operational. ArcGIS subset is `docs/archive/BERGEN_INGEST_RUNBOOK.md`. The PDF subset is what this runbook covers.

---

## Sequencing — Bergen PDF munis by parcel impact

Highest-impact munis first (operator gets the biggest coverage lift per hour). Sourced from `backend/data/bergen_zoning_directory.json` plus Bergen parcel-count snapshots (`/tmp/op5_factory/pre_factory_db_snapshot.json` from PR #180).

| Tier | Bergen munis | Criteria | Operator hours |
|---|---|---|---:|
| **A — Hackensack-class large dense** (raster + complex) | Hackensack, Englewood, Teaneck, Bergenfield, Lodi, Fair Lawn, Ridgewood | ≥7,000 parcels, raster or text-only-legend | 60-80 min each |
| **B — Mid-size vector** | ~25 munis from Ramsey through Wyckoff | Vector PDFs (pdfplumber lines > 50) | 45-60 min each |
| **C — Small clean vector** | ~24 munis (boroughs < 3,000 parcels) | Vector, single legend, simple geometry | 30-45 min each |

Total: ~56 munis × 50 min average = **~47 operator-hours** (~2 weeks full-time or 4-5 weeks part-time).

(Exact Tier-A/B/C lists are produced by `op5_discovery_classify.py --county bergen` — operator runs once, prioritizes downward.)

---

## Per-muni workflow (the recipe)

For every Bergen PDF muni, operator follows these eight steps. The steps mirror `docs/archive/BERGEN_PDF_OPERATIONALIZATION.md` §4 with toolkit additions called out.

### Step 1 — Lookup + classify (1 min, toolkit-driven)

```bash
PYTHONPATH=backend python3 backend/scripts/op5_discovery_classify.py --county bergen
# Inspects backend/data/bergen_zoning_directory.json; emits
# /tmp/op5_factory/bergen_classification.json with per-muni:
#   class: arcgis_verified | arcgis_candidate | njsea | vector | raster | absent
#   map_url, ordinance_url
```

If `class` is `arcgis_*` or `njsea`: stop, use `docs/archive/BERGEN_INGEST_RUNBOOK.md` instead — that's the direct-ingest track, not the operator-assisted track.

If `class` is `vector` or `raster`: continue with this runbook.

If `class` is `absent`: source URL is dead. Either re-hunt the muni website for a current zoning map link OR mark the muni as `operator_queue_absent` and defer.

### Step 2 — Source acquisition (5-10 min)

Download the PDF from `map_url`. Use `curl`, browser save-as, or whatever. Save to a working directory keyed by muni: `~/op5/bergen/{muni_normalized}/source.pdf`.

If PDF is rotated 90°/270° (Fort Lee was 270°), note the rotation — QGIS will need it.

### Step 3 — QGIS georeferencing (10-20 min for raster, 2-5 min for vector)

Open QGIS 3.28+ (3.40 recommended). For **vector** PDFs:
- `gdal_translate -of GeoJSON source.pdf vectorized.geojson` produces a starter GeoJSON from the embedded linework.
- Open in QGIS; reproject to EPSG:4326 if needed.

For **raster** PDFs:
- Open the Georeferencer plugin.
- Add 4-8 ground control points using either OpenStreetMap basemap or a TIGERweb places layer. Named intersections work best.
- Save as GeoTIFF, then digitize on top.

### Step 4 — Polygon trace + zone-code assignment (20-40 min)

Use QGIS digitizer. For each visible zoning district:
- Trace polygon boundary
- Set attribute `zone_code` to the printed label (or legend-derived code)
- Set attribute `zone_class` to one of `residential|commercial|industrial|mixed_use|overlay|special|open_space|agricultural|unknown`
- Set attribute `confidence` 0.6-1.0 (operator's certainty)

For the toolkit helper, run `backend/scripts/extract_pdf_zone_legend.py` (pre-existing, from BERGEN_PDF_OPERATIONALIZATION.md Phase 2) to pre-seed the legend attributes — saves ~30 minutes on dense vector maps.

### Step 5 — Export GeoJSON

QGIS → Export → Save as → GeoJSON, EPSG:4326. Save to `~/op5/bergen/{muni}/zoning.geojson`.

### Step 6 — Upload via existing endpoint (2-3 min)

```bash
JID=$(curl -sS "${API}/api/jurisdictions?name=Bergen" | jq -r '.[0].id')

curl -sS -X POST "${API}/api/jurisdictions/${JID}/_upload-zoning?spatial_join=true&replace=false" \
  -F "file=@/Users/arench/op5/bergen/${muni}/zoning.geojson" \
  -F "source_url=<original PDF URL>" \
  -F "municipality=${muni_dca_name}"
```

This calls `ingest_zoning_districts` and runs spatial backfill (centroid containment + nearest_within_meters=100.0 from PR #172).

**F2 protect-list (PR #178)**: if the operator accidentally uses `op5_town` that collides with proof state (`fort_lee`, `garfield`, `hackensack`), the ingest helper refuses to delete prior rows. The proof state is safe. If you see a `ProofStateCollisionError` in logs, you picked a bad op5_town — re-namespace.

### Step 7 — Matrix adjudication (10-15 min)

For each zone code in the new layer, author or update a row in `zone_use_matrix`. Use one of the pattern scripts as a template:
- `backend/scripts/pattern_bergen_fort_lee_adjudication.py`
- `backend/scripts/pattern_bergen_garfield_adjudication.py`
- `backend/scripts/pattern_bergen_hackensack_adjudication.py`

The pattern script encodes:
- Per-zone-code self_storage / mini_warehouse / light_industrial / luxury_garage_condo verdicts
- Ordinance citations (`zone_use_matrix.citations` JSONB)
- Confidence + notes
- `municipality` scope

Run the pattern script with `--apply` against preview to insert matrix rows.

### Step 8 — Review queue sign-off (5-10 min, toolkit-driven)

Browse to `/admin/op5-review` (PR #177, now shipped). Filter by the muni you just ingested. For each row:
- Confidence ≥ 0.90 → bulk-approve via "Approve all ≥90% confidence" toolbar button
- Confidence < 0.90 → per-row review; either Approve or Reject with reason

The UI writes `human_reviewed=true` on `zone_use_matrix` rows and (for rejects) sets `deleted_at`.

### Step 9 — Audit + spot-check (3-5 min)

```bash
python backend/scripts/audit_zoning_coverage.py --json --jurisdiction "Bergen County, NJ" \
  | jq '.audits[] | select(.municipality == "Hackensack city")'
```

Expect: `parcel_zoning_code_coverage_pct >= 70%`, `matrix_match_pct_of_zoned >= 95%`, `operational_readiness = operational`.

Spot-check 10 random parcels manually (compare assigned zone vs town's online assessor). If <9/10 pass, debug before moving on.

If `parcel_zoning_code_coverage_pct < 70%`: try `backfill_parcel_zoning_from_districts(jurisdiction_id, nearest_within_meters=200.0)` for the muni's scope. Per Dispatch P, 200m closes most coverage gaps.

---

## Promotion to prod (after a batch of munis is preview-verified)

Once 5-10 munis are operational on preview:
1. Snapshot prod state for rollback safety.
2. Re-run the same `_upload-zoning` + matrix-adjudication + audit cycle against the prod API. The scripts and patterns are environment-agnostic — flip `DATABASE_URL` and `API` env vars.
3. Run a fresh spot-check on prod (different seed) to verify the cross-environment migration.
4. Update `docs/PHASE2_PROGRESS.md` §1 KPI snapshot.

Master must approve the first prod-promotion batch in writing (per the lane charter). After that, operator can ship batches autonomously.

---

## Stop conditions

Halt the operator track and surface to Master if any of:

1. >3 munis in a row spot-check at <8/10 after polygon trace (signals operator process drift OR genuine source-PDF quality issue).
2. `_upload-zoning` returns an error from `ingest_zoning_districts` not seen during the proof (signals platform-side regression).
3. A muni's zone_code distribution is wildly skewed (>70% of parcels in one code) — usually means operator missed a district during trace.
4. `parcel_zoning_code_coverage_pct < 50%` even after `nearest_within_meters=200.0` (signals systematic georef drift; needs the GENZ2024 shapefile approach from `docs/OP5_FACTORY_ABANDONED.md` lessons).

---

## Per-muni audit ledger

Operator maintains a CSV at `/tmp/op5_operator/bergen_ledger.csv` with one row per muni:

```csv
muni_code,muni_name,date,tier,source_class,coverage_pct,matrix_match_pct,spot_check_pass_pct,operator_hours,notes
0223,Hackensack city,2026-06-12,A,raster,72.4,96.8,9/10,1.2,manual georef + trace
0219,Fort Lee borough,2026-06-12,A,vector,84.1,100.0,9/10,0.8,existing proof; promotion only
...
```

Master reviews the ledger weekly. After 30 munis, Master re-evaluates whether to widen scope to non-Bergen.

---

## Not in scope for this runbook

- ArcGIS-served munis (use `docs/archive/BERGEN_INGEST_RUNBOOK.md` direct-ingest pattern instead).
- Non-Bergen NJ counties (deferred per `docs/OP5_FACTORY_ABANDONED.md`).
- The factory orchestrator (`op5_factory_orchestrator.py`) — abandoned; not used.
- The per-muni runner's heavy extraction (`op5_per_muni_runner.py`'s `default_extract_polygons_from_map`) — known-buggy per `docs/OP5_FACTORY_ABANDONED.md` bug 6. Operator does extraction in QGIS, not the runner.
- Bug 6 + bug 7 fixes — only if operator track surfaces them as blocking.
