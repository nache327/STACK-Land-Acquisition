# Archived one-off scripts

These scripts were written during the NY/PA/NJ bootstrap to repair data that
the pipeline had already ingested incorrectly (case-sensitive field lookup
bug, FEMA 500-on-large-bbox bug, stale NYC zoning URL).

They are kept for reference only. **Do not run them** — the bugs they worked
around are fixed in the main pipeline, and re-running them would delete and
re-download data unnecessarily.

- `repair_philly.py` — re-ran Philly zoning ingest + spatial backfill after
  the case-sensitive `_first()` fix.
- `repair_nyc.py` — re-ran NYC zoning ingest against the correct
  `v_Zoning_Districts_NYZD` endpoint.
- `ingest_overlays_only.py` — overlay-only re-run for Philly + NYC after the
  FEMA pagination + USFWS AGOL-URL fixes.
- `ingest_nyc_wetlands_only.py` — NYC-only wetland retry with partial-data
  tolerance on 504s.

If you need to re-ingest anything, create a fresh `Job` via
`scripts/ingest_ny_pa_bootstrap.py` — the pipeline is now idempotent (replaces
existing rows on conflict).
