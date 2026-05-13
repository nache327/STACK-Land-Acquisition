"""POST /api/listings/upload — multipart Excel/CSV upload of CoStar /
LoopNet / Crexi exports. Parses, UPSERTs into forsale_listings,
triggers matching in a background task. Returns immediately with
``{inserted, updated, dropped, match_pending, source, parser_warnings}``.

GET /api/jurisdictions/{id}/listings — current listings for the map
layer (GeoJSON-like response).

Mirrors the KMZ upload pattern at app/api/competition.py:203-237:
read file into memory, defer work to a BackgroundTask, ack fast.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker, get_db
from app.models.forsale_listing import ForsaleListing
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.services.geocode_census import geocode_address
from app.services.listing_matcher import match_pending_listings, rematch_listing
from app.services.listings_parsers import ListingRow, ParseResult, ParserError, parse_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["listings"])


# ── helpers ──────────────────────────────────────────────────────────────────


async def _resolve_jurisdiction(
    db: AsyncSession,
    rows: list[ListingRow],
    explicit_id: uuid.UUID | None,
) -> uuid.UUID:
    """Find the jurisdiction either from the supplied UUID or from the
    first row's city + state. Raises HTTPException(404) when unresolvable.
    """
    if explicit_id is not None:
        j = await db.get(Jurisdiction, explicit_id)
        if j is None:
            raise HTTPException(404, f"Jurisdiction {explicit_id} not found")
        return j.id

    for r in rows:
        if not r.city or not r.state:
            continue
        result = await db.execute(
            select(Jurisdiction).where(
                func.lower(Jurisdiction.name).like(f"%{r.city.lower()}%"),
                func.upper(Jurisdiction.state) == r.state.upper(),
            )
        )
        j = result.scalars().first()
        if j is not None:
            return j.id

    raise HTTPException(
        422,
        "Could not resolve jurisdiction from upload — pass jurisdiction_id "
        "in the form, or ensure the first row has a recognized City + State.",
    )


def _listing_row_to_dict(r: ListingRow, jurisdiction_id: uuid.UUID, source: str, filename: str) -> dict[str, Any]:
    return {
        "jurisdiction_id": jurisdiction_id,
        "source": source,
        "source_file": filename,
        "address": r.address,
        "city": r.city,
        "state": r.state,
        "zip": r.zip,
        "sale_status": r.sale_status,
        "sale_category": r.sale_category,
        "property_type": r.property_type,
        "secondary_type": r.secondary_type,
        "rating": r.rating,
        "size_sf": r.size_sf,
        "sale_price": r.sale_price,
        "price_per_sf": r.price_per_sf,
        "cap_rate": r.cap_rate,
        "days_on_market": r.days_on_market,
        "sale_type": r.sale_type,
        "property_name": r.property_name,
        "land_area_ac": r.land_area_ac,
        "land_area_sf": r.land_area_sf,
        "price_per_ac": r.price_per_ac,
        "price_per_land_sf": r.price_per_land_sf,
        "num_units": r.num_units,
        "price_per_unit": r.price_per_unit,
        "listing_broker_company": r.listing_broker_company,
        "listing_broker_contact": r.listing_broker_contact,
        "listing_broker_phone": r.listing_broker_phone,
        "listing_broker_email": r.listing_broker_email,
        "building_class": r.building_class,
        "zoning_listed": r.zoning_listed,
        "market": r.market,
        "submarket": r.submarket,
        "county": r.county,
        "raw_row": r.raw_row,
        "is_current": True,
    }


# ── upload ───────────────────────────────────────────────────────────────────


@router.post("/listings/upload")
async def upload_listings(
    file: UploadFile = File(...),
    source: str | None = Form(default=None),
    jurisdiction_id: uuid.UUID | None = Form(default=None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest a listings export.

    1. Parse via registry (auto-sniffs source if not supplied).
    2. Resolve jurisdiction.
    3. Mark prior (jurisdiction, source) listings is_current=false +
       dropped_at=now() — provider-scoped, doesn't touch other sources.
    4. UPSERT each row on (jurisdiction, source, address, sale_status).
    5. Background-task the matching cascade.
    """
    if not file.filename or not (
        file.filename.lower().endswith(".xlsx")
        or file.filename.lower().endswith(".csv")
    ):
        raise HTTPException(400, "File must be .xlsx or .csv")

    content = await file.read()
    try:
        result: ParseResult = parse_file(content, file.filename, source=source)
    except ParserError as exc:
        raise HTTPException(422, str(exc))
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))
    except Exception as exc:
        logger.exception("Listings parse failed: %s", exc)
        raise HTTPException(422, f"Failed to parse {file.filename}: {exc}")

    # Wrap the rest in a single try so any DB/UPSERT failure surfaces as
    # JSON {detail: ...} instead of the Railway-edge "Internal Server Error"
    # string that drops the stack trace.
    try:
        return await _persist_and_match(
            db, file.filename, result, jurisdiction_id, background_tasks,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Listings upload failed for %s: %s", file.filename, exc)
        raise HTTPException(500, f"Listings ingest failed: {type(exc).__name__}: {exc}")


async def _persist_and_match(
    db: AsyncSession,
    filename: str,
    result: ParseResult,
    jurisdiction_id: uuid.UUID | None,
    background_tasks: BackgroundTasks,
) -> dict:

    detected_source = result.detected_source
    # Dedupe by (address, sale_status) — CoStar exports occasionally list
    # the same property twice in one report (e.g. listed under two brokers).
    # PostgreSQL's ON CONFLICT DO UPDATE won't accept duplicates within a
    # single statement, so we keep the LAST occurrence here. The earlier
    # ones still appear in raw_row of the surviving record if the operator
    # wants to inspect them.
    seen: dict[tuple, "ListingRow"] = {}
    for r in result.rows:
        seen[(r.address, r.sale_status)] = r
    rows = list(seen.values())
    if len(rows) < len(result.rows):
        result.warnings.append(
            f"Deduped {len(result.rows) - len(rows)} duplicate row(s) by (address, sale_status); "
            f"kept the last occurrence of each."
        )
    if not rows:
        return {
            "inserted": 0,
            "updated": 0,
            "dropped": 0,
            "match_pending": 0,
            "source": detected_source,
            "parser_warnings": result.warnings,
            "message": "File parsed cleanly but contained no rows.",
        }

    jid = await _resolve_jurisdiction(db, rows, jurisdiction_id)
    now = datetime.now(timezone.utc)

    # Step 1: existing rows in scope (jurisdiction, source) — used to compute
    # inserts vs updates and to find drops.
    existing_rows = (
        await db.execute(
            select(
                ForsaleListing.id,
                ForsaleListing.address,
                ForsaleListing.sale_status,
                ForsaleListing.is_current,
            ).where(
                ForsaleListing.jurisdiction_id == jid,
                ForsaleListing.source == detected_source,
            )
        )
    ).all()
    existing_keys = {(r.address, r.sale_status) for r in existing_rows}
    uploaded_keys = {(r.address, r.sale_status) for r in rows}

    inserted = len(uploaded_keys - existing_keys)
    updated = len(uploaded_keys & existing_keys)
    dropped = len(existing_keys - uploaded_keys)

    # Step 2: mark drops (rows previously current but absent in this upload)
    if dropped > 0:
        drop_keys = list(existing_keys - uploaded_keys)
        # batch-update — chunk to avoid IN-list explosion
        for chunk_start in range(0, len(drop_keys), 500):
            chunk = drop_keys[chunk_start : chunk_start + 500]
            await db.execute(
                update(ForsaleListing)
                .where(
                    ForsaleListing.jurisdiction_id == jid,
                    ForsaleListing.source == detected_source,
                    ForsaleListing.is_current.is_(True),
                    # tuple-IN: SQLAlchemy expands a list of tuples
                    func.row(ForsaleListing.address, ForsaleListing.sale_status).in_(
                        [func.row(a, s) for a, s in chunk]
                    ),
                )
                .values(is_current=False, dropped_at=now)
            )

    # Step 3: UPSERT each row
    if rows:
        records = [
            _listing_row_to_dict(r, jid, detected_source, filename)
            for r in rows
        ]
        stmt = pg_insert(ForsaleListing).values(records)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_forsale_listings_juris_source_addr_status",
            set_={
                "city": stmt.excluded.city,
                "state": stmt.excluded.state,
                "zip": stmt.excluded.zip,
                "sale_category": stmt.excluded.sale_category,
                "property_type": stmt.excluded.property_type,
                "secondary_type": stmt.excluded.secondary_type,
                "rating": stmt.excluded.rating,
                "size_sf": stmt.excluded.size_sf,
                "sale_price": stmt.excluded.sale_price,
                "price_per_sf": stmt.excluded.price_per_sf,
                "cap_rate": stmt.excluded.cap_rate,
                "days_on_market": stmt.excluded.days_on_market,
                "sale_type": stmt.excluded.sale_type,
                "property_name": stmt.excluded.property_name,
                "land_area_ac": stmt.excluded.land_area_ac,
                "land_area_sf": stmt.excluded.land_area_sf,
                "price_per_ac": stmt.excluded.price_per_ac,
                "price_per_land_sf": stmt.excluded.price_per_land_sf,
                "num_units": stmt.excluded.num_units,
                "price_per_unit": stmt.excluded.price_per_unit,
                "listing_broker_company": stmt.excluded.listing_broker_company,
                "listing_broker_contact": stmt.excluded.listing_broker_contact,
                "listing_broker_phone": stmt.excluded.listing_broker_phone,
                "listing_broker_email": stmt.excluded.listing_broker_email,
                "building_class": stmt.excluded.building_class,
                "zoning_listed": stmt.excluded.zoning_listed,
                "market": stmt.excluded.market,
                "submarket": stmt.excluded.submarket,
                "county": stmt.excluded.county,
                "raw_row": stmt.excluded.raw_row,
                "source_file": stmt.excluded.source_file,
                "is_current": True,
                "last_seen_at": now,
                "dropped_at": None,
            },
        )
        await db.execute(stmt)

    await db.commit()

    # Step 4: background-task the matching cascade + alert worker
    async def _bg_match_and_alert() -> None:
        from app.workers.listing_alerts import fire_alerts_for_upload
        async with async_session_maker() as bg_db:
            try:
                counts = await match_pending_listings(jid, detected_source, bg_db)
                logger.info(
                    "Listing match complete for juris=%s source=%s: %s",
                    jid, detected_source, counts,
                )
            except Exception as exc:
                logger.error("Listing match failed for juris=%s source=%s: %s", jid, detected_source, exc)
                return
            try:
                alert_counts = await fire_alerts_for_upload(jid, bg_db)
                logger.info(
                    "Listing alerts complete for juris=%s: %s",
                    jid, alert_counts,
                )
            except Exception as exc:
                logger.error("Listing alerts failed for juris=%s: %s", jid, exc)

    background_tasks.add_task(_bg_match_and_alert)

    return {
        "inserted": inserted,
        "updated": updated,
        "dropped": dropped,
        "match_pending": inserted + updated,
        "source": detected_source,
        "jurisdiction_id": str(jid),
        "parser_warnings": result.warnings,
    }


# ── list ─────────────────────────────────────────────────────────────────────


@router.get("/jurisdictions/{jurisdiction_id}/listings")
async def list_jurisdiction_listings(
    jurisdiction_id: uuid.UUID,
    is_current: bool = True,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return current listings for a jurisdiction. Shape used by the map
    layer + admin review page. Coordinates come from either the matched
    parcel's centroid or the geocoded fallback."""
    rows = (
        await db.execute(
            select(ForsaleListing)
            .where(
                ForsaleListing.jurisdiction_id == jurisdiction_id,
                ForsaleListing.is_current.is_(is_current),
            )
            .order_by(ForsaleListing.uploaded_at.desc())
        )
    ).scalars().all()

    out: list[dict] = []
    for r in rows:
        out.append({
            "id": str(r.id),
            "source": r.source,
            "address": r.address,
            "city": r.city,
            "state": r.state,
            "zip": r.zip,
            "sale_status": r.sale_status,
            "sale_price": float(r.sale_price) if r.sale_price is not None else None,
            "days_on_market": r.days_on_market,
            "listing_broker_company": r.listing_broker_company,
            "listing_broker_contact": r.listing_broker_contact,
            "listing_broker_phone": r.listing_broker_phone,
            "listing_broker_email": r.listing_broker_email,
            "matched_parcel_id": r.matched_parcel_id,
            "match_confidence": float(r.match_confidence) if r.match_confidence is not None else None,
            "match_method": r.match_method,
            "lat": float(r.geocoded_lat) if r.geocoded_lat is not None else None,
            "lon": float(r.geocoded_lon) if r.geocoded_lon is not None else None,
            "is_current": r.is_current,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            "co_listed_parcels": r.co_listed_parcels,
        })
    return out


# ── manual reassign ──────────────────────────────────────────────────────────


@router.patch("/listings/{listing_id}/match")
async def reassign_listing(
    listing_id: uuid.UUID,
    matched_parcel_id: int | None = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually link a listing to a parcel (or unlink with null).

    Operator uses this from the ListingCard's "Reassign" button when
    the automated matcher landed on the wrong parcel. The case that
    motivated this: same-owner cluster matching can pick the wrong
    cluster when a developer owns multiple disjoint groups of parcels.

    Side effects: match_method='manual', match_confidence=1.0,
    co_listed_parcels cleared (operator is overriding with a single
    parcel; if they want to re-cluster they re-run matching).
    """
    listing = await db.get(ForsaleListing, listing_id)
    if listing is None:
        raise HTTPException(404, "Listing not found")

    if matched_parcel_id is None:
        # Unlink
        listing.matched_parcel_id = None
        listing.match_confidence = None
        listing.match_method = "manual_unlinked"
        listing.co_listed_parcels = None
    else:
        parcel = await db.get(Parcel, matched_parcel_id)
        if parcel is None:
            raise HTTPException(404, f"Parcel {matched_parcel_id} not found")
        if parcel.jurisdiction_id != listing.jurisdiction_id:
            raise HTTPException(
                400,
                f"Parcel jurisdiction {parcel.jurisdiction_id} does not match "
                f"listing jurisdiction {listing.jurisdiction_id}",
            )
        listing.matched_parcel_id = parcel.id
        listing.match_confidence = 1.0
        listing.match_method = "manual"
        listing.co_listed_parcels = None

    await db.commit()
    await db.refresh(listing)

    return {
        "id": str(listing.id),
        "matched_parcel_id": listing.matched_parcel_id,
        "match_confidence": (
            float(listing.match_confidence) if listing.match_confidence is not None else None
        ),
        "match_method": listing.match_method,
    }


# ── debug ────────────────────────────────────────────────────────────────────


@router.get("/listings/_debug-geocode")
async def debug_geocode(address: str, city: str = "", state: str = "") -> dict:
    """One-shot Census geocode test. Confirms whether the Railway
    container can actually reach geocoding.geo.census.gov."""
    geo = await geocode_address(address, city or None, state or None)
    if geo is None:
        return {"address": address, "city": city, "state": state, "match": None}
    return {
        "address": address,
        "matched": geo.matched_address,
        "lat": geo.lat,
        "lon": geo.lon,
        "match_type": geo.match_type,
    }


@router.post("/listings/_debug-rematch/{jurisdiction_id}")
async def debug_rematch(
    jurisdiction_id: uuid.UUID,
    source: str = "costar",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset match state for one (jurisdiction, source) and kick off
    a fresh matching cascade in the background. Returns immediately
    with the number of rows queued. Poll
    GET /api/jurisdictions/{id}/listings to see lat/lon and
    match_method populate. Useful when the original upload's
    background task silently failed."""
    result = await db.execute(
        update(ForsaleListing)
        .where(
            ForsaleListing.jurisdiction_id == jurisdiction_id,
            ForsaleListing.source == source,
            ForsaleListing.is_current.is_(True),
        )
        .values(
            matched_parcel_id=None,
            match_confidence=None,
            match_method=None,
            geocoded_lat=None,
            geocoded_lon=None,
        )
    )
    await db.commit()
    queued = result.rowcount or 0

    async def _bg() -> None:
        async with async_session_maker() as bg_db:
            try:
                counts = await match_pending_listings(
                    jurisdiction_id, source, bg_db
                )
                logger.info(
                    "debug-rematch juris=%s source=%s: %s",
                    jurisdiction_id, source, counts,
                )
            except Exception as exc:
                logger.exception(
                    "debug-rematch failed juris=%s source=%s: %s",
                    jurisdiction_id, source, exc,
                )

    background_tasks.add_task(_bg)
    return {"queued": queued, "jurisdiction_id": str(jurisdiction_id), "source": source}


# ── rematch-all (admin) ──────────────────────────────────────────────────────
#
# In-memory job registry. Single-instance Railway deploy makes this safe;
# if the dyno restarts mid-job, the rematch is idempotent so the operator
# can simply re-fire. Surviving job records across restarts would mean
# persisting state to Postgres or Redis — not worth the complexity until
# we have evidence anyone needs the history.
#
# Capped at 20 most-recent jobs to bound memory; older entries are evicted
# in FIFO order when a new job is registered.
_REMATCH_JOBS: dict[str, dict[str, Any]] = {}
_REMATCH_JOBS_MAX = 20
# Cap on how many "flipped to matched" diagnostics we keep in a job
# record. The full list is in the logs; the response is just a sample.
_FLIPPED_SAMPLE_CAP = 100


def _register_job(job_id: str, state: dict[str, Any]) -> None:
    _REMATCH_JOBS[job_id] = state
    while len(_REMATCH_JOBS) > _REMATCH_JOBS_MAX:
        # Evict oldest by insertion order — dicts preserve it in 3.7+.
        oldest = next(iter(_REMATCH_JOBS))
        del _REMATCH_JOBS[oldest]


@router.post("/listings/_rematch-all", status_code=202)
async def rematch_all_listings(
    background_tasks: BackgroundTasks,
    jurisdiction_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Re-run the matcher cascade against every ``is_current`` listing,
    optionally scoped to one jurisdiction. Returns 202 immediately with a
    ``job_id``; poll ``GET /api/listings/_rematch-status/{job_id}`` for
    progress.

    Does NOT re-geocode. Reuses ``geocoded_lat``/``geocoded_lon`` from
    the original ingest. Listings that were never geocoded only get the
    address-based tiers 1-2. This keeps the run cheap and bounded —
    useful after matcher-logic improvements ship, less useful after
    geocoder improvements (those need a full re-ingest or a separate
    re-geocode endpoint).

    Auth: none, mirroring _run-digest and _score-all. The operation is
    idempotent and only mutates listing rows; no external side effects.
    """
    job_id = str(uuid.uuid4())
    state: dict[str, Any] = {
        "job_id": job_id,
        "status": "running",
        "jurisdiction_id": str(jurisdiction_id) if jurisdiction_id else None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total": 0,
        "processed": 0,
        "matched": 0,
        "newly_matched": 0,
        "still_unmatched": 0,
        "method_counts": {},
        "flipped_to_matched": [],
        "flipped_sample_truncated": False,
        "errors": [],
    }
    _register_job(job_id, state)

    async def _bg() -> None:
        try:
            async with async_session_maker() as bg_db:
                stmt = select(ForsaleListing).where(
                    ForsaleListing.is_current.is_(True)
                )
                if jurisdiction_id is not None:
                    stmt = stmt.where(
                        ForsaleListing.jurisdiction_id == jurisdiction_id
                    )
                listings = list((await bg_db.execute(stmt)).scalars().all())
                state["total"] = len(listings)

                for listing in listings:
                    prior_matched_parcel = listing.matched_parcel_id
                    try:
                        result = await rematch_listing(listing, bg_db)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception(
                            "rematch_listing failed for listing=%s", listing.id
                        )
                        state["errors"].append({
                            "listing_id": str(listing.id),
                            "error": str(exc),
                        })
                        state["processed"] += 1
                        continue

                    state["processed"] += 1
                    method = result.match_method or "unmatched"
                    state["method_counts"][method] = (
                        state["method_counts"].get(method, 0) + 1
                    )
                    if result.matched_parcel_id is not None:
                        state["matched"] += 1
                        if prior_matched_parcel is None:
                            state["newly_matched"] += 1
                            if (
                                len(state["flipped_to_matched"])
                                < _FLIPPED_SAMPLE_CAP
                            ):
                                state["flipped_to_matched"].append({
                                    "listing_id": str(listing.id),
                                    "address": listing.address,
                                    "method": result.match_method,
                                    "confidence": result.match_confidence,
                                })
                            else:
                                state["flipped_sample_truncated"] = True
                    else:
                        state["still_unmatched"] += 1

                await bg_db.commit()

            state["status"] = "completed"
            logger.info(
                "rematch-all job=%s complete: total=%d matched=%d "
                "newly_matched=%d still_unmatched=%d methods=%s errors=%d",
                job_id, state["total"], state["matched"],
                state["newly_matched"], state["still_unmatched"],
                state["method_counts"], len(state["errors"]),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("rematch-all job=%s failed: %s", job_id, exc)
            state["status"] = "failed"
            state["errors"].append({"listing_id": None, "error": str(exc)})
        finally:
            state["finished_at"] = datetime.now(timezone.utc).isoformat()

    background_tasks.add_task(_bg)
    return {"job_id": job_id, "status": "started"}


@router.get("/listings/_rematch-status/{job_id}")
async def rematch_status(job_id: str) -> dict[str, Any]:
    """Return the current state of an in-flight or completed rematch
    job. 404 if the job_id is unknown (either never existed or evicted
    from the in-memory registry — see _REMATCH_JOBS_MAX).
    """
    state = _REMATCH_JOBS.get(job_id)
    if state is None:
        raise HTTPException(404, "rematch job not found (may have been evicted)")
    return state
