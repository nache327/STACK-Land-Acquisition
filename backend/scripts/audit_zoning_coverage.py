"""
Comprehensive zoning coverage audit for self-storage sourcing readiness.

This is intentionally stricter than jurisdictions.coverage_level.

It measures, per jurisdiction:
  - parcel coverage
  - zoning polygon coverage
  - zone-use-matrix coverage over actual parcel zoning codes
  - self-storage classification coverage
  - operational readiness for the candidate parcel search flow

Usage:
    python scripts/audit_zoning_coverage.py
    python scripts/audit_zoning_coverage.py --json
    python scripts/audit_zoning_coverage.py --jurisdiction "Draper City, UT"
    python scripts/audit_zoning_coverage.py --database-url postgresql+asyncpg://...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings


@dataclass
class SchemaProfile:
    has_parcels_table: bool
    has_zone_use_matrix_table: bool
    has_zoning_districts_table: bool
    has_overlays_table: bool
    has_parcel_zone_class_column: bool
    has_parcel_zone_binding_method_column: bool
    has_jurisdiction_coverage_level_column: bool
    has_jurisdiction_bbox_column: bool


@dataclass
class JurisdictionAudit:
    id: str
    name: str
    state: str
    county: str | None
    coverage_level: str | None
    last_indexed_at: str | None
    has_bbox: bool
    parcel_count: int
    parcel_with_geom_count: int
    parcel_with_zoning_code_count: int
    parcel_with_zone_class_count: int
    parcel_zoning_code_contained_count: int
    parcel_zoning_code_nearest_count: int
    vacant_parcel_count: int
    flood_parcel_count: int
    wetland_parcel_count: int
    parcel_distinct_zone_count: int
    zoning_district_count: int
    zoning_district_with_geom_count: int
    matrix_zone_count: int
    matrix_self_storage_permitted_count: int
    matrix_self_storage_conditional_count: int
    matrix_self_storage_prohibited_count: int
    matrix_self_storage_unclear_count: int
    matrix_human_reviewed_count: int
    parcels_with_zoning_code: int
    parcels_with_matrix_match: int
    parcels_self_storage_permitted: int
    parcels_self_storage_conditional: int
    parcels_self_storage_prohibited: int
    parcels_self_storage_unclear: int
    parcel_distinct_zone_with_matrix_match_count: int
    unmatched_zone_samples: list[str]
    parcel_geom_coverage_pct: float
    parcel_zoning_code_coverage_pct: float
    parcel_zoning_code_coverage_pct_contained: float
    parcel_zoning_code_coverage_pct_nearest: float
    parcel_zone_class_coverage_pct: float
    zoning_polygon_coverage_flag: bool
    matrix_zone_match_pct: float
    matrix_distinct_zone_match_pct: float
    self_storage_classified_parcel_pct: float
    self_storage_positive_parcel_pct: float
    operational_readiness: str
    blocking_gaps: list[str]


async def _load_schema_profile(conn) -> SchemaProfile:
    table_rows = await conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('parcels', 'zone_use_matrix', 'zoning_districts', 'jurisdictions', 'overlays')
            """
        )
    )
    tables = {row.table_name for row in table_rows}

    column_rows = await conn.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('parcels', 'jurisdictions')
            """
        )
    )
    columns = {(row.table_name, row.column_name) for row in column_rows}

    return SchemaProfile(
        has_parcels_table="parcels" in tables,
        has_zone_use_matrix_table="zone_use_matrix" in tables,
        has_zoning_districts_table="zoning_districts" in tables,
        has_overlays_table="overlays" in tables,
        has_parcel_zone_class_column=("parcels", "zone_class") in columns,
        has_parcel_zone_binding_method_column=(
            "parcels",
            "zone_binding_method",
        ) in columns,
        has_jurisdiction_coverage_level_column=("jurisdictions", "coverage_level") in columns,
        has_jurisdiction_bbox_column=("jurisdictions", "bbox") in columns,
    )


def _build_audit_sql(schema: SchemaProfile):
    coverage_level_expr = (
        "j.coverage_level"
        if schema.has_jurisdiction_coverage_level_column
        else "NULL::text AS coverage_level"
    )
    has_bbox_expr = (
        "j.bbox IS NOT NULL AS has_bbox"
        if schema.has_jurisdiction_bbox_column
        else "FALSE AS has_bbox"
    )
    zone_class_count_expr = (
        "COUNT(*) FILTER (WHERE p.zone_class IS NOT NULL)::bigint AS parcel_with_zone_class_count"
        if schema.has_parcel_zone_class_column
        else "0::bigint AS parcel_with_zone_class_count"
    )
    # Binding-method split: contained vs nearest-fallback. Only counts parcels
    # that have zoning_code populated (i.e. show up in the numerator of the
    # operational ≥70% gate). If the column is absent, both counts are zero
    # and parcel_zoning_code_coverage_pct_contained collapses to the existing
    # total — preserves the operational gate semantics on un-migrated DBs.
    if schema.has_parcel_zone_binding_method_column:
        zone_binding_method_count_exprs = (
            "COUNT(*) FILTER ("
            "  WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> ''"
            "    AND p.zone_binding_method = 'contained'"
            ")::bigint AS parcel_zoning_code_contained_count,\n"
            "                COUNT(*) FILTER ("
            "  WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> ''"
            "    AND p.zone_binding_method IS NOT NULL"
            "    AND p.zone_binding_method LIKE 'nearest_%'"
            ")::bigint AS parcel_zoning_code_nearest_count"
        )
    else:
        zone_binding_method_count_exprs = (
            "0::bigint AS parcel_zoning_code_contained_count,\n"
            "                0::bigint AS parcel_zoning_code_nearest_count"
        )
    zoning_stats_cte = (
        """
        zoning_stats AS (
            SELECT
                zd.jurisdiction_id,
                COUNT(*)::bigint AS zoning_district_count,
                COUNT(*) FILTER (WHERE zd.geom IS NOT NULL)::bigint AS zoning_district_with_geom_count
            FROM zoning_districts zd
            GROUP BY zd.jurisdiction_id
        ),
        """
        if schema.has_zoning_districts_table
        else """
        zoning_stats AS (
            SELECT
                NULL::uuid AS jurisdiction_id,
                0::bigint AS zoning_district_count,
                0::bigint AS zoning_district_with_geom_count
            WHERE FALSE
        ),
        """
    )
    return text(
        f"""
        WITH parcel_stats AS (
            SELECT
                p.jurisdiction_id,
                COUNT(*)::bigint AS parcel_count,
                COUNT(*) FILTER (WHERE p.geom IS NOT NULL)::bigint AS parcel_with_geom_count,
                COUNT(*) FILTER (WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> '')::bigint AS parcel_with_zoning_code_count,
                {zone_class_count_expr},
                {zone_binding_method_count_exprs},
                COUNT(*) FILTER (WHERE p.has_structure IS FALSE)::bigint AS vacant_parcel_count,
                COUNT(*) FILTER (WHERE p.in_flood_zone IS TRUE)::bigint AS flood_parcel_count,
                COUNT(*) FILTER (WHERE p.in_wetland IS TRUE)::bigint AS wetland_parcel_count
            FROM parcels p
            GROUP BY p.jurisdiction_id
        ),
        distinct_parcel_zones AS (
            SELECT
                p.jurisdiction_id,
                COUNT(DISTINCT p.zoning_code)::bigint AS parcel_distinct_zone_count
            FROM parcels p
            WHERE p.zoning_code IS NOT NULL
              AND btrim(p.zoning_code) <> ''
            GROUP BY p.jurisdiction_id
        ),
        {zoning_stats_cte}
        matrix_stats AS (
            SELECT
                zum.jurisdiction_id,
                COUNT(*)::bigint AS matrix_zone_count,
                COUNT(*) FILTER (WHERE zum.self_storage = 'permitted')::bigint AS matrix_self_storage_permitted_count,
                COUNT(*) FILTER (WHERE zum.self_storage = 'conditional')::bigint AS matrix_self_storage_conditional_count,
                COUNT(*) FILTER (WHERE zum.self_storage = 'prohibited')::bigint AS matrix_self_storage_prohibited_count,
                COUNT(*) FILTER (WHERE zum.self_storage = 'unclear')::bigint AS matrix_self_storage_unclear_count,
                COUNT(*) FILTER (WHERE zum.human_reviewed IS TRUE)::bigint AS matrix_human_reviewed_count
            FROM zone_use_matrix zum
            GROUP BY zum.jurisdiction_id
        ),
        parcel_zone_matrix AS (
            SELECT
                p.jurisdiction_id,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                )::bigint AS parcels_with_zoning_code,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                )::bigint AS parcels_with_matrix_match,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                      AND zum.self_storage = 'permitted'
                )::bigint AS parcels_self_storage_permitted,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                      AND zum.self_storage = 'conditional'
                )::bigint AS parcels_self_storage_conditional,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                      AND zum.self_storage = 'prohibited'
                )::bigint AS parcels_self_storage_prohibited,
                COUNT(*) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                      AND zum.self_storage = 'unclear'
                )::bigint AS parcels_self_storage_unclear,
                COUNT(DISTINCT p.zoning_code) FILTER (
                    WHERE p.zoning_code IS NOT NULL
                      AND btrim(p.zoning_code) <> ''
                      AND zum.zone_code IS NOT NULL
                )::bigint AS parcel_distinct_zone_with_matrix_match_count
            FROM parcels p
            LEFT JOIN zone_use_matrix zum
              ON zum.jurisdiction_id = p.jurisdiction_id
             AND zum.zone_code = p.zoning_code
            GROUP BY p.jurisdiction_id
        ),
        unmatched_zone_samples AS (
            SELECT
                sample.jurisdiction_id,
                json_agg(sample.zoning_code ORDER BY sample.parcel_count DESC, sample.zoning_code) AS unmatched_zone_samples
            FROM (
                SELECT
                    p.jurisdiction_id,
                    p.zoning_code,
                    COUNT(*)::bigint AS parcel_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.jurisdiction_id
                        ORDER BY COUNT(*) DESC, p.zoning_code
                    ) AS rn
                FROM parcels p
                LEFT JOIN zone_use_matrix zum
                  ON zum.jurisdiction_id = p.jurisdiction_id
                 AND zum.zone_code = p.zoning_code
                WHERE p.zoning_code IS NOT NULL
                  AND btrim(p.zoning_code) <> ''
                  AND zum.zone_code IS NULL
                GROUP BY p.jurisdiction_id, p.zoning_code
            ) sample
            WHERE sample.rn <= 10
            GROUP BY sample.jurisdiction_id
        )
        SELECT
            j.id,
            j.name,
            j.state,
            j.county,
            {coverage_level_expr},
            j.last_indexed_at,
            {has_bbox_expr},
            COALESCE(ps.parcel_count, 0) AS parcel_count,
            COALESCE(ps.parcel_with_geom_count, 0) AS parcel_with_geom_count,
            COALESCE(ps.parcel_with_zoning_code_count, 0) AS parcel_with_zoning_code_count,
            COALESCE(ps.parcel_with_zone_class_count, 0) AS parcel_with_zone_class_count,
            COALESCE(ps.parcel_zoning_code_contained_count, 0) AS parcel_zoning_code_contained_count,
            COALESCE(ps.parcel_zoning_code_nearest_count, 0) AS parcel_zoning_code_nearest_count,
            COALESCE(ps.vacant_parcel_count, 0) AS vacant_parcel_count,
            COALESCE(ps.flood_parcel_count, 0) AS flood_parcel_count,
            COALESCE(ps.wetland_parcel_count, 0) AS wetland_parcel_count,
            COALESCE(dpz.parcel_distinct_zone_count, 0) AS parcel_distinct_zone_count,
            COALESCE(zs.zoning_district_count, 0) AS zoning_district_count,
            COALESCE(zs.zoning_district_with_geom_count, 0) AS zoning_district_with_geom_count,
            COALESCE(ms.matrix_zone_count, 0) AS matrix_zone_count,
            COALESCE(ms.matrix_self_storage_permitted_count, 0) AS matrix_self_storage_permitted_count,
            COALESCE(ms.matrix_self_storage_conditional_count, 0) AS matrix_self_storage_conditional_count,
            COALESCE(ms.matrix_self_storage_prohibited_count, 0) AS matrix_self_storage_prohibited_count,
            COALESCE(ms.matrix_self_storage_unclear_count, 0) AS matrix_self_storage_unclear_count,
            COALESCE(ms.matrix_human_reviewed_count, 0) AS matrix_human_reviewed_count,
            COALESCE(pzm.parcels_with_zoning_code, 0) AS parcels_with_zoning_code,
            COALESCE(pzm.parcels_with_matrix_match, 0) AS parcels_with_matrix_match,
            COALESCE(pzm.parcels_self_storage_permitted, 0) AS parcels_self_storage_permitted,
            COALESCE(pzm.parcels_self_storage_conditional, 0) AS parcels_self_storage_conditional,
            COALESCE(pzm.parcels_self_storage_prohibited, 0) AS parcels_self_storage_prohibited,
            COALESCE(pzm.parcels_self_storage_unclear, 0) AS parcels_self_storage_unclear,
            COALESCE(pzm.parcel_distinct_zone_with_matrix_match_count, 0) AS parcel_distinct_zone_with_matrix_match_count,
            COALESCE(uzs.unmatched_zone_samples, '[]'::json) AS unmatched_zone_samples
        FROM jurisdictions j
        LEFT JOIN parcel_stats ps ON ps.jurisdiction_id = j.id
        LEFT JOIN distinct_parcel_zones dpz ON dpz.jurisdiction_id = j.id
        LEFT JOIN zoning_stats zs ON zs.jurisdiction_id = j.id
        LEFT JOIN matrix_stats ms ON ms.jurisdiction_id = j.id
        LEFT JOIN parcel_zone_matrix pzm ON pzm.jurisdiction_id = j.id
        LEFT JOIN unmatched_zone_samples uzs ON uzs.jurisdiction_id = j.id
        WHERE (
            CAST(:jurisdiction_name AS text) IS NULL
            OR lower(j.name) = lower(CAST(:jurisdiction_name AS text))
        )
        ORDER BY j.name
        """
    )


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _operational_readiness(
    blocking_gaps: list[str],
    parcel_count: int,
    parcel_zoning_code_coverage_pct: float,
) -> str:
    if parcel_count == 0:
        return "not_loaded"
    if parcel_zoning_code_coverage_pct < 70.0:
        return "partial"
    if not blocking_gaps:
        return "operational"
    return "partial"


def _build_audit(row: Any, schema: SchemaProfile) -> JurisdictionAudit:
    parcel_geom_coverage_pct = _pct(row.parcel_with_geom_count, row.parcel_count)
    parcel_zoning_code_coverage_pct = _pct(
        row.parcel_with_zoning_code_count, row.parcel_count
    )
    parcel_zoning_code_coverage_pct_contained = _pct(
        row.parcel_zoning_code_contained_count, row.parcel_count
    )
    parcel_zoning_code_coverage_pct_nearest = _pct(
        row.parcel_zoning_code_nearest_count, row.parcel_count
    )
    parcel_zone_class_coverage_pct = _pct(
        row.parcel_with_zone_class_count, row.parcel_count
    )
    matrix_zone_match_pct = _pct(
        row.parcels_with_matrix_match, row.parcels_with_zoning_code
    )
    matrix_distinct_zone_match_pct = _pct(
        row.parcel_distinct_zone_with_matrix_match_count, row.parcel_distinct_zone_count
    )
    self_storage_classified_parcel_pct = _pct(
        row.parcels_self_storage_permitted
        + row.parcels_self_storage_conditional
        + row.parcels_self_storage_prohibited,
        row.parcels_with_matrix_match,
    )
    self_storage_positive_parcel_pct = _pct(
        row.parcels_self_storage_permitted + row.parcels_self_storage_conditional,
        row.parcels_with_matrix_match,
    )

    blocking_gaps: list[str] = []
    if row.parcel_count == 0:
        blocking_gaps.append("no_parcels")
    if row.parcel_with_geom_count == 0 and row.parcel_count > 0:
        blocking_gaps.append("no_parcel_geometry")
    if row.parcel_with_zoning_code_count == 0 and row.parcel_count > 0:
        blocking_gaps.append("no_parcel_zoning_codes")
    if row.matrix_zone_count == 0:
        blocking_gaps.append("no_zone_use_matrix")
    if row.parcels_with_zoning_code > 0 and row.parcels_with_matrix_match == 0:
        blocking_gaps.append("no_matrix_matches_for_parcel_zones")
    if row.parcels_with_zoning_code > 0 and matrix_zone_match_pct < 90.0:
        blocking_gaps.append("low_matrix_match_pct")
    if row.parcels_with_matrix_match > 0 and self_storage_classified_parcel_pct < 95.0:
        blocking_gaps.append("high_unclear_self_storage_share")
    if not schema.has_parcel_zone_class_column:
        blocking_gaps.append("missing_parcel_zone_class_column")
    if not schema.has_zoning_districts_table:
        blocking_gaps.append("missing_zoning_districts_table")
    elif row.zoning_district_count == 0:
        # `no_zoning_polygons` is only a real blocker when parcels lack
        # zoning_code coverage. Many jurisdictions (Lake IL, Mont MD, Howard MD,
        # Loudoun VA, Allentown PA, most UT cities) carry zoning_code on the
        # parcel record itself — no separate polygon layer is needed for
        # parcel-level verdicts. If zoning_code coverage is high AND matrix
        # is bound at >=90%, parcel-source zoning is sufficient.
        parcel_source_zoned = (
            row.parcels_with_zoning_code > 1000
            and parcel_zoning_code_coverage_pct >= 80.0
            and row.matrix_zone_count > 0
            and matrix_zone_match_pct >= 90.0
        )
        if not parcel_source_zoned:
            blocking_gaps.append("no_zoning_polygons")
    if not schema.has_jurisdiction_bbox_column:
        blocking_gaps.append("missing_jurisdiction_bbox_column")
    elif not row.has_bbox:
        blocking_gaps.append("missing_bbox")
    if not schema.has_overlays_table:
        blocking_gaps.append("missing_overlays_table")
    if row.coverage_level == "full" and blocking_gaps:
        blocking_gaps.append("coverage_level_overstates_readiness")

    return JurisdictionAudit(
        id=str(row.id),
        name=row.name,
        state=row.state,
        county=row.county,
        coverage_level=row.coverage_level,
        last_indexed_at=row.last_indexed_at.isoformat() if row.last_indexed_at else None,
        has_bbox=bool(row.has_bbox),
        parcel_count=int(row.parcel_count),
        parcel_with_geom_count=int(row.parcel_with_geom_count),
        parcel_with_zoning_code_count=int(row.parcel_with_zoning_code_count),
        parcel_with_zone_class_count=int(row.parcel_with_zone_class_count),
        parcel_zoning_code_contained_count=int(row.parcel_zoning_code_contained_count),
        parcel_zoning_code_nearest_count=int(row.parcel_zoning_code_nearest_count),
        vacant_parcel_count=int(row.vacant_parcel_count),
        flood_parcel_count=int(row.flood_parcel_count),
        wetland_parcel_count=int(row.wetland_parcel_count),
        parcel_distinct_zone_count=int(row.parcel_distinct_zone_count),
        zoning_district_count=int(row.zoning_district_count),
        zoning_district_with_geom_count=int(row.zoning_district_with_geom_count),
        matrix_zone_count=int(row.matrix_zone_count),
        matrix_self_storage_permitted_count=int(row.matrix_self_storage_permitted_count),
        matrix_self_storage_conditional_count=int(row.matrix_self_storage_conditional_count),
        matrix_self_storage_prohibited_count=int(row.matrix_self_storage_prohibited_count),
        matrix_self_storage_unclear_count=int(row.matrix_self_storage_unclear_count),
        matrix_human_reviewed_count=int(row.matrix_human_reviewed_count),
        parcels_with_zoning_code=int(row.parcels_with_zoning_code),
        parcels_with_matrix_match=int(row.parcels_with_matrix_match),
        parcels_self_storage_permitted=int(row.parcels_self_storage_permitted),
        parcels_self_storage_conditional=int(row.parcels_self_storage_conditional),
        parcels_self_storage_prohibited=int(row.parcels_self_storage_prohibited),
        parcels_self_storage_unclear=int(row.parcels_self_storage_unclear),
        parcel_distinct_zone_with_matrix_match_count=int(
            row.parcel_distinct_zone_with_matrix_match_count
        ),
        unmatched_zone_samples=list(row.unmatched_zone_samples or []),
        parcel_geom_coverage_pct=parcel_geom_coverage_pct,
        parcel_zoning_code_coverage_pct=parcel_zoning_code_coverage_pct,
        parcel_zoning_code_coverage_pct_contained=parcel_zoning_code_coverage_pct_contained,
        parcel_zoning_code_coverage_pct_nearest=parcel_zoning_code_coverage_pct_nearest,
        parcel_zone_class_coverage_pct=parcel_zone_class_coverage_pct,
        zoning_polygon_coverage_flag=int(row.zoning_district_count) > 0,
        matrix_zone_match_pct=matrix_zone_match_pct,
        matrix_distinct_zone_match_pct=matrix_distinct_zone_match_pct,
        self_storage_classified_parcel_pct=self_storage_classified_parcel_pct,
        self_storage_positive_parcel_pct=self_storage_positive_parcel_pct,
        operational_readiness=_operational_readiness(
            blocking_gaps,
            int(row.parcel_count),
            parcel_zoning_code_coverage_pct,
        ),
        blocking_gaps=blocking_gaps,
    )


def _summary(audits: list[JurisdictionAudit]) -> dict[str, Any]:
    return {
        "jurisdiction_count": len(audits),
        "operational_count": sum(a.operational_readiness == "operational" for a in audits),
        "partial_count": sum(a.operational_readiness == "partial" for a in audits),
        "not_loaded_count": sum(a.operational_readiness == "not_loaded" for a in audits),
        "with_parcels_count": sum(a.parcel_count > 0 for a in audits),
        "with_matrix_count": sum(a.matrix_zone_count > 0 for a in audits),
        "with_zoning_polygons_count": sum(a.zoning_district_count > 0 for a in audits),
        "with_good_matrix_match_count": sum(a.matrix_zone_match_pct >= 90.0 for a in audits),
    }


def _print_table(audits: list[JurisdictionAudit]) -> None:
    header = (
        f"{'Jurisdiction':32} {'Ready':12} {'Parcels':>8} {'ZCodes%':>7} "
        f"{'Matrix%':>7} {'Poly':>5} {'Unclear%':>8}  Gaps"
    )
    print(header)
    print("-" * len(header))
    for audit in audits:
        unclear_pct = round(
            100.0 - audit.self_storage_classified_parcel_pct, 1
        ) if audit.parcels_with_matrix_match > 0 else 100.0
        gaps = ",".join(audit.blocking_gaps[:3]) if audit.blocking_gaps else "-"
        print(
            f"{audit.name[:32]:32} "
            f"{audit.operational_readiness:12} "
            f"{audit.parcel_count:8d} "
            f"{audit.parcel_zoning_code_coverage_pct:7.1f} "
            f"{audit.matrix_zone_match_pct:7.1f} "
            f"{('yes' if audit.zoning_polygon_coverage_flag else 'no'):>5} "
            f"{unclear_pct:8.1f}  "
            f"{gaps}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit zoning coverage by jurisdiction")
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--jurisdiction", help="Filter to a single jurisdiction name")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    settings = Settings()
    database_url = args.database_url or settings.database_url
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )

    async with engine.connect() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        schema = await _load_schema_profile(conn)
        if not schema.has_parcels_table or not schema.has_zone_use_matrix_table:
            raise RuntimeError(
                "Database does not contain the required public.parcels and public.zone_use_matrix tables"
            )
        result = await conn.execute(
            _build_audit_sql(schema), {"jurisdiction_name": args.jurisdiction}
        )
        audits = [_build_audit(row, schema) for row in result]

    await engine.dispose()

    payload = {
        "schema_profile": asdict(schema),
        "summary": _summary(audits),
        "jurisdictions": [asdict(audit) for audit in audits],
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Zoning coverage audit")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print()
    _print_table(audits)


if __name__ == "__main__":
    asyncio.run(main())
