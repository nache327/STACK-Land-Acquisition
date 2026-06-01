"""Backfill parcels.has_structure from AGRC LIR PROP_CLASS.

Why this exists: county-wide UGRC parcel ingests (Salt Lake County, etc.)
leave parcels.has_structure NULL on the vast majority of rows because the
non-LIR parcel layer is sparse on LAND_USE / PROP_TYPE — the fields
_map_row uses to derive vacancy. Without has_structure, every parcel
fails the dashboard's `vacancy_unknown` viability check, which is why
Hot Deals and Worth a Look surface zero matches in SLCo despite having
~400k parcels with real demographics.

AGRC publishes a separate LIR (Local Information Records) layer per
county — same parcels, plus a PROP_CLASS string ("Vacant", "Residential",
"Tax Exempt - Government", etc.). The existing scripts/lir_fallback_zoning.py
already uses this layer to populate zoning_code; we can mine the same
PROP_CLASS string for vacancy signal.

Mapping rules — `_has_structure_from_prop_class`:

  Vacant / Vacant - Agricultural / Vacant - Commercial / Undeveloped
      → has_structure = False
  Residential / Commercial / Commercial - Retail / Commercial - Office
  Space / Commercial - Apartment & Condo / Commercial - Industrial /
  Industrial / Mixed Use
      → has_structure = True
  Tax Exempt / Tax Exempt - Government / Tax Exempt - Charitable
  Organization or Religious / Greenbelt / Centrally Assessed / unknown
      → leave NULL (ambiguous — can be developed or undeveloped)

Idempotent: only fills `has_structure IS NULL`. Re-running after new
parcel ingests for the same county is safe and additive.
"""
from __future__ import annotations

import logging
import time
import uuid
import asyncio
import re
from typing import Any

import geopandas as gpd
import httpx
from shapely.geometry import shape as shapely_shape
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.arcgis_bbox import get_parcel_bbox

logger = logging.getLogger(__name__)


# AGRC's published rate limit: 6000 request units per minute. A LIR
# feature-chunk call at 500 features with geometry consumes ~10-15
# request units (varies by polygon vertex count), so ~400-600 calls/min
# is the safe envelope. A 100ms sleep between calls = ~600 calls/min
# which leaves headroom for the variable cost.
_LIR_INTER_CALL_SLEEP_S = 0.15
_LIR_MAX_429_RETRIES = 3


# AGRC LIR FeatureServers — same source as scripts/lir_fallback_zoning.py.
# Keyed by (state, county) where county is the canonical Jurisdiction.county
# value (post-2026-05-28 normalization — see project_sibling_discovery memory).
_LIR_URLS: dict[tuple[str, str], str] = {
    ("UT", "Salt Lake"): "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_SaltLake_LIR/FeatureServer/0",
    ("UT", "Davis"):     "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Davis_LIR/FeatureServer/0",
    ("UT", "Weber"):     "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Weber_LIR/FeatureServer/0",
    ("UT", "Utah"):      "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah_LIR/FeatureServer/0",
}


# Sets defined as upper-case for case-insensitive matching against whatever
# PROP_CLASS string the LIR layer publishes (we've seen "Vacant" and
# "VACANT" historically; cheap to defend against drift).
_VACANT_PROP_CLASSES = {
    "VACANT",
    "VACANT - AGRICULTURAL",
    "VACANT - COMMERCIAL",
    "UNDEVELOPED",
}
_BUILT_PROP_CLASSES = {
    "RESIDENTIAL",
    "COMMERCIAL",
    "COMMERCIAL - APARTMENT & CONDO",
    "COMMERCIAL - RETAIL",
    "COMMERCIAL - OFFICE SPACE",
    "COMMERCIAL - INDUSTRIAL",
    "INDUSTRIAL",
    "MIXED USE",
}
# Everything else (Tax Exempt, Greenbelt, Centrally Assessed, NULL, unknown)
# is intentionally ambiguous — could be a federal building, an undeveloped
# park, a roadside drainage easement. We leave has_structure NULL rather
# than guess.


def has_structure_from_prop_class(prop_class: str | None) -> bool | None:
    """Map an AGRC LIR PROP_CLASS string to a has_structure tri-state.
    Pure helper; same logic the SQL UPDATE applies. Exposed for the
    unit test."""
    if prop_class is None:
        return None
    key = str(prop_class).strip().upper()
    if not key:
        return None
    if key in _VACANT_PROP_CLASSES:
        return False
    if key in _BUILT_PROP_CLASSES:
        return True
    return None


async def backfill_has_structure_for_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Spatial-join LIR PROP_CLASS polygons to this jurisdiction's parcels
    and fill `has_structure` where it's currently NULL. Returns a summary
    of what changed.

    Only works for jurisdictions whose (state, county) maps to a known
    LIR FeatureServer (currently Salt Lake / Davis / Weber / Utah).
    """
    started = time.monotonic()

    from app.models.jurisdiction import Jurisdiction
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise ValueError(f"Jurisdiction {jurisdiction_id} not found")
    lir_url = _LIR_URLS.get((j.state, (j.county or "").strip()))
    if lir_url is None:
        raise ValueError(
            f"No LIR layer registered for {j.state}/{j.county!r}. Add a "
            f"row to _LIR_URLS in lir_has_structure_backfill.py if AGRC "
            f"publishes one."
        )

    bbox = await get_parcel_bbox(jurisdiction_id, db)
    if bbox is None:
        raise ValueError(
            f"Jurisdiction {j.name} has no parcel bbox — re-ingest parcels first."
        )

    logger.info(
        "LIR has_structure backfill: %s bbox=%s url=%s",
        j.name, bbox, lir_url,
    )
    # Call the LIR layer directly with `outFields=PROP_CLASS` only — the
    # generic download_bbox_features helper uses `outFields=*` which on
    # this 30-field, 400k-row layer times out at the server side and
    # returns zero features after ~60s. Pulling just the one field +
    # geometry keeps each page small and fast (verified <1s per 1000
    # rows in manual probes).
    gdf = await _fetch_lir_features(
        lir_url, bbox, where="PROP_CLASS IS NOT NULL"
    )
    if gdf is None or gdf.empty:
        return {
            "jurisdiction_id": str(jurisdiction_id),
            "lir_features_fetched": 0,
            "parcels_updated_built": 0,
            "parcels_updated_vacant": 0,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    # Classify each LIR feature into has_structure True / False / None.
    # Polygons that map to None are dropped — they contribute no signal.
    prop_class_col = next(
        (c for c in gdf.columns if c.upper() == "PROP_CLASS"), None
    )
    if prop_class_col is None:
        raise ValueError(
            f"LIR response missing PROP_CLASS column; got {list(gdf.columns)}"
        )

    breakdown: dict[str, int] = {}
    classified_geoms_built: list = []
    classified_geoms_vacant: list = []
    for _, row in gdf.iterrows():
        pc = row[prop_class_col]
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        has_struct = has_structure_from_prop_class(pc)
        breakdown[str(pc)] = breakdown.get(str(pc), 0) + 1
        if has_struct is True:
            classified_geoms_built.append(geom)
        elif has_struct is False:
            classified_geoms_vacant.append(geom)
        # has_struct is None: skip (ambiguous PROP_CLASS — federal land,
        # greenbelt, etc.)

    # Two UPDATEs: one for has_structure=True, one for has_structure=False.
    # Mirrors the overlays.py ST_Subdivide pattern so the GiST index on
    # parcels.centroid can actually be used.
    updated_built = await _update_parcels_in_polygons(
        jurisdiction_id, classified_geoms_built, has_structure=True, db=db
    )
    updated_vacant = await _update_parcels_in_polygons(
        jurisdiction_id, classified_geoms_vacant, has_structure=False, db=db
    )

    await db.commit()

    summary = {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "lir_features_fetched": int(len(gdf)),
        "lir_features_built": len(classified_geoms_built),
        "lir_features_vacant": len(classified_geoms_vacant),
        "lir_features_ambiguous": len(gdf) - len(classified_geoms_built) - len(classified_geoms_vacant),
        "parcels_updated_built": updated_built,
        "parcels_updated_vacant": updated_vacant,
        "prop_class_breakdown": dict(sorted(breakdown.items(), key=lambda kv: -kv[1])),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    logger.info(
        "LIR has_structure backfill done: %s — built=%d vacant=%d (lir_features=%d, %.1fs)",
        j.name, updated_built, updated_vacant, len(gdf), summary["elapsed_seconds"],
    )
    return summary


# ── Internals ────────────────────────────────────────────────────────────


class LirFetchDiagnostic(RuntimeError):
    """Carries structured info from a failed LIR fetch so the admin endpoint
    can surface what actually happened instead of returning a silent empty
    GDF that looks like 'no data'."""


async def _fetch_lir_features(
    url: str,
    bbox: tuple[float, float, float, float],  # noqa: ARG001 — kept for API parity; LIR layers are already county-scoped
    *,
    where: str,
    page_size: int = 500,
) -> gpd.GeoDataFrame | None:
    """Fetch LIR features via objectId-range chunking (NOT offset pagination).

    The naive offset-paginated approach capped at ~3,200 features per
    request even though the layer has 391k features. AGRC silently
    truncates deep offsets without setting exceededTransferLimit or
    returning an error. AGRC also rejects `returnIdsOnly=true` when
    combined with a geometry filter (HTTP 400 "Unable to perform query"),
    so we can't even ask for the IDs in a bbox.

    But we don't need to — the LIR layer (Parcels_SaltLake_LIR /
    Parcels_Davis_LIR / etc.) is already county-scoped by construction.
    So the right strategy is:

      Phase 1: `where + returnIdsOnly=true` (no geometry filter) → every
               OBJECTID in the layer matching PROP_CLASS IS NOT NULL.
               One call, returns ~395k ints, ~3 MB payload.

      Phase 2: chunk OBJECTIDs in groups of 500 → `where=OBJECTID IN (...)
               outFields=OBJECTID,PROP_CLASS, returnGeometry=true`. About
               780 calls total at ~0.5s each, ~6 min.

    Raises LirFetchDiagnostic if either phase returns a server error so
    the operator sees what AGRC actually said instead of a silent empty.
    """
    query_url = url.rstrip("/") + "/query"

    # AGRC services1.arcgis.com appears to throttle / WAF cloud IPs
    # presenting the default `python-httpx/x.y.z` User-Agent — the same
    # query from a laptop succeeds, the same query from Railway returns
    # either a silent 60s timeout (page_size=1000) or a generic HTTP 400
    # "Unable to perform query" (page_size=200). Presenting a normal
    # browser UA + an Accept hint clears the gate. Mirrors what
    # scripts/lir_fallback_zoning.py does implicitly via `requests`.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, application/geo+json, */*",
    }

    all_features: list[dict] = []
    async with httpx.AsyncClient(
        timeout=60.0, follow_redirects=True, headers=headers,
    ) as client:
        # Phase 1: get every matching OBJECTID in a single call. AGRC honors
        # returnIdsOnly without an offset cap, where features+offsets are
        # silently truncated past ~3k.
        # No geometry filter — AGRC rejects returnIdsOnly+geometry combos
        # with HTTP 400, AND the LIR layer is already county-scoped (e.g.
        # Parcels_SaltLake_LIR contains only SLCo parcels) so a bbox would
        # filter to a near-100% subset anyway. We spatial-join against
        # parcels.jurisdiction_id in the DB later.
        ids_params = {
            "where": where,
            "returnIdsOnly": "true",
            "f": "json",
        }
        try:
            resp = await client.get(query_url, params=ids_params)
        except httpx.HTTPError as e:
            raise LirFetchDiagnostic(
                f"LIR ID-list HTTP error: {type(e).__name__}: {e}"
            ) from e
        if resp.status_code != 200:
            raise LirFetchDiagnostic(
                f"LIR ID-list HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise LirFetchDiagnostic(
                f"LIR ID-list non-JSON body: {e}; first 200: {resp.text[:200]!r}"
            ) from e
        if data.get("error"):
            raise LirFetchDiagnostic(
                f"LIR ID-list server error: {data['error']}"
            )

        object_ids = data.get("objectIds") or []
        oid_field = data.get("objectIdFieldName", "OBJECTID")
        if not object_ids:
            logger.warning(
                "LIR ID-list returned no matching OBJECTIDs for where=%r",
                where,
            )
            return None

        logger.info(
            "LIR: %d matching OBJECTIDs (field=%s); fetching features in chunks of %d",
            len(object_ids), oid_field, page_size,
        )

        # Phase 2: fetch features by OBJECTID chunk. POST (not GET) because
        # at chunk_size=500 the WHERE clause URL-encodes to ~10KB which
        # exceeds AGRC's IIS URL length limit (404 HTML page back).
        #
        # Rate-limit handling: AGRC enforces a per-minute request-unit
        # cap and returns code 429 with a Retry-After hint when exceeded.
        # Sleeping `_LIR_INTER_CALL_SLEEP_S` between calls keeps the
        # steady-state under the cap; the 429 branch handles the
        # occasional burst overflow.
        for start in range(0, len(object_ids), page_size):
            chunk = object_ids[start : start + page_size]
            id_list = ",".join(str(i) for i in chunk)
            feat_params = {
                "where": f"{oid_field} IN ({id_list})",
                "outSR": "4326",
                "outFields": f"{oid_field},PROP_CLASS",
                "returnGeometry": "true",
                "f": "geojson",
            }

            attempts = 0
            while True:
                try:
                    fresp = await client.post(query_url, data=feat_params)
                except httpx.HTTPError as e:
                    raise LirFetchDiagnostic(
                        f"LIR feature-chunk HTTP error at start={start}: "
                        f"{type(e).__name__}: {e}"
                    ) from e
                if fresp.status_code != 200:
                    raise LirFetchDiagnostic(
                        f"LIR feature-chunk HTTP {fresp.status_code} at start={start}: "
                        f"{fresp.text[:300]}"
                    )
                try:
                    fdata = fresp.json()
                except Exception as e:
                    raise LirFetchDiagnostic(
                        f"LIR feature-chunk non-JSON at start={start}: {e}; "
                        f"first 200: {fresp.text[:200]!r}"
                    ) from e
                err = fdata.get("error") or {}
                if err.get("code") == 429:
                    # Parse "Retry after 60 sec" out of details, default to 60s.
                    wait_s = 60
                    for detail in err.get("details") or []:
                        m = re.search(r"after\s+(\d+)\s*sec", str(detail), re.I)
                        if m:
                            wait_s = int(m.group(1)) + 2
                            break
                    attempts += 1
                    if attempts > _LIR_MAX_429_RETRIES:
                        raise LirFetchDiagnostic(
                            f"LIR feature-chunk exhausted 429 retries at "
                            f"start={start}: {err}"
                        )
                    logger.warning(
                        "LIR 429 at start=%d — sleeping %ds (attempt %d/%d)",
                        start, wait_s, attempts, _LIR_MAX_429_RETRIES,
                    )
                    await asyncio.sleep(wait_s)
                    continue
                if err:
                    raise LirFetchDiagnostic(
                        f"LIR feature-chunk server error at start={start}: {err}"
                    )
                batch = fdata.get("features", []) or []
                all_features.extend(batch)
                break  # success — leave the retry loop

            if (start // page_size) % 25 == 0:
                logger.info(
                    "LIR fetch: %d / %d OBJECTIDs done (%d features in hand)",
                    start + len(chunk), len(object_ids), len(all_features),
                )
            # Steady-state throttle. Spread calls so the per-minute unit
            # quota is never approached in the first place — 429 retry is
            # the fallback, not the main path.
            await asyncio.sleep(_LIR_INTER_CALL_SLEEP_S)

    if not all_features:
        return None
    return gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")


async def _update_parcels_in_polygons(
    jurisdiction_id: uuid.UUID,
    geoms: list,
    *,
    has_structure: bool,
    db: AsyncSession,
) -> int:
    """Set parcels.has_structure = :has_structure for parcels whose
    centroid falls in any of `geoms`. NULL-only — never overwrites an
    existing value.

    Uses the same ST_Subdivide + temp GiST pattern as overlays.py so
    the spatial join scales on county-sized jurisdictions.
    """
    if not geoms:
        return 0

    from shapely.ops import unary_union

    valid = [g for g in geoms if g is not None and not g.is_empty]
    if not valid:
        return 0
    union = unary_union(valid)
    if union is None or union.is_empty:
        return 0

    pieces_tbl = f"_lir_pieces_{uuid.uuid4().hex[:12]}"
    try:
        await db.execute(text(
            f"CREATE TEMP TABLE {pieces_tbl} "
            f"(geom geometry(Geometry, 4326)) ON COMMIT PRESERVE ROWS"
        ))
        await db.execute(
            text(
                f"INSERT INTO {pieces_tbl} (geom) "
                f"SELECT (ST_Dump(ST_Subdivide("
                f"  ST_GeomFromText(:geom, 4326), 256))).geom"
            ),
            {"geom": union.wkt},
        )
        await db.execute(text(
            f"CREATE INDEX ON {pieces_tbl} USING GIST (geom)"
        ))
        await db.execute(text(f"ANALYZE {pieces_tbl}"))

        result = await db.execute(
            text(
                f"""
                UPDATE parcels p
                SET has_structure = :has_structure
                WHERE p.jurisdiction_id = :jid
                  AND p.has_structure IS NULL
                  AND p.centroid IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM {pieces_tbl} op
                    WHERE ST_Intersects(p.centroid, op.geom)
                  )
                """
            ),
            {"jid": str(jurisdiction_id), "has_structure": has_structure},
        )
        return result.rowcount or 0
    finally:
        try:
            await db.execute(text(f"DROP TABLE IF EXISTS {pieces_tbl}"))
        except Exception:  # noqa: BLE001
            pass
