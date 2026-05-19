"""prepare_pdf_for_qgis — turn a vector zoning PDF into a starter GeoJSON for QGIS.

This is the cold-side half of the PDF onboarding pipeline. It runs the three
automatable steps so the operator opens QGIS to a pre-seeded project:

  1. Polygon extraction:    ogr2ogr -f GeoJSON pdf.geojson source.pdf
  2. Polygon noise filter:  drop sub-threshold features and non-polygon geoms.
  3. Label auto-pairing:    if a zone-code text label falls INSIDE a polygon,
                            seed that polygon's `zone_code` attribute.
  4. Legend extraction:     parallel call into extract_pdf_zone_legend.

Output: a GeoJSON FeatureCollection in PDF page coords (NOT georeferenced).
The operator must:
  - Open the GeoJSON in QGIS atop the georeferenced PDF raster
  - Fill NULL zone_code on the polygons the auto-pairing missed
  - Drop any spurious polygons (decorative shapes, text outlines)
  - Re-export as GeoJSON in EPSG:4326

Empirically (Garfield NJ pilot, 2026-05-18): produces 88 candidate polygons,
~35-40% of which get a zone_code auto-assigned. Operator filters/fills the
rest in QGIS in ~45 min.

Usage:
    python -m scripts.prepare_pdf_for_qgis /tmp/garfield.pdf > starter.geojson
    python -m scripts.prepare_pdf_for_qgis --report /tmp/garfield.pdf  # print stats
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Cold-backend module (avoid duplicating the regex catalog).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.extract_pdf_zone_legend import extract_legend  # type: ignore


_MIN_POLYGON_AREA_PDF_UNITS = 1000  # filter sub-threshold polygons (decorations)


def run_ogr2ogr(pdf_path: str) -> dict:
    """Convert PDF to GeoJSON via ogr2ogr. Returns the parsed FeatureCollection.

    ogr2ogr emits "Non closed ring detected" warnings on most zoning PDFs and
    exits non-zero — but it DID produce the output. We check the output file
    content (not the exit code) to determine success. The pilot on Garfield
    surfaced this gotcha: ogr2ogr produced 5,094 features and a 1.6 MB GeoJSON
    while exiting 1 due to warnings.
    """
    # Generate a temp path WITHOUT pre-creating the file. ogr2ogr refuses to
    # overwrite an existing target (even a zero-byte tempfile) and silently
    # bails. Pilot finding 2026-05-18.
    tmpdir = Path(tempfile.gettempdir())
    out_path = str(tmpdir / f"prepare_pdf_{os.getpid()}_{abs(hash(pdf_path))}.geojson")
    if Path(out_path).exists():
        Path(out_path).unlink()
    try:
        proc = subprocess.run(
            ["ogr2ogr", "-f", "GeoJSON", out_path, pdf_path],
            capture_output=True, text=True, timeout=60,
        )
        # Check output, not exit code. Empty file = real failure.
        if not Path(out_path).exists() or Path(out_path).stat().st_size < 100:
            raise RuntimeError(
                f"ogr2ogr produced no output (exit {proc.returncode}); stderr: {proc.stderr[:300]}"
            )
        try:
            data = json.load(open(out_path))
        except Exception as exc:
            raise RuntimeError(f"ogr2ogr produced unparseable output: {exc}")
        if not data.get("features"):
            raise RuntimeError(
                f"ogr2ogr returned 0 features (exit {proc.returncode}); "
                f"PDF may be raster-only. stderr: {proc.stderr[:300]}"
            )
        return data
    finally:
        try: os.unlink(out_path)
        except OSError: pass


def polygon_area(coords: list) -> float:
    """Shoelace area for the first ring of a Polygon's coordinates."""
    if not coords or not coords[0]: return 0.0
    ring = coords[0]
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i+1][1] - ring[i+1][0] * ring[i][1]
    return abs(a) / 2


def feature_centroid(feat: dict) -> tuple[float, float] | None:
    g = feat.get("geometry") or {}
    if g.get("type") == "Polygon":
        ring = g["coordinates"][0]
    elif g.get("type") == "MultiPolygon":
        ring = g["coordinates"][0][0]
    else:
        return None
    if not ring: return None
    n = len(ring)
    return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n


def auto_pair_labels(
    polygons: list[dict],
    pdf_path: str,
    valid_codes: set[str],
) -> list[dict]:
    """For each polygon, check if any zone-code text label falls inside it.
    Mutates `polygons` in place — adds `properties.zone_code` where matched.

    Real-world friction (Garfield pilot, 2026-05-18):
      - `valid_codes` must be PRE-FILTERED to legend-band codes only. The
        `extract_legend` function emits anything matching the loose pattern
        including single-letter map-body decorations (N, H, BR) that DO
        appear inside polygons but are NOT zoning codes. Caller passes only
        codes from the legend's largest-font cluster.
      - Scale detection must use the GLOBAL polygon bbox, not the first
        polygon's bbox — first polygon may not span the page.
    """
    import pdfplumber
    from shapely.geometry import Polygon as ShPoly, Point

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(extra_attrs=["size"])
        page_w, page_h = page.width, page.height

    # Scale: use the GLOBAL polygon-bbox, not the first feature's.
    # ogr2ogr's PDF rasterizer outputs coords in its own PDF-page units
    # (~3637 wide / ~5437 tall for Garfield's PDF). pdfplumber sees the same
    # PDF at a different DPI (1746 wide / 2610 tall). Same scale x and y.
    all_xs: list[float] = []
    all_ys: list[float] = []
    for feat in polygons:
        g = feat.get("geometry") or {}
        rings = g["coordinates"] if g.get("type") == "Polygon" else g.get("coordinates", [[]])[0]
        if not rings or not rings[0]: continue
        for x, y in rings[0]:
            all_xs.append(x); all_ys.append(y)
    if all_xs and all_ys:
        scale = min(page_w / max(all_xs), page_h / max(all_ys))
    else:
        scale = 1.0

    # In-map labels — filter to PRE-VALIDATED zone codes only (caller-supplied set).
    in_map_labels = [
        w for w in words
        if (w.get("text") or "").strip() in valid_codes
    ]

    for feat in polygons:
        g = feat.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"): continue
        rings = g["coordinates"] if g["type"] == "Polygon" else g["coordinates"][0]
        if not rings or not rings[0]: continue
        pp_ring = [(x * scale, y * scale) for x, y in rings[0]]
        if len(pp_ring) < 4: continue
        try:
            sp = ShPoly(pp_ring)
            if not sp.is_valid:
                sp = sp.buffer(0)
        except Exception:
            continue
        votes: dict[str, int] = {}
        for w in in_map_labels:
            wx = (w["x0"] + w["x1"]) / 2
            wy = (w["top"] + w["bottom"]) / 2
            if sp.contains(Point(wx, wy)):
                t = w["text"].strip()
                votes[t] = votes.get(t, 0) + 1
        if votes:
            winner = max(votes.items(), key=lambda kv: kv[1])[0]
            feat.setdefault("properties", {})["zone_code"] = winner
            feat["properties"]["zone_code_source"] = "auto_paired_in_polygon"
            feat["properties"]["zone_code_votes"] = votes[winner]
        else:
            feat.setdefault("properties", {})["zone_code"] = None
            feat["properties"]["zone_code_source"] = "operator_must_fill"

    return polygons


def prepare(pdf_path: str) -> dict:
    """Run the full prepare pipeline. Returns {features, legend, stats}."""
    raw = run_ogr2ogr(pdf_path)
    all_feats = raw.get("features") or []

    # Filter to substantial polygons.
    polys = []
    for f in all_feats:
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"): continue
        a = polygon_area(g["coordinates"] if g["type"] == "Polygon" else g["coordinates"][0])
        if a < _MIN_POLYGON_AREA_PDF_UNITS: continue
        f.setdefault("properties", {})
        f["properties"]["pdf_page_area"] = round(a, 1)
        polys.append(f)

    # Legend.
    legend_entries = extract_legend(pdf_path)
    # Identify the LEGEND-band font size (the modal large size among legend candidates).
    # Garfield pilot: legend uses 18.0pt; map body uses 6-12pt. Single-letter
    # body decorations (N=73pt north arrow, H/D/F decorative letters) appear
    # at large sizes but ARE NOT zone codes. We narrow to the most frequent
    # large size that occurs with multiple distinct codes.
    from collections import Counter
    size_to_codes: dict[float, set[str]] = {}
    for e in legend_entries:
        s = e.get("size", 0)
        if s < 14: continue
        size_to_codes.setdefault(s, set()).add(e["code"])
    # Modal legend size = the size with the most distinct codes
    if size_to_codes:
        legend_size = max(size_to_codes, key=lambda s: len(size_to_codes[s]))
        candidate_codes = sorted(size_to_codes[legend_size])
    else:
        legend_size = None
        candidate_codes = []

    # Auto-pair labels into polygons.
    polys = auto_pair_labels(polys, pdf_path, set(candidate_codes))

    paired = sum(1 for p in polys if p.get("properties", {}).get("zone_code"))
    code_dist: dict[str, int] = {}
    for p in polys:
        zc = p.get("properties", {}).get("zone_code")
        if zc:
            code_dist[zc] = code_dist.get(zc, 0) + 1

    fc = {
        "type": "FeatureCollection",
        "features": polys,
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:LOCAL:PDF_PAGE_UNITS",
            },
        },
    }
    return {
        "feature_collection": fc,
        "legend_entries": legend_entries,
        "stats": {
            "raw_features": len(all_feats),
            "after_polygon_filter": len(polys),
            "auto_paired": paired,
            "paired_fraction": round(paired / max(1, len(polys)), 3),
            "candidate_codes": candidate_codes,
            "code_distribution": code_dist,
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert vector zoning PDF to a starter GeoJSON for QGIS cleanup.")
    p.add_argument("pdf", help="path to the PDF")
    p.add_argument("--report", action="store_true", help="emit only the stats summary, not the GeoJSON")
    args = p.parse_args(argv)

    if not Path(args.pdf).exists():
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 2

    result = prepare(args.pdf)
    if args.report:
        json.dump({"stats": result["stats"], "legend": result["legend_entries"]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(result["feature_collection"], sys.stdout)
        sys.stdout.write("\n")
        # Stats to stderr so stdout stays clean for piping.
        print(json.dumps(result["stats"], indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
