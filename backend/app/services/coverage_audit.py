"""coverage_audit — thin async wrapper around audit_zoning_coverage CLI logic.

The CLI script at `backend/scripts/audit_zoning_coverage.py` already
computes per-jurisdiction tier counts via a single set of carefully-tuned
SQL queries. This module reuses its `_load_schema_profile`,
`_build_audit_sql`, and `_build_audit` functions; it does NOT duplicate
the SQL. The wrapper persists each `JurisdictionAudit` into the
`coverage_snapshots` table so the dashboard can read pre-computed
coverage instead of running the multi-million-row COUNT queries live.

A full sweep across ~75 jurisdictions runs ~2–3 min on prod-scale data
(the audit script is the bottleneck, not the persistence). Acceptable
for a daily refresh; the optional `jurisdiction_id` parameter scopes
to one for fast operator-triggered checks.
"""
from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.coverage_snapshot import CoverageSnapshot


logger = logging.getLogger(__name__)


# audit_zoning_coverage lives in backend/scripts/, not in app/, so it isn't
# normally importable from app/. Add the scripts dir to sys.path on first use.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))


def _import_audit_module():
    import audit_zoning_coverage  # type: ignore
    return audit_zoning_coverage


async def refresh_all_snapshots(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID | None = None,
    source: str = "manual",
) -> dict:
    """Run the audit, persist one row per jurisdiction into coverage_snapshots.

    Uses a raw asyncpg connection drawn from the SQLAlchemy session's
    underlying engine for the audit query itself — the audit script's SQL
    expects a plain asyncpg-style cursor and bind-parameter syntax.
    Inserts are batched into a single transaction via the SQLAlchemy
    session for atomicity with the rest of the app.

    Uses the long_running_session_maker (command_timeout=3600 as of
    2026-06-08; bumped from 600 after Hunterdon hit the 10-min ceiling)
    for the audit reads — the SQL legitimately takes minutes on big
    counties. The injected `db` (from the request) is used only for the
    snapshot INSERTs at the end.

    Returns: {"snapshots_written": N, "summary": <audit summary>}.
    """
    from app.db import long_running_session_maker
    az = _import_audit_module()

    # Open a long-running session for the audit query (which can take 1-3
    # minutes on Middlesex MA / Mont MD / Mont PA). The injected `db`
    # has command_timeout=90 which is too short for big counties.
    async with long_running_session_maker() as long_running_db:
        return await _refresh_all_snapshots_inner(
            db=db,
            long_running_db=long_running_db,
            az=az,
            jurisdiction_id=jurisdiction_id,
            source=source,
        )


async def _refresh_all_snapshots_inner(
    *,
    db: AsyncSession,
    long_running_db: AsyncSession,
    az,
    jurisdiction_id: uuid.UUID | None,
    source: str,
) -> dict:
    conn = await long_running_db.connection()

    schema = await az._load_schema_profile(conn)
    if not schema.has_parcels_table or not schema.has_zone_use_matrix_table:
        raise RuntimeError(
            "Database missing required tables: parcels and/or zone_use_matrix"
        )

    if jurisdiction_id is not None:
        # The audit SQL accepts a `jurisdiction_name` filter — fetch the name
        # so we can pass it through verbatim.
        from app.models.jurisdiction import Jurisdiction
        j = await db.get(Jurisdiction, jurisdiction_id)
        if j is None:
            raise ValueError(f"jurisdiction {jurisdiction_id} not found")
        jurisdiction_name = j.name
    else:
        jurisdiction_name = None

    # The audit SQL has multiple JOINs over parcels (millions of rows).
    # Default asyncpg/pgbouncer statement_timeout (~30s) is too short for
    # big counties (Mont MD 281k, Mont PA 301k, Middlesex MA 423k all
    # observed timing out). Disable the timeout for this audit query only.
    try:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
    except Exception as exc:
        logger.warning("could not disable statement_timeout for audit (%s); proceeding with default", exc)

    # The audit SQL is heavy + jurisdiction-specific data shapes can break it
    # (observed: Mont MD and Mont PA hit 500s post-Phase-3 ingest, NYC 500'd
    # on muni breakdown before the try/except in line 100 was added).
    # Wrap the execute+build in try/except so per-jurisdiction refresh returns
    # cleanly with snapshots_written=0 instead of HTTP 500.
    try:
        result = await conn.execute(
            az._build_audit_sql(schema),
            {
                "jurisdiction_id": str(jurisdiction_id) if jurisdiction_id is not None else None,
                "jurisdiction_name": jurisdiction_name,
            },
        )
        audits = [az._build_audit(row, schema) for row in result]
    except Exception as exc:
        logger.warning(
            "audit SQL/build failed for jurisdiction_name=%s (%s); returning empty snapshot",
            jurisdiction_name, exc,
        )
        return {
            "snapshots_written": 0,
            "snapshots_failed": 1,
            "summary": {"error": f"audit failed: {type(exc).__name__}: {str(exc)[:200]}"},
        }

    written = 0
    failed = 0
    for audit in audits:
        try:
            data = asdict(audit)
            jid = uuid.UUID(data["id"])
            # Per-municipality rollup — degrades gracefully to a single 'unknown'
            # bucket if `parcels.city` is null across the board for this
            # jurisdiction. Skipped silently on any error so a rollup hiccup
            # doesn't break the broader audit refresh.
            try:
                muni_breakdown = await _per_municipality_breakdown(conn, jid)
            except Exception as exc:
                logger.warning("muni breakdown failed for jurisdiction %s (%s); skipping", jid, exc)
                muni_breakdown = None
        except Exception as exc:
            logger.warning("audit prep failed for jurisdiction (%s); skipping", exc)
            failed += 1
            continue
        # `JurisdictionAudit.id` is a string; cast to UUID for the FK column.
        snap = CoverageSnapshot(
            jurisdiction_id=jid,
            jurisdiction_name=data["name"],
            state=data.get("state"),
            county=data.get("county"),
            coverage_level=data.get("coverage_level"),
            last_indexed_at=_parse_iso(data.get("last_indexed_at")),
            has_bbox=data.get("has_bbox"),
            parcel_count=data.get("parcel_count"),
            parcel_with_geom_count=data.get("parcel_with_geom_count"),
            parcel_with_zoning_code_count=data.get("parcel_with_zoning_code_count"),
            parcel_with_zone_class_count=data.get("parcel_with_zone_class_count"),
            parcel_distinct_zone_count=data.get("parcel_distinct_zone_count"),
            vacant_parcel_count=data.get("vacant_parcel_count"),
            flood_parcel_count=data.get("flood_parcel_count"),
            wetland_parcel_count=data.get("wetland_parcel_count"),
            zoning_district_count=data.get("zoning_district_count"),
            zoning_district_with_geom_count=data.get("zoning_district_with_geom_count"),
            matrix_zone_count=data.get("matrix_zone_count"),
            matrix_self_storage_permitted_count=data.get("matrix_self_storage_permitted_count"),
            matrix_self_storage_conditional_count=data.get("matrix_self_storage_conditional_count"),
            matrix_self_storage_prohibited_count=data.get("matrix_self_storage_prohibited_count"),
            matrix_self_storage_unclear_count=data.get("matrix_self_storage_unclear_count"),
            matrix_human_reviewed_count=data.get("matrix_human_reviewed_count"),
            parcels_with_zoning_code=data.get("parcels_with_zoning_code"),
            parcels_with_matrix_match=data.get("parcels_with_matrix_match"),
            parcels_self_storage_permitted=data.get("parcels_self_storage_permitted"),
            parcels_self_storage_conditional=data.get("parcels_self_storage_conditional"),
            parcels_self_storage_prohibited=data.get("parcels_self_storage_prohibited"),
            parcels_self_storage_unclear=data.get("parcels_self_storage_unclear"),
            parcel_distinct_zone_with_matrix_match_count=data.get("parcel_distinct_zone_with_matrix_match_count"),
            parcel_geom_coverage_pct=data.get("parcel_geom_coverage_pct"),
            parcel_zoning_code_coverage_pct=data.get("parcel_zoning_code_coverage_pct"),
            parcel_zone_class_coverage_pct=data.get("parcel_zone_class_coverage_pct"),
            zoning_polygon_coverage_flag=data.get("zoning_polygon_coverage_flag"),
            matrix_zone_match_pct=data.get("matrix_zone_match_pct"),
            matrix_distinct_zone_match_pct=data.get("matrix_distinct_zone_match_pct"),
            self_storage_classified_parcel_pct=data.get("self_storage_classified_parcel_pct"),
            self_storage_positive_parcel_pct=data.get("self_storage_positive_parcel_pct"),
            operational_readiness=data.get("operational_readiness"),
            blocking_gaps=data.get("blocking_gaps"),
            unmatched_zone_samples=data.get("unmatched_zone_samples"),
            municipality_breakdown=muni_breakdown,
            source=source,
        )
        try:
            db.add(snap)
            await db.flush()
            written += 1
        except Exception as exc:
            logger.warning("snapshot insert failed for jurisdiction %s (%s); rolling back this row", jid, exc)
            try:
                await db.rollback()
            except Exception:
                pass
            failed += 1
            continue
    try:
        await db.commit()
    except Exception as exc:
        logger.warning("final commit failed (%s); attempting rollback", exc)
        try:
            await db.rollback()
        except Exception:
            pass

    return {
        "snapshots_written": written,
        "snapshots_failed": failed,
        "summary": az._summary(audits),
    }


async def latest_snapshots(db: AsyncSession) -> list[CoverageSnapshot]:
    """Return the most recent snapshot per jurisdiction. Single fast query —
    O(snapshots) not O(parcels)."""
    result = await db.execute(text(
        """
        SELECT DISTINCT ON (jurisdiction_id) *
        FROM coverage_snapshots
        ORDER BY jurisdiction_id, captured_at DESC
        """
    ))
    rows = result.mappings().all()
    # Hydrate into ORM objects so the route can return them via response_model.
    out: list[CoverageSnapshot] = []
    for r in rows:
        snap = CoverageSnapshot(**{k: r[k] for k in r.keys() if hasattr(CoverageSnapshot, k)})
        out.append(snap)
    return out


def _parse_iso(value: Any) -> Any:
    """Audit script stores last_indexed_at as ISO string; coerce to datetime
    for the DateTime column."""
    if value is None:
        return None
    if hasattr(value, "year"):  # already a datetime
        return value
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def source_distribution_for_all(
    db: AsyncSession,
) -> dict[str, dict]:
    """Compute per-jurisdiction source-confidence distribution + counts.

    Returns a dict keyed by jurisdiction_id (str), with each value:
      {
        "source_count_total": int,
        "source_count_verified": int,
        "source_count_rejected": int,
        "source_count_pending": int,
        "source_confidence_distribution": {
          "0-30": int, "30-50": int, "50-70": int, "70-90": int, "90-100": int
        }
      }

    Computed via a single SQL aggregate; safe to embed inline in the
    /admin/coverage GET response.
    """
    from sqlalchemy import text as _text
    try:
        rows = (await db.execute(
            _text(
                """
                SELECT
                    jurisdiction_id::text AS jid,
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE validation_status = 'verified')::int AS verified,
                    COUNT(*) FILTER (WHERE validation_status = 'rejected')::int AS rejected,
                    COUNT(*) FILTER (WHERE validation_status = 'pending')::int AS pending,
                    COUNT(*) FILTER (WHERE confidence_score >= 0  AND confidence_score < 30)::int AS b0_30,
                    COUNT(*) FILTER (WHERE confidence_score >= 30 AND confidence_score < 50)::int AS b30_50,
                    COUNT(*) FILTER (WHERE confidence_score >= 50 AND confidence_score < 70)::int AS b50_70,
                    COUNT(*) FILTER (WHERE confidence_score >= 70 AND confidence_score < 90)::int AS b70_90,
                    COUNT(*) FILTER (WHERE confidence_score >= 90)::int AS b90_100
                FROM zoning_sources
                WHERE jurisdiction_id IS NOT NULL
                GROUP BY jurisdiction_id
                """
            )
        )).mappings().all()
        return {
            r["jid"]: {
                "source_count_total": r["total"],
                "source_count_verified": r["verified"],
                "source_count_rejected": r["rejected"],
                "source_count_pending": r["pending"],
                "source_confidence_distribution": {
                    "0-30": r["b0_30"],
                    "30-50": r["b30_50"],
                    "50-70": r["b50_70"],
                    "70-90": r["b70_90"],
                    "90-100": r["b90_100"],
                },
            }
            for r in rows
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "source_distribution_for_all failed: %r", exc,
        )
        return {}


async def progression_for_jurisdiction(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID,
    days: int = 30,
) -> list[dict]:
    """Return a time-series of coverage_snapshots for one jurisdiction over
    the last N days. Cheap query — single index scan on coverage_snapshots.

    Each row: {captured_at, parcel_with_zoning_code_count, zoning_district_count,
    operational_readiness}. Used by operators to see progression without
    raw SQL.
    """
    from sqlalchemy import text as _text
    rows = (await db.execute(
        _text(
            """
            SELECT
                captured_at,
                parcel_count,
                parcel_with_zoning_code_count,
                zoning_district_count,
                operational_readiness
            FROM coverage_snapshots
            WHERE jurisdiction_id = :jid
              AND captured_at > NOW() - (:days || ' days')::interval
            ORDER BY captured_at
            """
        ),
        {"jid": jurisdiction_id, "days": str(days)},
    )).mappings().all()
    return [
        {
            "captured_at": r["captured_at"].isoformat() if r["captured_at"] else None,
            "parcel_count": r["parcel_count"],
            "parcel_with_zoning_code_count": r["parcel_with_zoning_code_count"],
            "zoning_district_count": r["zoning_district_count"],
            "operational_readiness": r["operational_readiness"],
        }
        for r in rows
    ]


async def _per_municipality_breakdown(
    conn, jurisdiction_id: uuid.UUID,
) -> dict | None:
    """Roll up parcels + zoning_overlays per `parcels.city` for one jurisdiction.

    Returns a dict shaped like:
      {town_name: {parcels, parcels_with_zoning, zoning_overlays}}

    Skips zoning_districts per-town (no city column on zoning_districts).
    Returns None if the jurisdiction has zero parcels with a non-null
    city — i.e. when the per-muni rollup would be a single 'unknown'
    bucket equal to the per-jurisdiction count anyway.

    Defensive: ANY exception swallows + returns None so a rollup hiccup
    doesn't break the broader audit refresh.
    """
    from sqlalchemy import text as _text
    try:
        rows = (await conn.execute(
            _text(
                """
                SELECT
                    COALESCE(NULLIF(TRIM(city), ''), 'unknown') AS town,
                    COUNT(*)::int AS parcels,
                    COUNT(*) FILTER (
                        WHERE zoning_code IS NOT NULL AND zoning_code != ''
                    )::int AS parcels_with_zoning
                FROM parcels
                WHERE jurisdiction_id = :jid
                GROUP BY COALESCE(NULLIF(TRIM(city), ''), 'unknown')
                HAVING COUNT(*) > 0
                """
            ),
            {"jid": jurisdiction_id},
        )).mappings().all()

        if not rows:
            return None
        # Skip the rollup if every parcel is in the single 'unknown' bucket
        # — that's no better than the per-jurisdiction count.
        if len(rows) == 1 and rows[0]["town"] == "unknown":
            return None

        overlay_rows = (await conn.execute(
            _text(
                """
                SELECT
                    COALESCE(NULLIF(TRIM(p.city), ''), 'unknown') AS town,
                    COUNT(*)::int AS overlays
                FROM zoning_overlays o
                JOIN parcels p ON p.id = o.parcel_id
                WHERE p.jurisdiction_id = :jid
                GROUP BY COALESCE(NULLIF(TRIM(p.city), ''), 'unknown')
                """
            ),
            {"jid": jurisdiction_id},
        )).mappings().all()
        overlays_by_town = {r["town"]: r["overlays"] for r in overlay_rows}

        return {
            r["town"]: {
                "parcels": r["parcels"],
                "parcels_with_zoning": r["parcels_with_zoning"],
                "zoning_overlays": overlays_by_town.get(r["town"], 0),
            }
            for r in rows
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "per-muni rollup failed for %s: %r", jurisdiction_id, exc,
        )
        return None
