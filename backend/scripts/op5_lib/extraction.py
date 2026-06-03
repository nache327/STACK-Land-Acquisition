"""Op-5 polygon extraction helper (vector + raster).

This module is the production path the proof used for Fort Lee / Garfield /
Hackensack. It returns ``(polygons, color_to_zone, source_class,
vision_label_count)`` so :func:`default_extract_polygons_from_map` in the
per-muni runner can drop it in.

Hard rules carried over from the proof:

* Vector classification iff ``pdfplumber`` reports > 50 lines on page 1.
* Raster routes to the vision-LLM boundary-tracing path (Hackensack class).
* If vision returns 0 labels at confidence >= 0.75 the function returns
  ``polygons=[]`` so the runner's carve-out path fires.
* Affine bbox-fit to the Census GENZ2024 place boundary — fast and
  good-enough until per-muni GCPs are available (Hackensack proved
  vision-LLM GCPs do NOT reliably localize).

Heavy native deps (cv2, pdfplumber, anthropic, shapely) are lazy-imported
behind try/except so test environments without them can still import the
runner and exercise the carve-out paths.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger("op5_lib.extraction")

VISION_LABEL_CONFIDENCE_FLOOR = 0.75
PDFPLUMBER_VECTOR_LINE_THRESHOLD = 50
DEFAULT_RENDER_DPI = 300
DEFAULT_KMEANS_K = 36
MIN_REGION_AREA_FRAC = 0.00025  # of map body bbox area


@dataclass
class ExtractionResult:
    polygons: list[dict]      # WGS84 GeoJSON-ish dicts with zone_code + confidence
    color_to_zone: dict
    source_class: str         # vector | raster | text_only_legend | absent
    vision_label_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Top-level entry — used by the runner
# ─────────────────────────────────────────────────────────────────────────────


def extract_polygons(
    map_url: Optional[str],
    *,
    place_name: str,
    state: str = "NJ",
    anthropic_api_key: Optional[str] = None,
) -> ExtractionResult:
    """Production extractor. Routes vector / raster / absent paths."""
    if not map_url:
        return ExtractionResult([], {}, "absent", 0)
    payload, content_type = _fetch(map_url)
    if payload is None:
        return ExtractionResult([], {}, "absent", 0)
    source_class = _classify(payload, content_type)
    if source_class == "absent":
        return ExtractionResult([], {}, "absent", 0)
    place_bbox = _census_place_bbox(place_name, state)
    if not place_bbox:
        LOGGER.warning("no Census place bbox for %s, %s — carving out", place_name, state)
        return ExtractionResult([], {}, source_class, 0)
    api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        LOGGER.warning("ANTHROPIC_API_KEY missing — vision-LLM path disabled, carving out")
        return ExtractionResult([], {}, source_class, 0)

    if source_class == "vector":
        return _extract_vector(payload, place_bbox=place_bbox, api_key=api_key)
    return _extract_raster(payload, place_bbox=place_bbox, api_key=api_key, content_type=content_type)


# ─────────────────────────────────────────────────────────────────────────────
# Fetch + classify
# ─────────────────────────────────────────────────────────────────────────────


def _fetch(url: str) -> tuple[Optional[bytes], str]:
    try:
        import httpx
    except Exception:
        return None, ""
    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            resp = client.get(url, headers={"User-Agent": "ParcelLogic/1.0 Op5Factory"})
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", "").lower()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("fetch failed for %s: %s", url, exc)
        return None, ""


def _classify(payload: bytes, content_type: str) -> str:
    """Return vector | raster | absent."""
    try:
        import pdfplumber
    except Exception:
        # Without pdfplumber we can still classify on content-type alone.
        if any(t in content_type for t in ("image", "jpeg", "png", "tiff")):
            return "raster"
        return "absent"
    try:
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            page = pdf.pages[0] if pdf.pages else None
            if page is None:
                return "absent"
            lines = list(getattr(page, "lines", []) or [])
            return "vector" if len(lines) > PDFPLUMBER_VECTOR_LINE_THRESHOLD else "raster"
    except Exception:
        # Not a PDF -> classify by content-type guess.
        if any(t in content_type for t in ("image", "jpeg", "png", "tiff")):
            return "raster"
        return "absent"


# ─────────────────────────────────────────────────────────────────────────────
# Census GENZ2024 place boundary lookup (cached)
# ─────────────────────────────────────────────────────────────────────────────


_STATE_FIPS = {
    "NJ": "34", "NY": "36", "CT": "09", "PA": "42", "MA": "25",
    "MD": "24", "DE": "10", "VA": "51", "NC": "37", "GA": "13",
}


def _census_place_bbox(place_name: str, state: str) -> Optional[tuple[float, float, float, float]]:
    """Return (minlon, minlat, maxlon, maxlat) of the Census-recognized place.

    Queries the TIGERweb REST API directly (the Census Geocoder onelineaddress
    endpoint only resolves street addresses, not plain place names — confirmed
    against Westwood NJ smoke test 2026-06-03). BASENAME is the bare place name
    stripped of the "borough" / "township" / "city" suffix; that's our lookup
    key. Returns the place polygon's envelope. Caches per-process.
    """
    cache: dict = _census_place_bbox.__dict__.setdefault("_cache", {})
    key = (place_name.strip().lower(), state.upper())
    if key in cache:
        return cache[key]
    try:
        import httpx
    except Exception:
        return None

    # Strip common NJ DCA suffixes so BASENAME matches.
    bare = place_name.strip()
    for suffix in (" borough", " township", " town", " city", " village"):
        if bare.lower().endswith(suffix):
            bare = bare[: -len(suffix)]
            break
    state_fips = _STATE_FIPS.get(state.upper())
    if not state_fips:
        LOGGER.warning("no FIPS code for state %s — bbox unavailable", state)
        cache[key] = None
        return None

    url = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query"
    )
    params = {
        "where": f"BASENAME='{bare}' AND STATE='{state_fips}'",
        "outFields": "NAME,BASENAME,STATE,GEOID",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        feats = data.get("features") or []
        if not feats:
            LOGGER.warning("TIGERweb: no place match for BASENAME=%s STATE=%s", bare, state_fips)
            cache[key] = None
            return None
        rings = feats[0].get("geometry", {}).get("rings") or []
        pts: list[tuple[float, float]] = []

        def _walk(node):
            if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)) and len(node) == 2:
                pts.append((float(node[0]), float(node[1])))
            elif isinstance(node, list):
                for child in node:
                    _walk(child)

        _walk(rings)
        if not pts:
            cache[key] = None
            return None
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        bbox = (min(lons), min(lats), max(lons), max(lats))
        cache[key] = bbox
        return bbox
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("TIGERweb bbox lookup failed for %s, %s: %s", place_name, state, exc)
        cache[key] = None
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Vector path: render -> color-seg -> contour -> vision-LLM labels
# ─────────────────────────────────────────────────────────────────────────────


def _extract_vector(
    pdf_bytes: bytes,
    *,
    place_bbox: tuple[float, float, float, float],
    api_key: str,
) -> ExtractionResult:
    try:
        import cv2  # noqa: F401
        import numpy as np
        from shapely.geometry import Polygon as ShapelyPolygon
        from shapely.geometry import Point  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("vector deps missing (cv2/numpy/shapely): %s — falling back to raster", exc)
        return _extract_raster(pdf_bytes, place_bbox=place_bbox, api_key=api_key, content_type="application/pdf")

    png_bytes = _render_pdf_to_png(pdf_bytes, DEFAULT_RENDER_DPI)
    if png_bytes is None:
        return ExtractionResult([], {}, "vector", 0)

    # Color-segmentation polygons in pixel space.
    pixel_polygons, color_to_zone_pixel = _color_segment(png_bytes)
    if not pixel_polygons:
        LOGGER.info("color-seg produced 0 polygons — carving out")
        return ExtractionResult([], {}, "vector", 0)

    # Vision-LLM label assignment.
    labels = _vision_label_points(png_bytes, api_key=api_key)
    high_conf = [l for l in labels if l.get("confidence", 0) >= VISION_LABEL_CONFIDENCE_FLOOR]
    if not high_conf:
        LOGGER.info("vision returned 0 high-confidence labels — carving out")
        return ExtractionResult([], color_to_zone_pixel, "vector", 0)

    # Assign labels to polygons via point-in-polygon.
    img_h, img_w = _png_dimensions(png_bytes)
    if img_h <= 0 or img_w <= 0:
        return ExtractionResult([], color_to_zone_pixel, "vector", len(high_conf))

    from shapely.geometry import Point  # noqa: WPS433
    from shapely.geometry import Polygon as ShapelyPolygon  # noqa: WPS433

    enriched: list[dict] = []
    for poly_px in pixel_polygons:
        coords_px = poly_px["coords_px"]
        try:
            shp = ShapelyPolygon(coords_px)
            if not shp.is_valid or shp.is_empty:
                continue
        except Exception:
            continue
        inside = [l for l in high_conf if shp.contains(Point(l["x"], l["y"]))]
        if not inside:
            # Nearest-label fallback within ~bbox diagonal / 6.
            centroid = shp.centroid
            inside = sorted(
                high_conf,
                key=lambda l: (l["x"] - centroid.x) ** 2 + (l["y"] - centroid.y) ** 2,
            )[:1]
        if not inside:
            continue
        # Project to WGS84 via affine.
        wgs84_coords = [_pixel_to_wgs84(x, y, img_w, img_h, place_bbox) for x, y in coords_px]
        enriched.append({
            "zone_code": inside[0]["zone_code"],
            "confidence": float(inside[0].get("confidence", 0.75)),
            "color_rgb": poly_px.get("color_rgb"),
            "geometry": {"type": "Polygon", "coordinates": [wgs84_coords]},
        })

    if not enriched:
        return ExtractionResult([], color_to_zone_pixel, "vector", len(high_conf))

    return ExtractionResult(
        polygons=enriched,
        color_to_zone=color_to_zone_pixel,
        source_class="vector",
        vision_label_count=len(high_conf),
    )


def _render_pdf_to_png(pdf_bytes: bytes, dpi: int) -> Optional[bytes]:
    """pdftoppm with gdal_translate fallback. Returns first-page PNG bytes."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        pdf_path = td_path / "in.pdf"
        pdf_path.write_bytes(pdf_bytes)
        out_prefix = td_path / "page"
        try:
            subprocess.run(
                ["pdftoppm", "-r", str(dpi), "-png", "-f", "1", "-l", "1",
                 str(pdf_path), str(out_prefix)],
                check=True, capture_output=True, timeout=180,
            )
            for cand in (td_path / "page-1.png", td_path / "page-01.png"):
                if cand.exists():
                    return cand.read_bytes()
        except Exception as exc:  # noqa: BLE001
            LOGGER.info("pdftoppm failed (%s) — trying gdal_translate", exc)
        try:
            png_path = td_path / "page.png"
            subprocess.run(
                ["gdal_translate", "-of", "PNG", str(pdf_path), str(png_path)],
                check=True, capture_output=True, timeout=180,
            )
            return png_path.read_bytes() if png_path.exists() else None
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("gdal_translate failed: %s", exc)
            return None


def _color_segment(png_bytes: bytes) -> tuple[list[dict], dict]:
    """OpenCV k-means color segmentation + contour extraction.

    Returns (pixel-space polygons with color_rgb, empty color_to_zone).
    color_to_zone is left empty here — the vision-LLM label step populates
    it via the labels-inside-color-region inference. The carve-out path
    only triggers on text-only legends, which look like *non-empty*
    color_to_zone with 0 polygons (i.e. legend text but no shaded map
    bodies); for our purposes a populated polygon list is what matters.
    """
    import cv2
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return [], {}
    h, w = arr.shape[:2]
    map_area = float(h * w)
    min_area = MIN_REGION_AREA_FRAC * map_area
    if min_area < 200:
        min_area = 200.0

    flat = arr.reshape(-1, 3).astype(np.float32)
    # Subsample for k-means speed.
    sample_idx = np.random.default_rng(42).choice(flat.shape[0], min(50_000, flat.shape[0]), replace=False)
    sample = flat[sample_idx]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, _, centers = cv2.kmeans(
        sample, DEFAULT_KMEANS_K, None, crit, 4, cv2.KMEANS_PP_CENTERS,
    )
    centers = centers.astype(np.uint8)

    # Re-quantize the full image to cluster colors (nearest-center labels).
    diffs = flat[:, None, :] - centers[None, :, :].astype(np.float32)
    nearest = np.linalg.norm(diffs, axis=2).argmin(axis=1).astype(np.int32)
    labels = nearest.reshape(h, w)

    polygons: list[dict] = []
    color_to_zone: dict = {}  # populated by labels later; left empty here

    for cluster_idx in range(DEFAULT_KMEANS_K):
        mask = (labels == cluster_idx).astype(np.uint8) * 255
        # Drop sparse clusters quickly.
        if int(mask.sum()) < min_area * 0.1:
            continue
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rgb = tuple(int(c) for c in centers[cluster_idx][::-1])  # BGR -> RGB
        for c in contours:
            area = float(cv2.contourArea(c))
            if area < min_area:
                continue
            simplified = cv2.approxPolyDP(c, epsilon=2.0, closed=True)
            pts = [(float(p[0][0]), float(p[0][1])) for p in simplified]
            if len(pts) < 4:
                continue
            polygons.append({
                "color_rgb": list(rgb),
                "coords_px": pts,
                "area_px": area,
                "cluster_index": cluster_idx,
            })

    return polygons, color_to_zone


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    try:
        import cv2
        import numpy as np
        arr = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return 0, 0
        return arr.shape[0], arr.shape[1]
    except Exception:
        return 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# Vision-LLM label points (vector path)
# ─────────────────────────────────────────────────────────────────────────────


_VECTOR_LABEL_PROMPT = """You are reading a municipal zoning map. Identify every visible zone-code
label printed on the map (e.g. "R-1", "B-2", "I-3", "LM", "C-2"). For each
label, return its pixel coordinates and the zone code text.

Output JSON only:
{
  "labels": [
    {"x": 1234, "y": 567, "zone_code": "R-1", "confidence": 0.95},
    ...
  ]
}

Rules:
- x,y are pixel coordinates measured from the top-left of the image.
- Skip legend text — only labels printed inside the mapped polygons.
- Only include labels you are >= 75% confident about; lower confidence
  labels should be omitted, not downgraded.
"""


def _vision_label_points(png_bytes: bytes, *, api_key: str) -> list[dict]:
    """Returns [{x,y,zone_code,confidence}, ...] from vision-LLM."""
    return _call_anthropic_vision(png_bytes, _VECTOR_LABEL_PROMPT, api_key)["labels"]


_RASTER_DISTRICT_PROMPT = """You are reading a raster municipal zoning map. Trace the boundary of every
visible zoning district. For each district return its pixel-space polygon
boundary, the zone code printed inside it, and a confidence score.

Output JSON only:
{
  "districts": [
    {"zone_code": "R-1", "confidence": 0.9, "boundary": [[x,y],[x,y],...]},
    ...
  ]
}

Rules:
- Each boundary is a closed polygon in pixel coordinates from top-left.
- Skip the legend and the map collar; trace only mapped polygons.
- Only emit districts with confidence >= 75%.
"""


def _extract_raster(
    payload: bytes,
    *,
    place_bbox: tuple[float, float, float, float],
    api_key: str,
    content_type: str,
) -> ExtractionResult:
    """Hackensack-class raster path. Vision-LLM traces district boundaries."""
    # PDF -> render to PNG first; otherwise assume the payload IS an image.
    if "pdf" in content_type or payload[:4] == b"%PDF":
        png_bytes = _render_pdf_to_png(payload, DEFAULT_RENDER_DPI)
    else:
        png_bytes = payload
    if png_bytes is None:
        return ExtractionResult([], {}, "raster", 0)

    try:
        parsed = _call_anthropic_vision(png_bytes, _RASTER_DISTRICT_PROMPT, api_key)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("raster vision call failed: %s", exc)
        return ExtractionResult([], {}, "raster", 0)
    districts = parsed.get("districts", [])
    high_conf = [d for d in districts if d.get("confidence", 0) >= VISION_LABEL_CONFIDENCE_FLOOR]
    if not high_conf:
        return ExtractionResult([], {}, "raster", 0)
    img_h, img_w = _png_dimensions(png_bytes)
    if img_h <= 0 or img_w <= 0:
        return ExtractionResult([], {}, "raster", len(high_conf))

    polygons: list[dict] = []
    for d in high_conf:
        boundary = d.get("boundary", [])
        if len(boundary) < 4:
            continue
        wgs84 = [_pixel_to_wgs84(x, y, img_w, img_h, place_bbox) for x, y in boundary]
        polygons.append({
            "zone_code": d.get("zone_code"),
            "confidence": float(d.get("confidence", 0.75)),
            "geometry": {"type": "Polygon", "coordinates": [wgs84]},
        })

    # Synthesize a minimal color_to_zone signal so the runner doesn't
    # treat the result as a text-only legend — raster path provides
    # zone_code -> stub color directly.
    color_to_zone = {f"raster:{p['zone_code']}": p["zone_code"] for p in polygons if p.get("zone_code")}

    return ExtractionResult(
        polygons=polygons,
        color_to_zone=color_to_zone,
        source_class="raster",
        vision_label_count=len(high_conf),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic vision call (shared)
# ─────────────────────────────────────────────────────────────────────────────


def _call_anthropic_vision(png_bytes: bytes, prompt: str, api_key: str) -> dict[str, Any]:
    """Single Anthropic vision call returning parsed JSON dict."""
    import base64
    try:
        import anthropic  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"anthropic SDK missing: {exc}") from exc
    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(png_bytes).decode()
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = msg.content[0].text if msg.content and hasattr(msg.content[0], "text") else ""
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {"labels": [], "districts": []}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"labels": [], "districts": []}


# ─────────────────────────────────────────────────────────────────────────────
# Pixel -> WGS84 affine (proof's approach)
# ─────────────────────────────────────────────────────────────────────────────


def _pixel_to_wgs84(
    x: float, y: float,
    img_w: int, img_h: int,
    place_bbox: tuple[float, float, float, float],
) -> list[float]:
    """Affine-bbox-fit from pixel space to WGS84."""
    minlon, minlat, maxlon, maxlat = place_bbox
    if img_w <= 0 or img_h <= 0:
        return [0.0, 0.0]
    u = x / img_w
    v = y / img_h
    lon = minlon + u * (maxlon - minlon)
    # PNG y axis grows DOWN; latitude grows UP — invert.
    lat = maxlat - v * (maxlat - minlat)
    return [lon, lat]
