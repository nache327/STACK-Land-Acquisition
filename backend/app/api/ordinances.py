"""
POST /api/ordinances/{jurisdiction_id}/parse  — trigger ordinance parse
GET  /api/ordinances/{jurisdiction_id}/status — parse status
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.jurisdiction import Jurisdiction
from app.services.pipeline import _parse_and_save_ordinance

router = APIRouter(tags=["ordinances"])


class OrdinanceParseRequest(BaseModel):
    ordinance_url: str | None = None


@router.post("/ordinances/{jurisdiction_id}/parse")
async def trigger_parse(
    jurisdiction_id: uuid.UUID,
    body: OrdinanceParseRequest = OrdinanceParseRequest(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger ordinance parsing for a jurisdiction — runs synchronously so errors
    are visible in the response.
    """
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    url = body.ordinance_url or j.ordinance_url
    if not url:
        raise HTTPException(
            status_code=422,
            detail="No ordinance URL provided and none stored for this jurisdiction.",
        )

    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections
    from app.models.zone_use_matrix import ZoneUseMatrix
    from app.models.parcel import Parcel
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select as sa_select

    # Fetch known zone codes
    rows = await db.execute(
        sa_select(Parcel.zoning_code)
        .where(Parcel.jurisdiction_id == jurisdiction_id, Parcel.zoning_code.isnot(None))
        .distinct()
    )
    known_codes = sorted({r[0] for r in rows.fetchall() if r[0]})

    # Fetch ordinance
    try:
        sections = await fetch_from_url(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}")

    if not sections:
        raise HTTPException(status_code=422, detail="Fetcher returned 0 sections — page may be JavaScript-rendered or empty.")

    combined = "\n\n".join(
        f"[Section {s.section_id}: {s.heading}]\n{s.text}" for s in sections
    )

    # Parse with Claude
    try:
        output = await parse_ordinance_sections(combined, j.name, known_codes)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Claude parse failed: {exc}")

    # Deduplicate zones by code (keep highest confidence if Claude returns duplicates)
    seen: dict[str, object] = {}
    for zone in output.zones:
        if zone.code not in seen or zone.confidence > seen[zone.code].confidence:
            seen[zone.code] = zone
    deduped_zones = list(seen.values())

    # Upsert zones — insert or update existing row for the same (jurisdiction_id, zone_code)
    for zone in deduped_zones:
        stmt = pg_insert(ZoneUseMatrix).values(
            jurisdiction_id=jurisdiction_id,
            zone_code=zone.code,
            zone_name=zone.name,
            self_storage=zone.self_storage,
            mini_warehouse=zone.mini_warehouse,
            light_industrial=zone.light_industrial,
            luxury_garage_condo=zone.luxury_garage_condo,
            citations=[c.model_dump() for c in zone.citations] if zone.citations else None,
            confidence=zone.confidence,
            notes=zone.notes,
        ).on_conflict_do_update(
            constraint="uq_zone_matrix",
            set_=dict(
                zone_name=zone.name,
                self_storage=zone.self_storage,
                mini_warehouse=zone.mini_warehouse,
                light_industrial=zone.light_industrial,
                luxury_garage_condo=zone.luxury_garage_condo,
                citations=[c.model_dump() for c in zone.citations] if zone.citations else None,
                confidence=zone.confidence,
                notes=zone.notes,
            ),
            where=ZoneUseMatrix.confidence < zone.confidence,
        )
        await db.execute(stmt)
    j.ordinance_url = url
    await db.commit()

    return {
        "status": "ok",
        "sections_fetched": len(sections),
        "chars_sent": len(combined),
        "known_codes": known_codes,
        "zones_saved": len(output.zones),
        "unknown_zones": output.unknown_zones,
        "parser_warnings": output.parser_warnings,
    }


@router.get("/ordinances/test-fetch")
async def test_fetch(url: str) -> dict:
    """Debug: fetch a URL and return what the ordinance fetcher sees."""
    from app.services.ordinance_fetcher import fetch_from_url
    try:
        sections = await fetch_from_url(url)
        return {
            "section_count": len(sections),
            "total_chars": sum(len(s.text) for s in sections),
            "sections": [
                {"id": s.section_id, "heading": s.heading[:80], "chars": len(s.text), "preview": s.text[:200]}
                for s in sections[:5]
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "section_count": 0}


@router.get("/ordinances/fetch-text")
async def fetch_ordinance_text(url: str) -> dict:
    """
    Fetch ordinance text from a URL using the full backend fetcher (Playwright for
    JS-rendered / Cloudflare-protected sites like municipal.codes and municode).
    Returns combined text suitable for passing to Claude.
    Called by the Next.js fetch-ordinance edge function for sites it can't reach.
    """
    from app.services.ordinance_fetcher import fetch_from_url, _MAX_ORDINANCE_CHARS
    try:
        sections = await fetch_from_url(url)
        if not sections:
            return {"text": "", "section_count": 0, "error": "No sections found"}
        combined = "\n\n".join(
            f"[Section {s.section_id}: {s.heading}]\n{s.text}"
            for s in sections
        )[:_MAX_ORDINANCE_CHARS]
        return {
            "text": combined,
            "section_count": len(sections),
            "total_chars": len(combined),
        }
    except Exception as exc:
        return {"text": "", "section_count": 0, "error": str(exc)}


async def _run_parse(jurisdiction_id: uuid.UUID, ordinance_url: str) -> None:
    """Background wrapper — creates its own DB session."""
    from app.db import async_session_maker

    async with async_session_maker() as db:
        j = await db.get(Jurisdiction, jurisdiction_id)
        if j is None:
            return
        try:
            await _parse_and_save_ordinance(db, j, ordinance_url)
            await db.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "Background ordinance parse failed for %s: %s", jurisdiction_id, exc
            )
