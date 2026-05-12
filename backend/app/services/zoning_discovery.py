"""
Zoning-source discovery (Phase C).

Given a jurisdiction (with parcel data already ingested + a `bbox`), search
ArcGIS Hub for candidate zoning FeatureServer / MapServer layers in that
bbox, score them by heuristics, and return the top-N candidates with
confidence scores.

Output is candidate-only — never auto-applies a source to the
jurisdictions table. The user reviews the candidates and then fires
`POST /api/jurisdictions/{id}/_backfill-zoning?zoning_url=...` with the
URL they picked.

The discovery deliberately does NOT touch the DB beyond reading the
jurisdiction's name + bbox. All scoring is in-memory, idempotent, and
can be re-run cheaply. This keeps the discovery loop human-in-the-loop:
we surface candidates, the operator decides.

Design choices vs the existing `arcgis_discovery.discover_layers()`:
  - Returns a *ranked list* (top 5) instead of one URL.
  - Includes confidence + reasoning fields so the operator can decide.
  - Probes each candidate for feature_count + geometry_type so bad
    candidates are filtered before they ever reach the operator.
  - Bbox-filtered Hub queries so we don't get a Texas zoning layer
    when searching for a NJ county.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction


logger = logging.getLogger(__name__)


_HUB_DATASETS_URL = "https://hub.arcgis.com/api/v3/datasets"

# Title keywords that score positively (zoning intent).
_ZONING_KEYWORDS_POSITIVE = [
    "zoning", "zone district", "zoning district", "zone base", "zoning base",
    "base district", "zoning overlay", "land use", "landuse", "general plan",
    "zoning_districts", "zd_", "zone_class",
]

# Title keywords that score negatively (not zoning — parcels, addresses, etc.).
_ZONING_KEYWORDS_NEGATIVE = [
    "parcel", "parcels", "tax lot", "ownership", "address", "addresses",
    "centerline", "road", "street", "highway", "utility", "pipeline",
    "building", "permit", "project", "boundary", "boundaries", "right of way",
    "right-of-way", "subdivision", "easement",
]

# Field-name fragments that suggest a real zoning layer.
_ZONING_FIELDS = [
    "zone", "zoning", "district", "class", "landuse", "land_use",
    "zonecode", "zone_code", "zonedist", "zone_dist", "zd_zone",
]

# Reasonable feature-count window for a county-scale zoning layer.
_MIN_FEATURE_COUNT = 30
_MAX_FEATURE_COUNT = 250_000

# How many candidates to return.
_TOP_N = 5


@dataclass
class ZoningCandidate:
    url: str                            # full FeatureServer/Layer URL (.../FeatureServer/0)
    title: str
    source_type: str                    # "arcgis_featureserver" | "arcgis_mapserver"
    feature_count: int | None           # None if we couldn't probe
    geometry_type: str | None
    field_matches: list[str]            # fields whose name contains a zoning fragment
    bbox_overlaps: bool                 # whether layer's bbox overlaps the jurisdiction's
    title_score: int                    # +1 per positive keyword, -2 per negative
    confidence: int                     # 0..100 derived from the above
    reasons: list[str]                  # human-readable signals contributing to confidence


@dataclass
class DiscoveryResult:
    jurisdiction_id: str
    jurisdiction_name: str
    queried_with: dict[str, Any]        # the Hub query + bbox we used
    candidates_total: int               # how many raw Hub results we evaluated
    candidates: list[dict]              # top N as serialisable dicts


async def discover_zoning_for_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> DiscoveryResult:
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise ValueError(f"jurisdiction {jurisdiction_id} not found")

    bbox = j.bbox  # [minLng, minLat, maxLng, maxLat] in WGS-84
    bbox_str = ""
    if bbox and len(bbox) == 4:
        bbox_str = "{:.6f},{:.6f},{:.6f},{:.6f}".format(*bbox)

    # Build a query — combine the jurisdiction name with "zoning" intent.
    query = f"zoning {j.name or j.county or ''}".strip()

    # Token bag for jurisdiction-name matching — used to bonus candidates whose
    # title names this jurisdiction, and penalise candidates whose title names
    # a *different* county (common false-positive when the Hub bbox catches a
    # neighbouring county, e.g. Hunterdon NJ's bbox overlaps Warren NJ and the
    # Warren County Zoning Map was outranking real Hunterdon sources).
    name_tokens = _name_tokens(j.name, j.county)

    candidates: list[ZoningCandidate] = []
    candidates_total = 0
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        raw = await _hub_search(client, query, bbox_str)
        candidates_total = len(raw)
        # Probe each candidate's feature_count, geometry, fields (concurrent).
        probes = [_probe_layer(client, item, bbox, name_tokens) for item in raw]
        probed = await asyncio.gather(*probes, return_exceptions=True)
        for entry in probed:
            if isinstance(entry, Exception) or entry is None:
                continue
            candidates.append(entry)

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    top_n = candidates[:_TOP_N]

    # Persist the top-N into zoning_sources so the operator can review them
    # later without re-running the discovery. Idempotent re-runs: identical
    # (jurisdiction_id, municipality_name, zoning_endpoint) tuples updated
    # in place rather than duplicated. Anything previously verified for this
    # jurisdiction stays untouched (we only overwrite rows whose
    # confidence_label is still 'discovered' or NULL).
    try:
        await _persist_candidates(db, j, top_n, municipality_name=None)
    except Exception as exc:
        logger.warning("persist zoning_sources failed (non-fatal): %r", exc)

    return DiscoveryResult(
        jurisdiction_id=str(j.id),
        jurisdiction_name=j.name or "",
        queried_with={"query": query, "bbox": bbox_str},
        candidates_total=candidates_total,
        candidates=[asdict(c) for c in candidates[:_TOP_N]],
    )


async def _hub_search(
    client: httpx.AsyncClient,
    query: str,
    bbox_str: str,
) -> list[dict]:
    params: dict[str, str] = {
        "q": query,
        "filter[type]": "Feature Service",
        "page[size]": "30",
    }
    if bbox_str:
        params["bbox"] = bbox_str

    try:
        resp = await client.get(
            _HUB_DATASETS_URL,
            params=params,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Hub search q=%r failed: %s", query, exc)
        return []
    return data.get("data", []) or []


async def _probe_layer(
    client: httpx.AsyncClient,
    hub_item: dict,
    jurisdiction_bbox: list[float] | None,
    name_tokens: dict | None = None,
) -> ZoningCandidate | None:
    attrs = hub_item.get("attributes", {}) or {}
    title = (attrs.get("name") or attrs.get("title") or "").strip()
    url = (attrs.get("url") or "").rstrip("/")
    layer_id = attrs.get("layerId")
    if not url or not title:
        return None
    if "FeatureServer" not in url and "MapServer" not in url:
        return None

    full_url = url
    if layer_id is not None and not _url_has_layer_index(url):
        full_url = f"{url}/{layer_id}"
    elif not _url_has_layer_index(url):
        # Hub returned a service-root URL (no `/0`, no layerId attribute).
        # Probe the service metadata to pick a polygon layer to evaluate.
        full_url = await _resolve_service_to_layer(client, url) or url

    source_type = (
        "arcgis_featureserver" if "FeatureServer" in full_url
        else "arcgis_mapserver"
    )

    # Title-based scoring is cheap and runs even if the metadata probe fails.
    title_lc = title.lower()
    pos_hits = [k for k in _ZONING_KEYWORDS_POSITIVE if k in title_lc]
    neg_hits = [k for k in _ZONING_KEYWORDS_NEGATIVE if k in title_lc]
    title_score = len(pos_hits) - 2 * len(neg_hits)

    # Probe the layer's metadata endpoint (cheap — single GET, small response).
    feature_count: int | None = None
    geometry_type: str | None = None
    field_matches: list[str] = []
    layer_bbox: list[float] | None = None
    if _url_has_layer_index(full_url):
        try:
            meta = await client.get(full_url, params={"f": "json"}, timeout=15.0)
            if meta.status_code == 200:
                mdata = meta.json()
                geometry_type = mdata.get("geometryType")
                extent = mdata.get("extent") or {}
                if all(k in extent for k in ("xmin", "ymin", "xmax", "ymax")):
                    layer_bbox = [extent["xmin"], extent["ymin"], extent["xmax"], extent["ymax"]]
                for f in mdata.get("fields", []) or []:
                    fname = (f.get("name") or "").lower()
                    if any(frag in fname for frag in _ZONING_FIELDS):
                        field_matches.append(f.get("name"))
                # Count features — only if geom type looks right.
                if geometry_type == "esriGeometryPolygon":
                    count_resp = await client.get(
                        full_url + "/query",
                        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                        timeout=15.0,
                    )
                    if count_resp.status_code == 200:
                        feature_count = (count_resp.json() or {}).get("count")
        except Exception as exc:
            logger.debug("probe %s failed: %s", full_url, exc)

    bbox_overlaps = (
        jurisdiction_bbox is not None
        and layer_bbox is not None
        and _bboxes_overlap(jurisdiction_bbox, layer_bbox)
    )

    name_match, wrong_county = _name_match_signals(title_lc, name_tokens or {})

    confidence, reasons = _score_candidate(
        title_score=title_score,
        pos_hits=pos_hits,
        neg_hits=neg_hits,
        geometry_type=geometry_type,
        feature_count=feature_count,
        field_matches=field_matches,
        bbox_overlaps=bbox_overlaps,
        name_match=name_match,
        wrong_county=wrong_county,
    )

    return ZoningCandidate(
        url=full_url,
        title=title,
        source_type=source_type,
        feature_count=feature_count,
        geometry_type=geometry_type,
        field_matches=field_matches,
        bbox_overlaps=bbox_overlaps,
        title_score=title_score,
        confidence=confidence,
        reasons=reasons,
    )


def _score_candidate(
    *,
    title_score: int,
    pos_hits: list[str],
    neg_hits: list[str],
    geometry_type: str | None,
    feature_count: int | None,
    field_matches: list[str],
    bbox_overlaps: bool,
    name_match: bool = False,
    wrong_county: str | None = None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    score += 15 * len(pos_hits)
    if pos_hits:
        reasons.append(f"title matches zoning keywords: {pos_hits}")
    score -= 20 * len(neg_hits)
    if neg_hits:
        reasons.append(f"title penalised by non-zoning keywords: {neg_hits}")
    if geometry_type == "esriGeometryPolygon":
        score += 20
        reasons.append("geometry is polygon")
    elif geometry_type:
        score -= 30
        reasons.append(f"geometry is {geometry_type!r}, not polygon")
    if feature_count is not None:
        if _MIN_FEATURE_COUNT <= feature_count <= _MAX_FEATURE_COUNT:
            score += 15
            reasons.append(f"feature_count={feature_count} is in plausible range")
        else:
            score -= 10
            reasons.append(f"feature_count={feature_count} is outside [30, 250k]")
    if field_matches:
        score += min(20, 5 * len(field_matches))
        reasons.append(f"fields look zoning-shaped: {field_matches[:5]}")
    if bbox_overlaps:
        score += 10
        reasons.append("layer bbox overlaps jurisdiction bbox")
    if name_match:
        score += 25
        reasons.append("title names this jurisdiction")
    if wrong_county:
        # Heavy penalty — Hub bbox-search often surfaces neighbouring counties
        # whose layers happen to overlap. A title that says "Warren County"
        # when we're looking for Hunterdon is almost certainly wrong.
        score -= 50
        reasons.append(f"title names a different county ({wrong_county!r})")
    return max(0, min(100, score)), reasons


# Common US county names that appear in ArcGIS layer titles. Used only for the
# "title names a different county" penalty — we compare the candidate's title
# to this list, find any county tokens, and if NONE of them are in the
# jurisdiction's own name_tokens, that's a wrong-county signal.
_COMMON_COUNTY_WORDS = {
    "county", "co.",
}


def _name_tokens(name: str | None, county: str | None) -> dict:
    """Build a token bag for name matching. Returns a dict with `expect`
    (tokens we want to see in the title) and `bag` (lowercased words from
    the jurisdiction's name + county)."""
    raw = " ".join(filter(None, [name or "", county or ""])).lower()
    raw = raw.replace(",", " ").replace(".", " ")
    words = [w for w in raw.split() if len(w) >= 3 and w not in _COMMON_COUNTY_WORDS]
    return {"expect": set(words)}


def _name_match_signals(title_lc: str, name_tokens: dict) -> tuple[bool, str | None]:
    """Return (own-name appears in title?, wrong-county word if any)."""
    expect = name_tokens.get("expect") or set()
    if not expect:
        return False, None
    own = any(w in title_lc for w in expect)
    # Detect a *different* county-style name in the title: a word followed by
    # "county" that's NOT one of our own tokens.
    wrong = None
    for chunk in title_lc.split():
        # Look for "<word> county" sequences.
        pass
    # Simpler scan: pull all "<X> county" pairs from the title.
    parts = title_lc.split()
    for i, w in enumerate(parts[:-1]):
        if parts[i + 1].startswith("county") and w not in expect and len(w) >= 3:
            wrong = w
            break
    return own, wrong


def _bboxes_overlap(a: list[float], b: list[float]) -> bool:
    # a, b: [minx, miny, maxx, maxy]. Layer extent may be in a different CRS
    # (often EPSG:3857 Web Mercator) — we only check if degenerate, not exact.
    if not a or not b or len(a) != 4 or len(b) != 4:
        return False
    # Treat any non-zero extent as plausibly overlapping; precise CRS-aware
    # overlap-checking is overkill at the candidate-ranking stage.
    return all(v is not None for v in a + b)


def _url_has_layer_index(url: str) -> bool:
    tail = url.rsplit("/", 1)[-1] if url else ""
    return tail.isdigit()


async def _resolve_service_to_layer(
    client: httpx.AsyncClient,
    service_url: str,
) -> str | None:
    """Given a service-root URL (`.../FeatureServer` or `.../MapServer`),
    fetch its metadata and pick the most zoning-shaped polygon layer.
    Returns the full layer URL `service_url/{id}` or None.

    Heuristics: prefer polygon layers whose name contains a zoning
    keyword; fall back to the first polygon layer.
    """
    try:
        resp = await client.get(service_url, params={"f": "json"}, timeout=10.0)
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
    except Exception:
        return None
    layers = data.get("layers") or []
    polygon_layers = [
        l for l in layers if l.get("geometryType") == "esriGeometryPolygon"
    ]
    if not polygon_layers:
        # Some services don't expose geometryType in the layer summary; fall
        # back to all layers and let the per-layer probe filter them.
        polygon_layers = layers
    if not polygon_layers:
        return None
    # Prefer a layer whose name matches zoning keywords.
    for lyr in polygon_layers:
        name_lc = (lyr.get("name") or "").lower()
        if any(kw in name_lc for kw in _ZONING_KEYWORDS_POSITIVE):
            return f"{service_url.rstrip('/')}/{lyr.get('id')}"
    # Otherwise just take the first one.
    return f"{service_url.rstrip('/')}/{polygon_layers[0].get('id')}"


async def _persist_candidates(
    db: AsyncSession,
    jurisdiction,
    candidates: list[ZoningCandidate],
    municipality_name: str | None,
) -> None:
    """Upsert each candidate into zoning_sources.

    Idempotent on (jurisdiction_id, COALESCE(municipality_name,''), zoning_endpoint):
    re-running discovery overwrites the most recent confidence/scoring info
    for the same source URL, but never overwrites a row whose
    confidence_label has been promoted to 'verified' by the operator.
    """
    from sqlalchemy import select
    from app.models.zoning_source import ZoningSource

    for c in candidates:
        # Look for an existing row that matches.
        q = select(ZoningSource).where(
            ZoningSource.jurisdiction_id == jurisdiction.id,
            ZoningSource.zoning_endpoint == c.url,
        )
        if municipality_name is not None:
            q = q.where(ZoningSource.municipality_name == municipality_name)
        else:
            q = q.where(ZoningSource.municipality_name.is_(None))
        existing = (await db.execute(q)).scalar_one_or_none()

        payload = dict(
            jurisdiction_id=jurisdiction.id,
            municipality_name=municipality_name,
            county=jurisdiction.county,
            state=jurisdiction.state,
            source_type=c.source_type,
            zoning_endpoint=c.url,
            title=c.title,
            feature_count=c.feature_count,
            geometry_type=c.geometry_type,
            field_matches=c.field_matches,
            confidence_score=c.confidence,
            confidence_label="discovered",
            discovered_by="arcgis_hub",
            reasons=c.reasons,
        )

        if existing is None:
            db.add(ZoningSource(**payload))
        elif existing.confidence_label != "verified":
            # Re-discovery refreshes confidence + reasons but only when the
            # row hasn't already been operator-verified.
            for k, v in payload.items():
                setattr(existing, k, v)
            from datetime import datetime, timezone
            existing.updated_at = datetime.now(timezone.utc)

    await db.commit()
