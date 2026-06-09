"""Factory-safe writes to ``zone_use_matrix`` — the Op-5 coordination rule.

Adam-ack'd coordination proposal (2026-06-08): the Op-5 factory must NEVER
overwrite hand-grounded verdicts. This module is the one chokepoint the
factory's per-county adjudication step calls to persist matrix rows. It mirrors
Adam's F2 protect-list contract (``op5_lib.ingestion_helpers`` — which guards
``zoning_districts`` + Op-5 *proof* towns) one table over, onto ``zone_use_matrix``
+ hand rows.

Rule:
  1. Human verdicts are truth — rows with ``human_reviewed = true`` are never
     touched. Per muni, query those zone_codes first and SKIP them.
  2. Survivors INSERT with ``ON CONFLICT DO NOTHING`` against the partial unique
     index ``uq_zone_matrix`` (jurisdiction_id, zone_code, COALESCE(municipality,
     '')) WHERE deleted_at IS NULL — never ``DO UPDATE``/UPSERT.
  3. Factory rows carry ``classification_source='op5_factory_catchall'`` (catchall
     stub) or ``'op5_factory'`` (grounded) so the audit can always distinguish
     factory rows from ``'human'`` rows.
  4. After each muni, ``audit_muni_gap`` runs the matrix_codes ⊇ parcel_codes
     gap check (the Bedminster failure-mode gate) and the caller logs a WARNING
     on any gap — surfaced, not blocking.

asyncpg-based to match the factory's raw-connection ingest path.
"""
from __future__ import annotations

import logging
import re
from typing import Any

LOGGER = logging.getLogger(__name__)

_VALID_FACTORY_SOURCES = {"op5_factory", "op5_factory_catchall"}
_USE_FIELDS = ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo")

# INSERT must name the partial-index inference (columns + WHERE predicate) so
# ON CONFLICT DO NOTHING actually fires against uq_zone_matrix. A bare
# `ON CONFLICT DO NOTHING` would NOT match the partial index and would raise.
_INSERT_SQL = """
INSERT INTO zone_use_matrix
    (jurisdiction_id, municipality, zone_code, zone_name,
     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
     confidence, notes, classification_source, human_reviewed)
VALUES
    ($1::uuid, $2, $3, $4,
     $5::use_permission_enum, $6::use_permission_enum,
     $7::use_permission_enum, $8::use_permission_enum,
     $9, $10, $11::classification_source_enum, false)
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality, ''))
    WHERE deleted_at IS NULL
DO NOTHING
"""


def _norm(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


async def factory_safe_write(
    conn,  # asyncpg.Connection
    jurisdiction_id: str,
    municipality: str,
    rows: list[dict[str, Any]],
    *,
    default_source: str = "op5_factory_catchall",
) -> dict[str, int]:
    """Write factory-generated ``zone_use_matrix`` rows with hand-row protection.

    1. Query existing ``human_reviewed=true`` zone_codes for (jid, muni).
    2. Filter incoming ``rows`` to exclude those zone_codes (case/format-insensitive).
    3. ``INSERT ... ON CONFLICT DO NOTHING`` for survivors.
    4. Return ``{written, skipped_human, skipped_conflict}`` for the audit log.

    ``rows`` items: ``{zone_code, zone_name?, self_storage?, mini_warehouse?,
    light_industrial?, luxury_garage_condo?, confidence?, notes?,
    classification_source?}``. Missing use cells default to ``'unclear'``.
    """
    human = await conn.fetch(
        """
        SELECT zone_code FROM zone_use_matrix
        WHERE jurisdiction_id = $1::uuid AND municipality = $2
          AND human_reviewed = true AND deleted_at IS NULL
        """,
        jurisdiction_id,
        municipality,
    )
    human_norm = {_norm(r["zone_code"]) for r in human}

    written = skipped_human = skipped_conflict = 0
    for row in rows:
        code = (row.get("zone_code") or "").strip()
        if not code:
            continue
        if _norm(code) in human_norm:
            skipped_human += 1
            continue
        source = row.get("classification_source", default_source)
        if source not in _VALID_FACTORY_SOURCES:
            # Never let a factory write masquerade as 'human'/etc.
            source = default_source
        status = await conn.execute(
            _INSERT_SQL,
            jurisdiction_id,
            municipality,
            code,
            row.get("zone_name"),
            row.get("self_storage", "unclear"),
            row.get("mini_warehouse", "unclear"),
            row.get("light_industrial", "unclear"),
            row.get("luxury_garage_condo", "unclear"),
            row.get("confidence"),
            (row.get("notes") or None),
            source,
        )
        # asyncpg returns e.g. "INSERT 0 1" (inserted) or "INSERT 0 0"
        # (conflict — DO NOTHING fired).
        if str(status).rsplit(" ", 1)[-1] == "0":
            skipped_conflict += 1
        else:
            written += 1

    return {
        "written": written,
        "skipped_human": skipped_human,
        "skipped_conflict": skipped_conflict,
    }


async def audit_muni_gap(
    conn,  # asyncpg.Connection
    jurisdiction_id: str,
    municipality: str,
) -> dict[str, Any]:
    """Per-muni completeness gate: do the matrix zone_codes cover every
    ``parcels.zoning_code`` the muni carries? (matrix_codes ⊇ parcel_codes —
    the check that caught Bedminster + 10 incompletely-grounded hand towns.)

    Returns ``{parcel_codes, matrix_codes, gap_codes, gap_parcels}``. Caller
    logs a WARNING when ``gap_codes`` is non-empty. Non-blocking — surfaces,
    does not raise. Mirrors backend/scripts/_coverage_audit.py.
    """
    pcode_rows = await conn.fetch(
        """
        SELECT DISTINCT zoning_code FROM parcels
        WHERE jurisdiction_id = $1::uuid AND city = $2 AND zoning_code IS NOT NULL
        """,
        jurisdiction_id,
        municipality,
    )
    pcodes = {_norm(r["zoning_code"]): r["zoning_code"] for r in pcode_rows}
    mcode_rows = await conn.fetch(
        """
        SELECT zone_code FROM zone_use_matrix
        WHERE jurisdiction_id = $1::uuid AND municipality = $2 AND deleted_at IS NULL
        """,
        jurisdiction_id,
        municipality,
    )
    mcodes = {_norm(r["zone_code"]) for r in mcode_rows}
    gap = [orig for n, orig in pcodes.items() if n not in mcodes]
    gap_parcels = 0
    if gap:
        gap_parcels = int(
            await conn.fetchval(
                """
                SELECT COUNT(*) FROM parcels
                WHERE jurisdiction_id = $1::uuid AND city = $2
                  AND zoning_code = ANY($3::text[])
                """,
                jurisdiction_id,
                municipality,
                gap,
            )
        )
        LOGGER.warning(
            "zone_matrix gap after factory write — %s: %d uncovered parcel "
            "code(s) (%d parcels): %s",
            municipality,
            len(gap),
            gap_parcels,
            gap,
        )
    return {
        "parcel_codes": len(pcodes),
        "matrix_codes": len(mcodes),
        "gap_codes": gap,
        "gap_parcels": gap_parcels,
    }
