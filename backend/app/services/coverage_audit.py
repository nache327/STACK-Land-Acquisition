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

    Returns: {"snapshots_written": N, "summary": <audit summary>}.
    """
    az = _import_audit_module()

    # Resolve the underlying AsyncConnection once — `db.connection()` is async
    # and returns the SQLAlchemy AsyncConnection (which is what the audit
    # script's _load_schema_profile / _build_audit_sql call .execute() on).
    conn = await db.connection()

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

    result = await conn.execute(
        az._build_audit_sql(schema),
        {"jurisdiction_name": jurisdiction_name},
    )
    audits = [az._build_audit(row, schema) for row in result]

    written = 0
    for audit in audits:
        data = asdict(audit)
        # `JurisdictionAudit.id` is a string; cast to UUID for the FK column.
        snap = CoverageSnapshot(
            jurisdiction_id=uuid.UUID(data["id"]),
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
            source=source,
        )
        db.add(snap)
        written += 1
    await db.commit()

    return {
        "snapshots_written": written,
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
