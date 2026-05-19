"""onboard_municipality — operational pipeline for landing a verified zoning
source into a jurisdiction.

Walks the standard sequence: spatial-check → upsert source → verify → ingest
→ validate coverage delta. Idempotent at every step. Drives operator-driven
ingest from a single shell command instead of 4-5 curl calls.

Designed to be run inside the API container (Railway/local) so it can import
the same service code paths the prod API uses. **Does not deploy. Does not
mutate prod schema. Reuses existing service functions only.**

Usage:
    python -m scripts.onboard_municipality \\
        --jurisdiction-id 4bf00234-4455-4987-a067-b22ee6b6aa1f \\
        --source-url https://services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/20200609_Zoning/FeatureServer/0 \\
        --where "MUN_CODE LIKE '02%'" \\
        --label "NJSEA Meadowlands - Bergen (10 munis)" \\
        --auto-verify

For per-muni sources (one source = one town), --muni and --label suffice:
    python -m scripts.onboard_municipality \\
        --jurisdiction-id 4bf00234-... \\
        --source-url https://services6.../Westwood_Zoning_2019/FeatureServer/0 \\
        --muni "Westwood" \\
        --label "Westwood vendor (Paramus consultant)" \\
        --auto-verify

Output:
    JSON status report per step (spatial_check, source_upsert, verify, ingest,
    coverage_delta) so the operator can ack each step. Exits non-zero on any
    blocking failure.

Lane safety: this script is read+verify only against zoning_sources, and
calls existing _backfill-zoning logic for ingest. Does not touch pipeline.py,
ingestion.py, zoning_system.py, spatial_backfill.py, or migrations.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Make `app` importable when run as `python -m scripts.onboard_municipality`
# from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


logger = logging.getLogger("onboard_municipality")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _resolve_db_url() -> str:
    import os
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


async def _session() -> AsyncSession:
    engine = create_async_engine(_resolve_db_url(), pool_pre_ping=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return sm()


async def step_spatial_check(source_url: str, jurisdiction_bbox: list | None) -> dict:
    """Wraps zoning_discovery.spatial_check_for_url."""
    from app.services.zoning_discovery import spatial_check_for_url
    result = await spatial_check_for_url(source_url, jurisdiction_bbox)
    return {"step": "spatial_check", **result}


async def step_upsert_source(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID,
    source_url: str,
    municipality_name: str | None,
    label: str | None,
) -> dict:
    """Insert or refresh a `zoning_sources` row for this source. Returns the
    source's UUID. Does not flip validation_status — that's `verify`'s job.
    """
    from app.models.zoning_source import ZoningSource
    from app.models.jurisdiction import Jurisdiction

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise SystemExit(f"jurisdiction {jurisdiction_id} not found")

    q = select(ZoningSource).where(
        ZoningSource.jurisdiction_id == jurisdiction_id,
        ZoningSource.zoning_endpoint == source_url,
    )
    if municipality_name is not None:
        q = q.where(ZoningSource.municipality_name == municipality_name)
    existing = (await db.execute(q)).scalar_one_or_none()

    if existing is not None:
        return {
            "step": "upsert_source",
            "action": "found_existing",
            "source_id": str(existing.id),
            "current_status": existing.validation_status,
        }

    row = ZoningSource(
        jurisdiction_id=jurisdiction_id,
        municipality_name=municipality_name,
        county=j.county,
        state=j.state,
        source_type="arcgis_featureserver",
        zoning_endpoint=source_url,
        title=label or source_url.rsplit("/", 2)[-2],
        confidence_label="discovered",
        confidence_score=80,
        validation_status="pending",
        discovered_by="onboard_script",
        notes=label or None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"step": "upsert_source", "action": "inserted", "source_id": str(row.id)}


async def step_verify(db: AsyncSession, source_id: uuid.UUID, reason: str | None = None) -> dict:
    """Flip validation_status to verified. Idempotent."""
    from app.models.zoning_source import ZoningSource
    src = await db.get(ZoningSource, source_id)
    if src is None:
        return {"step": "verify", "error": "source not found"}
    if src.validation_status == "verified":
        return {"step": "verify", "action": "already_verified"}
    src.validation_status = "verified"
    src.confidence_label = "verified"
    src.last_verified_at = datetime.now(timezone.utc)
    if reason and not src.notes:
        src.notes = reason
    await db.commit()

    # Auto-grow tenant catalog if Op-1 cold module is present (silent if not).
    try:
        from app.services import tenant_catalog
        await tenant_catalog.add_verified_muni(
            url=src.zoning_endpoint,
            municipality_name=src.municipality_name,
            state=src.state,
            service_name=(src.title or src.zoning_endpoint.rsplit("/", 2)[-2]),
            vendor=None,
        )
    except Exception as exc:
        logger.debug("tenant_catalog auto-grow skipped: %r", exc)

    return {"step": "verify", "action": "verified", "source_id": str(source_id)}


async def step_ingest(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID,
    source_url: str,
    where_clause: str = "1=1",
    replace: bool = False,
    spatial_join: bool = True,
) -> dict:
    """Trigger the existing zoning ingestion pipeline for this source.

    Delegates to backfill_zoning in the API (which already handles
    bulk_ingest_zoning_for_jurisdiction + spatial_backfill). Does NOT
    re-implement ingestion logic — that's a hot file owned by the ingestion
    lane.
    """
    from app.api.jurisdictions import backfill_zoning
    try:
        result = await backfill_zoning(
            jurisdiction_id=jurisdiction_id,
            zoning_url=source_url,
            where=where_clause,
            replace=replace,
            spatial_join=spatial_join,
            db=db,
        )
        return {"step": "ingest", "action": "completed", **(result if isinstance(result, dict) else {})}
    except Exception as exc:
        logger.exception("ingest failed")
        return {"step": "ingest", "error": str(exc)[:300]}


async def step_validate(db: AsyncSession, jurisdiction_id: uuid.UUID) -> dict:
    """Snapshot post-ingest coverage. Pulls from coverage_audit if present;
    falls back to a raw SQL count.
    """
    try:
        from app.services.coverage_audit import compute_coverage_for_jurisdiction
        snap = await compute_coverage_for_jurisdiction(db, jurisdiction_id)
        return {"step": "validate", "snapshot": snap if isinstance(snap, dict) else {"raw": str(snap)[:200]}}
    except Exception as exc:
        # Fallback raw count
        from sqlalchemy import text
        row = await db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "COUNT(zoning_code) AS with_zoning "
                "FROM parcels WHERE jurisdiction_id = :jid"
            ),
            {"jid": str(jurisdiction_id)},
        )
        rec = row.first()
        return {
            "step": "validate",
            "parcel_count": rec.total if rec else None,
            "parcel_with_zoning_code_count": rec.with_zoning if rec else None,
            "note": f"coverage_audit unavailable: {exc!r}",
        }


async def onboard(args: argparse.Namespace) -> int:
    jurisdiction_id = uuid.UUID(args.jurisdiction_id)
    db = await _session()
    try:
        from app.models.jurisdiction import Jurisdiction
        j = await db.get(Jurisdiction, jurisdiction_id)
        if j is None:
            print(json.dumps({"error": "jurisdiction not found"}))
            return 2
        jbbox = j.bbox

        # Step 1 — spatial check
        sp = await step_spatial_check(args.source_url, jbbox)
        print(json.dumps(sp, default=str, indent=2))
        if sp.get("verdict") == "disjoint" and not args.force:
            print(json.dumps({"abort": "spatial-check failed (disjoint); pass --force to override"}))
            return 3

        # Step 2 — upsert source
        up = await step_upsert_source(db, jurisdiction_id, args.source_url, args.muni, args.label)
        print(json.dumps(up, default=str, indent=2))
        source_id = uuid.UUID(up["source_id"])

        # Step 3 — verify (if --auto-verify)
        if args.auto_verify:
            ve = await step_verify(db, source_id, reason=args.label)
            print(json.dumps(ve, default=str, indent=2))
        else:
            print(json.dumps({"step": "verify", "action": "skipped (use --auto-verify to flip)", "source_id": str(source_id)}, indent=2))

        # Step 4 — ingest (unless --dry-run)
        if args.dry_run:
            print(json.dumps({"step": "ingest", "action": "skipped (dry-run)"}, indent=2))
        else:
            ig = await step_ingest(
                db, jurisdiction_id, args.source_url,
                where_clause=args.where or "1=1",
                replace=args.replace,
                spatial_join=not args.no_spatial_join,
            )
            print(json.dumps(ig, default=str, indent=2))
            if ig.get("error"):
                return 4

        # Step 5 — validate
        va = await step_validate(db, jurisdiction_id)
        print(json.dumps(va, default=str, indent=2))
        return 0
    finally:
        await db.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Onboard a verified zoning source into a jurisdiction (discover→verify→ingest→validate).",
    )
    p.add_argument("--jurisdiction-id", required=True, help="UUID of the county jurisdiction.")
    p.add_argument("--source-url", required=True, help="FeatureServer/0 (or MapServer/0) URL.")
    p.add_argument("--muni", help="Municipality name for per-muni sources. Omit for multi-muni sources (NJSEA).")
    p.add_argument("--label", help="Human-readable label (becomes title/notes).")
    p.add_argument("--where", default="1=1", help="SQL where clause to filter features (e.g. \"MUN_CODE LIKE '02%%'\"). Default 1=1.")
    p.add_argument("--auto-verify", action="store_true", help="Flip validation_status to verified before ingest.")
    p.add_argument("--dry-run", action="store_true", help="Run steps 1-3 (spatial-check, upsert, verify) but skip ingest.")
    p.add_argument("--force", action="store_true", help="Ingest even if spatial-check returns disjoint.")
    p.add_argument("--replace", action="store_true", help="Replace existing zoning_districts rows for this jurisdiction (default: additive).")
    p.add_argument("--no-spatial-join", action="store_true", help="Skip the parcel spatial-join step (only writes to zoning_districts).")
    args = p.parse_args()
    return asyncio.run(onboard(args))


if __name__ == "__main__":
    sys.exit(main())
