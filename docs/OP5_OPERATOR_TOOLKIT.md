# Op-5 Operator Toolkit

**Owner:** Master Planning Thread
**Status:** Shipped 2026-06-10 as the operator-assisted alternative to the abandoned 25-agent factory (`docs/OP5_FACTORY_ABANDONED.md`).
**Audience:** Operators running Op-5 zoning ingest at scale, plus engineers triaging the toolkit.

---

## What the toolkit is

The four PRs originally authored as the factory pre-build are net-positive on their own. They became the operator toolkit when the unattended-factory thesis was abandoned; nothing about them is factory-specific.

| Capability | PR | Files | Use |
|---|---|---|---|
| Proof-state protection | [#178](https://github.com/nache327/STACK-Land-Acquisition/pull/178) | `backend/scripts/op5_lib/ingestion_helpers.py` (`assert_no_proof_state_collision`, `ProofStateCollisionError`, `op5_factory='true'` DELETE filter) | Any new Op-5 ingest run that uses `op5_town` tagging refuses to overwrite proof-state rows lacking the `op5_factory='true'` marker. Op-5 proof on Bergen (Fort Lee 99 polygons, Garfield 215, Hackensack 50) is now safe from accidental wipe. |
| ArcGIS-first classification + lookup | #178 | `backend/scripts/op5_lib/arcgis_lookup.py` (`lookup_arcgis_source`, `probe_feature_server`) | Operators or future automation can ask "is this NJ muni ArcGIS-served, and if so what's the FeatureServer URL?" Priority: verified-tenant → candidate-tenant → NJSEA Meadowlands → None. Honors `non_zoning_munis` exclusions. |
| Discovery classifier w/ map_url fallback | #178 | `backend/scripts/op5_discovery_classify.py` + `discover_map_url_from_website` | Given a NJ muni record, classify source as `vector \| raster \| absent \| arcgis_verified \| arcgis_candidate \| njsea`. When `map_url` is null in the directory, attempts lightweight HTTP probe of `website_url` for zoning-map links. |
| Per-muni runner (uses toolkit pieces) | #178 | `backend/scripts/op5_per_muni_runner.py` | Single-muni CP1→CP2→CP3 shell — idempotent on `/tmp/op5_factory/{county}/{muni}/cp3_summary.json`, exit codes 0/1/2/3 for operational/non-operational/carve-out/transient. Known bugs 6 + 7 documented in `docs/OP5_FACTORY_ABANDONED.md`; operator may use it where the bugs don't bite (e.g. classification-only invocations) or call the underlying libs directly. |
| Per-county orchestrator (CLI shell) | #178 | `backend/scripts/op5_factory_orchestrator.py` | Multi-muni dispatcher capped at `--max-parallel 14` per CP-Pre Finding 1 (Supavisor pool limit). Operator can use it for batch classify (`--dry-run` + classification mode); full extraction was the failed factory path. |
| Admin review queue UI | [#177](https://github.com/nache327/STACK-Land-Acquisition/pull/177) | `frontend/app/admin/op5-review/page.tsx`, `backend/app/api/admin_op5.py` | `/admin/op5-review` shows pending matrix adjudications with filters (county/state/municipality/confidence). Per-row Approve/Reject + bulk-approve at ≥90% confidence threshold. Backend endpoints under `/api/admin/op5/adjudications`. Critical for batch operator review of operator-assisted Op-5 output. |
| 4 county zoning directories | [#179](https://github.com/nache327/STACK-Land-Acquisition/pull/179) | `backend/data/{essex,middlesex_nj,monmouth,burlington}_zoning_directory.json` | 140 munis with `muni_code`, `muni_name`, `website_url`, `ordinance_url` populated; `map_url` populated for 18 (per CP-Pre Decision 3). Format matches `backend/data/bergen_zoning_directory.json` with field name `in_statewide_aggregator` per Master brief. |
| DB capacity report + check script | [#180](https://github.com/nache327/STACK-Land-Acquisition/pull/180) | `docs/OP5_DB_CAPACITY_REPORT.md`, `backend/scripts/op5_db_capacity_check.py` | Documents the Supavisor session-mode pool cap (15 client connections), pre-factory snapshot (10.3 M Bergen parcels, 48 K zoning_districts, 5.1 K zone_use_matrix rows), GIST index health, 25-vs-14 concurrent latency. Operator-routed work should respect the 14-writer cap. |

---

## What operators do with the toolkit

### 1. Direct ArcGIS ingests (zero new code, runbook-driven)

For Bergen ArcGIS-served munis (NJSEA Meadowlands 10 + Paramus + Westwood + any future tenant verifications):
- `arcgis_lookup.lookup_arcgis_source('<muni name>', 'NJ')` returns the FeatureServer URL.
- Operator runs the proven pattern from `docs/archive/BERGEN_INGEST_RUNBOOK.md` (probe → backfill → spatial-check).
- F2 protect-list prevents accidental overwrite of proof-state munis.

### 2. PDF-class Op-5 (operator-assisted QGIS workflow)

For Bergen vector/raster PDF munis (~56 munis after subtracting the immediate ArcGIS wins):
- Operator follows `docs/OP5_OPERATOR_RUNBOOK.md` (this PR), which extends `docs/archive/BERGEN_PDF_OPERATIONALIZATION.md`.
- QGIS for georef + polygon trace (~55-80 min per muni), ingest via the existing `_upload-zoning` endpoint.
- Matrix adjudication uses the per-muni pattern script template (`backend/scripts/pattern_bergen_*_adjudication.py`).
- Review queue UI (`/admin/op5-review`) batches matrix sign-off for the operator.

### 3. Non-Bergen NJ counties (deferred)

Essex, Middlesex NJ, Monmouth, Burlington — directories are loaded but `map_url` discovery rate was 12.9%. Per Master's CP-Pre v3 decision these are deferred until Bergen is complete. The toolkit doesn't go anywhere; it's ready when these counties enter scope.

---

## Known issues carried forward

Both classified as "out of scope, fix only if operator track reveals these blocking other work" per `docs/OP5_FACTORY_ABANDONED.md`:

- **Bug 6 — F5 ArcGIS field normalization.** `_ingest_arcgis_source` in the per-muni runner doesn't map FeatureServer field variants (`ZONE`, `ZONE_CODE`, `Zone_Code`) to platform's expected `zone_code`. Westwood smoke surfaced this: 3,686 features downloaded, 3,686 skipped at the platform mapper. Workaround for now: operator runs direct ingest scripts (which can include field-mapping inline) rather than the per-muni runner.
- **Bug 7 — Per-muni audit scope.** `default_audit_muni` returns jurisdiction-wide coverage % instead of muni-scoped. Operator should query muni-scoped audit results directly via `audit_zoning_coverage.py --jurisdiction-id <id>` + post-hoc filter by `parcels.city`.

---

## Where the toolkit lives in the repo

```
backend/scripts/op5_lib/
  arcgis_lookup.py       # ArcGIS-first classification + probe
  extraction.py          # PDF-path color-seg + vision-LLM (factory-shell, has runtime bugs)
  ingestion_helpers.py   # F2 protect-list + ingest pattern
backend/scripts/
  op5_discovery_classify.py
  op5_per_muni_runner.py
  op5_factory_orchestrator.py
  op5_backfill_map_urls.py
  op5_db_capacity_check.py
backend/app/api/admin_op5.py
frontend/app/admin/op5-review/page.tsx
backend/data/
  bergen_zoning_directory.json
  essex_zoning_directory.json
  middlesex_nj_zoning_directory.json
  monmouth_zoning_directory.json
  burlington_zoning_directory.json
  zoning_source_tenants.json      # pre-existing vendor catalog
  nj_municipalities.json          # PR #170
docs/
  OP5_OPERATOR_TOOLKIT.md     # this file
  OP5_OPERATOR_RUNBOOK.md     # per-muni operator workflow (separate PR)
  OP5_FACTORY_ABANDONED.md    # decision record (separate PR)
  OP5_DB_CAPACITY_REPORT.md   # from PR #180
  OP5_PRE_BUILD_REPORT.md     # iteration history
  archive/BERGEN_INGEST_RUNBOOK.md
  archive/BERGEN_PDF_OPERATIONALIZATION.md
```
