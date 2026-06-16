"""Op-5 matrix-row upload API (M2 from docs/OP5_FACTORY_ABANDONED.md).

POST /api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows

Lets a future operator dispatch promote a batch of `zone_use_matrix`
rows in one call. Closes the "Matrix gap" that surfaced in the Bergen
14-flip dry-run: today there's no public-API path to apply a CP2 sign-off
to `zone_use_matrix`, only direct asyncpg scripts
(`scripts/pattern_bergen_garfield_adjudication.py`). This endpoint is the
HTTP equivalent of that script's `ingest_matrix(...)` step, generalized
to any jurisdiction and any row set.

Scope of writes:
    * Reads ONLY `jurisdictions` (404 resolution) and `zone_use_matrix`
      (upsert resolution).
    * Writes ONLY `zone_use_matrix`. Does NOT touch `zoning_districts`,
      `parcels`, or any other table.

Upsert key (matches the partial unique index from migration 0028):
    (jurisdiction_id, zone_code, COALESCE(municipality, ''))

Per-row resolution (one of):
    * row does not exist                 -> INSERT
    * row exists, deleted_at IS NULL     -> UPDATE if replace_existing=true,
                                            else SKIP-NO-OP
    * row exists, deleted_at IS NOT NULL -> UNDELETE + UPDATE (always —
                                            an operator dispatch should
                                            resurrect a tombstoned row
                                            with the new verdicts; the
                                            tombstone protects against
                                            heuristic re-seeding, not
                                            against an explicit operator
                                            upload).

Atomicity:
    The handler is wrapped in a single SQLAlchemy transaction via the
    `get_db` dependency (which commits on success / rolls back on
    raise). If row N fails validation, the handler raises 422 with the
    offending row index, which triggers the rollback — no partial
    writes survive.

Auth:
    No auth dependency, matching the existing /admin/op5/* and
    jurisdictions._backfill-* posture. Master adds an auth dep in one
    line via include_router(dependencies=...) when the codebase changes
    its admin auth posture.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.zone_use_matrix import (
    ClassificationSource,
    UsePermission,
    ZoneUseMatrix,
)
from app.services.zone_matrix_write import blocks_human_overwrite
logger = logging.getLogger(__name__)

# Router prefix matches `jurisdictions.router` (no prefix on the router
# itself; mounted at `/api` in main.py). This lets the path live under
# /api/jurisdictions/... without editing jurisdictions.py (Slot-1 hot).
router = APIRouter(tags=["admin-op5"])


# ────────────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────────────


class UploadCitation(BaseModel):
    """Citation as supplied by the operator dispatch.

    Tolerant on read (matches CitationRead) but kept strict on quote
    length when present to inherit the same write-time guard the LLM
    parser uses (CitationSchema.quote max_length=200). A `url` field is
    accepted and round-tripped because operator dispatches include the
    source URL (see scripts/pattern_bergen_garfield_adjudication.py
    Citation dataclass), and dropping it on ingest would lose
    provenance.
    """

    model_config = ConfigDict(extra="allow")

    section: str | None = None
    quote: str | None = Field(default=None, max_length=200)
    url: str | None = None


class UploadMatrixRow(BaseModel):
    """One zone_use_matrix row in an upload batch.

    Mirrors the dataclass shape used by
    scripts/pattern_bergen_garfield_adjudication.py and the canonical
    matrix row JSON it emits at /tmp/op5_proof/<town>/matrix_rows.json.
    """

    zone_code: str = Field(..., min_length=1, max_length=50)
    zone_name: str | None = Field(default=None, max_length=255)
    # NULL = "default for this county"; a value = township-specific
    # override. Empty-string is collapsed onto NULL by the uniqueness
    # index (COALESCE(municipality, '')), so we treat them as
    # equivalent for the upsert lookup but persist exactly what the
    # operator sent so they can see their input echoed back.
    municipality: str | None = Field(default=None, max_length=255)

    self_storage: UsePermission
    mini_warehouse: UsePermission
    light_industrial: UsePermission
    luxury_garage_condo: UsePermission

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = Field(default=None, max_length=2048)
    citations: list[UploadCitation] | None = None
    classification_source: ClassificationSource = ClassificationSource.human
    human_reviewed: bool = False


class UploadMatrixRequest(BaseModel):
    rows: list[UploadMatrixRow] = Field(..., min_length=1, max_length=2000)
    replace_existing: bool = False

    @field_validator("rows")
    @classmethod
    def _no_duplicate_keys_within_batch(
        cls, rows: list[UploadMatrixRow]
    ) -> list[UploadMatrixRow]:
        """A single batch must not contain two rows with the same upsert key.

        The DB would happily resolve them in order (last write wins),
        but that's a footgun: operator scripts that emit duplicate
        (zone_code, municipality) pairs probably intend to merge them
        upstream, not silently shadow each other. Reject early with a
        clear message instead of producing a confusing audit trail.
        """
        seen: set[tuple[str, str]] = set()
        for idx, row in enumerate(rows):
            key = (row.zone_code, (row.municipality or ""))
            if key in seen:
                raise ValueError(
                    f"duplicate (zone_code, municipality) key at row index {idx}: "
                    f"zone_code={row.zone_code!r} municipality={row.municipality!r}"
                )
            seen.add(key)
        return rows


class UploadRowError(BaseModel):
    index: int
    zone_code: str
    municipality: str | None
    reason: str


class UploadMatrixResponse(BaseModel):
    jurisdiction_id: uuid.UUID
    received: int
    inserted: int
    updated: int
    undeleted: int
    skipped: int
    # Rows skipped because they would have overwritten a live human_reviewed
    # verdict with a non-human (factory) row (catch #13 protection).
    skipped_human: int = 0
    errors: list[UploadRowError] = []


# ────────────────────────────────────────────────────────────────────────────
# Endpoint
# ────────────────────────────────────────────────────────────────────────────


@router.post(
    "/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
    response_model=UploadMatrixResponse,
)
async def upload_matrix_rows(
    jurisdiction_id: uuid.UUID,
    payload: UploadMatrixRequest,
    db: AsyncSession = Depends(get_db),
) -> UploadMatrixResponse:
    """Batch-upsert zone_use_matrix rows for a jurisdiction.

    See module docstring for the upsert resolution rules. The whole
    batch lives inside the single transaction opened by `get_db`; any
    raised HTTPException triggers a rollback so partial state never
    lands.
    """
    # 1. Validate jurisdiction exists.
    juris = await db.get(Jurisdiction, jurisdiction_id)
    if juris is None:
        raise HTTPException(404, f"jurisdiction {jurisdiction_id} not found")

    # Pydantic already validated every row at parse time (including
    # the enum permission values and citation quote length) — a single
    # invalid enum surfaces as 422 before this handler runs, satisfying
    # the "reject the batch with 422 if any invalid value" contract
    # without per-row inspection here.

    inserted = 0
    updated = 0
    undeleted = 0
    skipped = 0
    skipped_human = 0

    for idx, row in enumerate(payload.rows):
        try:
            # Upsert resolution: COALESCE(municipality, '') matches the
            # partial unique index from migration 0028. We can't use
            # SQLAlchemy's `IS DISTINCT FROM` shortcut here because the
            # existing index uses the COALESCE form; matching it
            # guarantees we surface the same row the index would
            # collide on.
            existing_stmt = (
                select(ZoneUseMatrix)
                .where(
                    ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
                    ZoneUseMatrix.zone_code == row.zone_code,
                    func.coalesce(ZoneUseMatrix.municipality, "")
                    == (row.municipality or ""),
                )
                .limit(1)
            )
            existing = (await db.execute(existing_stmt)).scalar_one_or_none()

            if existing is None:
                _insert_row(db, jurisdiction_id, row)
                inserted += 1
                continue

            if existing.deleted_at is not None:
                # Undelete + update. Operator upload is an explicit
                # intent; the tombstone exists to fence off the
                # heuristic seeder, not a human-driven dispatch.
                _apply_row_values(existing, row)
                existing.deleted_at = None
                undeleted += 1
                continue

            # Row exists and is live.
            # Catch #13 chokepoint: a factory / non-human row must NEVER
            # overwrite a human-grounded verdict, regardless of
            # replace_existing. Single canonical rule lives in
            # zone_matrix_write.blocks_human_overwrite (same protection
            # factory_safe_write enforces structurally).
            if blocks_human_overwrite(existing.human_reviewed, row.human_reviewed):
                skipped_human += 1
                continue

            if not payload.replace_existing:
                skipped += 1
                continue

            _apply_row_values(existing, row)
            updated += 1
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # Per-row failure aborts the whole batch — convert to 422
            # with row index + reason so the operator can fix and retry.
            raise HTTPException(
                422,
                f"row {idx} (zone_code={row.zone_code!r}, "
                f"municipality={row.municipality!r}): {exc}",
            ) from exc

    await db.flush()

    logger.info(
        "op5-matrix upload jurisdiction=%s received=%d inserted=%d "
        "updated=%d undeleted=%d skipped=%d skipped_human=%d replace_existing=%s",
        jurisdiction_id,
        len(payload.rows),
        inserted,
        updated,
        undeleted,
        skipped,
        skipped_human,
        payload.replace_existing,
    )

    return UploadMatrixResponse(
        jurisdiction_id=jurisdiction_id,
        received=len(payload.rows),
        inserted=inserted,
        updated=updated,
        undeleted=undeleted,
        skipped=skipped,
        skipped_human=skipped_human,
        errors=[],
    )


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _citations_to_jsonb(
    citations: list[UploadCitation] | None,
) -> list[dict[str, Any]] | None:
    """Round-trip citations to plain dicts for JSONB storage.

    Preserves any extra fields (e.g. `url`) the operator dispatch
    included via `model_config = ConfigDict(extra="allow")` so
    provenance is not silently dropped on ingest.
    """
    if citations is None:
        return None
    out: list[dict[str, Any]] = []
    for c in citations:
        out.append(c.model_dump(exclude_none=False))
    return out


def _insert_row(
    db: AsyncSession, jurisdiction_id: uuid.UUID, row: UploadMatrixRow
) -> None:
    new_row = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code=row.zone_code,
        zone_name=row.zone_name,
        municipality=row.municipality,
        self_storage=row.self_storage,
        mini_warehouse=row.mini_warehouse,
        light_industrial=row.light_industrial,
        luxury_garage_condo=row.luxury_garage_condo,
        citations=_citations_to_jsonb(row.citations),
        confidence=row.confidence,
        human_reviewed=row.human_reviewed,
        notes=row.notes,
        classification_source=row.classification_source,
    )
    db.add(new_row)


def _apply_row_values(existing: ZoneUseMatrix, row: UploadMatrixRow) -> None:
    """Apply the upload row to an existing matrix row.

    Mutates verdicts, citations, confidence, notes,
    classification_source, human_reviewed, and zone_name. Does NOT touch
    municipality (part of the row's identity — to change the scope an
    operator must reject + re-insert via a different row).
    """
    existing.zone_name = row.zone_name
    existing.self_storage = row.self_storage
    existing.mini_warehouse = row.mini_warehouse
    existing.light_industrial = row.light_industrial
    existing.luxury_garage_condo = row.luxury_garage_condo
    existing.citations = _citations_to_jsonb(row.citations)
    existing.confidence = row.confidence
    existing.notes = row.notes
    existing.classification_source = row.classification_source
    existing.human_reviewed = row.human_reviewed
