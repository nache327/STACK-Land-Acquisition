"""Municipality-level operational validation.

Answers ONE operator question: "is this municipality operationally
trustworthy?"

A municipality is the unit a sales conversation happens against. For
NJ-style counties (Bergen) it is one town per `parcels.city` value. For
city-jurisdictions (Draper UT, Lehi UT) the jurisdiction itself IS the
municipality and we return a single-row roll-up.

Compute path is read-only and indexed:
  - One scan of `parcels` per jurisdiction, grouped by `city`.
  - One scan of `zoning_districts` per jurisdiction, joined to each
    muni's parcel envelope.
  - Per-muni overlay-overlap sample uses `ST_Overlaps` on a small
    (≤ 200) sample of districts so the cost stays bounded even on
    counties with 100k+ polygons.

Trustworthiness is a single string + a list of `gaps`. Operators
filter munis by band; the gaps list explains why.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Operational trustworthiness thresholds.
#
# These thresholds are deliberate, conservative, and operator-tunable.
# A muni that meets every floor is "operational"; missing one demotes
# it. The bands match `jurisdictions.operational_readiness` semantics
# already in use elsewhere so the dashboard doesn't grow a parallel
# vocabulary.
# ──────────────────────────────────────────────────────────────────────

# Parcel count below this means "we don't really have data for this muni
# yet" — almost certainly missing parcels or wrong-city tagging.
MIN_PARCEL_COUNT_FOR_OPERATIONAL = 50

# Parcel-with-zoning-code rate. 80%+ = healthy overlay. Below 50% means
# the spatial join with zoning_districts didn't bind for most parcels.
MIN_PARCEL_ZONING_PCT_OPERATIONAL = 0.80
MIN_PARCEL_ZONING_PCT_PARTIAL = 0.50

# Parcel-with-zone-class rate. Lower than parcel_zoning_pct is fine
# (matrix bootstrap is the rate-limiter) but a big gap means matrix
# coverage is missing.
MIN_PARCEL_CLASS_PCT_PARTIAL = 0.30

# District count below this is suspect on a real US municipality —
# even a small NJ borough usually has 5+ districts (R, B, I, etc.).
MIN_DISTRICT_COUNT_FOR_OPERATIONAL = 3

# Fraction of districts whose polygons overlap a sibling. Some overlap
# is normal (overlay districts, PUD layers); >5% suggests duplicate
# polygons from a botched re-ingest.
MAX_DISTRICT_OVERLAP_RATIO = 0.05

# District-extent vs parcel-extent overlap. Below 0.5 = the zoning data
# was ingested for the wrong location.
MIN_EXTENT_OVERLAP_RATIO = 0.50

# Sample size for the O(n²) overlap-pair check. Keeps the query bounded
# on huge counties; statistically representative for the duplicate-detect
# signal we care about.
OVERLAP_SAMPLE_LIMIT = 200


@dataclass(slots=True)
class MunicipalityHealth:
    """Per-muni health snapshot — one row per municipality."""
    jurisdiction_id: str
    jurisdiction_name: str
    municipality: str | None        # None when jurisdiction == municipality

    parcel_count: int
    parcel_with_geom_count: int
    parcel_with_zoning_code_count: int
    parcel_with_zone_class_count: int
    parcel_distinct_zone_count: int

    district_count: int
    district_invalid_geom_count: int
    district_overlap_sample_count: int  # pairs in OVERLAP_SAMPLE_LIMIT-sized window
    district_distinct_zone_count: int

    parcel_envelope: list[float] | None     # [xmin, ymin, xmax, ymax]
    district_envelope: list[float] | None

    parcel_zoning_pct: float | None         # parcel_with_zoning_code / parcel_count
    parcel_class_pct: float | None
    extent_overlap_ratio: float | None      # parcel envelope ∩ district envelope
    overlap_ratio: float | None             # district_overlap_sample / sample size
    orphan_zone_code_count: int             # parcel.zoning_code values not in any district

    trustworthiness: str                    # operational | partial | degraded | broken | empty
    gaps: list[str]                         # human-readable reasons for the band

    def to_dict(self) -> dict[str, Any]:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "jurisdiction_name": self.jurisdiction_name,
            "municipality": self.municipality,
            "parcel_count": self.parcel_count,
            "parcel_with_geom_count": self.parcel_with_geom_count,
            "parcel_with_zoning_code_count": self.parcel_with_zoning_code_count,
            "parcel_with_zone_class_count": self.parcel_with_zone_class_count,
            "parcel_distinct_zone_count": self.parcel_distinct_zone_count,
            "district_count": self.district_count,
            "district_invalid_geom_count": self.district_invalid_geom_count,
            "district_overlap_sample_count": self.district_overlap_sample_count,
            "district_distinct_zone_count": self.district_distinct_zone_count,
            "parcel_envelope": self.parcel_envelope,
            "district_envelope": self.district_envelope,
            "parcel_zoning_pct": self.parcel_zoning_pct,
            "parcel_class_pct": self.parcel_class_pct,
            "extent_overlap_ratio": self.extent_overlap_ratio,
            "overlap_ratio": self.overlap_ratio,
            "orphan_zone_code_count": self.orphan_zone_code_count,
            "trustworthiness": self.trustworthiness,
            "gaps": self.gaps,
        }


async def jurisdiction_municipalities_health(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    municipality: str | None = None,
) -> dict[str, Any]:
    """Compute per-muni health for one jurisdiction.

    When `municipality` is given, returns only that muni (drill-down).
    Otherwise returns every muni this jurisdiction has data for, plus a
    rollup band-count summary.
    """
    juris = await db.get(Jurisdiction, jurisdiction_id)
    if juris is None:
        return {"error": "jurisdiction not found", "jurisdiction_id": str(jurisdiction_id)}

    munis = await _list_municipalities(jurisdiction_id, db)
    if municipality is not None:
        munis = [m for m in munis if m == municipality]

    # If the jurisdiction has no `city`-tagged parcels at all, treat it
    # as a single-muni rollup (city-jurisdictions like Draper UT).
    if not munis:
        munis = [None]

    health: list[MunicipalityHealth] = []
    for m in munis:
        h = await _one_municipality_health(juris, m, db)
        if h is not None:
            health.append(h)

    band_counts: dict[str, int] = {}
    for h in health:
        band_counts[h.trustworthiness] = band_counts.get(h.trustworthiness, 0) + 1

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": juris.name,
        "municipality_count": len(health),
        "band_counts": band_counts,
        "thresholds": _threshold_descriptor(),
        "municipalities": [h.to_dict() for h in health],
    }


# ───────────────────────── internals ─────────────────────────────────────────

async def _list_municipalities(
    jurisdiction_id: uuid.UUID, db: AsyncSession,
) -> list[str]:
    """Distinct, non-null `parcels.city` values for this jurisdiction.
    Cheap — one indexed scan."""
    rows = (await db.execute(
        text(
            "SELECT DISTINCT city FROM parcels "
            "WHERE jurisdiction_id = :jid AND city IS NOT NULL "
            "ORDER BY city"
        ).bindparams(jid=jurisdiction_id)
    )).all()
    return [r[0] for r in rows]


async def _one_municipality_health(
    juris: Jurisdiction, municipality: str | None, db: AsyncSession,
) -> MunicipalityHealth | None:
    parcel_stats = await _parcel_stats(juris.id, municipality, db)
    if parcel_stats["parcel_count"] == 0 and municipality is not None:
        # Operator filtered to a muni name we have nothing for — skip.
        return None

    district_stats = await _district_stats(
        juris.id, parcel_stats.get("parcel_envelope"), db,
    )

    extent_overlap = _envelope_overlap_ratio(
        parcel_stats.get("parcel_envelope"),
        district_stats.get("district_envelope"),
    )

    orphan_zone_codes = await _orphan_zone_code_count(juris.id, municipality, db)

    overlap_ratio = (
        district_stats["district_overlap_sample_count"] /
        max(1, min(district_stats["district_count"], OVERLAP_SAMPLE_LIMIT))
    ) if district_stats["district_count"] > 0 else None

    parcel_zoning_pct = (
        parcel_stats["parcel_with_zoning_code_count"] / parcel_stats["parcel_count"]
        if parcel_stats["parcel_count"] > 0 else None
    )
    parcel_class_pct = (
        parcel_stats["parcel_with_zone_class_count"] / parcel_stats["parcel_count"]
        if parcel_stats["parcel_count"] > 0 else None
    )

    band, gaps = _classify(
        parcel_count=parcel_stats["parcel_count"],
        district_count=district_stats["district_count"],
        district_invalid=district_stats["district_invalid_geom_count"],
        parcel_zoning_pct=parcel_zoning_pct,
        parcel_class_pct=parcel_class_pct,
        extent_overlap_ratio=extent_overlap,
        overlap_ratio=overlap_ratio,
        orphan_zone_code_count=orphan_zone_codes,
    )

    return MunicipalityHealth(
        jurisdiction_id=str(juris.id),
        jurisdiction_name=juris.name,
        municipality=municipality,
        parcel_count=parcel_stats["parcel_count"],
        parcel_with_geom_count=parcel_stats["parcel_with_geom_count"],
        parcel_with_zoning_code_count=parcel_stats["parcel_with_zoning_code_count"],
        parcel_with_zone_class_count=parcel_stats["parcel_with_zone_class_count"],
        parcel_distinct_zone_count=parcel_stats["parcel_distinct_zone_count"],
        district_count=district_stats["district_count"],
        district_invalid_geom_count=district_stats["district_invalid_geom_count"],
        district_overlap_sample_count=district_stats["district_overlap_sample_count"],
        district_distinct_zone_count=district_stats["district_distinct_zone_count"],
        parcel_envelope=parcel_stats.get("parcel_envelope"),
        district_envelope=district_stats.get("district_envelope"),
        parcel_zoning_pct=parcel_zoning_pct,
        parcel_class_pct=parcel_class_pct,
        extent_overlap_ratio=extent_overlap,
        overlap_ratio=overlap_ratio,
        orphan_zone_code_count=orphan_zone_codes,
        trustworthiness=band,
        gaps=gaps,
    )


async def _parcel_stats(
    jurisdiction_id: uuid.UUID, municipality: str | None, db: AsyncSession,
) -> dict[str, Any]:
    """One indexed scan over the muni's parcels. Returns the count
    aggregates + parcel envelope (for joining to districts)."""
    sql = (
        "SELECT "
        "  COUNT(*) AS total, "
        "  COUNT(geom) AS with_geom, "
        "  COUNT(zoning_code) AS with_zoning, "
        "  COUNT(zone_class) FILTER (WHERE zone_class IS NOT NULL "
        "                            AND zone_class::text <> 'unknown') AS with_class, "
        "  COUNT(DISTINCT zoning_code) FILTER (WHERE zoning_code IS NOT NULL) AS distinct_codes, "
        "  ST_XMin(ST_Extent(geom))::float AS xmin, "
        "  ST_YMin(ST_Extent(geom))::float AS ymin, "
        "  ST_XMax(ST_Extent(geom))::float AS xmax, "
        "  ST_YMax(ST_Extent(geom))::float AS ymax "
        "FROM parcels WHERE jurisdiction_id = :jid"
    )
    params = {"jid": jurisdiction_id}
    if municipality is not None:
        sql += " AND city = :muni"
        params["muni"] = municipality

    row = (await db.execute(text(sql).bindparams(**params))).first()
    if row is None:
        return {
            "parcel_count": 0, "parcel_with_geom_count": 0,
            "parcel_with_zoning_code_count": 0, "parcel_with_zone_class_count": 0,
            "parcel_distinct_zone_count": 0, "parcel_envelope": None,
        }
    envelope = None
    if row.xmin is not None and row.ymin is not None:
        envelope = [row.xmin, row.ymin, row.xmax, row.ymax]
    return {
        "parcel_count": row.total or 0,
        "parcel_with_geom_count": row.with_geom or 0,
        "parcel_with_zoning_code_count": row.with_zoning or 0,
        "parcel_with_zone_class_count": row.with_class or 0,
        "parcel_distinct_zone_count": row.distinct_codes or 0,
        "parcel_envelope": envelope,
    }


async def _district_stats(
    jurisdiction_id: uuid.UUID,
    parcel_envelope: list[float] | None,
    db: AsyncSession,
) -> dict[str, Any]:
    """Per-muni district stats. When `parcel_envelope` is None (no parcels
    yet) we still count the jurisdiction's full districts so the operator
    can see districts ingested ahead of parcels."""
    if parcel_envelope is None:
        sql = (
            "SELECT "
            "  COUNT(*) AS total, "
            "  COUNT(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)) AS invalid_count, "
            "  COUNT(DISTINCT zone_code) AS distinct_codes, "
            "  ST_XMin(ST_Extent(geom))::float AS xmin, "
            "  ST_YMin(ST_Extent(geom))::float AS ymin, "
            "  ST_XMax(ST_Extent(geom))::float AS xmax, "
            "  ST_YMax(ST_Extent(geom))::float AS ymax "
            "FROM zoning_districts WHERE jurisdiction_id = :jid"
        )
        params = {"jid": jurisdiction_id}
    else:
        # Filter districts to those intersecting the muni's parcel envelope.
        sql = (
            "SELECT "
            "  COUNT(*) AS total, "
            "  COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalid_count, "
            "  COUNT(DISTINCT zone_code) AS distinct_codes, "
            "  ST_XMin(ST_Extent(geom))::float AS xmin, "
            "  ST_YMin(ST_Extent(geom))::float AS ymin, "
            "  ST_XMax(ST_Extent(geom))::float AS xmax, "
            "  ST_YMax(ST_Extent(geom))::float AS ymax "
            "FROM zoning_districts WHERE jurisdiction_id = :jid "
            "  AND geom IS NOT NULL "
            "  AND ST_Intersects(geom, ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326))"
        )
        params = {
            "jid": jurisdiction_id,
            "xmin": parcel_envelope[0], "ymin": parcel_envelope[1],
            "xmax": parcel_envelope[2], "ymax": parcel_envelope[3],
        }
    row = (await db.execute(text(sql).bindparams(**params))).first()
    envelope = None
    if row and row.xmin is not None:
        envelope = [row.xmin, row.ymin, row.xmax, row.ymax]

    overlap_sample_count = await _district_overlap_sample(
        jurisdiction_id, parcel_envelope, db,
    ) if (row and row.total) else 0

    return {
        "district_count": (row.total or 0) if row else 0,
        "district_invalid_geom_count": (row.invalid_count or 0) if row else 0,
        "district_distinct_zone_count": (row.distinct_codes or 0) if row else 0,
        "district_envelope": envelope,
        "district_overlap_sample_count": overlap_sample_count,
    }


async def _district_overlap_sample(
    jurisdiction_id: uuid.UUID,
    parcel_envelope: list[float] | None,
    db: AsyncSession,
) -> int:
    """Count pairwise ST_Overlaps inside a bounded sample of districts.
    A self-join on `zoning_districts` is O(n²); the LIMIT keeps it
    cheap on big counties (Loudoun VA has 4k+ districts) while still
    surfacing duplicate-polygon ingests reliably."""
    base = (
        "WITH sample AS ("
        "  SELECT id, zone_code, geom FROM zoning_districts "
        "  WHERE jurisdiction_id = :jid AND geom IS NOT NULL"
    )
    params: dict[str, Any] = {"jid": jurisdiction_id, "lim": OVERLAP_SAMPLE_LIMIT}
    if parcel_envelope is not None:
        base += (
            "    AND ST_Intersects(geom, ST_MakeEnvelope(:xmin,:ymin,:xmax,:ymax,4326))"
        )
        params.update(
            xmin=parcel_envelope[0], ymin=parcel_envelope[1],
            xmax=parcel_envelope[2], ymax=parcel_envelope[3],
        )
    base += (
        "  LIMIT :lim"
        ") "
        "SELECT COUNT(*) FROM sample a "
        "JOIN sample b ON a.id < b.id "
        "WHERE a.zone_code = b.zone_code AND ST_Overlaps(a.geom, b.geom)"
    )
    result = (await db.execute(text(base).bindparams(**params))).scalar_one()
    return int(result or 0)


async def _orphan_zone_code_count(
    jurisdiction_id: uuid.UUID, municipality: str | None, db: AsyncSession,
) -> int:
    """Zone codes appearing on parcels but NOT on any zoning_district.

    > 0 usually means parcel.zoning_code was populated from the parcel
    source itself (Regrid / county assessor) rather than via spatial
    join against `zoning_districts`. Operationally that's fine but
    the matrix step downstream won't bind these codes — operator
    should know.
    """
    sql = (
        "SELECT COUNT(*) FROM ("
        "  SELECT DISTINCT zoning_code FROM parcels "
        "  WHERE jurisdiction_id = :jid AND zoning_code IS NOT NULL"
    )
    params = {"jid": jurisdiction_id}
    if municipality is not None:
        sql += " AND city = :muni"
        params["muni"] = municipality
    sql += (
        "  EXCEPT SELECT DISTINCT zone_code FROM zoning_districts "
        "  WHERE jurisdiction_id = :jid"
        ") orphans"
    )
    return int((await db.execute(text(sql).bindparams(**params))).scalar_one() or 0)


def _envelope_overlap_ratio(
    a: list[float] | None, b: list[float] | None,
) -> float | None:
    """Same primitive as `_bbox_overlap_ratio` in zoning_discovery —
    inlined here so we don't reach into discovery internals from the
    health module. Returns max(inter/a, inter/b) clamped to [0, 1]."""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return None
    inter_xmin = max(a[0], b[0])
    inter_ymin = max(a[1], b[1])
    inter_xmax = min(a[2], b[2])
    inter_ymax = min(a[3], b[3])
    if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
        return 0.0
    inter = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    if area_a <= 0 or area_b <= 0:
        return None
    return min(1.0, max(inter / area_a, inter / area_b))


def _classify(
    *,
    parcel_count: int,
    district_count: int,
    district_invalid: int,
    parcel_zoning_pct: float | None,
    parcel_class_pct: float | None,
    extent_overlap_ratio: float | None,
    overlap_ratio: float | None,
    orphan_zone_code_count: int,
) -> tuple[str, list[str]]:
    """Map the raw metrics to one of five trustworthiness bands +
    a human-readable gaps list. Bands cascade — a single broken
    signal demotes; gaps explain why."""
    gaps: list[str] = []

    # Empty — operator doesn't have data yet.
    if parcel_count == 0 and district_count == 0:
        return "empty", ["no parcels and no zoning_districts"]

    # Broken — disjoint or near-zero zoning rate, or extent mismatch.
    if parcel_count > 0 and (parcel_zoning_pct or 0) < 0.10:
        gaps.append(
            f"only {(parcel_zoning_pct or 0):.0%} of parcels carry zoning_code "
            f"— spatial join likely failed"
        )
    if extent_overlap_ratio is not None and extent_overlap_ratio < MIN_EXTENT_OVERLAP_RATIO:
        gaps.append(
            f"parcel and district extents overlap only "
            f"{extent_overlap_ratio:.0%} — districts may belong to wrong location"
        )
    if district_invalid > 0:
        gaps.append(
            f"{district_invalid} zoning_district rows have invalid PostGIS geometry"
        )
    if parcel_count > 0 and district_count == 0:
        gaps.append("districts ingested for this muni: 0")

    is_broken = any([
        parcel_count > 0 and (parcel_zoning_pct or 0) < 0.10,
        extent_overlap_ratio is not None and extent_overlap_ratio < MIN_EXTENT_OVERLAP_RATIO,
        district_invalid > 0,
        parcel_count > 0 and district_count == 0,
    ])
    if is_broken:
        return "broken", gaps

    # Degraded — meaningful gaps but data is usable for some operator
    # workflows.
    if parcel_count > 0 and (parcel_zoning_pct or 0) < MIN_PARCEL_ZONING_PCT_PARTIAL:
        gaps.append(
            f"only {(parcel_zoning_pct or 0):.0%} of parcels carry zoning_code "
            f"(<{MIN_PARCEL_ZONING_PCT_PARTIAL:.0%} threshold)"
        )
    if overlap_ratio is not None and overlap_ratio > MAX_DISTRICT_OVERLAP_RATIO:
        gaps.append(
            f"{overlap_ratio:.0%} of sampled districts overlap a sibling — "
            f"likely duplicate polygons from re-ingest"
        )
    if district_count > 0 and district_count < MIN_DISTRICT_COUNT_FOR_OPERATIONAL:
        gaps.append(
            f"only {district_count} distinct district polygons — suspiciously few"
        )
    if parcel_count > 0 and parcel_count < MIN_PARCEL_COUNT_FOR_OPERATIONAL:
        gaps.append(
            f"only {parcel_count} parcels — below the {MIN_PARCEL_COUNT_FOR_OPERATIONAL} floor"
        )

    is_degraded = any([
        parcel_count > 0 and (parcel_zoning_pct or 0) < MIN_PARCEL_ZONING_PCT_PARTIAL,
        overlap_ratio is not None and overlap_ratio > MAX_DISTRICT_OVERLAP_RATIO,
        district_count > 0 and district_count < MIN_DISTRICT_COUNT_FOR_OPERATIONAL,
        parcel_count > 0 and parcel_count < MIN_PARCEL_COUNT_FOR_OPERATIONAL,
    ])
    if is_degraded:
        return "degraded", gaps

    # Partial — usable but matrix coverage / orphan codes hold us short of
    # full operational.
    if parcel_count > 0 and (parcel_zoning_pct or 0) < MIN_PARCEL_ZONING_PCT_OPERATIONAL:
        gaps.append(
            f"{(parcel_zoning_pct or 0):.0%} of parcels carry zoning_code "
            f"(operational floor {MIN_PARCEL_ZONING_PCT_OPERATIONAL:.0%})"
        )
    if parcel_count > 0 and (parcel_class_pct or 0) < MIN_PARCEL_CLASS_PCT_PARTIAL:
        gaps.append(
            f"only {(parcel_class_pct or 0):.0%} of parcels have a non-unknown zone_class "
            f"— matrix coverage is shallow"
        )
    if orphan_zone_code_count > 0:
        gaps.append(
            f"{orphan_zone_code_count} zone codes on parcels not present on any district"
        )

    is_partial = any([
        parcel_count > 0 and (parcel_zoning_pct or 0) < MIN_PARCEL_ZONING_PCT_OPERATIONAL,
        parcel_count > 0 and (parcel_class_pct or 0) < MIN_PARCEL_CLASS_PCT_PARTIAL,
        orphan_zone_code_count > 0,
    ])
    if is_partial:
        return "partial", gaps

    return "operational", gaps


def _threshold_descriptor() -> dict[str, Any]:
    """Inline the operational thresholds in every response so the dashboard
    can render them next to the band — operators shouldn't have to dig
    through code to know what 'partial' means."""
    return {
        "min_parcel_count_for_operational": MIN_PARCEL_COUNT_FOR_OPERATIONAL,
        "min_parcel_zoning_pct_operational": MIN_PARCEL_ZONING_PCT_OPERATIONAL,
        "min_parcel_zoning_pct_partial": MIN_PARCEL_ZONING_PCT_PARTIAL,
        "min_parcel_class_pct_partial": MIN_PARCEL_CLASS_PCT_PARTIAL,
        "min_district_count_for_operational": MIN_DISTRICT_COUNT_FOR_OPERATIONAL,
        "max_district_overlap_ratio": MAX_DISTRICT_OVERLAP_RATIO,
        "min_extent_overlap_ratio": MIN_EXTENT_OVERLAP_RATIO,
        "overlap_sample_limit": OVERLAP_SAMPLE_LIMIT,
    }
