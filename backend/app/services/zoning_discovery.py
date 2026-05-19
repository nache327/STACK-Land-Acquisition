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
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction


logger = logging.getLogger(__name__)


_HUB_DATASETS_URL = "https://hub.arcgis.com/api/v3/datasets"

# Scoring schema version — bump when `_score_candidate` adds or reshapes
# components. Rows persisted under an older version are candidates for
# rescore. The eligibility check in `stale_score_remediation` reads this;
# the operator-facing audit endpoint reports it.
#
# History:
#   v1 — initial scoring v2 (title/geometry/feature/field components).
#   v2 — added Component F (bbox_overlap_*) on 2026-05-12.
SCORING_VERSION = 2

# Per-version: the set of breakdown-component names that, when present
# in a stored confidence_breakdown, prove the row was scored under at
# least this version. Stale detection uses these markers to infer the
# version of a row without a per-row column.
SCORING_VERSION_MARKERS: dict[int, frozenset[str]] = {
    2: frozenset({"bbox_overlap_strong", "bbox_overlap_tiny", "bbox_overlap_disjoint"}),
}

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


# US state names + abbreviations for Component B (wrong-state penalty).
# Lowercased name → 2-letter abbrev.
_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
_US_STATE_ABBREVS = set(_US_STATES.values())

# Generic-layer titles for Component C (penalty when no jurisdiction-name match).
_GENERIC_TITLES = {
    "zoning", "zoning districts", "zoning district", "zoning map",
    "zoning layer", "land use", "landuse", "planning", "zone districts",
}


@dataclass
class ScoreComponent:
    """One signal contributing to a candidate's confidence score."""
    name: str
    delta: int
    reason: str | None = None


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
    # Structured per-component score deltas, e.g. {"name_match": 25, ...}.
    # Populated by scoring v2; kept None if scoring v1 was used.
    confidence_breakdown: dict[str, int] | None = None


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
    denylist = await _fetch_rejected_endpoints(db)

    candidates: list[ZoningCandidate] = []
    candidates_total = 0
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        raw = await _hub_search(client, query, bbox_str)
        candidates_total = len(raw)
        # Probe each candidate's feature_count, geometry, fields (concurrent).
        probes = [
            _probe_layer(client, item, bbox, name_tokens, jurisdiction=j, denylist=denylist)
            for item in raw
        ]
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
    *,
    jurisdiction: Jurisdiction | None = None,
    denylist: set[str] | None = None,
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
    layer_bbox_srid: int | None = None
    if _url_has_layer_index(full_url):
        try:
            meta = await client.get(full_url, params={"f": "json"}, timeout=15.0)
            if meta.status_code == 200:
                mdata = meta.json()
                geometry_type = mdata.get("geometryType")
                extent = mdata.get("extent") or {}
                if all(k in extent for k in ("xmin", "ymin", "xmax", "ymax")):
                    layer_bbox = [extent["xmin"], extent["ymin"], extent["xmax"], extent["ymax"]]
                    # ArcGIS extent.spatialReference can have wkid (Esri code)
                    # or latestWkid (EPSG). 102100 == EPSG:3857 (WebMercator).
                    sr = extent.get("spatialReference") or {}
                    layer_bbox_srid = sr.get("latestWkid") or sr.get("wkid") or None
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

    # Reproject layer extent to WGS84 + compute overlap ratio vs jurisdiction
    # bbox. None when either side is missing or reprojection is unsupported
    # (e.g. exotic State Plane CRS). The ratio drives Component F (bbox
    # overlap scoring); preserves the old bool for backward compat on the
    # ZoningCandidate dataclass.
    #
    # Per-town municipal discovery calls _probe_layer with the positional
    # `jurisdiction_bbox=None` (towns are too small to geocode cheaply) but
    # still passes the COUNTY's Jurisdiction object via keyword. Fall back
    # to county.bbox so Component F can fire even for per-town candidates
    # (catches New Milford CT vs Bergen NJ — disjoint bboxes).
    effective_juris_bbox = jurisdiction_bbox or (
        jurisdiction.bbox if jurisdiction is not None else None
    )
    layer_bbox_4326 = reproject_bbox_to_wgs84(layer_bbox, layer_bbox_srid)
    bbox_overlap_ratio = _bbox_overlap_ratio(
        effective_juris_bbox, layer_bbox_4326,
    )
    bbox_overlaps = bool(bbox_overlap_ratio and bbox_overlap_ratio > 0)

    name_signals = _name_match_signals(title, name_tokens or {})

    confidence, components = _score_candidate(
        title=title,
        url=full_url,
        pos_hits=pos_hits,
        neg_hits=neg_hits,
        geometry_type=geometry_type,
        feature_count=feature_count,
        field_matches=field_matches,
        bbox_overlap_ratio=bbox_overlap_ratio,
        name_signals=name_signals,
        jurisdiction=jurisdiction,
        denylist=denylist,
    )
    reasons = [c.reason for c in components if c.reason]
    confidence_breakdown = {c.name: c.delta for c in components}

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
        confidence_breakdown=confidence_breakdown,
    )


def _score_candidate(
    *,
    title: str,
    url: str,
    pos_hits: list[str],
    neg_hits: list[str],
    geometry_type: str | None,
    feature_count: int | None,
    field_matches: list[str],
    bbox_overlap_ratio: float | None,
    name_signals: dict,
    jurisdiction: Jurisdiction | None = None,
    denylist: set[str] | None = None,
) -> tuple[int, list[ScoreComponent]]:
    """Scoring v2 — weighted components with explainable breakdown.

    Returns (clamped int 0-100, list of every component that contributed).
    """
    components: list[ScoreComponent] = []

    # Title positive keywords
    if pos_hits:
        components.append(ScoreComponent(
            "title_positive", 15 * len(pos_hits),
            f"title matches zoning keywords: {pos_hits}"))
    # Title negative keywords
    if neg_hits:
        components.append(ScoreComponent(
            "title_negative", -20 * len(neg_hits),
            f"title penalised by non-zoning keywords: {neg_hits}"))
    # Geometry
    if geometry_type == "esriGeometryPolygon":
        components.append(ScoreComponent(
            "geometry_polygon", 20, "geometry is polygon"))
    elif geometry_type:
        components.append(ScoreComponent(
            "geometry_not_polygon", -30,
            f"geometry is {geometry_type!r}, not polygon"))
    # Feature count
    if feature_count is not None:
        if _MIN_FEATURE_COUNT <= feature_count <= _MAX_FEATURE_COUNT:
            components.append(ScoreComponent(
                "feature_count_ok", 15,
                f"feature_count={feature_count} is in plausible range"))
        else:
            components.append(ScoreComponent(
                "feature_count_outlier", -10,
                f"feature_count={feature_count} is outside [30, 250k]"))
    # Field matches
    if field_matches:
        components.append(ScoreComponent(
            "field_matches", min(20, 5 * len(field_matches)),
            f"fields look zoning-shaped: {field_matches[:5]}"))
    # Component F — bbox overlap ratio (replaces the old bbox_overlaps bool).
    # ratio == None: no signal (CRS unsupported or extent missing).
    # ratio >= 0.5: strong overlap — likely covers the jurisdiction.
    # 0.05 <= ratio < 0.5: weak overlap — possible adjacent-county / partial.
    # 0 < ratio < 0.05: barely-touching — almost certainly wrong location.
    # ratio == 0.0: disjoint — different state / wrong-jurisdiction (e.g.
    #   New Milford CT vs New Milford NJ; layer extent in CT, jurisdiction
    #   bbox in NJ).
    if bbox_overlap_ratio is not None:
        if bbox_overlap_ratio >= 0.5:
            components.append(ScoreComponent(
                "bbox_overlap_strong", 10,
                f"layer bbox covers {int(bbox_overlap_ratio*100)}% of jurisdiction bbox"))
        elif bbox_overlap_ratio >= 0.05:
            # Weak overlap — could be a neighboring town or a partial
            # cover. No score signal; we don't have enough info.
            pass
        elif bbox_overlap_ratio > 0:
            components.append(ScoreComponent(
                "bbox_overlap_tiny", -30,
                f"layer bbox barely overlaps jurisdiction ({bbox_overlap_ratio*100:.1f}%)"))
        else:  # == 0.0
            components.append(ScoreComponent(
                "bbox_overlap_disjoint", -60,
                "layer bbox is completely disjoint from jurisdiction bbox "
                "(likely wrong city/state)"))

    # Component A — name match (word-boundary, tiered)
    multi = name_signals.get("multi_word_match", False)
    rare = name_signals.get("rare_match", False)
    common = name_signals.get("common_match", False)
    if multi:
        components.append(ScoreComponent(
            "name_match_multi_word", 30,
            "title contains all jurisdiction-name tokens (word-boundary)"))
    elif rare:
        components.append(ScoreComponent(
            "name_match_rare_token", 25,
            "title contains a rare (>=6 char) jurisdiction token (word-boundary)"))
    elif common:
        components.append(ScoreComponent(
            "name_match_common_token", 8,
            "title contains a common (3-5 char) jurisdiction token (word-boundary)"))

    # Wrong-county penalty
    wrong_county = name_signals.get("wrong_county")
    if wrong_county:
        components.append(ScoreComponent(
            "wrong_county", -50,
            f"title names a different county ({wrong_county!r})"))

    # Component B — wrong-state penalty
    if jurisdiction is not None and jurisdiction.state:
        wrong_state = _detect_wrong_state(title, jurisdiction.state)
        if wrong_state:
            components.append(ScoreComponent(
                "wrong_state", -40,
                f"title names a different state ({wrong_state!r})"))

    # Component C — generic-layer penalty (no jurisdiction name in title)
    normalized = _normalize_title(title)
    if normalized in _GENERIC_TITLES and not (multi or rare or common):
        components.append(ScoreComponent(
            "generic_layer", -30,
            f"title is generic ({normalized!r}) with no jurisdiction-name match"))

    # Component D — cross-jurisdiction deny-list
    if denylist and url in denylist:
        components.append(ScoreComponent(
            "denylist_rejected", -80,
            "url previously rejected by operator (cross-jurisdiction)"))

    # Component E — service-host bonus
    if jurisdiction is not None:
        bonus, reason = _service_host_bonus(
            url, jurisdiction.state, jurisdiction.county, jurisdiction.name,
        )
        if bonus:
            components.append(ScoreComponent("service_host", bonus, reason))

    total = max(0, min(100, sum(c.delta for c in components)))
    return total, components


# Common US county names that appear in ArcGIS layer titles. Used only for the
# "title names a different county" penalty — we compare the candidate's title
# to this list, find any county tokens, and if NONE of them are in the
# jurisdiction's own name_tokens, that's a wrong-county signal.
_COMMON_COUNTY_WORDS = {
    "county", "co.",
}


def _name_tokens(name: str | None, county: str | None) -> dict:
    """Build a token bag for v2 name matching.

    Returns:
      expect: set[str] — all 3+ char tokens from name + county
              (used for single-token bonuses + wrong-county detection)
      multi_word: list[str] — ordered 3+ char tokens of the *name* only
              (used for "all tokens present, in any order, word-boundary"
              multi-word bonus — strongest name-match signal)
    """
    raw_all = " ".join(filter(None, [name or "", county or ""])).lower()
    raw_all = raw_all.replace(",", " ").replace(".", " ")
    expect = {w for w in raw_all.split() if len(w) >= 3 and w not in _COMMON_COUNTY_WORDS}

    name_only = (name or "").lower().replace(",", " ").replace(".", " ")
    multi_word = [
        w for w in name_only.split()
        if len(w) >= 3 and w not in _COMMON_COUNTY_WORDS
    ]

    return {"expect": expect, "multi_word": multi_word}


def _name_match_signals(title: str, name_tokens: dict) -> dict:
    """Whole-word name-match signals for scoring components A + wrong-county.

    Returns dict with:
      multi_word_match: bool   — every token in `multi_word` appears in title (word-bound)
      rare_match: bool         — at least one >=6-char token matched (word-bound)
      common_match: bool       — at least one 3-5 char token matched (word-bound)
      wrong_county: str | None — "<X> county" in title where X ∉ expect
    """
    title_lc = title.lower()
    expect: set[str] = name_tokens.get("expect") or set()
    multi_word: list[str] = name_tokens.get("multi_word") or []

    if not expect and not multi_word:
        return {
            "multi_word_match": False,
            "rare_match": False,
            "common_match": False,
            "wrong_county": None,
        }

    # Multi-word match: every token of the jurisdiction's NAME must appear
    # in the title as a whole word. Only meaningful if name has 2+ tokens.
    multi_word_match = False
    if len(multi_word) >= 2:
        multi_word_match = all(
            re.search(rf"\b{re.escape(t)}\b", title_lc) for t in multi_word
        )

    # Single-token matches: bucket by length. Rare tokens (paramus, edgewater,
    # hackensack) are strong signal; common tokens (park, fort, lake) are weak.
    rare_tokens = {t for t in expect if len(t) >= 6}
    common_tokens = {t for t in expect if 3 <= len(t) <= 5}

    rare_match = any(
        re.search(rf"\b{re.escape(t)}\b", title_lc) for t in rare_tokens
    )
    common_match = any(
        re.search(rf"\b{re.escape(t)}\b", title_lc) for t in common_tokens
    )

    # Wrong-county: "<X> county" in title where X is NOT one of our tokens.
    parts = title_lc.split()
    wrong = None
    for i, w in enumerate(parts[:-1]):
        # Strip trailing punctuation from county-word too (e.g. "county,")
        next_w = parts[i + 1].strip(",.;:")
        if next_w.startswith("county") and w not in expect and len(w) >= 3:
            wrong = w
            break

    return {
        "multi_word_match": multi_word_match,
        "rare_match": rare_match,
        "common_match": common_match,
        "wrong_county": wrong,
    }


def _detect_wrong_state(title: str, jurisdiction_state: str | None) -> str | None:
    """Return the detected state name/abbrev if the title names a state that
    isn't the jurisdiction's state. None otherwise.

    Catches "Garfield County Utah" vs NJ, "North Charleston SC" vs NJ,
    "Franklin County Iowa" vs NJ.
    """
    if not jurisdiction_state:
        return None
    target_abbrev = jurisdiction_state.strip().upper()
    target_name = next(
        (n for n, ab in _US_STATES.items() if ab == target_abbrev), None,
    )
    title_lc = title.lower()

    # Full state name (word boundary): "garfield county utah"
    for name, abbrev in _US_STATES.items():
        if abbrev == target_abbrev:
            continue
        if name == target_name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", title_lc):
            return name

    # State abbreviation as a delimited token: " SC", ", SC", "SC ", "(SC)"
    # Case-sensitive on the abbrev to avoid matching every "co" / "or" / "in".
    for abbrev in _US_STATE_ABBREVS:
        if abbrev == target_abbrev:
            continue
        if re.search(rf"(?:^|[\s,(\[])({abbrev})(?:$|[\s,.;:)\]])", title):
            return abbrev

    return None


def _normalize_title(title: str) -> str:
    """Lowercase + strip non-word characters; collapse whitespace."""
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _service_host_bonus(
    url: str,
    state: str | None,
    county: str | None,
    name: str | None,
) -> tuple[int, str | None]:
    """If URL host contains jurisdiction state/county/name as a substring,
    return (+15, reason). Otherwise (0, None).

    Catches county portal services (e.g. gis.alleghenycounty.us) that don't
    surface well via Hub keywords but are higher-trust than community-shared
    services.arcgis.com tenants.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return 0, None
    if not host:
        return 0, None

    # State token in host (e.g. "arcgis.nj.gov") — short tokens need a delim
    # to avoid matching "njhospital" for NJ.
    state_lc = (state or "").lower()
    if state_lc and len(state_lc) == 2:
        if re.search(rf"(?:^|[.\-]){state_lc}(?:$|[.\-])", host):
            return 15, f"service host {host!r} contains state token {state_lc!r}"

    # County or name in host (>=4 chars to avoid noise)
    for token in (county or "").lower(), (name or "").lower():
        token = token.split(" ")[0]  # take first word of a multi-word name
        if token and len(token) >= 4 and token in host:
            return 15, f"service host {host!r} contains jurisdiction token {token!r}"

    return 0, None


async def spatial_check_for_url(
    zoning_url: str,
    jurisdiction_bbox: list[float] | None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Probe a FeatureServer/MapServer layer URL and report its geographic
    alignment with a jurisdiction's bbox.

    Used by:
      - the operator-facing /_spatial-check endpoint (visibility)
      - the pre-flight bbox check in ingest (refuse disjoint sources)

    Returns:
      {
        "layer_extent_raw":      [xmin, ymin, xmax, ymax] | None,
        "layer_extent_srid":     int | None,    # 4326 / 3857 / 102100 / etc.
        "layer_extent_wgs84":    [xmin, ymin, xmax, ymax] | None,  # reprojected
        "jurisdiction_bbox":     [xmin, ymin, xmax, ymax] | None,
        "bbox_overlap_ratio":    float | None,   # None = unknown
        "verdict":               "good" | "partial" | "tiny" | "disjoint" | "unknown",
        "error":                 str | None,
      }
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    result: dict[str, Any] = {
        "layer_extent_raw": None,
        "layer_extent_srid": None,
        "layer_extent_wgs84": None,
        "jurisdiction_bbox": jurisdiction_bbox,
        "bbox_overlap_ratio": None,
        "verdict": "unknown",
        "error": None,
    }

    try:
        resp = await client.get(zoning_url, params={"f": "json"}, timeout=15.0)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        meta = resp.json() or {}
        ext = meta.get("extent") or {}
        if all(k in ext for k in ("xmin", "ymin", "xmax", "ymax")):
            result["layer_extent_raw"] = [
                ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"],
            ]
            sr = ext.get("spatialReference") or {}
            result["layer_extent_srid"] = sr.get("latestWkid") or sr.get("wkid")
            result["layer_extent_wgs84"] = reproject_bbox_to_wgs84(
                result["layer_extent_raw"], result["layer_extent_srid"],
            )

        result["bbox_overlap_ratio"] = _bbox_overlap_ratio(
            jurisdiction_bbox, result["layer_extent_wgs84"],
        )
        r = result["bbox_overlap_ratio"]
        if r is None:
            result["verdict"] = "unknown"
        elif r >= 0.5:
            result["verdict"] = "good"
        elif r >= 0.05:
            result["verdict"] = "partial"
        elif r > 0:
            result["verdict"] = "tiny"
        else:
            result["verdict"] = "disjoint"
    except Exception as exc:
        result["error"] = repr(exc)[:200]
    finally:
        if own_client:
            await client.aclose()
    return result


async def _fetch_rejected_endpoints(db: AsyncSession) -> set[str]:
    """One-shot fetch of all currently-rejected zoning_endpoints for the
    cross-jurisdiction deny-list (Component D). Returns a set[str] for
    O(1) per-candidate lookup; one DB hop per discovery run.
    """
    from app.models.zoning_source import ZoningSource
    try:
        rows = await db.execute(
            select(ZoningSource.zoning_endpoint)
            .where(ZoningSource.validation_status == "rejected")
            .where(ZoningSource.zoning_endpoint.is_not(None))
        )
        return {r[0] for r in rows.all() if r[0]}
    except Exception as exc:
        logger.warning("denylist fetch failed (non-fatal): %r", exc)
        return set()


def _bboxes_overlap(a: list[float], b: list[float]) -> bool:
    """Back-compat: returns True if both bboxes are well-formed. Kept for
    callers that still want the bool; new code should use
    `_bbox_overlap_ratio` for an actual geographic test."""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return False
    return all(v is not None for v in a + b)


# EPSG / Esri WKID codes that mean WGS84 lat/lng (EPSG:4326)
_WGS84_CODES = {4326}
# Codes that mean Web Mercator (EPSG:3857; Esri's code is 102100)
_WEB_MERCATOR_CODES = {3857, 102100, 900913}


try:
    from pyproj import Transformer as _PyprojTransformer  # type: ignore
    _PYPROJ_AVAILABLE = True
except ImportError:
    _PYPROJ_AVAILABLE = False
    _PyprojTransformer = None  # type: ignore

# Cache transformers by source SRID — creating a Transformer is expensive
# (~100ms first time per CRS as PROJ loads grid files) but the per-bbox
# transform is fast. Keyed by integer SRID; None means we tried + failed.
_TRANSFORMER_CACHE: dict[int, Any] = {}


def reproject_bbox_to_wgs84(
    bbox: list[float] | None,
    srid: int | None,
) -> list[float] | None:
    """Reproject [xmin, ymin, xmax, ymax] to WGS84 lat/lng (EPSG:4326).

    Uses pyproj for general CRS support when available (covers all state-
    plane SRIDs + national grids + everything in PROJ's EPSG database).
    Falls back to a hand-rolled WebMercator formula for environments
    without pyproj (closed-form for EPSG:3857 / Esri:102100 only).

    `bbox` may already be in WGS84 if `srid` is None (the common case
    where the layer published an unmarked extent). We assume that's
    lat/lng if the values fall in [-180, 180] × [-90, 90].

    Returns None for unsupported CRSes — Component F then fails closed
    (no signal) rather than scoring on misaligned coords.
    """
    if not bbox or len(bbox) != 4:
        return None
    if any(v is None for v in bbox):
        return None

    if srid is None:
        if (-180.0 <= bbox[0] <= 180.0 and -180.0 <= bbox[2] <= 180.0
                and -90.0 <= bbox[1] <= 90.0 and -90.0 <= bbox[3] <= 90.0):
            return list(bbox)
        return None

    if srid in _WGS84_CODES:
        return list(bbox)

    # pyproj handles all EPSG codes including state planes. Try first.
    if _PYPROJ_AVAILABLE:
        py = _pyproj_reproject(bbox, srid)
        if py is not None:
            return py
        # pyproj couldn't handle it (rare) — fall through to closed-form.

    # Closed-form WebMercator fallback (used when pyproj is missing).
    if srid in _WEB_MERCATOR_CODES:
        return [
            _mercator_x_to_lng(bbox[0]),
            _mercator_y_to_lat(bbox[1]),
            _mercator_x_to_lng(bbox[2]),
            _mercator_y_to_lat(bbox[3]),
        ]

    return None


def _pyproj_reproject(bbox: list[float], srid: int) -> list[float] | None:
    """Use cached pyproj Transformer to reproject one bbox to WGS84. Returns
    None on any failure (unknown SRID, transform error, or corrupt
    extent values that produce an absurd reprojected bbox)."""
    if srid in _TRANSFORMER_CACHE:
        t = _TRANSFORMER_CACHE[srid]
    else:
        try:
            t = _PyprojTransformer.from_crs(
                f"EPSG:{srid}", "EPSG:4326", always_xy=True,
            )
        except Exception:
            t = None
        _TRANSFORMER_CACHE[srid] = t
    if t is None:
        return None
    try:
        x_min, y_min = t.transform(bbox[0], bbox[1])
        x_max, y_max = t.transform(bbox[2], bbox[3])
        # pyproj returns NaN/inf on out-of-bounds inputs.
        if any(_bad_coord(v) for v in (x_min, y_min, x_max, y_max)):
            return None
        # Sanity-check the reprojected bbox isn't absurdly large.
        # No US municipal zoning layer is going to span >30° of lng/lat.
        # The South Amboy "Zoning Districts" service publishes corrupt
        # extent metadata (raw bbox in 3424 reprojects to a hemispheric
        # span) — without this guard, Component F would fire +10 strong
        # overlap for nonsense extents that happen to encompass any
        # jurisdiction.
        if (x_max - x_min) > 30 or (y_max - y_min) > 30:
            return None
        # Also reject out-of-bounds lat (>±90) or lng (>±180).
        if not (-180 <= x_min <= 180 and -180 <= x_max <= 180
                and -90 <= y_min <= 90 and -90 <= y_max <= 90):
            return None
        return [x_min, y_min, x_max, y_max]
    except Exception:
        return None


def _bad_coord(v: float) -> bool:
    import math
    return v is None or math.isnan(v) or math.isinf(v)


def _mercator_x_to_lng(x: float) -> float:
    import math
    return (x / 6378137.0) * (180.0 / math.pi)


def _mercator_y_to_lat(y: float) -> float:
    import math
    return (math.atan(math.exp(y / 6378137.0)) * 2.0 - math.pi / 2.0) * (180.0 / math.pi)


def _bbox_overlap_ratio(
    juris: list[float] | None,
    layer: list[float] | None,
) -> float | None:
    """Return a geographic-overlap score in [0, 1] between a jurisdiction
    bbox and a candidate layer's bbox (both in EPSG:4326).

    Returns max(inter/juris, inter/layer) — the higher of:
      - "what fraction of the jurisdiction does this layer cover?"
        (high = comprehensive countywide source)
      - "what fraction of the layer is inside this jurisdiction?"
        (high = a small in-scope source, e.g. a single town's zoning
        inside its county's bbox)

    Taking the max handles both per-county discovery (where the layer
    should be ~county-sized) AND per-town discovery (where the layer
    is a small subset of the county). Without this, a legitimate per-
    town source would be penalized for "not covering" the whole county.

    Returns None if either bbox is missing — the caller treats None
    as "no signal" (Component F doesn't fire).

    Returns 0.0 for disjoint boxes (strongest "wrong location" signal).
    """
    if not juris or not layer or len(juris) != 4 or len(layer) != 4:
        return None
    j_xmin, j_ymin, j_xmax, j_ymax = juris
    l_xmin, l_ymin, l_xmax, l_ymax = layer
    if any(v is None for v in (*juris, *layer)):
        return None

    inter_xmin = max(j_xmin, l_xmin)
    inter_ymin = max(j_ymin, l_ymin)
    inter_xmax = min(j_xmax, l_xmax)
    inter_ymax = min(j_ymax, l_ymax)

    if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
        return 0.0  # disjoint

    inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
    juris_area = (j_xmax - j_xmin) * (j_ymax - j_ymin)
    layer_area = (l_xmax - l_xmin) * (l_ymax - l_ymin)
    if juris_area <= 0 or layer_area <= 0:
        return None

    return min(1.0, max(inter_area / juris_area, inter_area / layer_area))


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
            confidence_breakdown=c.confidence_breakdown,
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
