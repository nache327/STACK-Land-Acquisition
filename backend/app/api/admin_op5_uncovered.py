"""Op-5 uncovered-zone-codes enumeration API.

GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id=<uuid>

Returns the list of zone_codes that appear in `parcels` for a given
jurisdiction but have NO matching row in `zone_use_matrix`, ranked by
parcel count, with up to 3 sample municipality names per code.

This is the worklist driver for the Bergen matrix-completion sprint
(Phase 3): instead of reading the audit JSON's `unmatched_zone_samples`
(capped at 10) and re-running a per-juris query, callers can hit this
endpoint to enumerate the full long tail in one shot and prioritize the
highest-parcel-count gaps first. Reusable for Morris / Monmouth / Essex
sprints when those land.

Scope of reads:
    * `jurisdictions` — 404 resolution + name in the response envelope.
    * `parcels`        — zoning_code population and per-(code, city) counts.
    * `zone_use_matrix` — the LEFT-JOIN-IS-NULL filter that defines
      "uncovered".

Scope of writes: NONE. This endpoint is strictly read-only.

Join semantics:
    Jurisdiction-wide LEFT JOIN, mirroring `backend/scripts/
    audit_zoning_coverage.py` lines 244-300. Specifically:

        LEFT JOIN zone_use_matrix zum
          ON zum.jurisdiction_id = p.jurisdiction_id
         AND zum.zone_code       = p.zoning_code

    NOTE: the join is intentionally NOT muni-scoped — a county-default
    matrix row (municipality IS NULL) covers every parcel of that
    zone_code in the jurisdiction, regardless of which town the parcel
    lives in. Mirroring the audit's semantics is the whole point: this
    endpoint exists to enumerate the same "uncovered" set the audit
    surfaces in its top-10 sample.

Auth:
    No auth dependency, matching the existing /api/admin/op5/* and
    /api/jurisdictions/{id}/_upload-matrix-rows posture. Master can add
    an auth dep in one line via include_router(dependencies=...) when
    the codebase changes its admin auth posture.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.jurisdiction import Jurisdiction

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-op5"], prefix="/admin/op5")


# ────────────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────────────


class UncoveredZoneCodeRow(BaseModel):
    """One uncovered zone_code with its parcel count and top-3 muni samples."""

    zone_code: str
    parcel_count: int
    # Top 3 municipalities (by parcel count for this code) where the code
    # appears. `parcels.city` is the muni grouping field; can be empty
    # when no parcel of this code has a non-NULL city.
    sample_towns: list[str]


class UncoveredZoneCodesResponse(BaseModel):
    jurisdiction_id: uuid.UUID
    jurisdiction_name: str
    # Total distinct zone_codes that have NO matching matrix row in the
    # jurisdiction. NOT capped by `limit` — this is the true count of
    # gaps the matrix sprint needs to close.
    uncovered_count: int
    # Total parcels stranded on those uncovered codes. Useful for sizing
    # the impact of the sprint (e.g. "92k of 281k Bergen parcels lack a
    # matrix verdict").
    total_parcels_uncovered: int
    # The top `limit` rows by parcel_count DESC, zone_code ASC.
    rows: list[UncoveredZoneCodeRow]


# ────────────────────────────────────────────────────────────────────────────
# Endpoint
# ────────────────────────────────────────────────────────────────────────────


# Raw SQL used for both queries. Keeping it as text() instead of building
# the LEFT-JOIN-IS-NULL through SQLAlchemy ORM nets two wins:
#   1. The shape matches `audit_zoning_coverage.py` 1:1, so anyone
#      cross-referencing the audit's `unmatched_zone_samples` against
#      this endpoint sees the same query in both places.
#   2. The nested `sample_towns` subquery is a correlated subquery
#      against the outer (p.jurisdiction_id, p.zoning_code) group —
#      cleaner to write as SQL than via ORM constructs.
#
# Both queries are safe on Bergen (~281k parcels, ~92k unmatched) —
# the (jurisdiction_id, zoning_code) index on `parcels` and the
# (jurisdiction_id, zone_code) lookup into `zone_use_matrix` keep this
# in the sub-second range even before considering that the outer query
# is bounded by LIMIT.

_ROWS_SQL = text(
    """
    SELECT
        p.zoning_code,
        COUNT(*)::bigint AS parcel_count,
        COALESCE(
            (
                SELECT json_agg(s.city ORDER BY s.cnt DESC, s.city)
                FROM (
                    SELECT p2.city, COUNT(*) AS cnt
                    FROM parcels p2
                    WHERE p2.jurisdiction_id = p.jurisdiction_id
                      AND p2.zoning_code = p.zoning_code
                      AND p2.city IS NOT NULL
                    GROUP BY p2.city
                    ORDER BY COUNT(*) DESC, p2.city
                    LIMIT 3
                ) s
            ),
            '[]'::json
        ) AS sample_towns
    FROM parcels p
    LEFT JOIN zone_use_matrix zum
      ON zum.jurisdiction_id = p.jurisdiction_id
     AND zum.zone_code = p.zoning_code
    WHERE p.jurisdiction_id = :jurisdiction_id
      AND p.zoning_code IS NOT NULL
      AND btrim(p.zoning_code) <> ''
      AND zum.zone_code IS NULL
    GROUP BY p.jurisdiction_id, p.zoning_code
    HAVING COUNT(*) >= :min_parcel_count
    ORDER BY COUNT(*) DESC, p.zoning_code ASC
    LIMIT :limit
    """
)


# Summary query: enumerates ALL uncovered codes (not just the top
# `limit`), so callers can render "showing top N of M" and reason about
# the size of the long tail. min_parcel_count is intentionally NOT
# applied here — the summary describes the full uncovered set, while
# the rows describe the operator's filtered worklist.
_SUMMARY_SQL = text(
    """
    SELECT
        COUNT(DISTINCT p.zoning_code)::bigint AS uncovered_count,
        COUNT(*)::bigint                       AS total_parcels_uncovered
    FROM parcels p
    LEFT JOIN zone_use_matrix zum
      ON zum.jurisdiction_id = p.jurisdiction_id
     AND zum.zone_code = p.zoning_code
    WHERE p.jurisdiction_id = :jurisdiction_id
      AND p.zoning_code IS NOT NULL
      AND btrim(p.zoning_code) <> ''
      AND zum.zone_code IS NULL
    """
)


@router.get(
    "/uncovered-zone-codes",
    response_model=UncoveredZoneCodesResponse,
)
async def list_uncovered_zone_codes(
    jurisdiction_id: uuid.UUID = Query(
        ...,
        description="Jurisdiction UUID to enumerate uncovered zone codes for.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Max rows returned. Summary counts are NOT bounded by this.",
    ),
    min_parcel_count: int = Query(
        default=1,
        ge=1,
        description=(
            "Drop codes with fewer than this many parcels from `rows`. "
            "Does NOT affect the summary counts."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> UncoveredZoneCodesResponse:
    """Enumerate zone_codes present in parcels but absent from zone_use_matrix.

    Returns up to `limit` rows ordered by `(parcel_count DESC, zone_code
    ASC)` plus a summary of the full uncovered set
    (`uncovered_count`, `total_parcels_uncovered`). The summary is
    computed independently of `limit` and `min_parcel_count` so callers
    can size the sprint backlog without inflating the requested page.
    """
    # 1. Resolve jurisdiction (404 if missing).
    juris = await db.get(Jurisdiction, jurisdiction_id)
    if juris is None:
        raise HTTPException(404, f"jurisdiction {jurisdiction_id} not found")

    # 2. Top-N uncovered rows for the worklist.
    rows_result = await db.execute(
        _ROWS_SQL,
        {
            "jurisdiction_id": jurisdiction_id,
            "min_parcel_count": min_parcel_count,
            "limit": limit,
        },
    )
    rows = [
        UncoveredZoneCodeRow(
            zone_code=r.zoning_code,
            parcel_count=int(r.parcel_count),
            # json_agg can return None when no parcel of this code has
            # a non-NULL city — COALESCE in SQL handles the all-NULL
            # case by emitting '[]', but the driver sometimes still
            # decodes that to None in edge cases on older asyncpg
            # versions, so defend at the Python boundary too.
            sample_towns=list(r.sample_towns or []),
        )
        for r in rows_result.all()
    ]

    # 3. Summary across the full uncovered set (not bounded by limit).
    summary_row = (
        await db.execute(
            _SUMMARY_SQL, {"jurisdiction_id": jurisdiction_id}
        )
    ).one()

    logger.info(
        "op5-uncovered list jurisdiction=%s returned_rows=%d "
        "uncovered_count=%d total_parcels_uncovered=%d min_parcel_count=%d",
        jurisdiction_id,
        len(rows),
        int(summary_row.uncovered_count),
        int(summary_row.total_parcels_uncovered),
        min_parcel_count,
    )

    return UncoveredZoneCodesResponse(
        jurisdiction_id=jurisdiction_id,
        jurisdiction_name=juris.name,
        uncovered_count=int(summary_row.uncovered_count),
        total_parcels_uncovered=int(summary_row.total_parcels_uncovered),
        rows=rows,
    )
