"""Op-5 review queue API.

GET    /api/admin/op5/adjudications                  — list pending|approved|rejected|all rows
POST   /api/admin/op5/adjudications/{row_id}/approve — mark human_reviewed=true
POST   /api/admin/op5/adjudications/bulk-approve     — bulk-approve by ids or by filter
POST   /api/admin/op5/adjudications/{row_id}/reject  — soft-delete (deleted_at=now)

Critical-path tooling for Pre-build B of the Op-5 factory build
(see docs/OP5_FACTORY_72H_PLAN.md). Reviewing 210 munis end-to-end
implies ~1,500 zone-code decisions; per-row click-through is the
throughput killer this queue eliminates.

Scope:
    * Reads `zone_use_matrix` rows joined to `jurisdictions` and a
      per-(jurisdiction, zone_code) parcel count.
    * Writes ONLY `zone_use_matrix.human_reviewed`,
      `zone_use_matrix.classification_source` (-> "human" on approve),
      `zone_use_matrix.notes`, and `zone_use_matrix.deleted_at`.
    * Does NOT touch `zoning_districts` or `parcels`.

Status semantics on the list endpoint:
    Rejection on this model is encoded as a soft-delete: the reject
    endpoint sets `deleted_at = now()` and prepends "REJECTED: " to
    `notes`. There is no separate `status` / `rejected_at` column on
    `zone_use_matrix` — `deleted_at IS NOT NULL` IS the rejected state.

    * `status=pending`   → human_reviewed IS FALSE AND deleted_at IS NULL
    * `status=approved`  → human_reviewed IS TRUE  AND deleted_at IS NULL
    * `status=rejected`  → deleted_at IS NOT NULL    (the soft-delete tombstone)
    * `status=all`       → no human_reviewed / deleted_at filter at all

    `status=all` mirrors what `backend/scripts/audit_zoning_coverage.py`'s
    `matrix_stats` CTE counts — that CTE has no WHERE clause, so any row in
    `zone_use_matrix` (active OR tombstoned) is included in the audit's
    `matrix_zone_count`. Exposing `status=all|rejected` lets operators see
    the rows the audit is scoring but that pending|approved was hiding
    (e.g. Allentown's 81-row delta between audit `matrix_zone_count=117`
    and the 36 rows visible via `status=approved`+`status=pending`).

Auth:
    No new auth surface — reuses the dependency hook already used by
    other `/api/admin/*` routes (admin_backfill mounted unauthenticated
    behind the same /admin prefix; if/when an auth dep is added there,
    apply it to this router via include_router(dependencies=...)).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zone_use_matrix import (
    ClassificationSource,
    UsePermission,
    ZoneUseMatrix,
)
from app.schemas.zone_use_matrix import CitationRead

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-op5"], prefix="/admin/op5")


# ────────────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────────────


class AdjudicationRow(BaseModel):
    """One row in the review queue.

    Combines a `zone_use_matrix` row with its jurisdiction context
    (county + name) and the count of parcels currently bound to this
    zone_code in the same jurisdiction — gives reviewers a sense of
    blast radius before approving."""

    id: int
    jurisdiction_id: uuid.UUID
    jurisdiction_name: str
    state: str
    county: str | None
    municipality: str | None
    zone_code: str
    zone_name: str | None
    parcel_count: int

    self_storage: UsePermission
    mini_warehouse: UsePermission
    light_industrial: UsePermission
    luxury_garage_condo: UsePermission

    confidence: float | None
    human_reviewed: bool
    classification_source: ClassificationSource
    notes: str | None
    citations: list[CitationRead] | None
    created_at: datetime
    updated_at: datetime
    # Computed bucket the row falls into in the review queue. Derived
    # from `human_reviewed` + `deleted_at`; not a stored column. Lets
    # operators see at-a-glance which slice of the queue each row is
    # in when calling with `status=all`.
    status: Literal["pending", "approved", "rejected"]


class BulkApproveByIds(BaseModel):
    """Bulk-approve a known list of row ids (Approve-Selected toolbar)."""

    row_ids: list[int] = Field(..., max_length=2000)


class BulkApproveByFilter(BaseModel):
    """Bulk-approve every PENDING row matching the filter.

    Used by the "Approve all >= X% confidence in current filter"
    toolbar action. The frontend re-uses whatever filters the user
    has set on the GET list endpoint.
    """

    county: str | None = None
    municipality: str | None = None
    state: str | None = None
    min_confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    # Defensive cap so a misclick can't blast-approve the whole DB.
    max_rows: int = Field(default=500, ge=1, le=2000)


class BulkApprovePayload(BaseModel):
    """Either-or: provide ids OR filter. Validation enforces exactly one."""

    by_ids: BulkApproveByIds | None = None
    by_filter: BulkApproveByFilter | None = None


class RejectPayload(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1024)


class BulkApproveResult(BaseModel):
    approved: int
    row_ids: list[int]


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _parcel_count_subquery():
    """Per-(jurisdiction_id, zoning_code) parcel counts.

    Materialized as a subquery the list endpoint LEFT JOINs against
    so the UI can render parcel_count without an N+1.
    """
    return (
        select(
            Parcel.jurisdiction_id.label("juris_id"),
            Parcel.zoning_code.label("zoning_code"),
            func.count(Parcel.id).label("parcel_count"),
        )
        .where(Parcel.zoning_code.isnot(None))
        .group_by(Parcel.jurisdiction_id, Parcel.zoning_code)
        .subquery()
    )


def _row_status(row: ZoneUseMatrix) -> Literal["pending", "approved", "rejected"]:
    """Compute the queue-bucket label for one matrix row.

    `deleted_at IS NOT NULL` is the soft-delete tombstone the reject
    endpoint writes — that wins over human_reviewed because a row can
    be approved AND later rejected, in which case the operator's
    intent is "rejected" (tombstoned)."""
    if row.deleted_at is not None:
        return "rejected"
    if row.human_reviewed:
        return "approved"
    return "pending"


def _row_to_adjudication(
    row: ZoneUseMatrix,
    jurisdiction: Jurisdiction,
    parcel_count: int | None,
) -> AdjudicationRow:
    return AdjudicationRow(
        id=row.id,
        jurisdiction_id=row.jurisdiction_id,
        jurisdiction_name=jurisdiction.name,
        state=jurisdiction.state,
        county=jurisdiction.county,
        municipality=row.municipality,
        zone_code=row.zone_code,
        zone_name=row.zone_name,
        parcel_count=int(parcel_count or 0),
        self_storage=row.self_storage,
        mini_warehouse=row.mini_warehouse,
        light_industrial=row.light_industrial,
        luxury_garage_condo=row.luxury_garage_condo,
        confidence=float(row.confidence) if row.confidence is not None else None,
        human_reviewed=row.human_reviewed,
        classification_source=row.classification_source,
        notes=row.notes,
        citations=[CitationRead.model_validate(c) for c in (row.citations or [])]
        if row.citations
        else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=_row_status(row),
    )


# ────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.get("/adjudications", response_model=list[AdjudicationRow])
async def list_pending_adjudications(
    status: Annotated[
        Literal["pending", "approved", "rejected", "all"], Query()
    ] = "pending",
    county: str | None = None,
    municipality: str | None = None,
    state: str | None = None,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    max_confidence: float = Query(default=1.0, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AdjudicationRow]:
    """Return adjudication rows for the review queue.

    Status semantics (rejection is encoded as a soft-delete — no
    separate column exists; see module docstring):

    * `status="pending"`  → human_reviewed=false, deleted_at IS NULL
    * `status="approved"` → human_reviewed=true,  deleted_at IS NULL
    * `status="rejected"` → deleted_at IS NOT NULL (soft-deleted rows)
    * `status="all"`      → no filter beyond the user filters below
      (mirrors `audit_zoning_coverage.py`'s `matrix_stats` CTE, which
      counts every row in the table)

    Default remains `pending` to preserve existing caller behavior.
    """
    counts = _parcel_count_subquery()

    # No baseline deleted_at filter — each `status` branch adds its
    # own predicate so `all` and `rejected` can see tombstones, while
    # `pending`/`approved` keep the historical "active rows only"
    # semantics.
    stmt = (
        select(ZoneUseMatrix, Jurisdiction, counts.c.parcel_count)
        .join(Jurisdiction, Jurisdiction.id == ZoneUseMatrix.jurisdiction_id)
        .join(
            counts,
            and_(
                counts.c.juris_id == ZoneUseMatrix.jurisdiction_id,
                counts.c.zoning_code == ZoneUseMatrix.zone_code,
            ),
            isouter=True,
        )
    )

    if status == "pending":
        stmt = stmt.where(
            ZoneUseMatrix.deleted_at.is_(None),
            ZoneUseMatrix.human_reviewed.is_(False),
        )
    elif status == "approved":
        stmt = stmt.where(
            ZoneUseMatrix.deleted_at.is_(None),
            ZoneUseMatrix.human_reviewed.is_(True),
        )
    elif status == "rejected":
        stmt = stmt.where(ZoneUseMatrix.deleted_at.is_not(None))
    # status == "all" → no extra status predicate; mirrors audit CTE.

    if county:
        stmt = stmt.where(Jurisdiction.county == county)
    if state:
        stmt = stmt.where(Jurisdiction.state == state)
    if municipality:
        stmt = stmt.where(ZoneUseMatrix.municipality == municipality)
    if min_confidence > 0.0:
        stmt = stmt.where(ZoneUseMatrix.confidence >= min_confidence)
    if max_confidence < 1.0:
        stmt = stmt.where(ZoneUseMatrix.confidence <= max_confidence)

    # Order: lowest confidence first so reviewers see the hard cases on top.
    # Tie-breaker by updated_at desc so freshly-parsed rows surface above
    # legacy unclear=NULL.
    stmt = (
        stmt.order_by(
            ZoneUseMatrix.confidence.asc().nulls_last(),
            ZoneUseMatrix.updated_at.desc(),
            ZoneUseMatrix.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    out: list[AdjudicationRow] = []
    for row, jurisdiction, parcel_count in result.all():
        out.append(_row_to_adjudication(row, jurisdiction, parcel_count))
    return out


@router.post(
    "/adjudications/{row_id}/approve",
    response_model=AdjudicationRow,
)
async def approve_adjudication(
    row_id: int,
    db: AsyncSession = Depends(get_db),
) -> AdjudicationRow:
    """Approve a single matrix row.

    Sets `human_reviewed=true` and `classification_source='human'` so
    the row is excluded from future bulk-bootstrapper resets. Idempotent
    — re-approving an already-approved row is a no-op."""
    row = await db.get(ZoneUseMatrix, row_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(404, "adjudication row not found")
    juris = await db.get(Jurisdiction, row.jurisdiction_id)
    if juris is None:
        raise HTTPException(500, "jurisdiction not found for row")

    row.human_reviewed = True
    row.classification_source = ClassificationSource.human
    await db.flush()

    parcel_count = await _count_parcels(db, row.jurisdiction_id, row.zone_code)
    logger.info(
        "op5-review approve row_id=%d jurisdiction=%s zone_code=%s",
        row_id, row.jurisdiction_id, row.zone_code,
    )
    return _row_to_adjudication(row, juris, parcel_count)


@router.post(
    "/adjudications/bulk-approve",
    response_model=BulkApproveResult,
)
async def bulk_approve_adjudications(
    payload: BulkApprovePayload,
    db: AsyncSession = Depends(get_db),
) -> BulkApproveResult:
    """Bulk-approve by ids or by filter.

    Exactly one of `by_ids` or `by_filter` must be provided. With
    `by_filter`, only rows currently in `status=pending` and matching
    the filter are flipped — already-approved rows are skipped to keep
    the count meaningful."""
    if (payload.by_ids is None) == (payload.by_filter is None):
        raise HTTPException(
            400, "exactly one of `by_ids` or `by_filter` must be set"
        )

    if payload.by_ids is not None:
        ids = payload.by_ids.row_ids
        if not ids:
            return BulkApproveResult(approved=0, row_ids=[])
        stmt = (
            update(ZoneUseMatrix)
            .where(
                ZoneUseMatrix.id.in_(ids),
                ZoneUseMatrix.deleted_at.is_(None),
                ZoneUseMatrix.human_reviewed.is_(False),
            )
            .values(
                human_reviewed=True,
                classification_source=ClassificationSource.human,
            )
            .returning(ZoneUseMatrix.id)
        )
        result = await db.execute(stmt)
        approved_ids = [r[0] for r in result.all()]
        logger.info(
            "op5-review bulk_approve by_ids approved=%d requested=%d",
            len(approved_ids), len(ids),
        )
        return BulkApproveResult(approved=len(approved_ids), row_ids=approved_ids)

    f = payload.by_filter
    assert f is not None
    # Resolve matching ids first so we can return them and respect max_rows
    # without scanning twice.
    sel = (
        select(ZoneUseMatrix.id)
        .join(Jurisdiction, Jurisdiction.id == ZoneUseMatrix.jurisdiction_id)
        .where(
            ZoneUseMatrix.deleted_at.is_(None),
            ZoneUseMatrix.human_reviewed.is_(False),
            ZoneUseMatrix.confidence.isnot(None),
            ZoneUseMatrix.confidence >= f.min_confidence,
        )
    )
    if f.county:
        sel = sel.where(Jurisdiction.county == f.county)
    if f.state:
        sel = sel.where(Jurisdiction.state == f.state)
    if f.municipality:
        sel = sel.where(ZoneUseMatrix.municipality == f.municipality)
    sel = sel.order_by(ZoneUseMatrix.id.asc()).limit(f.max_rows)

    candidate_ids = (await db.execute(sel)).scalars().all()
    if not candidate_ids:
        return BulkApproveResult(approved=0, row_ids=[])

    stmt = (
        update(ZoneUseMatrix)
        .where(ZoneUseMatrix.id.in_(candidate_ids))
        .values(
            human_reviewed=True,
            classification_source=ClassificationSource.human,
        )
        .returning(ZoneUseMatrix.id)
    )
    result = await db.execute(stmt)
    approved_ids = [r[0] for r in result.all()]
    logger.info(
        "op5-review bulk_approve by_filter approved=%d min_conf=%.2f county=%s",
        len(approved_ids), f.min_confidence, f.county,
    )
    return BulkApproveResult(approved=len(approved_ids), row_ids=approved_ids)


@router.post(
    "/adjudications/{row_id}/reject",
    response_model=AdjudicationRow,
)
async def reject_adjudication(
    row_id: int,
    payload: RejectPayload,
    db: AsyncSession = Depends(get_db),
) -> AdjudicationRow:
    """Soft-delete a row — sets `deleted_at=now()` plus a note with the
    rejection reason. The matrix_bootstrap heuristic seeder respects
    tombstones, so a rejected row stays rejected even if discovery
    re-fires for the same (jurisdiction, zone_code, municipality)."""
    row = await db.get(ZoneUseMatrix, row_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(404, "adjudication row not found")
    juris = await db.get(Jurisdiction, row.jurisdiction_id)
    if juris is None:
        raise HTTPException(500, "jurisdiction not found for row")

    row.deleted_at = datetime.now(timezone.utc)
    # Append, don't overwrite — preserves whatever LLM notes were there.
    existing = (row.notes or "").strip()
    rejection_note = f"REJECTED: {payload.reason}"
    row.notes = f"{existing}\n{rejection_note}".strip() if existing else rejection_note
    await db.flush()

    parcel_count = await _count_parcels(db, row.jurisdiction_id, row.zone_code)
    logger.info(
        "op5-review reject row_id=%d reason=%s",
        row_id, payload.reason[:80],
    )
    return _row_to_adjudication(row, juris, parcel_count)


async def _count_parcels(
    db: AsyncSession, jurisdiction_id: uuid.UUID, zone_code: str
) -> int:
    stmt = (
        select(func.count(Parcel.id))
        .where(
            Parcel.jurisdiction_id == jurisdiction_id,
            Parcel.zoning_code == zone_code,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)
