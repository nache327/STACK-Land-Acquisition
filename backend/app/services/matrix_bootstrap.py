"""
Rule-based zone-use-matrix bootstrap for jurisdictions without ordinance parses.
"""
from __future__ import annotations

import uuid

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.zoning_district import ZoneClass
from app.models.zone_use_matrix import UsePermission, ZoneUseMatrix
from app.services.classification import classify_zone_code


ZONE_CLASS_TO_SELF_STORAGE: dict[ZoneClass, UsePermission] = {
    ZoneClass.industrial: UsePermission.permitted,
    ZoneClass.commercial: UsePermission.conditional,
    ZoneClass.mixed_use: UsePermission.conditional,
    ZoneClass.agricultural: UsePermission.conditional,
    ZoneClass.residential: UsePermission.prohibited,
    ZoneClass.open_space: UsePermission.prohibited,
    ZoneClass.special: UsePermission.prohibited,
    ZoneClass.overlay: UsePermission.prohibited,
    ZoneClass.unknown: UsePermission.unclear,
}


def _permission_for(zone_class: ZoneClass) -> UsePermission:
    return ZONE_CLASS_TO_SELF_STORAGE.get(zone_class, UsePermission.unclear)


async def bootstrap_zone_use_matrix(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    replace: bool = False,
    missing_only: bool = True,
) -> int:
    """
    Seed `zone_use_matrix` from parcel/zoning codes using zone-class heuristics.
    """
    if replace:
        await db.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jurisdiction_id},
        )

    existing_codes: set[str] = set()
    if missing_only and not replace:
        rows = await db.execute(
            text(
                """
                SELECT zone_code
                FROM zone_use_matrix
                WHERE jurisdiction_id = :jid
                """
            ),
            {"jid": jurisdiction_id},
        )
        existing_codes = {row.zone_code for row in rows if row.zone_code}

    code_rows = await db.execute(
        text(
            """
            WITH source_codes AS (
                SELECT DISTINCT
                    NULLIF(BTRIM(p.zoning_code), '') AS zone_code,
                    NULL::text AS zone_name
                FROM parcels p
                WHERE p.jurisdiction_id = :jid

                UNION

                SELECT DISTINCT
                    NULLIF(BTRIM(zd.zone_code), '') AS zone_code,
                    NULLIF(BTRIM(zd.zone_name), '') AS zone_name
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = :jid
            )
            SELECT zone_code, max(zone_name) AS zone_name
            FROM source_codes
            WHERE zone_code IS NOT NULL
            GROUP BY zone_code
            ORDER BY zone_code
            """
        ),
        {"jid": jurisdiction_id},
    )

    inserts: list[dict] = []
    for row in code_rows:
        zone_code = row.zone_code
        if not zone_code or zone_code in existing_codes:
            continue

        zone_name = row.zone_name
        zone_class = classify_zone_code(zone_code, zone_name=zone_name)
        storage = _permission_for(zone_class)
        inserts.append(
            {
                "jurisdiction_id": jurisdiction_id,
                "zone_code": zone_code,
                "zone_name": zone_name or zone_code,
                "self_storage": storage,
                "mini_warehouse": storage,
                "light_industrial": (
                    UsePermission.permitted
                    if zone_class == ZoneClass.industrial
                    else storage
                ),
                "luxury_garage_condo": storage,
                "confidence": 0.35,
                "human_reviewed": False,
                "notes": f"Heuristic bootstrap from inferred zone_class={zone_class.value}",
            }
        )

    if not inserts:
        return 0

    await db.execute(insert(ZoneUseMatrix), inserts)
    await db.flush()
    return len(inserts)
