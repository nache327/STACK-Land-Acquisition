"""nj_municipal_discovery — per-town zoning-source discovery for NJ counties.

NJ counties don't publish county-wide zoning. Each of NJ's ~565
municipalities runs its own zoning, so the discovery pattern that works
for VA / MD / Mid-Atlantic counties produces only false positives for
Bergen / Morris / Hunterdon / etc.

This service drives a two-stage loop:

  A. Read the municipality list for a county from
     `backend/data/nj_municipalities.json`.
  B. For each town, run the existing zoning_discovery against the town's
     name, persist top candidates to `zoning_sources` with
     municipality_name set to the town. Confidence threshold ≥ 70
     marks `confidence_label='discovered'`; below threshold
     `confidence_label='discovered_low'`.

The operator then reviews via `GET /jurisdictions/{county_id}/_sources`,
promotes accepted candidates with `_sources/{src_id}/verify`, and runs
`_ingest-municipal-zoning` to actually ingest each verified source into
the county's zoning_districts table.

Per-town bbox lookup uses the existing geocoder
(`arcgis_discovery.geocode_jurisdiction`) — already battle-tested for
this kind of query and avoids depending on a separate
Municipal_Boundaries FeatureServer (which can be rate-limited).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction
from app.models.zoning_source import ZoningSource
from app.services.zoning_discovery import (
    ZoningCandidate,
    _fetch_rejected_endpoints,
    _hub_search,
    _name_tokens,
    _persist_candidates,
    _probe_layer,
    _TOP_N,
)


logger = logging.getLogger(__name__)


# Limit concurrency on outbound Hub + geocoder calls so we don't get rate-
# limited when sweeping a 70-town county.
_PER_TOWN_CONCURRENCY = 4
# Discovery threshold: candidates below this confidence don't get
# auto-promoted to "discovered"; they're stored as "discovered_low" so the
# operator can decide whether they're worth a manual review.
_HIGH_CONFIDENCE_THRESHOLD = 70


@dataclass
class TownDiscoveryResult:
    municipality_name: str
    queried_with: dict[str, Any]
    candidates_total: int
    persisted_count: int
    top_candidates: list[dict]
    error: str | None = None


def _load_municipalities(state: str, county: str) -> list[str]:
    """Read the static municipality reference list for a state+county.

    Currently only NJ is supported (Bergen, Morris, Hunterdon). Returns
    [] if the county isn't in the reference file.
    """
    if (state or "").lower() != "nj":
        return []
    path = Path(__file__).resolve().parent.parent.parent / "data" / "nj_municipalities.json"
    if not path.exists():
        logger.warning("nj_municipalities.json missing at %s", path)
        return []
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        logger.warning("nj_municipalities.json parse error: %s", exc)
        return []
    county_lc = (county or "").lower().replace(" county", "").strip()
    return list(data.get(county_lc) or [])


async def discover_municipal_zoning_for_county(
    county_jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    municipality_names: list[str] | None = None,
) -> dict:
    """Run per-town discovery across every municipality in this county.

    Persists results to zoning_sources keyed on (county_jurisdiction_id,
    municipality_name, zoning_endpoint). Idempotent; re-running refreshes
    confidence without clobbering operator-verified picks.

    Returns a summary {county_name, total_municipalities, results: [...]}.
    """
    j = await db.get(Jurisdiction, county_jurisdiction_id)
    if j is None:
        raise ValueError(f"jurisdiction {county_jurisdiction_id} not found")

    towns = municipality_names or _load_municipalities(j.state or "", j.county or "")
    if not towns:
        return {
            "county": j.name,
            "total_municipalities": 0,
            "results": [],
            "note": (
                f"No municipality reference found for state={j.state!r} "
                f"county={j.county!r}. Check backend/data/nj_municipalities.json."
            ),
        }

    sem = asyncio.Semaphore(_PER_TOWN_CONCURRENCY)
    # AsyncSession isn't safe for concurrent access. Hub probes happen in
    # parallel (network-bound), but the persist/commit critical section
    # must serialize — otherwise commits race and persisted_count returns
    # 0 even when rows landed in the DB.
    db_lock = asyncio.Lock()
    # Pre-fetch the cross-jurisdiction rejected-endpoint set once per sweep
    # so Component D in zoning_discovery._score_candidate has O(1) lookup
    # per candidate (avoids 2,100 DB hops on a 70-town × 30-candidate sweep).
    denylist = await _fetch_rejected_endpoints(db)
    results: list[TownDiscoveryResult] = []

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        async def _one(town: str) -> TownDiscoveryResult:
            async with sem:
                return await _discover_one_town(client, db, j, town, db_lock, denylist)
        results = await asyncio.gather(*[_one(t) for t in towns])

    return {
        "county_jurisdiction_id": str(county_jurisdiction_id),
        "county": j.name,
        "total_municipalities": len(towns),
        "results": [
            {
                "municipality_name": r.municipality_name,
                "candidates_total": r.candidates_total,
                "persisted_count": r.persisted_count,
                "top_candidates": r.top_candidates,
                "error": r.error,
            }
            for r in results
        ],
    }


async def _discover_one_town(
    client: httpx.AsyncClient,
    db: AsyncSession,
    county: Jurisdiction,
    town: str,
    db_lock: asyncio.Lock | None = None,
    denylist: set[str] | None = None,
) -> TownDiscoveryResult:
    """Discover candidates for one town and persist them into zoning_sources."""
    # Query string scopes the Hub search to this specific town.
    state = county.state or ""
    query = f"zoning {town} {state}".strip()

    # Name-match tokens prefer the TOWN name (not the county) so adjacent-
    # county FP suppression still works for per-town queries.
    name_tokens = _name_tokens(town, county.county)

    try:
        # No bbox filter — town-level bboxes are hard to derive without an
        # extra geocode hop. The name-match bonus + wrong-county penalty in
        # the scoring give us most of what bbox-filtering would.
        raw = await _hub_search(client, query, bbox_str="")
    except Exception as exc:
        logger.warning("hub_search failed for %r in %s: %r", town, county.name, exc)
        return TownDiscoveryResult(
            municipality_name=town, queried_with={"query": query},
            candidates_total=0, persisted_count=0, top_candidates=[], error=str(exc),
        )

    candidates: list[ZoningCandidate] = []
    probes = [
        _probe_layer(
            client, item, None, name_tokens,
            jurisdiction=county, denylist=denylist,
        )
        for item in raw
    ]
    probed = await asyncio.gather(*probes, return_exceptions=True)
    for entry in probed:
        if isinstance(entry, Exception) or entry is None:
            continue
        candidates.append(entry)
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    top_n = candidates[:_TOP_N]

    persisted = 0

    async def _do_persist() -> int:
        await _persist_candidates(db, county, top_n, municipality_name=town)
        if top_n:
            from sqlalchemy import update
            await db.execute(
                update(ZoningSource)
                .where(
                    ZoningSource.jurisdiction_id == county.id,
                    ZoningSource.municipality_name == town,
                    ZoningSource.confidence_score < _HIGH_CONFIDENCE_THRESHOLD,
                    ZoningSource.confidence_label != "verified",
                )
                .values(confidence_label="discovered_low")
            )
            await db.commit()
        return len(top_n)

    try:
        if db_lock is not None:
            async with db_lock:
                persisted = await _do_persist()
        else:
            persisted = await _do_persist()
    except Exception as exc:
        logger.warning("persist for %r failed: %r", town, exc)

    return TownDiscoveryResult(
        municipality_name=town,
        queried_with={"query": query, "name_tokens": list(name_tokens.get("expect") or [])},
        candidates_total=len(raw),
        persisted_count=persisted,
        top_candidates=[
            {
                "url": c.url,
                "title": c.title,
                "confidence": c.confidence,
                "feature_count": c.feature_count,
                "geometry_type": c.geometry_type,
            }
            for c in top_n
        ],
    )


async def ingest_verified_municipal_zoning(
    county_jurisdiction_id: uuid.UUID,
    source_ids: list[uuid.UUID],
    db: AsyncSession,
) -> dict:
    """For each given zoning_sources row (must be verified + match this county),
    invoke the existing _backfill-zoning code path so the source is ingested
    into the county's zoning_districts table.

    Returns per-source result rows with the count of districts ingested +
    parcels spatial-updated.
    """
    from sqlalchemy import select
    from app.api.jurisdictions import backfill_zoning as _backfill

    results: list[dict] = []
    for src_id in source_ids:
        src = await db.get(ZoningSource, src_id)
        if src is None or src.jurisdiction_id != county_jurisdiction_id:
            results.append({"source_id": str(src_id), "error": "not found / wrong jurisdiction"})
            continue
        if src.confidence_label != "verified":
            results.append({
                "source_id": str(src_id),
                "municipality_name": src.municipality_name,
                "error": "source not verified — verify it first via _sources/{id}/verify",
            })
            continue
        if not src.zoning_endpoint:
            results.append({"source_id": str(src_id), "error": "no zoning_endpoint"})
            continue
        try:
            # Replace=false so multiple towns aggregate into one county's
            # zoning_districts table. _backfill internally already uses
            # raw asyncpg + ON CONFLICT idempotency for the overlay step.
            r = await _backfill(
                jurisdiction_id=county_jurisdiction_id,
                zoning_url=src.zoning_endpoint,
                where="1=1",
                replace=False,
                spatial_join=True,
                db=db,
            )
            results.append({
                "source_id": str(src_id),
                "municipality_name": src.municipality_name,
                **(r if isinstance(r, dict) else {}),
            })
        except Exception as exc:
            logger.exception("backfill failed for %r", src_id)
            results.append({
                "source_id": str(src_id),
                "municipality_name": src.municipality_name,
                "error": str(exc)[:300],
            })

    return {
        "county_jurisdiction_id": str(county_jurisdiction_id),
        "ingested_sources": len(source_ids),
        "results": results,
    }
