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

import re
import uuid
from dataclasses import dataclass, asdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.address_normalizer import normalize, strip_unit

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

# Columns every tier returns, so the client render path is uniform. Centroid
# coords (not the possibly-NULL lat/lng columns) so fly-to always has a point.
_COLS = """p.id AS parcel_id, p.jurisdiction_id, j.name AS jurisdiction_name,
    p.apn, p.address, p.city, p.state, p.owner_name,
    ST_Y(ST_Centroid(p.geom)) AS lat, ST_X(ST_Centroid(p.geom)) AS lng"""


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
    )


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


async def _geocode_tier(db, q: str, limit) -> list[LocateResult]:
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
        return []
    # Parcel whose geometry contains the point (GiST); else nearest within 60 m.
    sql = text(f"""
        WITH pt AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
        SELECT {_COLS},
               CASE WHEN ST_Contains(p.geom, (SELECT g FROM pt)) THEN 88.0 ELSE 70.0 END AS _score
          FROM parcels p JOIN jurisdictions j ON j.id = p.jurisdiction_id
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
    return out


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
    if not results:
        _extend(await _geocode_tier(db, q, limit))

    results.sort(key=lambda r: r.score, reverse=True)
    return [asdict(r) for r in results[:limit]]
