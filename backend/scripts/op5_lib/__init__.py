"""Op-5 factory runner helpers (CP-Pre Finding 2 / A2).

Small modules that keep `op5_per_muni_runner.py` readable:

* :mod:`op5_lib.extraction` — vector/raster polygon extraction (color-seg +
  vision-LLM) mirroring the proof's per-muni pipeline.
* :mod:`op5_lib.ingestion_helpers` — additive asyncpg PostGIS insert scoped
  by ``raw_attributes->>'op5_town'`` so the Op-5 proof state on preview
  is never touched.
"""
