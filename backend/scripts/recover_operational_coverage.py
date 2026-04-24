"""
Operational coverage recovery runner for Supabase/PostGIS.

This is the scrappy production repair entrypoint:
  - merges duplicate jurisdiction rows
  - loads missing parcels/zoning from confirmed public GIS sources
  - backfills parcel zoning by polygon intersection
  - bootstraps zone_use_matrix where ordinance parsing is absent
  - recomputes bbox / coverage_level
  - reruns flood + wetland overlays
  - backfills vacancy using heuristics + building footprints when available

Usage:
    python scripts/recover_operational_coverage.py
    python scripts/recover_operational_coverage.py --jurisdiction Allentown --phase load --phase zoning
    python scripts/recover_operational_coverage.py --strict-vacancy --phase vacancy --phase bbox
    python scripts/recover_operational_coverage.py --allow-candidate-zoning --jurisdiction "Park City"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--jurisdiction",
        action="append",
        default=[],
        help="Jurisdiction name to target. Repeatable. Defaults to all.",
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=[
            "merge-duplicates",
            "load",
            "zoning",
            "matrix",
            "bbox",
            "overlays",
            "vacancy",
        ],
        default=[],
    )
    parser.add_argument(
        "--allow-candidate-zoning",
        action="store_true",
        help="Use candidate zoning sources for blocked jurisdictions such as Park City.",
    )
    parser.add_argument(
        "--strict-vacancy",
        action="store_true",
        help="Force unresolved has_structure values to FALSE after heuristics/buildings.",
    )
    parser.add_argument(
        "--reload-existing",
        action="store_true",
        help="Replace existing parcels/zoning for the targeted jurisdictions instead of skipping loaded data.",
    )
    return parser.parse_args()


ARGS = _parse_args()
if ARGS.database_url:
    os.environ["DATABASE_URL"] = ARGS.database_url

from shapely.ops import unary_union
from sqlalchemy import inspect, select, text

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.services.arcgis_bbox import download_bbox_features
from app.services.matrix_bootstrap import bootstrap_zone_use_matrix
from app.services.overlays import apply_flood_overlay, apply_wetland_overlay
from app.services.pipeline import KNOWN_JURISDICTIONS
from app.services.spatial_backfill import (
    backfill_parcel_zoning_from_districts,
    refresh_jurisdiction_bbox,
    refresh_jurisdiction_coverage_level,
)
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels
from app.services.vacancy import (
    backfill_vacancy_by_heuristics,
    backfill_vacancy_from_buildings,
    finalize_vacancy_backfill,
)
from app.services.zoning_ingestion import ingest_zoning_districts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


UTAH_BUILDINGS_URL = (
    "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Buildings/FeatureServer/0"
)
PARK_CITY_BUILDINGS_URL = (
    "https://cityworks.parkcity.org/arcgis/rest/services/Hosted/Buildings1/FeatureServer/0"
)


@dataclass(frozen=True)
class RecoverySource:
    name: str
    parcel_endpoint: str | None = None
    parcel_where: str = "1=1"
    parcel_clip_endpoint: str | None = None
    parcel_clip_where: str = "1=1"
    zoning_endpoint: str | None = None
    zoning_where: str = "1=1"
    candidate_zoning_endpoints: tuple[str, ...] = ()
    building_endpoint: str | None = None
    building_where: str = "1=1"
    notes: str | None = None


RECOVERY_SOURCES: dict[str, RecoverySource] = {
    "allentown": RecoverySource(
        name="Allentown",
        parcel_endpoint=KNOWN_JURISDICTIONS["allentown"].parcel_endpoint,
        parcel_where="COUNTY_NAME = 'LEHIGH'",
        parcel_clip_endpoint=KNOWN_JURISDICTIONS["allentown"].zoning_polygon_endpoint,
        zoning_endpoint=KNOWN_JURISDICTIONS["allentown"].zoning_polygon_endpoint,
        notes="Confirmed parcel + zoning sources from PA DEP and City of Allentown.",
    ),
    "payson": RecoverySource(
        name="Payson",
        parcel_endpoint=KNOWN_JURISDICTIONS["payson"].parcel_endpoint,
        parcel_where=KNOWN_JURISDICTIONS["payson"].where_clause or "1=1",
        zoning_endpoint=KNOWN_JURISDICTIONS["payson"].zoning_polygon_endpoint,
        building_endpoint=UTAH_BUILDINGS_URL,
        building_where="CITY='Payson'",
        notes="Confirmed UGRC parcels + Utah County zoning group layer + UGRC buildings.",
    ),
    "park city": RecoverySource(
        name="Park City",
        parcel_endpoint=KNOWN_JURISDICTIONS["park city"].parcel_endpoint,
        parcel_clip_endpoint="https://cityworks.parkcity.org/arcgis/rest/services/Hosted/City_limits1/FeatureServer/0",
        parcel_clip_where="name = 'Park City'",
        zoning_endpoint=None,
        candidate_zoning_endpoints=(
            "https://cityworks.parkcity.org/arcgis/rest/services/Hosted/Land_Use1/FeatureServer/0",
            "https://cityworks.parkcity.org/arcgis/rest/services/Hosted/Legacy_Zones1/FeatureServer/0",
        ),
        building_endpoint=PARK_CITY_BUILDINGS_URL,
        notes=(
            "Parcels/buildings confirmed. Zoning source still needs human confirmation; "
            "use --allow-candidate-zoning only if you are willing to treat Park City "
            "land-use/legacy-zone polygons as a temporary zoning proxy."
        ),
    ),
}


DUPLICATE_MERGES: list[tuple[str, str]] = [
    ("Draper, UT", "Draper City, UT"),
]


def _normalize_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r",\s*[a-z]{2}\b", "", name)
    return re.sub(r"\s+", " ", name)


def _city_name_for_buildings(jurisdiction: Jurisdiction) -> str:
    name = jurisdiction.name
    name = re.sub(r",\s*[A-Z]{2}\b", "", name)
    name = name.replace(".", "")
    return name.strip()


async def _existing_tables(db) -> set[str]:
    def run_inspector(sync_conn):
        return set(inspect(sync_conn).get_table_names(schema="public"))

    conn = await db.connection()
    return await conn.run_sync(run_inspector)


async def _get_jurisdictions(db, requested: Iterable[str]) -> list[Jurisdiction]:
    rows = (await db.execute(select(Jurisdiction).order_by(Jurisdiction.name))).scalars().all()
    if not requested:
        return rows
    requested_names = {_normalize_name(name) for name in requested}
    return [j for j in rows if _normalize_name(j.name) in requested_names]


async def _find_jurisdiction(db, name: str) -> Jurisdiction | None:
    normalized = _normalize_name(name)
    jurisdictions = await _get_jurisdictions(db, [])
    for jurisdiction in jurisdictions:
        if _normalize_name(jurisdiction.name) == normalized:
            return jurisdiction
    return None


async def merge_duplicate_jurisdictions(db) -> None:
    tables = await _existing_tables(db)
    for source_name, target_name in DUPLICATE_MERGES:
        source = await _find_jurisdiction(db, source_name)
        target = await _find_jurisdiction(db, target_name)
        if source is None or target is None:
            logger.warning("Duplicate merge skipped: %s -> %s not found", source_name, target_name)
            continue

        if source.id == target.id:
            continue

        logger.info("Merging duplicate jurisdiction %s -> %s", source.name, target.name)
        for table in ("parcels", "zone_use_matrix", "jobs", "shortlists", "zoning_districts", "overlays"):
            if table not in tables:
                continue
            if table == "zone_use_matrix":
                await db.execute(
                    text(
                        """
                        INSERT INTO zone_use_matrix (
                            jurisdiction_id,
                            zone_code,
                            zone_name,
                            self_storage,
                            mini_warehouse,
                            light_industrial,
                            luxury_garage_condo,
                            citations,
                            confidence,
                            human_reviewed,
                            notes,
                            created_at,
                            updated_at
                        )
                        SELECT
                            :target,
                            zone_code,
                            zone_name,
                            self_storage,
                            mini_warehouse,
                            light_industrial,
                            luxury_garage_condo,
                            citations,
                            confidence,
                            human_reviewed,
                            notes,
                            created_at,
                            updated_at
                        FROM zone_use_matrix
                        WHERE jurisdiction_id = :source
                        ON CONFLICT (jurisdiction_id, zone_code) DO NOTHING
                        """
                    ),
                    {"target": target.id, "source": source.id},
                )
                deleted = await db.execute(
                    text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :source"),
                    {"source": source.id},
                )
                if deleted.rowcount:
                    logger.info("  merged %d rows in zone_use_matrix", deleted.rowcount)
                continue

            if table == "zoning_districts":
                await db.execute(
                    text(
                        """
                        INSERT INTO zoning_districts (
                            jurisdiction_id,
                            zone_code,
                            zone_name,
                            zone_class,
                            allowed_uses,
                            max_far,
                            max_height_ft,
                            max_density_dua,
                            min_lot_area_sqft,
                            raw_attributes,
                            geom,
                            centroid,
                            source,
                            confidence,
                            human_reviewed,
                            geom_hash,
                            created_at,
                            updated_at
                        )
                        SELECT
                            :target,
                            zone_code,
                            zone_name,
                            zone_class,
                            allowed_uses,
                            max_far,
                            max_height_ft,
                            max_density_dua,
                            min_lot_area_sqft,
                            raw_attributes,
                            geom,
                            centroid,
                            source,
                            confidence,
                            human_reviewed,
                            geom_hash,
                            created_at,
                            updated_at
                        FROM zoning_districts
                        WHERE jurisdiction_id = :source
                        ON CONFLICT (jurisdiction_id, zone_code, geom_hash) DO NOTHING
                        """
                    ),
                    {"target": target.id, "source": source.id},
                )
                deleted = await db.execute(
                    text("DELETE FROM zoning_districts WHERE jurisdiction_id = :source"),
                    {"source": source.id},
                )
                if deleted.rowcount:
                    logger.info("  merged %d rows in zoning_districts", deleted.rowcount)
                continue

            result = await db.execute(
                text(f"UPDATE {table} SET jurisdiction_id = :target WHERE jurisdiction_id = :source"),
                {"target": target.id, "source": source.id},
            )
            if result.rowcount:
                logger.info("  moved %d rows in %s", result.rowcount, table)

        await db.execute(
            text("DELETE FROM jurisdictions WHERE id = :source"),
            {"source": source.id},
        )
    await db.flush()


def _recovery_source_for(jurisdiction: Jurisdiction) -> RecoverySource:
    key = _normalize_name(jurisdiction.name)
    source = RECOVERY_SOURCES.get(key)
    if source:
        return source

    pipeline_cfg = None
    for alias, cfg in KNOWN_JURISDICTIONS.items():
        if alias == key:
            pipeline_cfg = cfg
            break
    if pipeline_cfg is None:
        return RecoverySource(name=jurisdiction.name)

    building_endpoint = None
    building_where = "1=1"
    if jurisdiction.state == "UT":
        building_endpoint = UTAH_BUILDINGS_URL
        building_where = f"CITY='{_city_name_for_buildings(jurisdiction)}'"

    return RecoverySource(
        name=jurisdiction.name,
        parcel_endpoint=pipeline_cfg.parcel_endpoint,
        parcel_where=pipeline_cfg.where_clause or "1=1",
        zoning_endpoint=pipeline_cfg.zoning_polygon_endpoint or pipeline_cfg.zoning_endpoint,
        zoning_where=pipeline_cfg.zoning_where_clause or "1=1",
        building_endpoint=building_endpoint,
        building_where=building_where,
    )


async def _download_clipped_features(
    source_endpoint: str,
    *,
    where: str,
    clip_endpoint: str,
    clip_where: str,
):
    clip_gdf = await download_all_features(clip_endpoint, where=clip_where)
    if clip_gdf.empty:
        logger.warning("Clip source %s returned 0 rows", clip_endpoint)
        return clip_gdf

    minx, miny, maxx, maxy = clip_gdf.total_bounds
    candidate_gdf = await download_bbox_features(
        source_endpoint,
        (float(minx), float(miny), float(maxx), float(maxy)),
        where=where,
        page_size=1000,
        buffer_ratio=0.02,
    )
    if candidate_gdf is None or candidate_gdf.empty:
        return clip_gdf.iloc[0:0].copy()

    clip_geom = unary_union([geom for geom in clip_gdf.geometry if geom is not None and not geom.is_empty])
    if clip_geom.is_empty:
        logger.warning("Clip source %s had no usable geometry", clip_endpoint)
        return candidate_gdf

    clipped = candidate_gdf[candidate_gdf.geometry.intersects(clip_geom)].copy()
    clipped.reset_index(drop=True, inplace=True)
    logger.info(
        "Spatial clip %s -> %s retained %d / %d features",
        clip_endpoint,
        source_endpoint,
        len(clipped),
        len(candidate_gdf),
    )
    return clipped


async def load_parcels(db, jurisdiction: Jurisdiction, source: RecoverySource) -> int:
    existing = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM parcels WHERE jurisdiction_id = :jid"),
        {"jid": jurisdiction.id},
    )
    if int(existing.scalar_one()) > 0 and not ARGS.reload_existing:
        logger.info("[%s] parcels already present; skipping parcel load", jurisdiction.name)
        return 0
    if not source.parcel_endpoint:
        logger.warning("[%s] no parcel source configured", jurisdiction.name)
        return 0
    logger.info("[%s] downloading parcels from %s", jurisdiction.name, source.parcel_endpoint)
    if source.parcel_clip_endpoint:
        gdf = await _download_clipped_features(
            source.parcel_endpoint,
            where=source.parcel_where,
            clip_endpoint=source.parcel_clip_endpoint,
            clip_where=source.parcel_clip_where,
        )
    else:
        gdf = await download_all_features(source.parcel_endpoint, where=source.parcel_where)
    if gdf.empty:
        logger.warning("[%s] parcel source returned 0 rows", jurisdiction.name)
        return 0
    count = await ingest_parcels(gdf, jurisdiction.id, db, replace=True)
    await refresh_jurisdiction_bbox(jurisdiction, db)
    await db.flush()
    logger.info("[%s] ingested %d parcels", jurisdiction.name, count)
    return count


async def load_zoning(
    db,
    jurisdiction: Jurisdiction,
    source: RecoverySource,
    *,
    allow_candidate_zoning: bool,
) -> int:
    zoning_existing = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM zoning_districts WHERE jurisdiction_id = :jid"),
        {"jid": jurisdiction.id},
    )
    if int(zoning_existing.scalar_one()) > 0 and not ARGS.reload_existing:
        logger.info("[%s] zoning polygons already present; skipping zoning load", jurisdiction.name)
        return 0
    zoning_endpoint = source.zoning_endpoint
    if zoning_endpoint is None and allow_candidate_zoning and source.candidate_zoning_endpoints:
        zoning_endpoint = source.candidate_zoning_endpoints[0]
        logger.warning(
            "[%s] using candidate zoning source %s",
            jurisdiction.name,
            zoning_endpoint,
        )
    if zoning_endpoint is None:
        logger.warning("[%s] no zoning source configured", jurisdiction.name)
        return 0

    logger.info("[%s] downloading zoning from %s", jurisdiction.name, zoning_endpoint)
    gdf = await download_all_features(zoning_endpoint, where=source.zoning_where)
    if gdf.empty:
        logger.warning("[%s] zoning source returned 0 rows", jurisdiction.name)
        return 0
    count = await ingest_zoning_districts(gdf, jurisdiction.id, db, replace=True)
    updated = await backfill_parcel_zoning_from_districts(jurisdiction.id, db)
    logger.info("[%s] ingested %d zoning rows, updated %d parcel zoning rows", jurisdiction.name, count, updated)
    return count


async def run_matrix_phase(db, jurisdictions: Iterable[Jurisdiction]) -> None:
    for jurisdiction in jurisdictions:
        inserted = await bootstrap_zone_use_matrix(jurisdiction.id, db, missing_only=True)
        if inserted:
            logger.info("[%s] bootstrapped %d zone matrix rows", jurisdiction.name, inserted)


async def run_bbox_phase(db, jurisdictions: Iterable[Jurisdiction]) -> None:
    for jurisdiction in jurisdictions:
        bbox = await refresh_jurisdiction_bbox(jurisdiction, db)
        level = await refresh_jurisdiction_coverage_level(jurisdiction, db)
        logger.info("[%s] bbox=%s coverage_level=%s", jurisdiction.name, bbox, level.value)


async def run_overlay_phase(db, jurisdictions: Iterable[Jurisdiction]) -> None:
    for jurisdiction in jurisdictions:
        try:
            flood = await apply_flood_overlay(jurisdiction.id, db)
            wetland = await apply_wetland_overlay(jurisdiction.id, db)
            await db.commit()
            logger.info("[%s] flood=%d wetland=%d", jurisdiction.name, flood, wetland)
        except Exception as exc:
            await db.rollback()
            logger.warning("[%s] overlay backfill failed: %s", jurisdiction.name, exc)


async def run_vacancy_phase(db, jurisdictions: Iterable[Jurisdiction], strict: bool) -> None:
    for jurisdiction in jurisdictions:
        try:
            source = _recovery_source_for(jurisdiction)
            stats = await backfill_vacancy_by_heuristics(jurisdiction.id, db)
            building_hits = 0
            if source.building_endpoint:
                building_hits = await backfill_vacancy_from_buildings(
                    jurisdiction.id,
                    db,
                    source_url=source.building_endpoint,
                    where=source.building_where,
                )
            forced_false = await finalize_vacancy_backfill(
                jurisdiction.id,
                db,
                strict=strict,
            )
            await db.commit()
            logger.info(
                "[%s] vacancy heuristics=%s building_hits=%d forced_false=%d",
                jurisdiction.name,
                stats,
                building_hits,
                forced_false,
            )
        except Exception as exc:
            await db.rollback()
            logger.warning("[%s] vacancy backfill failed: %s", jurisdiction.name, exc)


async def main() -> None:
    phases = ARGS.phase or [
        "merge-duplicates",
        "load",
        "zoning",
        "matrix",
        "bbox",
        "overlays",
        "vacancy",
    ]

    async with async_session_maker() as db:
        jurisdictions = await _get_jurisdictions(db, ARGS.jurisdiction)
        if not jurisdictions:
            raise SystemExit("No matching jurisdictions found.")

        if "merge-duplicates" in phases:
            await merge_duplicate_jurisdictions(db)
            await db.commit()
            jurisdictions = await _get_jurisdictions(db, ARGS.jurisdiction)

        if "load" in phases:
            for jurisdiction in jurisdictions:
                source = _recovery_source_for(jurisdiction)
                if source.parcel_endpoint:
                    await load_parcels(db, jurisdiction, source)
            await db.commit()

        if "zoning" in phases:
            for jurisdiction in jurisdictions:
                source = _recovery_source_for(jurisdiction)
                await load_zoning(
                    db,
                    jurisdiction,
                    source,
                    allow_candidate_zoning=ARGS.allow_candidate_zoning,
                )
            await db.commit()

        if "matrix" in phases:
            await run_matrix_phase(db, jurisdictions)
            await db.commit()

        if "bbox" in phases:
            await run_bbox_phase(db, jurisdictions)
            await db.commit()

        if "overlays" in phases:
            await run_overlay_phase(db, jurisdictions)
            await db.commit()

        if "vacancy" in phases:
            await run_vacancy_phase(db, jurisdictions, strict=ARGS.strict_vacancy)
            await db.commit()

        logger.info("Recovery phases complete: %s", ", ".join(phases))


if __name__ == "__main__":
    asyncio.run(main())
