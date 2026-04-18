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


@router.post("/ordinances/{jurisdiction_id}/parse", status_code=202)
async def trigger_parse(
    jurisdiction_id: uuid.UUID,
    body: OrdinanceParseRequest = OrdinanceParseRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger ordinance parsing for a jurisdiction.
    Accepts an optional ordinance_url override; falls back to the stored URL.
    Runs in the background — returns 202 Accepted immediately.
    """
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    url = body.ordinance_url or j.ordinance_url
    if not url:
        raise HTTPException(
            status_code=422,
            detail=(
                "No ordinance URL provided and none stored for this jurisdiction. "
                "Pass ordinance_url in the request body."
            ),
        )

    background_tasks.add_task(_run_parse, jurisdiction_id, url)
    return {
        "status": "accepted",
        "jurisdiction_id": str(jurisdiction_id),
        "ordinance_url": url,
        "message": "Ordinance parsing started. Check /api/jurisdictions/{id}/zones for results.",
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
