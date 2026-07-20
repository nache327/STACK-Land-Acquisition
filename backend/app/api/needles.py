"""Needles-by-county read API — serves the precomputed needle_snapshot.

The product's one metric (wealth-gated needles) was CLI-only (verify_batch).
This exposes the nightly-precomputed snapshot for the in-app needles-by-county
view: a cheap read, never a live 40M-row scan.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter()


@router.get("/needles")
async def list_needles(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the latest needle snapshot per jurisdiction (both assets), plus
    portfolio totals. Ordered by LGC-effective needles desc — the biggest
    opportunities first. Empty ``jurisdictions`` until precompute_needles has run."""
    rows = (await db.execute(text(
        """
        SELECT jurisdiction_id, jurisdiction_name, state,
               storage_needles, lgc_needles, lgc_incremental,
               storage_deals, lgc_deals, computed_at
          FROM needle_snapshot
         ORDER BY lgc_needles DESC, jurisdiction_name ASC
        """
    ))).mappings().all()

    items = [
        {
            "jurisdiction_id": str(r["jurisdiction_id"]),
            "jurisdiction_name": r["jurisdiction_name"],
            "state": r["state"],
            "storage_needles": r["storage_needles"],
            "lgc_needles": r["lgc_needles"],
            "lgc_incremental": r["lgc_incremental"],
            "storage_deals": r["storage_deals"],
            "lgc_deals": r["lgc_deals"],
            "computed_at": r["computed_at"].isoformat() if r["computed_at"] else None,
        }
        for r in rows
    ]
    totals = {
        "storage_needles": sum(i["storage_needles"] for i in items),
        "lgc_needles": sum(i["lgc_needles"] for i in items),
        "lgc_incremental": sum(i["lgc_incremental"] for i in items),
        "storage_deals": sum(i["storage_deals"] for i in items),
        "lgc_deals": sum(i["lgc_deals"] for i in items),
    }
    computed_at = max((i["computed_at"] for i in items if i["computed_at"]), default=None)
    return {"jurisdictions": items, "totals": totals, "computed_at": computed_at}
