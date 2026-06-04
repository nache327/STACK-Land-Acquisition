"""Op-5 per-muni runner — single-municipality factory pipeline.

This script lifts the Op-5 proof orchestrator (Fort Lee / Garfield / Hackensack)
into a callable per-muni pipeline that the factory orchestrator dispatches
against every muni in a Tier-S NJ county.

Pipeline (mirrors the proof's CP1 -> CP2 -> CP3):

  CP1 — extraction
    1. Load muni record from `backend/data/{county}_zoning_directory.json`
       (or, as a fallback, from `backend/data/nj_municipalities.json`).
    2. Download the map asset (PDF or raster) from `map_url`.
    3. Render to 300 DPI PNG (pdftoppm with GDAL fallback).
    4. Color-segmentation polygon extraction (OpenCV k-means + contour +
       Douglas-Peucker simplification).
    5. Vision-LLM label assignment via the project's
       `_parse_with_claude_vision` helper. Filter at confidence >= 0.75.

  Carve-outs (exit code 2)
    - Vision returns 0 reliable labels OR pdfplumber says raster
      -> raster carve-out per docs/OP5_PROOF_DECISION.md.
    - Legend extraction returns empty color_to_zone -> text-only-legend
      carve-out (Fair Lawn class).

  CP2 — matrix adjudication
    Fetch ordinance + adjudicate zone codes against the four matrix uses.
    Falls back to a "general use restriction" catchall when the ordinance
    text is too sparse, marking every zone `requires_review=true`.

  CP3 — ingest + audit
    Ingest polygons to preview branch (asyncpg PostGIS pattern). Stamp
    `raw_attributes->>'op5_town'` and `op5_factory = true`. Call
    `backfill_parcel_zoning_from_districts(jurisdiction_id, db,
    nearest_within_meters=100.0)` (DEFAULT per docs/OP5_PROOF_DECISION.md).
    Audit + 10-parcel spot-check, capture coverage / spot-check / binding-
    method distribution.

Idempotency
  If `/tmp/op5_factory/{county}/{muni}/cp3_summary.json` exists with
  `status == "complete"` the runner exits 0 immediately. `--force`
  re-runs.

Exit codes
  0  complete-operational           (factory success, parcels bound)
  1  complete-not-operational       (factory ingested but coverage < gate)
  2  carve-out                      (raster / text-only-legend / vision-empty)
  3  transient-error                (transient I/O / DB / API failure)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# Hard rules: this script does not import or edit Slot-1 hot files. It only
# CALLS them through public APIs. The imports below stay lazy / behind
# functions so the script remains importable in unit tests without a live
# DB connection or Anthropic API key.

LOGGER = logging.getLogger("op5_per_muni_runner")

# Op-5 preview branch (Supabase) per docs/OP5_FACTORY_72H_PLAN.md.
DEFAULT_PREVIEW_BRANCH = "bbvywbpxwsoyvdvygvyw"
# Production default per docs/OP5_PROOF_DECISION.md.
DEFAULT_NEAREST_WITHIN_METERS = 100.0
# Coverage gate per municipality_health: >= 70% parcels zoned is the
# operational threshold.
OPERATIONAL_COVERAGE_PCT = 70.0
# Vision-LLM label confidence floor (proof default).
VISION_LABEL_CONFIDENCE_FLOOR = 0.75
# Spot-check sample size for CP3 v1 semantics.
SPOT_CHECK_SAMPLE_SIZE = 10

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"
ARTIFACT_ROOT = Path("/tmp/op5_factory")


# ── exit codes ─────────────────────────────────────────────────────────────

EXIT_COMPLETE_OPERATIONAL = 0
EXIT_COMPLETE_NOT_OPERATIONAL = 1
EXIT_CARVE_OUT = 2
EXIT_TRANSIENT_ERROR = 3


# ── data shapes ────────────────────────────────────────────────────────────


@dataclass
class MuniRecord:
    """Per-muni record drawn from the county zoning directory."""

    muni_code: str
    muni_name: str
    map_url: Optional[str]
    ordinance_url: Optional[str]
    website_url: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    polygons: list[dict]       # GeoJSON-ish polygons w/ zone label + confidence
    color_to_zone: dict        # legend mapping; empty -> text-only-legend carve-out
    source_class: str          # "vector" | "raster" | "text_only_legend" | "absent"
                               # | "arcgis_verified" | "arcgis_candidate" | "njsea"
    vision_label_count: int    # # labels at >= VISION_LABEL_CONFIDENCE_FLOOR
    arcgis_source: Optional[Any] = None  # ArcgisSource when source_class.startswith("arcgis_") or =="njsea"


@dataclass
class IngestResult:
    jurisdiction_id: str
    polygons_written: int
    nearest_within_meters: float


@dataclass
class AuditMetrics:
    parcel_count: int
    zoned_parcel_count: int
    coverage_pct: float                 # parcel_zoning_code_coverage_pct
    matrix_match_pct_of_zoned: float
    spot_check_total: int
    spot_check_passes: int
    spot_check_pass_pct: float
    binding_method_distribution: dict   # {"contained": N, "nearest_100m": M, ...}


# ── public coverage helper (used by tests) ─────────────────────────────────


def compute_coverage_pct(parcel_count: int, zoned_parcel_count: int) -> float:
    """parcel_zoning_code_coverage_pct math. 100 parcels / 70 zoned -> 70.0."""
    if parcel_count <= 0:
        return 0.0
    return round(100.0 * zoned_parcel_count / parcel_count, 2)


# ── directory loaders ──────────────────────────────────────────────────────


def load_county_directory(county: str, data_dir: Path = DATA_DIR) -> list[MuniRecord]:
    """Load a county directory or fall back to nj_municipalities.json.

    Bergen ships a richer directory (map_url + ordinance_url + website_url).
    Other counties initially come from the NJ DCA muni-list with only name +
    type + ordinance_vendor — those still flow through the runner but the
    map_url is unknown, which the runner handles by carving out as ``absent``.
    """
    county_norm = county.strip().lower().replace(" ", "_")
    directory_path = data_dir / f"{county_norm}_zoning_directory.json"
    if directory_path.exists():
        rows = json.loads(directory_path.read_text(encoding="utf-8"))
        return [
            MuniRecord(
                muni_code=row.get("muni_code") or row.get("name") or "",
                muni_name=row.get("muni_name") or row.get("name") or "",
                map_url=row.get("map_url"),
                ordinance_url=row.get("ordinance_url"),
                website_url=row.get("website_url"),
                extra=row,
            )
            for row in rows
        ]
    fallback_path = data_dir / "nj_municipalities.json"
    if not fallback_path.exists():
        raise FileNotFoundError(
            f"No zoning directory at {directory_path} and no fallback "
            f"nj_municipalities.json found in {data_dir}"
        )
    fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
    county_rows = fallback.get(county_norm)
    if not county_rows:
        raise KeyError(
            f"County {county_norm!r} not present in nj_municipalities.json "
            f"and no {directory_path.name} found."
        )
    out: list[MuniRecord] = []
    for row in county_rows:
        if isinstance(row, str):
            out.append(MuniRecord(
                muni_code=row, muni_name=row, map_url=None,
                ordinance_url=None, website_url=None, extra={"raw": row},
            ))
        else:
            out.append(MuniRecord(
                muni_code=row.get("muni_code") or row.get("name") or "",
                muni_name=row.get("name") or row.get("muni_name") or "",
                map_url=row.get("map_url"),
                ordinance_url=row.get("ordinance_url"),
                website_url=row.get("website_url"),
                extra=row,
            ))
    return out


def find_muni(county: str, muni: str, data_dir: Path = DATA_DIR) -> MuniRecord:
    rows = load_county_directory(county, data_dir=data_dir)
    target = muni.strip().lower()
    for r in rows:
        if (r.muni_name or "").strip().lower() == target:
            return r
        if (r.muni_code or "").strip().lower() == target:
            return r
    # Looser match — strip the common NJ DCA suffixes.
    suffixes = (" borough", " township", " town", " city", " village")
    for r in rows:
        name = (r.muni_name or "").strip().lower()
        for suf in suffixes:
            if name.endswith(suf):
                name = name[: -len(suf)]
                break
        if name == target:
            return r
    raise KeyError(f"Muni {muni!r} not found in county {county!r}")


def normalize_muni_token(muni_name: str) -> str:
    """Drop punctuation + DCA suffixes for `raw_attributes->>'op5_town'`."""
    name = (muni_name or "").strip().lower()
    for suf in (" borough", " township", " town", " city", " village"):
        if name.endswith(suf):
            name = name[: -len(suf)]
            break
    return name.replace(" ", "_")


# ── artifact paths ─────────────────────────────────────────────────────────


def muni_artifact_dir(county: str, muni: str, root: Path = ARTIFACT_ROOT) -> Path:
    return root / county.strip().lower() / normalize_muni_token(muni)


def cp3_summary_path(county: str, muni: str, root: Path = ARTIFACT_ROOT) -> Path:
    return muni_artifact_dir(county, muni, root=root) / "cp3_summary.json"


def carve_out_path(county: str, muni: str, root: Path = ARTIFACT_ROOT) -> Path:
    return muni_artifact_dir(county, muni, root=root) / "carve_out.json"


def matrix_rows_path(county: str, muni: str, root: Path = ARTIFACT_ROOT) -> Path:
    return muni_artifact_dir(county, muni, root=root) / "matrix_rows.json"


# ── extraction (CP1) ───────────────────────────────────────────────────────


def default_extract_polygons_from_map(muni: MuniRecord) -> ExtractionResult:
    """Production extraction path (CP-Pre Finding 2 / A2 + Finding 5).

    ArcGIS-first (CP-Pre Finding 5):
      Before any PDF work, consult :func:`op5_lib.arcgis_lookup.lookup_arcgis_source`.
      If a verified/candidate tenant service or NJSEA layer exists for the
      muni AND probes alive (returnCountOnly > 0), short-circuit: return an
      ExtractionResult with ``source_class='arcgis_<confidence>'`` (or
      ``'njsea'``), ``arcgis_source=<ArcgisSource>``, and empty polygons
      — the ingest stage will call the ArcGIS path instead of using
      extracted polygons. This is the master-identified critical path for
      Westwood and the 10 NJSEA Meadowlands towns.

    Routes through :mod:`op5_lib.extraction` on the PDF fallback:

    * Fetch ``muni.map_url`` (httpx, follow redirects).
    * Classify vector vs raster via ``pdfplumber`` line count (>50 -> vector).
    * Vector path: pdftoppm render -> OpenCV k-means colour segmentation ->
      contour extraction + Douglas-Peucker simplify -> vision-LLM label
      points at confidence >= 0.75 -> point-in-polygon assignment ->
      affine-bbox-fit to the Census place boundary.
    * Raster path: vision-LLM boundary tracing (Hackensack class). Each
      district returns a pixel polygon + zone_code + confidence; the same
      Census-bbox affine projects to WGS84.

    Carve-out preserved: vision returns 0 labels above 0.75 -> empty
    polygons so the runner's existing carve-out path fires.

    Returns an empty extraction (source_class unchanged) for any heavy
    failure path so the carve-out flow is the single error sink.
    """
    # ── ArcGIS-first short-circuit (CP-Pre Finding 5) ──────────────────
    try:
        from op5_lib.arcgis_lookup import (
            lookup_arcgis_source,
            probe_feature_server,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("op5_lib.arcgis_lookup import failed: %s — skipping arcgis path", exc)
        lookup_arcgis_source = None  # type: ignore[assignment]
        probe_feature_server = None  # type: ignore[assignment]

    if lookup_arcgis_source is not None:
        try:
            arc = lookup_arcgis_source(muni.muni_name, "NJ")
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("arcgis lookup error for %s: %s", muni.muni_name, exc)
            arc = None
        if arc is not None and probe_feature_server is not None:
            try:
                alive = probe_feature_server(arc.feature_server_url, arc.where_clause)
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("arcgis probe error for %s: %s", muni.muni_name, exc)
                alive = False
            if alive:
                source_class = (
                    "njsea" if arc.confidence == "njsea"
                    else f"arcgis_{arc.confidence}"
                )
                LOGGER.info(
                    "arcgis-first route for %s -> %s (%s)",
                    muni.muni_name, source_class, arc.feature_server_url,
                )
                return ExtractionResult(
                    polygons=[],
                    color_to_zone={},
                    source_class=source_class,
                    vision_label_count=0,
                    arcgis_source=arc,
                )
            else:
                LOGGER.info(
                    "arcgis lookup hit %s but probe failed; falling through to PDF",
                    muni.muni_name,
                )

    try:
        from op5_lib.extraction import extract_polygons as _extract
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("op5_lib.extraction import failed: %s — carving out", exc)
        return ExtractionResult(
            polygons=[], color_to_zone={},
            source_class="absent", vision_label_count=0,
        )

    if not muni.map_url:
        return ExtractionResult(
            polygons=[], color_to_zone={},
            source_class="absent", vision_label_count=0,
        )

    # The op5_lib path uses the muni name for Census-place bbox lookup.
    # Strip the DCA suffix so "Westwood Borough" -> "Westwood" matches
    # what the Census Geocoder expects.
    place_name = muni.muni_name or muni.muni_code
    for suf in (" Borough", " Township", " Town", " City", " Village",
                " borough", " township", " town", " city", " village"):
        if place_name.endswith(suf):
            place_name = place_name[: -len(suf)]
            break

    try:
        result = _extract(
            muni.map_url,
            place_name=place_name,
            state="NJ",
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("extract_polygons crashed for %s: %s", muni.muni_name, exc)
        return ExtractionResult(
            polygons=[], color_to_zone={},
            source_class="absent", vision_label_count=0,
        )

    return ExtractionResult(
        polygons=result.polygons,
        color_to_zone=result.color_to_zone,
        source_class=result.source_class,
        vision_label_count=result.vision_label_count,
    )


# ── matrix adjudication (CP2) ──────────────────────────────────────────────


def default_adjudicate_matrix(
    muni: MuniRecord,
    zone_codes: list[str],
) -> list[dict]:
    """Build matrix rows for the muni's zone codes.

    Production path fetches the ordinance + parses via the existing
    `app.services.ordinance_parser`. The orchestrator overrides this hook
    when adjudicating using the per-county pattern script (Garfield-style).
    """
    if not zone_codes:
        return []
    # "general use restriction" catchall — matches the spec section 7. Every
    # zone gets a row with requires_review=True until a per-county pattern
    # script overrides.
    return [
        {
            "zone_code": z,
            "municipality": muni.muni_name,
            "self_storage": "unclear",
            "mini_warehouse": "unclear",
            "light_industrial": "unclear",
            "luxury_garage_condo": "unclear",
            "classification_source": "op5_factory_catchall",
            "requires_review": True,
            "notes": "general use restriction catchall — ordinance text too sparse",
        }
        for z in zone_codes
    ]


# ── ingest (CP3) ───────────────────────────────────────────────────────────


async def default_ingest_polygons(
    muni: MuniRecord,
    extraction: ExtractionResult,
    *,
    preview_branch: str,
    county: str = "bergen",
) -> IngestResult:
    """Production additive asyncpg ingest (CP-Pre Finding 2 / A2 + Finding 5).

    Dispatcher: routes by ``extraction.source_class``.

    * ``arcgis_verified`` / ``arcgis_candidate`` / ``njsea`` -> ArcGIS path
      (:func:`_ingest_arcgis_source`). Uses ``replace=False`` to honor the
      F2 protect-list contract — existing non-factory rows are NOT touched.
    * Anything else -> extraction-based additive insert via
      :func:`op5_lib.ingestion_helpers.ingest_polygons_additive`.

    Tags every district with ``raw_attributes->>'op5_town'`` +
    ``op5_factory='true'`` + ``op5_factory_stage='cp3'`` so the spatial
    backfill (PR #172) and the audit can scope cleanly to just the muni
    we just ingested without touching the existing Op-5 proof state for
    Fort Lee / Garfield / Hackensack.

    REFUSES to run unless DATABASE_URL points at the preview branch.
    """
    import asyncpg  # local — keeps the runner importable in pure-test mode
    from op5_lib.ingestion_helpers import (
        assert_preview_url,
        ingest_polygons_additive,
        load_db_url,
        lookup_jurisdiction_id,
    )

    url = load_db_url()
    assert_preview_url(url)
    if preview_branch not in url:
        raise RuntimeError(
            f"DATABASE_URL preview ref does not match expected {preview_branch!r}"
        )

    # ── ArcGIS branch (CP-Pre Finding 5) ───────────────────────────────
    if extraction.source_class.startswith("arcgis_") or extraction.source_class == "njsea":
        if extraction.arcgis_source is None:
            raise RuntimeError(
                f"source_class={extraction.source_class!r} but extraction.arcgis_source is None"
            )
        return await _ingest_arcgis_source(
            muni,
            extraction.arcgis_source,
            preview_branch=preview_branch,
            county=county,
        )

    op5_town = normalize_muni_token(muni.muni_name)
    conn = await asyncpg.connect(url, statement_cache_size=0, command_timeout=900)
    try:
        jurisdiction_id = await lookup_jurisdiction_id(conn, county=county)
        if not jurisdiction_id:
            raise RuntimeError(
                f"No jurisdictions row found for county={county!r} state=NJ"
            )
        inserted = await ingest_polygons_additive(
            conn,
            jurisdiction_id=jurisdiction_id,
            op5_town=op5_town,
            polygons=extraction.polygons,
        )
    finally:
        await conn.close()
    return IngestResult(
        jurisdiction_id=jurisdiction_id,
        polygons_written=inserted,
        nearest_within_meters=DEFAULT_NEAREST_WITHIN_METERS,
    )


async def _ingest_arcgis_source(
    muni: MuniRecord,
    arc: Any,   # ArcgisSource
    *,
    preview_branch: str,
    county: str,
) -> IngestResult:
    """Ingest a muni from an ArcGIS FeatureServer via the platform API
    (download_all_features + ingest_zoning_districts).

    Honors the F2 protect-list contract by passing ``replace=False`` —
    existing rows (Op-5 proof state, sibling munis, non-factory rows) are
    NEVER deleted from this path.

    We still tag inserted rows with ``op5_factory`` markers so they sort
    cleanly in the audit + spatial-backfill scope. Tagging happens via a
    post-insert UPDATE because ``ingest_zoning_districts`` doesn't accept
    an ``extra_raw_attributes`` kwarg — this is the platform-touching
    boundary that PR #178 stays the right side of (we don't edit
    ``app.services.zoning_ingestion``).
    """
    import asyncpg
    import json as _json
    import uuid as _uuid

    from op5_lib.ingestion_helpers import (
        assert_preview_url,
        load_db_url,
        lookup_jurisdiction_id,
    )

    url = load_db_url()
    assert_preview_url(url)
    if preview_branch not in url:
        raise RuntimeError(
            f"DATABASE_URL preview ref does not match expected {preview_branch!r}"
        )

    # Look up jurisdiction id via raw asyncpg (mirrors the extraction path).
    op5_town = normalize_muni_token(muni.muni_name)
    pre_conn = await asyncpg.connect(url, statement_cache_size=0, command_timeout=900)
    try:
        jurisdiction_id = await lookup_jurisdiction_id(pre_conn, county=county)
    finally:
        await pre_conn.close()
    if not jurisdiction_id:
        raise RuntimeError(
            f"No jurisdictions row found for county={county!r} state=NJ"
        )

    # Download + ingest via the public platform APIs. We never call
    # ``ingest_zoning_districts(replace=True)`` from the factory.
    from app.config import settings  # noqa: WPS433 — public API
    from app.services.arcgis_query import download_all_features  # noqa: WPS433
    from app.services.zoning_ingestion import ingest_zoning_districts  # noqa: WPS433
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    inserted = 0
    pre_zone_ids: set = set()
    try:
        async with sessionmaker() as session:
            # Snapshot existing zoning_district ids for this jurisdiction so
            # the post-insert tag UPDATE only touches the rows WE inserted.
            from sqlalchemy import text as _sql_text  # local import — keep API surface narrow
            res = await session.execute(
                _sql_text(
                    "SELECT id::text FROM zoning_districts WHERE jurisdiction_id = :jid"
                ),
                {"jid": jurisdiction_id},
            )
            pre_zone_ids = {row[0] for row in res.fetchall()}

            gdf = await download_all_features(
                arc.feature_server_url,
                where=arc.where_clause or "1=1",
            )
            if gdf.empty:
                LOGGER.warning(
                    "arcgis download returned 0 features for %s (%s, where=%s)",
                    muni.muni_name, arc.feature_server_url, arc.where_clause,
                )
                inserted = 0
            else:
                jid_uuid = (
                    jurisdiction_id
                    if isinstance(jurisdiction_id, _uuid.UUID)
                    else _uuid.UUID(jurisdiction_id)
                )
                # CRITICAL: replace=False to honor F2 protect-list semantics.
                # The platform ingest will skip duplicates via
                # uq_zoning_districts_jur_code_hash.
                inserted = await ingest_zoning_districts(
                    gdf, jid_uuid, session, replace=False,
                )
                await session.commit()

                # Tag the rows we just inserted with op5_factory markers so
                # the audit + spatial backfill can scope cleanly. We can't
                # pass ``extra_raw_attributes`` to ``ingest_zoning_districts``
                # (kwarg doesn't exist in the public API); this post-insert
                # UPDATE is the workaround.
                raw_patch = {
                    "op5_town": op5_town,
                    "op5_factory": "true",
                    "op5_factory_stage": "cp3",
                    "op5_source_label": arc.source_label,
                    "op5_arcgis_confidence": arc.confidence,
                }
                # Use ANY(:pre_ids) over a uuid[] so we don't have to expand
                # a tuple into IN clauses (some pre-existing jurisdictions
                # have 10k+ rows). Empty array => everything in this
                # jurisdiction is treated as newly inserted.
                pre_ids_array = list(pre_zone_ids)
                res = await session.execute(
                    _sql_text(
                        "UPDATE zoning_districts SET raw_attributes = "
                        "COALESCE(raw_attributes, '{}'::jsonb) || CAST(:patch AS jsonb) "
                        "WHERE jurisdiction_id = CAST(:jid AS uuid) "
                        "AND NOT (id::text = ANY(CAST(:pre_ids AS text[]))) "
                        "RETURNING id"
                    ),
                    {"patch": _json.dumps(raw_patch),
                     "jid": str(jurisdiction_id),
                     "pre_ids": pre_ids_array},
                )
                tagged = len(res.fetchall())
                LOGGER.info(
                    "arcgis ingest %s: inserted=%d tagged=%d",
                    muni.muni_name, inserted, tagged,
                )
                await session.commit()
    finally:
        await engine.dispose()

    return IngestResult(
        jurisdiction_id=str(jurisdiction_id),
        polygons_written=int(inserted),
        nearest_within_meters=DEFAULT_NEAREST_WITHIN_METERS,
    )


async def default_run_backfill(
    jurisdiction_id: str,
    *,
    nearest_within_meters: float = DEFAULT_NEAREST_WITHIN_METERS,
) -> None:
    """Calls the merged spatial backfill API (PR #172) on a fresh AsyncSession.

    ``nearest_within_meters`` defaults to 100.0 per docs/OP5_PROOF_DECISION.md.
    """
    import uuid as _uuid

    from app.config import settings  # noqa: WPS433 — public API
    from app.services.spatial_backfill import (  # noqa: WPS433 — public API
        backfill_parcel_zoning_from_districts,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    if nearest_within_meters is None:
        nearest_within_meters = DEFAULT_NEAREST_WITHIN_METERS

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            await backfill_parcel_zoning_from_districts(
                _uuid.UUID(jurisdiction_id) if not isinstance(jurisdiction_id, _uuid.UUID) else jurisdiction_id,
                session,
                nearest_within_meters=float(nearest_within_meters),
            )
            await session.commit()
    finally:
        await engine.dispose()


# ── audit (CP3) ────────────────────────────────────────────────────────────


async def default_audit_muni(
    jurisdiction_id: str,
    muni: MuniRecord,
    *,
    seed: int = 8819,
    county: str = "bergen",
) -> AuditMetrics:
    """Run the merged coverage audit and a per-muni spot-check.

    Subprocesses ``backend/scripts/audit_zoning_coverage.py --json
    --jurisdiction "<County> County, NJ"`` (the merged CLI doesn't accept
    a per-muni filter; we read the per-jurisdiction roll-up). The
    per-muni spot-check is computed inline against the preview DB,
    seeded by ``hash(county + muni)`` for reproducibility per spec
    section 10 / CP3 v1.
    """
    import asyncpg

    from op5_lib.ingestion_helpers import assert_preview_url, load_db_url

    url = load_db_url()
    assert_preview_url(url)

    # Coverage audit via subprocess so we don't reach into the merged
    # script's internals. Surface only the figures we need.
    audit_data: dict = {}
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(REPO_ROOT / "backend" / "scripts" / "audit_zoning_coverage.py"),
            "--json",
            "--jurisdiction",
            f"{county.capitalize()} County, NJ",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT / "backend"),
        )
        stdout, _stderr = await proc.communicate()
        if proc.returncode == 0 and stdout:
            audit_data = json.loads(stdout.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("coverage audit subprocess failed: %s", exc)
        audit_data = {}

    matrix_match_pct = 0.0
    for row in audit_data.get("jurisdictions", []) or []:
        if str(row.get("id")) == str(jurisdiction_id):
            matrix_match_pct = float(row.get("matrix_zone_match_pct") or 0.0)
            break

    # Per-muni metrics + spot-check via direct asyncpg against the same
    # raw_attributes->>'op5_town' tag we just wrote.
    op5_town = normalize_muni_token(muni.muni_name)
    municipality_label = _muni_label_for_parcels(muni.muni_name)
    parcel_count = 0
    zoned = 0
    binding_dist: dict = {}
    spot_passes = 0
    spot_total = 0

    rng_seed = int(hashlib.sha1(f"{county}:{op5_town}".encode()).hexdigest()[:8], 16)
    conn = await asyncpg.connect(url, statement_cache_size=0, command_timeout=900)
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS parcels,
                COUNT(*) FILTER (
                    WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                )::int AS zoned
            FROM parcels
            WHERE jurisdiction_id = $1::uuid
              AND city = $2
            """,
            jurisdiction_id, municipality_label,
        )
        if row:
            parcel_count = int(row["parcels"])
            zoned = int(row["zoned"])
        method_rows = await conn.fetch(
            """
            SELECT COALESCE(zone_binding_method, 'unknown') AS method,
                   COUNT(*)::int AS n
            FROM parcels
            WHERE jurisdiction_id = $1::uuid
              AND city = $2
              AND zoning_code IS NOT NULL
            GROUP BY 1
            """,
            jurisdiction_id, municipality_label,
        )
        binding_dist = {r["method"]: int(r["n"]) for r in method_rows}

        # Per-muni spot-check: SPOT_CHECK_SAMPLE_SIZE random parcels with
        # a CP3 v1 verdict. Uses setseed() for reproducibility.
        await conn.execute("SELECT setseed($1)", float((rng_seed % 1_000_000) / 1_000_000))
        spot_rows = await conn.fetch(
            """
            SELECT p.id, p.zoning_code AS parcel_code,
                   zd.zone_code AS containing_code,
                   EXISTS (
                     SELECT 1 FROM zone_use_matrix z
                     WHERE z.jurisdiction_id = p.jurisdiction_id
                       AND z.zone_code = p.zoning_code
                       AND z.deleted_at IS NULL
                   ) AS has_matrix
            FROM parcels p
            LEFT JOIN LATERAL (
              SELECT zone_code
              FROM zoning_districts zd
              WHERE zd.jurisdiction_id = p.jurisdiction_id
                AND zd.raw_attributes->>'op5_town' = $3
                AND p.centroid IS NOT NULL
                AND ST_Covers(zd.geom, p.centroid)
              ORDER BY ST_Area(zd.geom::geography), zd.id
              LIMIT 1
            ) zd ON true
            WHERE p.jurisdiction_id = $1::uuid
              AND p.city = $2
            ORDER BY random()
            LIMIT $4
            """,
            jurisdiction_id, municipality_label, op5_town, SPOT_CHECK_SAMPLE_SIZE,
        )
        spot_total = len(spot_rows)
        for r in spot_rows:
            if r["parcel_code"] and r["parcel_code"] == r["containing_code"] and r["has_matrix"]:
                spot_passes += 1
    finally:
        await conn.close()

    coverage = compute_coverage_pct(parcel_count, zoned)
    spot_pct = compute_coverage_pct(spot_total, spot_passes) if spot_total else 0.0
    return AuditMetrics(
        parcel_count=parcel_count,
        zoned_parcel_count=zoned,
        coverage_pct=coverage,
        matrix_match_pct_of_zoned=matrix_match_pct,
        spot_check_total=spot_total,
        spot_check_passes=spot_passes,
        spot_check_pass_pct=spot_pct,
        binding_method_distribution=binding_dist,
    )


def _muni_label_for_parcels(muni_name: str) -> str:
    """Match the ``parcels.city`` form used during the proof. The DCA
    municipality form is e.g. ``"Garfield city"`` (lowercased suffix).
    Fall back to the raw input when it doesn't match a known pattern.
    """
    if not muni_name:
        return ""
    name = muni_name.strip()
    for suffix in ("Borough", "Township", "Town", "City", "Village"):
        if name.endswith(f" {suffix}"):
            return f"{name[: -len(suffix) - 1]} {suffix.lower()}"
    # Some directories store the lowercased form already.
    return name


# ── pipeline ───────────────────────────────────────────────────────────────


@dataclass
class RunnerHooks:
    """All side-effecting steps are routed through this hook bundle so the
    orchestrator (and unit tests) can swap implementations cleanly without
    monkeypatching globals."""

    extract: Callable[[MuniRecord], ExtractionResult] = default_extract_polygons_from_map
    adjudicate: Callable[[MuniRecord, list[str]], list[dict]] = default_adjudicate_matrix
    ingest: Callable[..., Any] = default_ingest_polygons
    backfill: Callable[..., Any] = default_run_backfill
    audit: Callable[..., Any] = default_audit_muni


async def run_per_muni(
    county: str,
    muni: MuniRecord,
    *,
    preview_branch: str = DEFAULT_PREVIEW_BRANCH,
    nearest_within_meters: float = DEFAULT_NEAREST_WITHIN_METERS,
    artifact_root: Path = ARTIFACT_ROOT,
    force: bool = False,
    hooks: Optional[RunnerHooks] = None,
) -> tuple[int, dict]:
    """Returns (exit_code, summary_dict). Writes cp3_summary.json or
    carve_out.json before returning."""
    hooks = hooks or RunnerHooks()
    started = time.time()
    artifact_dir = muni_artifact_dir(county, muni.muni_name, root=artifact_root)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary_path = cp3_summary_path(county, muni.muni_name, root=artifact_root)
    carve_path = carve_out_path(county, muni.muni_name, root=artifact_root)

    # Idempotency check.
    if summary_path.exists() and not force:
        try:
            prior = json.loads(summary_path.read_text(encoding="utf-8"))
            if prior.get("status") == "complete":
                LOGGER.info(
                    "idempotent: %s/%s already complete; exit 0",
                    county, muni.muni_name,
                )
                return EXIT_COMPLETE_OPERATIONAL, prior
        except json.JSONDecodeError:
            LOGGER.warning("malformed prior summary at %s; re-running", summary_path)

    # CP1 — extraction.
    extraction = hooks.extract(muni)

    # Raster / text-only-legend / absent / vision-empty carve-out.
    carve_reason: Optional[str] = None
    if extraction.source_class in ("raster", "absent"):
        carve_reason = f"source_class={extraction.source_class}"
    elif not extraction.color_to_zone:
        carve_reason = "empty color_to_zone (text-only legend)"
    elif extraction.vision_label_count == 0:
        carve_reason = "vision returned 0 reliable labels at confidence >= 0.75"

    if carve_reason is not None:
        payload = {
            "status": "carve_out",
            "county": county,
            "muni": muni.muni_name,
            "muni_code": muni.muni_code,
            "carve_reason": carve_reason,
            "source_class": extraction.source_class,
            "color_to_zone_keys": sorted(extraction.color_to_zone.keys()),
            "vision_label_count": extraction.vision_label_count,
            "map_url": muni.map_url,
            "ordinance_url": muni.ordinance_url,
            "wall_clock_s": round(time.time() - started, 2),
        }
        carve_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.info("carve-out: %s/%s — %s", county, muni.muni_name, carve_reason)
        return EXIT_CARVE_OUT, payload

    # CP2 — matrix adjudication.
    zone_codes = sorted({
        p.get("zone_code") for p in extraction.polygons if p.get("zone_code")
    })
    matrix_rows = hooks.adjudicate(muni, list(zone_codes))
    matrix_rows_path(county, muni.muni_name, root=artifact_root).write_text(
        json.dumps(matrix_rows, indent=2), encoding="utf-8",
    )

    # CP3 — ingest + backfill + audit.
    try:
        ingest_result = await _maybe_await(
            hooks.ingest(muni, extraction, preview_branch=preview_branch, county=county)
        )
        await _maybe_await(
            hooks.backfill(
                ingest_result.jurisdiction_id,
                nearest_within_meters=nearest_within_meters,
            )
        )
        audit = await _maybe_await(
            hooks.audit(ingest_result.jurisdiction_id, muni, county=county)
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("transient error running CP3 for %s/%s", county, muni.muni_name)
        payload = {
            "status": "transient_error",
            "county": county,
            "muni": muni.muni_name,
            "muni_code": muni.muni_code,
            "error": str(exc),
            "wall_clock_s": round(time.time() - started, 2),
        }
        summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return EXIT_TRANSIENT_ERROR, payload

    is_operational = audit.coverage_pct >= OPERATIONAL_COVERAGE_PCT
    summary = {
        "status": "complete",
        "operational": is_operational,
        "county": county,
        "muni": muni.muni_name,
        "muni_code": muni.muni_code,
        "jurisdiction_id": ingest_result.jurisdiction_id,
        "preview_branch": preview_branch,
        "polygons_written": ingest_result.polygons_written,
        "zone_codes": zone_codes,
        "matrix_rows": len(matrix_rows),
        "nearest_within_meters": nearest_within_meters,
        "parcel_zoning_code_coverage_pct": audit.coverage_pct,
        "matrix_match_pct_of_zoned": audit.matrix_match_pct_of_zoned,
        "spot_check_pass_pct": audit.spot_check_pass_pct,
        "spot_check_total": audit.spot_check_total,
        "spot_check_passes": audit.spot_check_passes,
        "binding_method_distribution": audit.binding_method_distribution,
        "wall_clock_s": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    code = EXIT_COMPLETE_OPERATIONAL if is_operational else EXIT_COMPLETE_NOT_OPERATIONAL
    return code, summary


async def _maybe_await(value: Any) -> Any:
    """Allow hooks to be sync or async."""
    if asyncio.iscoroutine(value):
        return await value
    return value


# ── CLI ────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--county", required=True, help="County name (e.g. bergen)")
    ap.add_argument("--muni", required=True, help="Municipality name (DCA form)")
    ap.add_argument("--preview-branch", default=DEFAULT_PREVIEW_BRANCH)
    ap.add_argument(
        "--nearest-within-meters", type=float, default=DEFAULT_NEAREST_WITHIN_METERS,
        help="Override for backfill_parcel_zoning_from_districts (default 100.0)",
    )
    ap.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--force", action="store_true", help="Ignore idempotency cache")
    ap.add_argument("--log-level", default=os.environ.get("OP5_LOG_LEVEL", "INFO"))
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        muni = find_muni(args.county, args.muni, data_dir=args.data_dir)
    except (FileNotFoundError, KeyError) as exc:
        LOGGER.error("muni lookup failed: %s", exc)
        return EXIT_TRANSIENT_ERROR
    code, summary = asyncio.run(run_per_muni(
        args.county, muni,
        preview_branch=args.preview_branch,
        nearest_within_meters=args.nearest_within_meters,
        artifact_root=args.artifact_root,
        force=args.force,
    ))
    print(json.dumps(summary, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
