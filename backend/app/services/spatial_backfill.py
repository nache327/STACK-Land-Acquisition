"""
Spatial backfills used by the ingestion pipeline and operational recovery.
"""
from __future__ import annotations

import logging
import uuid

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.jurisdiction import CoverageLevel, Jurisdiction


def _binding_needed_predicate(
    force: bool, district_beats_attr: bool, alias: str = ""
) -> str:
    """SQL predicate selecting parcels that still need a zoning (re)binding.

    Drives both the fast-skip count and the UPDATE's WHERE so they stay in
    lock-step. ``alias`` prefixes the columns (e.g. ``'p'``) for use inside the
    parcel subquery. Precedence policy (audit "D2"):
      - force            → rebind everything.
      - district_beats_attr (county_gis) → rebind unzoned parcels AND any whose
        code is not yet authoritatively district-contained, so a municipal
        district overrides a stale county 'parcel_attr' code.
      - default (city_gis) → only unzoned parcels (preserves the NYC fast-skip
        and the authoritative parcel-layer code).
    """
    col = f"{alias}." if alias else ""
    if force:
        return "TRUE"
    if district_beats_attr:
        return (
            f"({col}zoning_code IS NULL OR {col}zoning_code = '' "
            f"OR {col}zoning_code_source IS DISTINCT FROM 'district_spatial')"
        )
    return f"({col}zoning_code IS NULL OR {col}zoning_code = '')"


async def refresh_jurisdiction_bbox(
    jurisdiction: Jurisdiction, db: AsyncSession
) -> list[float] | None:
    """Persist [minLng, minLat, maxLng, maxLat] from parcel geometry."""
    result = await db.execute(
        text(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels
            WHERE jurisdiction_id = :jid
              AND geom IS NOT NULL
            """
        ),
        {"jid": jurisdiction.id},
    )
    row = result.one_or_none()
    if row is None or row.minx is None:
        return None
    bbox = [float(row.minx), float(row.miny), float(row.maxx), float(row.maxy)]
    jurisdiction.bbox = bbox
    return bbox


async def backfill_parcel_zoning_from_districts(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    fill_missing_zone_code: bool = True,
    nearest_within_meters: float | None = None,
    district_beats_attr: bool = False,
    force: bool = False,
) -> int:
    """
    Backfill `parcels.zone_class` using parcel centroid containment.

    Uses ST_Within(centroid, district) instead of full polygon intersection —
    10-100x faster on large jurisdictions (point-in-polygon vs polygon-polygon).
    Accurate for normal parcels; a parcel straddling a zone boundary gets the
    zone that contains its centroid.

    Runs on a fresh raw asyncpg connection (session-mode 5432 + command_timeout
    7200s + server-side statement_timeout=0) so Supabase doesn't cancel the
    query mid-flight on jurisdictions with hundreds of thousands of parcels.
    SQLAlchemy's asyncpg dialect imposes a much shorter per-statement timeout
    that has killed this UPDATE on Philadelphia (547k parcels × 29k districts).

    nearest_within_meters: when set, parcels not contained by any district
    after the ST_Within pass are bound to the *nearest* district within N
    meters via a second ST_DWithin pass. Off by default — the contained-only
    behavior is fully preserved. Op-5 needs this fallback because vendor
    zoning PDFs digitized to polygons typically leave 20-40% of parcels just
    outside any single polygon (street-frontage gaps, gutters between
    overlay districts) even when the human reader can unambiguously assign
    them to the visually-adjacent zone.

    Every write from this service stamps `parcels.zone_binding_method`
    ('contained' or 'nearest_<N>m') AND `parcels.zoning_code_source`
    ('district_spatial' or 'nearest') so the audit can split contained-vs-
    inferred coverage without changing the ≥70% operational gate.

    Precedence (audit "D2"): with ``district_beats_attr=True`` (pass this for
    county_gis jurisdictions), a municipal district binding OVERRIDES a county
    parcel-attribute code — the thin county attribute is the weaker authority.
    Default False preserves the city_gis behavior where the parcel layer's own
    zoning is authoritative (and keeps the NYC fast-skip intact). ``force``
    rebinds every parcel regardless of current source.
    """
    logger = logging.getLogger(__name__)
    # Which parcels still need a (re)binding drives both the fast-skip and the
    # UPDATE's WHERE. A parcel that is already authoritatively district-bound
    # ('district_spatial') is never rewritten unless forced — that keeps the NYC
    # fast-skip (13 unzoned of 856,670 → don't rewrite 856k rows) AND lets a
    # county's municipal layer override a stale 'parcel_attr' code (D2 item 3).
    needs_pred = _binding_needed_predicate(force, district_beats_attr)

    pre_counts = await db.execute(text(
        "SELECT "
        " (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid) AS total,"
        f" (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid AND {needs_pred}) AS needs"
    ), {"jid": jurisdiction_id})
    row = pre_counts.one()
    total = int(row.total or 0)
    needs = int(row.needs or 0)
    if total > 0 and needs / total < 0.01:
        # <1% still need binding — bail. Logged so the operator can tell the
        # difference between "skipped because already done" and "failed".
        logger.info(
            "backfill_parcel_zoning_from_districts skipping %s — "
            "%d/%d parcels (%.2f%%) already bound (district_beats_attr=%s force=%s)",
            jurisdiction_id, total - needs, total,
            (total - needs) / total * 100, district_beats_attr, force,
        )
        return 0

    # zoning_code + zoning_code_source are stamped together so a row's code and
    # its authority never diverge (D2 item 4). A district row always carries a
    # non-empty zone_code (enforced at ingest), so taking it also aligns
    # zone_class (set from the same district) with the code.
    zone_code_set = (
        ", zoning_code = sub.zone_code, zoning_code_source = 'district_spatial'"
        if fill_missing_zone_code
        else ""
    )
    # Same predicate as the skip check, aliased to the parcel subquery `p`.
    needs_pred_p = _binding_needed_predicate(force, district_beats_attr, alias="p")
    session_url = settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(
        session_url, statement_cache_size=0, command_timeout=7200
    )
    contained_updated = 0
    nearest_updated = 0
    try:
        await conn.execute("SET statement_timeout = 0")
        # ── Pass 1: ST_Within (centroid contained in district) ──────────────
        # LATERAL + LIMIT 1 instead of CTE + ROW_NUMBER. The earlier
        # ROW_NUMBER OVER (PARTITION BY p.id ORDER BY zd.id) query
        # materialised every parcel/district overlap (≈ N_parcels × 6 on
        # Fairfax) and sorted that 2.2M-row, 988-byte-wide result for the
        # window function — the sort spilled to disk and hung Fairfax for
        # the full 30-min dramatiq time_limit.
        # The LATERAL must live inside a subquery in the FROM clause —
        # PostgreSQL refuses to let a top-level LATERAL reference the
        # UPDATE target table directly ("invalid reference to FROM-clause
        # entry for table p"). Pulling parcels into the inner FROM lets
        # the lateral see p.geom while UPDATE joins target.id =
        # sub.parcel_id at the outer level.
        contained_status = await conn.execute(
            f"""
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = 'contained'
                {zone_code_set}
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1
                  AND p.geom IS NOT NULL
                  AND {needs_pred_p}
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            jurisdiction_id,
        )
        try:
            contained_updated = int(contained_status.split()[-1])
        except (ValueError, IndexError):
            contained_updated = 0

        # ── Pass 2: ST_DWithin fallback (optional) ──────────────────────────
        # Snap parcels not contained by any district to their *nearest*
        # district within N meters. Uses geography casts so $N is meters
        # (not degrees) and ORDER BY ST_Distance for tie-breaking on the
        # short list returned by the GIST index probe.
        if nearest_within_meters is not None and nearest_within_meters > 0:
            radius = float(nearest_within_meters)
            binding_label = f"nearest_{int(round(radius))}m"
            # Nearest binding is its own (weaker) authority in the provenance.
            zone_code_set_nearest = (
                ", zoning_code = sub.zone_code, zoning_code_source = 'nearest'"
                if fill_missing_zone_code
                else ""
            )
            nearest_status = await conn.execute(
                f"""
                UPDATE parcels target
                SET zone_class = sub.zone_class,
                    zone_binding_method = $2
                    {zone_code_set_nearest}
                FROM (
                    SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT zd.zone_class, zd.zone_code
                        FROM zoning_districts zd
                        WHERE zd.jurisdiction_id = $1
                          AND zd.geom IS NOT NULL
                          AND ST_DWithin(
                              zd.geom::geography,
                              ST_Centroid(p.geom)::geography,
                              $3
                          )
                        ORDER BY ST_Distance(
                            zd.geom::geography,
                            ST_Centroid(p.geom)::geography
                        )
                        LIMIT 1
                    ) m
                    WHERE p.jurisdiction_id = $1
                      AND p.geom IS NOT NULL
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id = sub.parcel_id
                """,
                jurisdiction_id,
                binding_label,
                radius,
            )
            try:
                nearest_updated = int(nearest_status.split()[-1])
            except (ValueError, IndexError):
                nearest_updated = 0
            logger.info(
                "backfill_parcel_zoning_from_districts %s: contained=%d, "
                "nearest_within_%.1fm=%d",
                jurisdiction_id, contained_updated, radius, nearest_updated,
            )
    finally:
        await conn.close()
    return contained_updated + nearest_updated


async def backfill_parcel_city_from_districts(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    municipality_keys: tuple[str, ...] = ("Municipality", "MUNICIPALITY", "municipality"),
) -> int:
    """Stamp ``parcels.city`` from the containing zoning district's municipality name.

    For county_gis jurisdictions whose PARCEL layer carries no municipality field
    (Montgomery County PA: the parcel layer is TAXPIN + acreage only) but whose
    ZONING layer is name-native — the municipality name lives in
    ``zoning_districts.raw_attributes`` (e.g. the ``Municipality`` key, Bucks/Mont PA).

    Catch #33/#35 family: stamps via ST_Within(centroid, district) **only WHERE
    parcels.city IS NULL**, so jurisdictions that already resolved city at ingest
    (Bucks native ``MUNICIPALITY`` field, Chester ``muni_name_map`` crosswalk) are
    never clobbered. No-op when no district in the jurisdiction carries a
    municipality value, so it is safe to run unconditionally for every county_gis
    ingest (the common case writes nothing).

    Same raw-asyncpg execution profile as ``backfill_parcel_zoning_from_districts``
    (session-mode 5432, statement_timeout=0, LATERAL + LIMIT 1, centroid containment)
    so Supabase doesn't cancel mid-flight on 300k+ parcel counties.
    """
    logger = logging.getLogger(__name__)
    # COALESCE the candidate JSONB keys into one municipality expression. The keys
    # are fixed code constants (not user input), so interpolation is injection-safe.
    muni_expr = "COALESCE(" + ", ".join(
        f"NULLIF(zd.raw_attributes->>'{k}', '')" for k in municipality_keys
    ) + ")"

    # Bail when no district carries a municipality value — avoids a full parcel
    # scan on the (majority) jurisdictions whose zoning layer has no muni field.
    has_muni = await db.execute(
        text(
            f"SELECT EXISTS(SELECT 1 FROM zoning_districts zd "
            f"WHERE zd.jurisdiction_id = :jid AND {muni_expr} IS NOT NULL)"
        ),
        {"jid": jurisdiction_id},
    )
    if not bool(has_muni.scalar()):
        logger.info(
            "backfill_parcel_city_from_districts skipping %s — "
            "no zoning_districts carry a municipality value",
            jurisdiction_id,
        )
        return 0

    session_url = settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(
        session_url, statement_cache_size=0, command_timeout=7200
    )
    updated = 0
    try:
        await conn.execute("SET statement_timeout = 0")
        status = await conn.execute(
            f"""
            UPDATE parcels target
            SET city = sub.muni
            FROM (
                SELECT p.id AS parcel_id, m.muni
                FROM parcels p,
                LATERAL (
                    SELECT {muni_expr} AS muni
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1
                      AND zd.geom IS NOT NULL
                      AND {muni_expr} IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1
                  AND p.geom IS NOT NULL
                  AND p.city IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            jurisdiction_id,
        )
        try:
            updated = int(status.split()[-1])
        except (ValueError, IndexError):
            updated = 0
    finally:
        await conn.close()
    logger.info(
        "backfill_parcel_city_from_districts %s: stamped city on %d parcels",
        jurisdiction_id, updated,
    )
    return updated


async def refresh_jurisdiction_coverage_level(
    jurisdiction: Jurisdiction,
    db: AsyncSession,
) -> CoverageLevel:
    """
    Set a stricter-but-still-compact coverage enum on the jurisdiction row.
    """
    result = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid) AS parcel_count,
                -- Real verdicts only (audit "D2"): exclude soft-deleted tombstones
                -- and the placeholder stubs (inherited_pending defers to a future
                -- sprint; op5_factory_catchall is requires-review; the default
                -- 'unclear' is the heuristic-bootstrap origin). Counting those
                -- inflated coverage_level to full/partial on jurisdictions that
                -- have no grounded matrix at all.
                (SELECT COUNT(*) FROM zone_use_matrix
                   WHERE jurisdiction_id = :jid
                     AND deleted_at IS NULL
                     AND classification_source NOT IN (
                         'inherited_pending', 'unclear', 'op5_factory_catchall'
                     )) AS matrix_count,
                (SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = :jid) AS zoning_count,
                (SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid AND has_structure IS NULL) AS null_vacancy_count
            """
        ),
        {"jid": jurisdiction.id},
    )
    row = result.one()
    if row.parcel_count > 0 and row.matrix_count > 0 and row.zoning_count > 0 and jurisdiction.bbox and row.null_vacancy_count == 0:
        jurisdiction.coverage_level = CoverageLevel.full
    elif row.parcel_count > 0 and (row.matrix_count > 0 or row.zoning_count > 0):
        jurisdiction.coverage_level = CoverageLevel.partial
    elif row.parcel_count > 0:
        jurisdiction.coverage_level = CoverageLevel.parcels_only
    elif row.matrix_count > 0 or row.zoning_count > 0:
        jurisdiction.coverage_level = CoverageLevel.zoning_only
    else:
        jurisdiction.coverage_level = CoverageLevel.partial
    return jurisdiction.coverage_level
