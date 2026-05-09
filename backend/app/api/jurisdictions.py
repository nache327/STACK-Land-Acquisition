"""
GET  /api/jurisdictions                         — list known jurisdictions
GET  /api/jurisdictions/:id                     — single jurisdiction
GET  /api/jurisdictions/:id/zones               — zone→use matrix
GET  /api/jurisdictions/:id/zones/:code         — single zone row (for Layer 3 verification)
PATCH /api/jurisdictions/:id/zones/:code        — human override
GET  /api/jurisdictions/:id/parcels/map         — GeoJSON FeatureCollection for MapLibre
POST /api/jurisdictions/_cleanup-empty          — admin: dedupe empty jurisdictions
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.job import Job
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix, ClassificationSource
from app.models.zoning_district import ZoningDistrict
from app.schemas.jurisdiction import JurisdictionList, JurisdictionRead
from app.schemas.zone_use_matrix import (
    ZoneMatrixResponse,
    ZoneUseMatrixCreate,
    ZoneUseMatrixRead,
    ZoneUseMatrixUpdate,
)

router = APIRouter(tags=["jurisdictions"])


@router.get("/jurisdictions", response_model=JurisdictionList)
async def list_jurisdictions(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Jurisdiction).order_by(Jurisdiction.name))
    jurisdictions = result.scalars().all()
    return {"items": jurisdictions, "total": len(jurisdictions)}


@router.get("/jurisdictions/{jurisdiction_id}", response_model=JurisdictionRead)
async def get_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Jurisdiction:
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    return j


@router.get("/jurisdictions/{jurisdiction_id}/zones", response_model=ZoneMatrixResponse)
async def get_zone_matrix(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(ZoneUseMatrix)
        .where(ZoneUseMatrix.jurisdiction_id == jurisdiction_id)
        .order_by(ZoneUseMatrix.zone_code)
    )
    zones = result.scalars().all()
    return {"zones": zones, "unknown_zones": [], "parser_warnings": []}


@router.post(
    "/jurisdictions/{jurisdiction_id}/zones",
    response_model=ZoneUseMatrixRead,
    status_code=201,
)
async def create_zone(
    jurisdiction_id: uuid.UUID,
    payload: ZoneUseMatrixCreate,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    existing = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == payload.zone_code,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Zone already exists")
    zone = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        **payload.model_dump(),
    )
    db.add(zone)
    await db.flush()
    await db.refresh(zone)
    return zone


@router.get(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def get_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    result = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == zone_code,
        )
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.patch(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def update_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    payload: ZoneUseMatrixUpdate,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    result = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == zone_code,
        )
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(zone, field, value)
    zone.human_reviewed = True
    zone.classification_source = ClassificationSource.human
    await db.flush()
    await db.refresh(zone)
    return zone


@router.get("/jurisdictions/{jurisdiction_id}/parcels/map")
async def get_parcels_map_layer(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Return all parcels for a jurisdiction as a GeoJSON FeatureCollection
    ready for MapLibre GL JS.

    Uses PostGIS ST_AsGeoJSON for efficient server-side serialization.
    Geometry is simplified to 6 decimal places (~0.1 m precision) to reduce
    payload size.  Only parcels with valid geometries are included.
    """
    sql = text("""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(
                json_agg(
                    json_build_object(
                        'type',       'Feature',
                        'id',         p.id,
                        'geometry',   ST_AsGeoJSON(p.geom, 6)::json,
                        'properties', json_build_object(
                            'id',                p.id,
                            'apn',               p.apn,
                            'zoning_code',       p.zoning_code,
                            'zone_class',        p.zone_class,
                            'acres',             p.acres,
                            'has_structure',     p.has_structure,
                            'in_flood_zone',     p.in_flood_zone,
                            'in_wetland',        p.in_wetland,
                            'address',           p.address,
                            'storage_permission', CASE
                                -- Any use permitted — show green regardless of source
                                WHEN zum.self_storage = 'permitted'
                                  OR zum.mini_warehouse = 'permitted'
                                  OR zum.luxury_garage_condo = 'permitted'
                                THEN 'permitted'
                                -- Any use conditional — show amber regardless of source
                                WHEN zum.self_storage = 'conditional'
                                  OR zum.mini_warehouse = 'conditional'
                                  OR zum.luxury_garage_condo = 'conditional'
                                THEN 'conditional'
                                -- Both primary storage uses prohibited — show gray even if lgc is unclear
                                WHEN zum.self_storage = 'prohibited'
                                 AND zum.mini_warehouse = 'prohibited'
                                THEN 'prohibited'
                                -- Primary storage use is unclear — show purple
                                WHEN zum.self_storage = 'unclear'
                                  OR zum.mini_warehouse = 'unclear'
                                THEN 'unclear'
                                -- Zone in matrix, all uses explicitly prohibited
                                WHEN zum.zone_code IS NOT NULL THEN 'prohibited'
                                ELSE 'unclassified'
                            END
                        )
                    )
                    ORDER BY p.id
                ) FILTER (WHERE p.geom IS NOT NULL),
                '[]'::json
            )
        ) AS fc
        FROM parcels p
        LEFT JOIN zone_use_matrix zum
            ON  zum.jurisdiction_id = p.jurisdiction_id
            AND zum.zone_code       = p.zoning_code
        WHERE p.jurisdiction_id = :jid
    """)

    result = await db.execute(sql, {"jid": jurisdiction_id})
    row = result.one_or_none()

    headers = {"Cache-Control": "no-store"}

    if row is None or row.fc is None:
        return JSONResponse(
            content={"type": "FeatureCollection", "features": []},
            media_type="application/geo+json",
            headers=headers,
        )

    return JSONResponse(content=row.fc, media_type="application/geo+json", headers=headers)


# ─── Admin: cleanup empty / duplicate jurisdictions ──────────────────────────

# Deletes jurisdictions that have:
#   - parcels = 0
#   - zoning_districts = 0
#   - zone_use_matrix = 0
# AND match one of the cleanup heuristics (state="NE" typo, or name-based dup
# of another jurisdiction in the same county).
#
# Job rows pointing at a deleted jurisdiction are re-pointed to the canonical
# sibling when one exists; otherwise their jurisdiction_id is set to NULL via
# the FK's ondelete=SET NULL.

# Map from "empty city name" (state="NE" typo) to canonical NJ county row name.
# These city-keyed rows were created by the live discovery path that misparsed
# state from the input; the county-keyed rows are doing the actual work.
_NJ_NE_TYPO_TO_COUNTY = {
    "elizabeth":      "Union County, NJ",
    "paterson":       "Passaic County, NJ",
    "new brunswick":  "Middlesex County, NJ",
}

# City rows that should be merged into county-level NJ rows even though their
# state is correct. Marlboro is in Monmouth County which already has 251k
# parcels under the county-level row.
_NJ_CITY_TO_COUNTY = {
    "marlboro": "Monmouth County, NJ",
}


@router.post("/jurisdictions/_cleanup-empty")
async def cleanup_empty_jurisdictions(
    confirm: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Identify and (optionally) delete empty / duplicate jurisdiction rows.

    Default is dry-run: returns the candidate rows without modifying anything.
    Pass ?confirm=true to actually delete.

    Heuristics:
      1. state='NE' rows (typo of NJ from live discovery) that have a clear
         county-level NJ row to redirect to.
      2. Name-based dups: city-level rows whose canonical county-level row
         exists and has data.
      3. Suffix-mismatch dups (e.g. 'Cedar Hills' vs 'Cedar Hills, UT').
    Only rows with parcels=0 + zoning_districts=0 + matrix=0 are eligible.
    """
    # Pull all jurisdictions plus their counts in one round trip.
    rows = (await db.execute(
        text(
            """
            SELECT
                j.id,
                j.name,
                j.state,
                j.county,
                COALESCE(p.cnt, 0)  AS parcels,
                COALESCE(zd.cnt, 0) AS zones,
                COALESCE(zm.cnt, 0) AS matrix
            FROM jurisdictions j
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM parcels GROUP BY jurisdiction_id
            ) p  ON p.jurisdiction_id = j.id
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM zoning_districts GROUP BY jurisdiction_id
            ) zd ON zd.jurisdiction_id = j.id
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM zone_use_matrix GROUP BY jurisdiction_id
            ) zm ON zm.jurisdiction_id = j.id
            """
        )
    )).mappings().all()

    by_name_state = {(r["name"].strip().lower(), (r["state"] or "").upper()): r for r in rows}

    candidates: list[dict] = []
    for r in rows:
        if r["parcels"] or r["zones"] or r["matrix"]:
            continue  # has real data, never auto-delete

        name_lc = r["name"].strip().lower()
        state = (r["state"] or "").upper()
        canonical_id = None
        canonical_name = None
        reason = None

        # 1. state='NE' typo
        if state == "NE" and name_lc in _NJ_NE_TYPO_TO_COUNTY:
            canon = _NJ_NE_TYPO_TO_COUNTY[name_lc]
            cr = by_name_state.get((canon.lower(), "NJ"))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "state=NE typo; redirect to NJ county row"

        # 2. NJ city → county redirect
        if reason is None and state == "NJ" and name_lc in _NJ_CITY_TO_COUNTY:
            canon = _NJ_CITY_TO_COUNTY[name_lc]
            cr = by_name_state.get((canon.lower(), "NJ"))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "city dup of populated NJ county row"

        # 3. Suffix-mismatch dup (e.g. 'Cedar Hills' vs 'Cedar Hills, UT')
        if reason is None and state and f", {state.lower()}" not in name_lc:
            cr = by_name_state.get((f"{name_lc}, {state.lower()}", state))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "suffix-mismatch dup of populated row"

        if reason is None:
            continue

        candidates.append({
            "id": str(r["id"]),
            "name": r["name"],
            "state": r["state"],
            "county": r["county"],
            "parcels": r["parcels"],
            "redirect_to_id": str(canonical_id) if canonical_id else None,
            "redirect_to_name": canonical_name,
            "reason": reason,
        })

    if not confirm:
        return {"dry_run": True, "candidates": candidates, "count": len(candidates)}

    # Live deletion: re-point jobs, then delete jurisdictions.
    deleted = 0
    for c in candidates:
        if c["redirect_to_id"]:
            await db.execute(
                update(Job)
                .where(Job.jurisdiction_id == uuid.UUID(c["id"]))
                .values(jurisdiction_id=uuid.UUID(c["redirect_to_id"]))
            )
        await db.execute(
            delete(Jurisdiction).where(Jurisdiction.id == uuid.UUID(c["id"]))
        )
        deleted += 1
    await db.commit()
    return {"dry_run": False, "deleted": deleted, "candidates": candidates}
