"""Locate a parcel from a free-text APN or street address (broker paste).

Powers the map SEARCH box. Three tiers, best-effort, most-precise first:

  1. APN         — separator-insensitive match (``0022-01-0003A`` ~ ``0022 01 0003A``).
  2. Address     — USPS-normalized, house-number-anchored token match against the
                   stored situs address (reuses services.address_normalizer, the
                   same pipe the listing matcher uses). Scoped to a jurisdiction
                   when one is supplied, for speed.
  3. Geocode     — geocode the string (Census → Nominatim) then find the parcel
                   whose geometry CONTAINS the point (GiST-indexed, cross-
                   jurisdiction). This is the catch-all for broker addresses: it
                   ignores how the situs string is stored and works even where the
                   situs column is empty (e.g. Fairfax's geometry-only parcels).

Returns ranked candidates with centroid lat/lng so the client can fly to them.
Read-only; no scoring, deliberately independent of the buy-box filter path.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, asdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.address_normalizer import normalize, strip_unit
from app.services.use_verdicts import LGC_SLUG, SELF_STORAGE_SLUG, verdict_expr

# Optional geocoders — import defensively so a missing dep never 500s the search.
try:
    from app.services.geocode_census import geocode_address as _census_geocode
except Exception:  # pragma: no cover
    _census_geocode = None
try:
    from app.services.geocode_nominatim import geocode_address as _nominatim_geocode
except Exception:  # pragma: no cover
    _nominatim_geocode = None

_ALNUM = re.compile(r"[^A-Za-z0-9]")
_HOUSE = re.compile(r"^(\d+)\s+(.+)$")

# READINESS joins, shared by every tier so the answer never depends on which tier
# happened to match. Both are LEFT joins: a parcel we cannot analyse must still be
# FOUND and returned, flagged, rather than filtered out of the search.
#
# The matrix LATERAL is aliased `zum` because that is the alias
# use_verdicts.verdict_expr() renders against — the verdict SQL is generated from the
# one shared definition rather than restated here (a fourth copy of the LGC rule is
# exactly the drift that produced 6,702 phantom Montgomery needles).
#
# It also restricts to human_reviewed rows, which is what makes "grounded" mean
# grounded: an un-reviewed matrix row yields no LATERAL row, so verdict comes back NULL
# and the UI can say NOT VERIFIED instead of rendering a machine guess as fact. The
# muni-aware shape (case-sensitive municipality = parcels.city, NULL-municipality rows
# ranked last) mirrors scripts/precompute_needles._LATERAL.
_READY_JOINS = """
    LEFT JOIN LATERAL (
        SELECT m.self_storage, m.mini_warehouse, m.light_industrial, m.human_reviewed
          FROM zone_use_matrix m
         WHERE m.jurisdiction_id = p.jurisdiction_id
           AND m.zone_code = p.zoning_code
           AND (m.municipality IS NULL OR m.municipality = p.city)
           AND m.deleted_at IS NULL
           AND m.human_reviewed
         ORDER BY (m.municipality IS NULL) ASC
         LIMIT 1
    ) zum ON true
    LEFT JOIN parcel_ring_metrics prm
           ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
"""

# Columns every tier returns, so the client render path is uniform. Centroid
# coords (not the possibly-NULL lat/lng columns) so fly-to always has a point.
#
# ring_measured deliberately requires computed_at <> to_timestamp(0): the epoch is the
# sentinel for "never validly computed", so an epoch-stamped row is UNMEASURED, not
# measured-at-1970. Without that clause the UI would report a confident $0.
_COLS = f"""p.id AS parcel_id, p.jurisdiction_id, j.name AS jurisdiction_name,
    p.apn, p.address, p.city, p.state, p.owner_name, p.acres, p.zoning_code,
    ST_Y(ST_Centroid(p.geom)) AS lat, ST_X(ST_Centroid(p.geom)) AS lng,
    (p.zoning_code IS NOT NULL) AS has_zoning_code,
    (zum.human_reviewed IS TRUE) AS zoning_grounded,
    ({verdict_expr(SELF_STORAGE_SLUG)}) AS verdict_self_storage,
    ({verdict_expr(LGC_SLUG)}) AS verdict_lgc,
    (prm.parcel_id IS NOT NULL
     AND prm.median_home_value IS NOT NULL
     AND prm.median_hhi IS NOT NULL
     AND prm.computed_at <> to_timestamp(0)) AS ring_measured,
    prm.median_home_value AS ring_median_home_value,
    prm.median_hhi AS ring_median_hhi,
    EXISTS (SELECT 1 FROM parcel_buybox_scores s WHERE s.parcel_id = p.id) AS scored"""


@dataclass
class LocateResult:
    parcel_id: int
    jurisdiction_id: str
    jurisdiction_name: str | None
    apn: str | None
    address: str | None
    city: str | None
    state: str | None
    owner_name: str | None
    lat: float | None
    lng: float | None
    match_method: str  # 'apn' | 'address' | 'geocode'
    score: float
    # ── readiness: what we actually know about this parcel ──────────────────
    # Four separate booleans, not one "complete" flag, because the useful answer
    # is WHICH half is missing. They exist so the UI can distinguish "no" from
    # "we never looked" -- today an ungrounded zone and a prohibited zone both
    # render blank, which is why a found parcel can still feel broken.
    acres: float | None = None
    zoning_code: str | None = None
    has_zoning_code: bool = False
    zoning_grounded: bool = False
    verdict_self_storage: str | None = None
    verdict_lgc: str | None = None
    ring_measured: bool = False
    ring_median_home_value: float | None = None
    ring_median_hhi: float | None = None
    scored: bool = False


def _looks_like_apn(token: str) -> bool:
    """Mostly-digits, few/no spaces — distinguishes '0022 01 0003A' from a street."""
    if len(token) < 4:
        return False
    digits = sum(c.isdigit() for c in token)
    return digits >= max(4, int(len(token) * 0.5))


def _row_to_result(m, method: str, score: float) -> LocateResult:
    return LocateResult(
        parcel_id=m["parcel_id"], jurisdiction_id=str(m["jurisdiction_id"]),
        jurisdiction_name=m["jurisdiction_name"], apn=m["apn"], address=m["address"],
        city=m["city"], state=m["state"], owner_name=m["owner_name"],
        lat=float(m["lat"]) if m["lat"] is not None else None,
        lng=float(m["lng"]) if m["lng"] is not None else None,
        match_method=method, score=score,
        acres=_f(m, "acres"),
        zoning_code=m.get("zoning_code"),
        has_zoning_code=bool(m.get("has_zoning_code")),
        zoning_grounded=bool(m.get("zoning_grounded")),
        verdict_self_storage=m.get("verdict_self_storage"),
        verdict_lgc=m.get("verdict_lgc"),
        ring_measured=bool(m.get("ring_measured")),
        ring_median_home_value=_f(m, "ring_median_home_value"),
        ring_median_hhi=_f(m, "ring_median_hhi"),
        scored=bool(m.get("scored")),
    )


def _f(m, key: str) -> float | None:
    """NUMERIC columns arrive as Decimal; the response model wants float|None."""
    v = m.get(key)
    return None if v is None else float(v)


async def _apn_tier(db, q: str, jid, limit) -> list[LocateResult]:
    norm = _ALNUM.sub("", q).upper()
    if not norm or not _looks_like_apn(norm):
        return []
    scope = "AND p.jurisdiction_id = :jid" if jid else ""
    # exact normalized apn, then prefix — index-friendly enough at interactive scale
    sql = text(f"""
        SELECT {_COLS},
               (CASE WHEN upper(regexp_replace(p.apn,'[^A-Za-z0-9]','','g')) = :norm
                     THEN 100.0 ELSE 85.0 END) AS _score
          FROM parcels p JOIN jurisdictions j ON j.id = p.jurisdiction_id
          {_READY_JOINS}
         WHERE upper(regexp_replace(p.apn,'[^A-Za-z0-9]','','g')) LIKE :prefix {scope}
         ORDER BY _score DESC, p.id LIMIT :lim
    """)
    params = {"norm": norm, "prefix": norm + "%", "lim": limit}
    if jid:
        params["jid"] = jid
    rows = (await db.execute(sql, params)).mappings().all()
    return [_row_to_result(m, "apn", float(m["_score"])) for m in rows]


async def _address_tier(db, q: str, jid, limit) -> list[LocateResult]:
    # Text tier is jurisdiction-scoped only — parcels.address has no trigram index,
    # so an unscoped substring scan over millions of rows would time out. Cross-
    # jurisdiction address lookup is the geocode tier's job (spatial GiST index).
    if jid is None:
        return []
    nq = strip_unit(q)
    hm = _HOUSE.match(nq)
    if not hm:
        return []
    house, street = hm.group(1), hm.group(2)
    street_tokens = [t for t in street.split(" ") if t]
    if not street_tokens:
        return []
    # Candidate pull: house number anchored on a space boundary ("14 …" / "… 14 …")
    # within the one jurisdiction, then rank in Python via the same normalize() pipe
    # so 'Main Street' matches stored 'MAIN ST'. ILIKE (not regex) + jid filter keeps
    # it interactive; the Python house-token check drops '140 …' false positives.
    sql = text(f"""
        SELECT {_COLS}
          FROM parcels p JOIN jurisdictions j ON j.id = p.jurisdiction_id
          {_READY_JOINS}
         WHERE p.jurisdiction_id = :jid
           AND p.address IS NOT NULL
           AND (p.address ILIKE :a OR p.address ILIKE :b)
         LIMIT 400
    """)
    params = {"jid": jid, "a": f"{house} %", "b": f"% {house} %", "lim": limit}
    rows = (await db.execute(sql, params)).mappings().all()
    out: list[LocateResult] = []
    for m in rows:
        na = normalize(m["address"])
        na_tokens = na.split(" ")
        if not na_tokens or na_tokens[0] != house:
            continue
        na_set = set(na_tokens)
        matched = sum(1 for t in street_tokens if t in na_set)
        if matched == 0:
            continue
        # full street-token coverage → strong; partial → proportional
        coverage = matched / len(street_tokens)
        score = 90.0 * coverage if coverage < 1 else 95.0
        out.append(_row_to_result(m, "address", score))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:limit]


async def _geocode_tier(db, q: str, limit) -> tuple[list[LocateResult], object | None]:
    """Returns (results, geo). The geo point is returned EVEN WHEN no parcel matched.

    That distinction is the whole out-of-coverage signal: "we could not find this
    address" and "this address is real, we simply do not own parcels there" are
    completely different answers for the user, and only the second one is actionable
    (queue the county). Discarding geo on a miss collapses them into one shrug.
    """
    geo = None
    for fn in (_census_geocode, _nominatim_geocode):
        if fn is None:
            continue
        try:
            geo = await fn(q)
        except Exception:
            geo = None
        if geo:
            break
    if not geo:
        return [], None
    # Parcel whose geometry contains the point (GiST); else nearest within 60 m.
    sql = text(f"""
        WITH pt AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
        SELECT {_COLS},
               CASE WHEN ST_Contains(p.geom, (SELECT g FROM pt)) THEN 88.0 ELSE 70.0 END AS _score
          FROM parcels p JOIN jurisdictions j ON j.id = p.jurisdiction_id
          {_READY_JOINS}
         WHERE ST_DWithin(p.geom, (SELECT g FROM pt), 0.0006)
         ORDER BY (NOT ST_Contains(p.geom, (SELECT g FROM pt))),
                  p.geom <-> (SELECT g FROM pt)
         LIMIT :lim
    """)
    rows = (await db.execute(sql, {"lat": geo.lat, "lon": geo.lon, "lim": limit})).mappings().all()
    # Boost a candidate whose stored situs actually matches the query's house+street
    # over a geocoder-interpolation neighbor (e.g. exact "320 E COURT ST" beats the
    # "312" parcel the interpolated point happened to land in).
    qn = strip_unit(q)
    qhm = _HOUSE.match(qn)
    qtok = set(qn.split(" "))  # includes trailing city/state — a superset of the situs
    out: list[LocateResult] = []
    for m in rows:
        score = float(m["_score"])
        if qhm and m["address"]:
            na = normalize(m["address"]).split(" ")
            stored_street = set(na[1:])
            # boost when the situs house# matches and its street tokens all appear
            # in the query (query is the superset — it carries city/state too)
            if na and na[0] == qhm.group(1) and stored_street and stored_street.issubset(qtok):
                score = 92.0
        out.append(_row_to_result(m, "geocode", score))
    out.sort(key=lambda r: r.score, reverse=True)
    return out, geo


# Slim column set for the NEARBY list. Deliberately NOT _COLS: that computes
# ST_Centroid(p.geom) per row (fine for <=8 locate hits, wasteful for a few hundred) and
# carries fields the list does not render. p.centroid is the indexed column and is what
# ST_DWithin filters on, so reading it directly is both cheaper and consistent.
#
# No geometry is returned. The 274MB unpaginated /ring-metrics stall is the standing
# lesson here: a list endpoint that ships geometry is a payload incident waiting to
# happen, and the map already has the shapes it needs.
_NEARBY_COLS = f"""p.id AS parcel_id, p.jurisdiction_id, j.name AS jurisdiction_name,
    p.apn, p.address, p.city, p.state, p.owner_name, p.acres, p.zoning_code,
    ST_Y(p.centroid) AS lat, ST_X(p.centroid) AS lng,
    (zum.human_reviewed IS TRUE) AS zoning_grounded,
    ({verdict_expr(SELF_STORAGE_SLUG)}) AS verdict_self_storage,
    ({verdict_expr(LGC_SLUG)}) AS verdict_lgc,
    (prm.parcel_id IS NOT NULL
     AND prm.median_home_value IS NOT NULL
     AND prm.median_hhi IS NOT NULL
     AND prm.computed_at <> to_timestamp(0)) AS ring_measured,
    prm.median_home_value AS ring_median_home_value,
    prm.median_hhi AS ring_median_hhi"""

# The wealth half of the needle gate, in the ring's own terms. Kept as one string so the
# SELECT and the ORDER BY cannot disagree about what "qualifying" means.
_QUALIFIES = """(
    p.acres >= 1.5
    AND prm.median_home_value >= 475000
    AND prm.median_hhi >= 100000
    AND prm.computed_at <> to_timestamp(0)
)"""

# Capped at 8, not 10, because the latency curve has a cliff. Measured in Chester
# County PA: 1mi 0.18s · 2mi 0.16s · 3mi 0.21s · 5mi 0.28s · 7mi 0.79s · 10mi 20.8s.
# Past ~7mi the bbox admits enough rows that the planner abandons the centroid index
# for a sequential scan. 8 keeps the endpoint interactive with headroom; the cliff is
# density-dependent, so a very dense county may still be slower than Chester at the
# same radius. 3 (the default) is the useful "what's nearby" answer regardless.
_MAX_RADIUS_MILES = 8.0
_MAX_NEARBY = 200


async def nearby_parcels(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_miles: float = 3.0,
    limit: int = 50,
    qualifying_only: bool = False,
) -> dict:
    """Parcels around a point, qualifying ones first — the "what else is nearby" half.

    Cross-jurisdiction on purpose: an address near a county line should surface the
    neighbours on both sides, and the geography filter does not care about our
    jurisdiction boundaries.

    Bounded twice over (radius cap AND row cap) because this is reachable from a text
    box: a 10-mile radius in a dense county touches a lot of parcels, and an unbounded
    version of this endpoint is exactly how the ring-metrics payload incident happened.
    """
    radius_miles = max(0.1, min(float(radius_miles), _MAX_RADIUS_MILES))
    limit = max(1, min(int(limit), _MAX_NEARBY))
    meters = radius_miles * 1609.34

    # TWO-STEP filter, and the order matters enormously:
    #
    #   1. `centroid && ST_Expand(point, :deg)` — plain GEOMETRY, so the GiST index on
    #      parcels.centroid is usable. This is what makes the query interactive.
    #   2. ST_DWithin on ::geography — exact metric distance, applied only to the
    #      handful of rows step 1 admitted.
    #
    # Casting the column to geography in the WHERE clause (the obvious one-step
    # version) makes the index unusable: EXPLAIN showed a Parallel Seq Scan over
    # 17.8M parcels and the call took 169 SECONDS. Same answer, unusable latency.
    #
    # :deg is a LONGITUDE-degree padding (metres / (111320 * cos(lat))), which is the
    # larger of the two axes away from the equator, so the box is a safe overestimate
    # and never clips a parcel that step 2 would have kept.
    deg = meters / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    # SPLIT BY COST, NOT BY DISTANCE. The candidate CTE does the geography filter AND
    # the qualifying test, because _QUALIFIES needs only p.acres + the ring row (a PK
    # join) — no zone_use_matrix. The expensive per-row LATERAL runs only on the final
    # `limit` rows.
    #
    # An earlier version prefetched the N nearest parcels and sorted within them, which
    # was fast but WRONG for this feature: in a dense area the nearest 2000 parcels all
    # sat inside ~1 mile, so qualifying parcels further out were crowded out entirely —
    # a 3-mile search returned nothing past 1.05mi and found 3 qualifying instead of
    # 50. "What else nearby qualifies" cannot be answered by looking only at what is
    # closest.
    sql = text(f"""
        WITH pt AS (
            SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS gm,
                   ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography AS gg
        ),
        cand AS (
            SELECT p.id,
                   ST_Distance(p.centroid::geography, (SELECT gg FROM pt)) / 1609.34
                     AS distance_miles,
                   -- COALESCE is load-bearing: with no ring row _QUALIFIES is NULL
                   -- (NULL >= 475000 is NULL, not false) and Postgres sorts NULLs
                   -- FIRST under DESC, so unmeasured parcels floated to the TOP of a
                   -- "qualifying first" list.
                   COALESCE({_QUALIFIES}, false) AS qualifies
              FROM parcels p
              LEFT JOIN parcel_ring_metrics prm
                     ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
             WHERE p.centroid IS NOT NULL
               AND p.centroid && ST_Expand((SELECT gm FROM pt), :deg)
               AND ST_DWithin(p.centroid::geography, (SELECT gg FROM pt), :meters)
               {"AND " + _QUALIFIES if qualifying_only else ""}
             -- Ranked across the WHOLE radius, then cut to `limit`, so a qualifying
             -- parcel 2 miles out still beats a non-qualifying neighbour next door.
             ORDER BY COALESCE({_QUALIFIES}, false) DESC,
                      ST_Distance(p.centroid::geography, (SELECT gg FROM pt)) ASC
             LIMIT :lim
        )
        SELECT {_NEARBY_COLS},
               c.distance_miles,
               c.qualifies
          FROM cand c
          JOIN parcels p ON p.id = c.id
          JOIN jurisdictions j ON j.id = p.jurisdiction_id
          {_READY_JOINS}
         ORDER BY c.qualifies DESC, c.distance_miles ASC
    """)
    rows = (await db.execute(sql, {
        "lat": lat, "lng": lng, "meters": meters, "deg": deg, "lim": limit,
    })).mappings().all()

    out = []
    for m in rows:
        out.append({
            "parcel_id": m["parcel_id"],
            "jurisdiction_id": str(m["jurisdiction_id"]),
            "jurisdiction_name": m["jurisdiction_name"],
            "apn": m["apn"], "address": m["address"], "city": m["city"],
            "state": m["state"], "owner_name": m["owner_name"],
            "acres": _f(m, "acres"), "zoning_code": m["zoning_code"],
            "lat": _f(m, "lat"), "lng": _f(m, "lng"),
            "zoning_grounded": bool(m["zoning_grounded"]),
            "verdict_self_storage": m["verdict_self_storage"],
            "verdict_lgc": m["verdict_lgc"],
            "ring_measured": bool(m["ring_measured"]),
            "ring_median_home_value": _f(m, "ring_median_home_value"),
            "ring_median_hhi": _f(m, "ring_median_hhi"),
            "distance_miles": _f(m, "distance_miles"),
            "qualifies": bool(m["qualifies"]),
        })
    return {
        "results": out,
        "radius_miles": radius_miles,
        # truncated tells the UI to say "showing first N" rather than implying the
        # list is exhaustive — a silent cap reads as "that's all there is".
        "truncated": len(out) >= limit,
        "qualifying_count": sum(1 for r in out if r["qualifies"]),
    }


async def locate_parcels(
    db: AsyncSession,
    query: str,
    jurisdiction_id: uuid.UUID | None = None,
    limit: int = 8,
) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    jid = jurisdiction_id
    results: list[LocateResult] = []
    seen: set[int] = set()

    def _extend(rs: list[LocateResult]) -> None:
        for r in rs:
            if r.parcel_id not in seen:
                seen.add(r.parcel_id)
                results.append(r)

    _extend(await _apn_tier(db, q, jid, limit))
    if len(results) < limit:
        _extend(await _address_tier(db, q, jid, limit))
    # Geocode catch-all — always try when the cheap tiers didn't nail it. Runs
    # cross-jurisdiction (spatial index), so a wrong-buy-box or null-situs address
    # still resolves. Rate-limited (~1s) but fine for one interactive lookup.
    geo = None
    if not results:
        geo_results, geo = await _geocode_tier(db, q, limit)
        _extend(geo_results)

    results.sort(key=lambda r: r.score, reverse=True)

    # COVERAGE — three distinct outcomes, because they need three different UIs:
    #   in_coverage  we own parcels here; show them.
    #   out_of_coverage  the address is real and we geocoded it, but we hold no
    #                    parcels there -> offer to queue that county. Actionable.
    #   unresolved   we could not even geocode it -> a typo or a bad paste.
    if results:
        coverage = "in_coverage"
    elif geo is not None:
        coverage = "out_of_coverage"
    else:
        coverage = "unresolved"

    geocoded = None
    if geo is not None:
        # GeocodeResult carries only lat/lon/matched_address -- no county. Derive the
        # county from the point via census_tracts (state_fips/county_fips, GiST) so the
        # "add this county" prompt can NAME what it would queue. Best-effort: TIGER
        # tracts are loaded per state as we go, so an address in a state we have never
        # touched yields no row, and the UI falls back to the matched address.
        fips = (await db.execute(text("""
            SELECT t.state_fips, t.county_fips
              FROM census_tracts t
             WHERE ST_Contains(t.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
             LIMIT 1
        """), {"lat": geo.lat, "lon": geo.lon})).mappings().first()
        geocoded = {
            "lat": geo.lat,
            "lng": geo.lon,
            "matched_address": getattr(geo, "matched_address", None),
            "state_fips": fips["state_fips"] if fips else None,
            "county_fips": fips["county_fips"] if fips else None,
        }

    return {
        "results": [asdict(r) for r in results[:limit]],
        "coverage": coverage,
        "geocoded": geocoded,
    }
