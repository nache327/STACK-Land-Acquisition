#!/usr/bin/env python3
"""Wayzata MN GeoPDF zoning extraction proof.

Read-only diagnostic proof for the official Wayzata zoning map PDF:
https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025

This script intentionally does not ingest or mutate application data. It
downloads/probes the PDF in a temp directory, extracts the GeoPDF zoning vector
layer while preserving OGR_STYLE, pairs polygon fill styles to the PDF legend,
and prints a JSON proof payload containing zone codes plus sample WKT polygons.

Observed constraint: several official legend entries share the same base fill
color and are differentiated by cartographic hatch/line overlays in the map.
The proof therefore emits `zone_code_candidates` for those styles instead of
pretending the GeoPDF exposes a semantic zone-code attribute.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pdfplumber
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


SOURCE_URL = (
    "https://www.wayzata.org/DocumentCenter/View/6010/"
    "Wayzata-Zoning-Map-Updated-March-2025"
)
ZONING_LAYER = "Layers_Zoning_Designation1"

# Expected order from PR #300 / docs/AUDIT_NOTES/wayzata_pdf_source_planning.md
# and the PDF legend. `pdfplumber` extracts many of these directly, but the
# tightly kerned C-2 through C-4A labels are split into single characters by the
# PDF text layer, so legend row position is more reliable for the full ordered
# list.
EXPECTED_LEGEND_ORDER = [
    "C-1",
    "C-1A",
    "C-1B",
    "C-2",
    "C-3",
    "C-3A",
    "C-4",
    "C-4A",
    "C-4B",
    "INS",
    "P",
    "PUD",
    "R-1",
    "R-1A",
    "R-2",
    "R-2A",
    "R-3",
    "R-3A",
    "R-4",
    "R-4A",
    "R-5",
]

ZONE_CODE_RE = re.compile(r"\b(?:C|R)-\d[A-Z]?\b|\b(?:INS|PUD|P)\b")
BRUSH_RE = re.compile(r"BRUSH\(fc:(#[0-9A-Fa-f]{6})\)")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required binary not found on PATH: {name}")
    return path


def download_pdf(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "wayzata-geopdf-proof/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())


def rgb_tuple_to_hex(rgb: tuple[float, ...] | None) -> str | None:
    if not rgb or len(rgb) < 3:
        return None
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02X}" for c in rgb[:3])


def extract_pdf_legend(pdf_path: Path) -> dict[str, Any]:
    """Return ordered zone codes and fill-style candidates from the PDF legend."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text(layout=False, x_tolerance=1, y_tolerance=3) or ""
        extracted_codes = list(dict.fromkeys(ZONE_CODE_RE.findall(text)))

        swatches: list[dict[str, Any]] = []
        seen: set[tuple[float, str]] = set()
        for rect in page.rects:
            # The legend swatches are the 18pt squares in the right map collar.
            if not (
                rect["x0"] > 990
                and 90 < rect["top"] < 750
                and rect["width"] > 10
                and rect["height"] > 10
            ):
                continue
            fill = rgb_tuple_to_hex(rect.get("non_stroking_color"))
            if not fill:
                continue
            key = (round(rect["top"], 1), fill)
            if key in seen:
                continue
            seen.add(key)
            swatches.append(
                {
                    "top": round(rect["top"], 1),
                    "bottom": round(rect["bottom"], 1),
                    "fill": fill,
                }
            )

    swatches.sort(key=lambda item: item["top"])
    if len(swatches) != len(EXPECTED_LEGEND_ORDER):
        raise RuntimeError(
            f"Expected {len(EXPECTED_LEGEND_ORDER)} legend swatches; found {len(swatches)}"
        )

    rows = []
    fill_to_codes: dict[str, list[str]] = defaultdict(list)
    for code, swatch in zip(EXPECTED_LEGEND_ORDER, swatches):
        row = {"zone_code": code, **swatch}
        rows.append(row)
        fill_to_codes[swatch["fill"]].append(code)

    return {
        "zone_codes": EXPECTED_LEGEND_ORDER,
        "pdfplumber_extracted_codes": extracted_codes,
        "pdfplumber_missing_codes_due_to_text_splitting": [
            code for code in EXPECTED_LEGEND_ORDER if code not in extracted_codes
        ],
        "legend_rows": rows,
        "fill_to_zone_code_candidates": dict(fill_to_codes),
    }


def gdal_metadata(pdf_path: Path) -> dict[str, Any]:
    info = run(["gdalinfo", "-json", str(pdf_path)]).stdout
    data = json.loads(info)
    return {
        "driver": data.get("driverShortName"),
        "coordinate_system": data.get("coordinateSystem", {}).get("wkt", "").split("\n", 1)[0],
        "geo_transform": data.get("geoTransform"),
        "corner_coordinates": data.get("cornerCoordinates"),
        "metadata": data.get("metadata", {}),
    }


def ogr_layers(pdf_path: Path) -> list[str]:
    output = run(["ogrinfo", "-ro", "-so", str(pdf_path)]).stdout
    layers = []
    for line in output.splitlines():
        match = re.match(r"\s*\d+:\s+(.+)$", line)
        if match:
            layers.append(match.group(1))
    return layers


def export_zoning_geojson(pdf_path: Path, out_path: Path) -> None:
    # OGR_STYLE is a special style string, not a normal attribute. Explicit SQL
    # selection is required; otherwise ogr2ogr writes empty feature properties.
    run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            str(out_path),
            str(pdf_path),
            "-sql",
            f"SELECT OGR_STYLE FROM {ZONING_LAYER}",
        ]
    )


def brush_fill(style: str | None) -> str | None:
    if not style:
        return None
    match = BRUSH_RE.search(style)
    if not match:
        return None
    return match.group(1).upper()


def valid_polygon(geom: BaseGeometry) -> BaseGeometry:
    if geom.is_valid:
        return geom
    return geom.buffer(0)


def sample_polygons(geojson_path: Path, fill_to_codes: dict[str, list[str]]) -> dict[str, Any]:
    data = json.loads(geojson_path.read_text())
    feature_counts_by_geometry = Counter()
    polygon_counts_by_fill: Counter[str] = Counter()
    polygon_area_by_fill: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    for idx, feature in enumerate(data["features"]):
        geometry = feature.get("geometry")
        if not geometry:
            feature_counts_by_geometry["null"] += 1
            continue
        geom_type = geometry["type"]
        feature_counts_by_geometry[geom_type] += 1
        if "Polygon" not in geom_type:
            continue
        style = feature.get("properties", {}).get("OGR_STYLE")
        fill = brush_fill(style)
        if not fill:
            continue
        geom = valid_polygon(shape(geometry))
        if geom.is_empty or geom.area <= 0:
            continue
        polygon_counts_by_fill[fill] += 1
        polygon_area_by_fill[fill] += geom.area
        if len(samples) < 10:
            simplified = geom.simplify(2.0, preserve_topology=True)
            samples.append(
                {
                    "source_feature_index": idx,
                    "ogr_style": style,
                    "fill": fill,
                    "zone_code_candidates": fill_to_codes.get(fill, []),
                    "area_square_hennepin_feet": round(geom.area, 2),
                    "bounds_hennepin_feet": [round(v, 2) for v in geom.bounds],
                    "geometry_wkt_hennepin_feet": simplified.wkt,
                }
            )

    return {
        "feature_counts_by_geometry": dict(feature_counts_by_geometry),
        "polygon_counts_by_fill": dict(polygon_counts_by_fill),
        "polygon_area_by_fill": {k: round(v, 2) for k, v in polygon_area_by_fill.items()},
        "sample_polygons": samples,
    }


def build_proof(url: str, pdf_override: str | None = None) -> dict[str, Any]:
    require_binary("gdalinfo")
    require_binary("ogrinfo")
    require_binary("ogr2ogr")
    with tempfile.TemporaryDirectory(prefix="wayzata_geopdf_") as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "wayzata_zoning_map_2025.pdf"
        geojson_path = temp_path / "wayzata_zoning_style.geojson"

        if pdf_override:
            shutil.copyfile(pdf_override, pdf_path)
        else:
            download_pdf(url, pdf_path)
        metadata = gdal_metadata(pdf_path)
        layers = ogr_layers(pdf_path)
        if metadata["driver"] != "PDF" or not metadata.get("geo_transform"):
            raise RuntimeError("PDF is not recognized as a georeferenced GDAL PDF source")
        if ZONING_LAYER not in layers:
            raise RuntimeError(f"Expected OGR layer not found: {ZONING_LAYER}")

        legend = extract_pdf_legend(pdf_path)
        export_zoning_geojson(pdf_path, geojson_path)
        polygons = sample_polygons(
            geojson_path,
            legend["fill_to_zone_code_candidates"],
        )

    ambiguous_fills = {
        fill: codes
        for fill, codes in legend["fill_to_zone_code_candidates"].items()
        if len(codes) > 1
    }
    return {
        "source_url": url,
        "source_vintage": "2025-03-25",
        "source_method": "GeoPDF vector extraction via GDAL/OGR + pdfplumber legend parsing",
        "verdict": "georeferenced_vector_pdf_viable_with_style_to_zone_qa",
        "gdal_metadata": metadata,
        "ogr_layers": layers,
        "zoning_layer": ZONING_LAYER,
        "legend": legend,
        "vector_extraction": polygons,
        "style_resolution_note": (
            "The GeoPDF exposes polygon geometries and styles, but no semantic zone-code "
            "attribute. Some legend entries share a base fill and require hatch/overlay QA "
            "before production parcel backfill."
        ),
        "ambiguous_fill_to_zone_code_candidates": ambiguous_fills,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=SOURCE_URL, help="Wayzata zoning GeoPDF URL")
    parser.add_argument(
        "--pdf",
        help="Optional local copy of the official PDF; skips the live download",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    try:
        proof = build_proof(args.url, args.pdf)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(proof, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
