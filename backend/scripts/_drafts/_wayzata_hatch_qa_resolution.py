#!/usr/bin/env python3
"""Wayzata GeoPDF hatch QA resolution diagnostic.

Outcome: HALT for fully automatic production mapping.

This read-only diagnostic extends `_wayzata_geopdf_extraction_proof.py` by
checking whether the shared-fill legend classes can be resolved from PDF text,
OGR hatch/overlay vectors, rendered legend pixels, or a quick public source
probe. It writes no application data and uses only temp files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import Image
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree


SOURCE_URL = (
    "https://www.wayzata.org/DocumentCenter/View/6010/"
    "Wayzata-Zoning-Map-Updated-March-2025"
)
PLANNING_URL = "https://www.wayzata.org/236/Planning"
ZONING_LAYER = "Layers_Zoning_Designation1"
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
PEN_RE = re.compile(r"PEN\(c:(#[0-9A-Fa-f]{6})\)")
BRUSH_RE = re.compile(r"BRUSH\(fc:(#[0-9A-Fa-f]{6})\)")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "wayzata-hatch-qa/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())


def color_hex(rgb: tuple[float, ...] | None) -> str | None:
    if not rgb:
        return None
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02X}" for c in rgb[:3])


def brush_fill(style: str | None) -> str | None:
    if not style:
        return None
    match = BRUSH_RE.search(style)
    return match.group(1).upper() if match else None


def pen_color(style: str | None) -> str | None:
    if not style:
        return None
    match = PEN_RE.search(style)
    return match.group(1).upper() if match else None


def export_zoning(pdf_path: Path, geojson_path: Path) -> None:
    run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            str(geojson_path),
            str(pdf_path),
            "-sql",
            f"SELECT OGR_STYLE FROM {ZONING_LAYER}",
        ]
    )


def legend_rows(pdf_path: Path) -> list[dict[str, Any]]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        rects: list[dict[str, Any]] = []
        seen: set[tuple[float, str]] = set()
        for rect in page.rects:
            if not (
                rect["x0"] > 990
                and 90 < rect["top"] < 750
                and rect["width"] > 10
                and rect["height"] > 10
            ):
                continue
            fill = color_hex(rect.get("non_stroking_color"))
            if not fill:
                continue
            key = (round(rect["top"], 1), fill)
            if key in seen:
                continue
            seen.add(key)
            rects.append(
                {
                    "top": round(rect["top"], 1),
                    "bottom": round(rect["bottom"], 1),
                    "x0": rect["x0"],
                    "x1": rect["x1"],
                    "fill": fill,
                }
            )
    rects.sort(key=lambda row: row["top"])
    if len(rects) != len(EXPECTED_LEGEND_ORDER):
        raise RuntimeError(f"Expected 21 legend swatches, found {len(rects)}")
    return [{"zone_code": code, **row} for code, row in zip(EXPECTED_LEGEND_ORDER, rects)]


def pdf_text_probe(pdf_path: Path) -> dict[str, Any]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        words = pdf.pages[0].extract_words(x_tolerance=1, y_tolerance=3)
    hits = [word for word in words if ZONE_CODE_RE.fullmatch(word["text"])]
    map_hits = [word for word in hits if word["x0"] < 980]
    return {
        "zone_like_word_hits": len(hits),
        "zone_like_map_hits": len(map_hits),
        "hit_texts": [word["text"] for word in hits],
    }


def overlay_signature_groups(
    geojson_path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    data = json.loads(geojson_path.read_text())
    polygons: list[tuple[int, BaseGeometry, str]] = []
    lines: list[tuple[BaseGeometry, str]] = []
    fill_to_codes: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        fill_to_codes[row["fill"]].append(row["zone_code"])

    for idx, feature in enumerate(data["features"]):
        geometry = feature.get("geometry")
        style = feature.get("properties", {}).get("OGR_STYLE")
        if not geometry:
            continue
        geom = shape(geometry)
        if "Polygon" in geometry["type"]:
            fill = brush_fill(style)
            if fill:
                polygons.append((idx, geom, fill))
        elif "LineString" in geometry["type"]:
            color = pen_color(style)
            if color and color != "#000000":
                lines.append((geom, color))

    tree = STRtree([line[0] for line in lines]) if lines else None
    summaries: dict[str, dict[str, Any]] = {}
    for fill, codes in sorted(fill_to_codes.items()):
        if len(codes) == 1:
            continue
        signatures: Counter[tuple[tuple[str, int], ...]] = Counter()
        examples: list[dict[str, Any]] = []
        for idx, polygon, poly_fill in polygons:
            if poly_fill != fill:
                continue
            lengths = overlay_lengths(polygon, lines, tree)
            signature = tuple(sorted((color, round(length / 100) * 100) for color, length in lengths.items()))
            signatures[signature] += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "feature_index": idx,
                        "area": round(polygon.area, 1),
                        "overlay_lengths": {color: round(length, 1) for color, length in lengths.items()},
                    }
                )
        summaries[fill] = {
            "candidate_zone_codes": codes,
            "polygon_count": sum(1 for _, _, poly_fill in polygons if poly_fill == fill),
            "signature_group_count": len(signatures),
            "top_signature_groups": [
                {"count": count, "signature": list(signature)}
                for signature, count in signatures.most_common(10)
            ],
            "examples": examples,
        }
    return summaries


def overlay_lengths(
    polygon: BaseGeometry,
    lines: list[tuple[BaseGeometry, str]],
    tree: STRtree | None,
) -> dict[str, float]:
    if tree is None:
        return {}
    lengths: Counter[str] = Counter()
    for hit in tree.query(polygon):
        line, color = lines[int(hit)]
        intersection = line.intersection(polygon)
        if intersection.is_empty:
            continue
        if intersection.length > 5:
            lengths[color] += intersection.length
    return dict(lengths)


def render_legend_profiles(pdf_path: Path, temp_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not shutil.which("pdftoppm"):
        return []
    render_base = temp_dir / "wayzata_page"
    run(["pdftoppm", "-png", "-r", "200", "-singlefile", str(pdf_path), str(render_base)])
    image = Image.open(render_base.with_suffix(".png")).convert("RGB")
    scale = 200 / 72
    profiles = []
    for row in rows:
        box = (
            int((row["x0"] + 2) * scale),
            int((row["top"] + 2) * scale),
            int((row["x1"] - 2) * scale),
            int((row["bottom"] - 2) * scale),
        )
        colors = Counter(image.crop(box).getdata()).most_common(8)
        profiles.append(
            {
                "zone_code": row["zone_code"],
                "fill": row["fill"],
                "top_rendered_colors": [
                    {"color": f"#{r:02X}{g:02X}{b:02X}", "pixels": count}
                    for (r, g, b), count in colors
                ],
            }
        )
    return profiles


def arcgis_search_probe() -> dict[str, Any]:
    queries = [
        "Wayzata zoning",
        "Wayzata zoning map",
        "Wayzata MN zoning",
        "Wayzata FeatureServer",
        "Hennepin Wayzata zoning",
        "Hennepin zoning Wayzata",
    ]
    results = {}
    for query in queries:
        url = "https://www.arcgis.com/sharing/rest/search?f=json&num=10&q=" + urllib.parse.quote(query)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                payload = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            results[query] = {"error": str(exc)}
            continue
        results[query] = {
            "total": payload.get("total"),
            "titles": [item.get("title") for item in payload.get("results", [])[:10]],
        }
    return results


def city_page_probe() -> dict[str, Any]:
    try:
        html = urllib.request.urlopen(PLANNING_URL, timeout=20).read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    document_links = re.findall(r'href="([^"]*DocumentCenter/View/[^"]+)"[^>]*>([^<]+)', html)
    map_links = [
        {"href": href, "label": re.sub(r"\s+", " ", label).strip()}
        for href, label in document_links
        if "map" in label.lower() or "zoning" in label.lower()
    ]
    non_pdf_terms = [term for term in ["shapefile", "geojson", "arcgis", "featureserver", "csv"] if term in html.lower()]
    return {"map_links": map_links, "non_pdf_terms_found": non_pdf_terms}


def build_report(pdf_override: str | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="wayzata_hatch_qa_") as temp:
        temp_dir = Path(temp)
        pdf_path = temp_dir / "wayzata_zoning_map_2025.pdf"
        geojson_path = temp_dir / "wayzata_zoning_style.geojson"
        if pdf_override:
            shutil.copyfile(pdf_override, pdf_path)
        else:
            download(SOURCE_URL, pdf_path)

        rows = legend_rows(pdf_path)
        text_probe = pdf_text_probe(pdf_path)
        export_zoning(pdf_path, geojson_path)
        shared_fill_summaries = overlay_signature_groups(geojson_path, rows)
        legend_profiles = render_legend_profiles(pdf_path, temp_dir, rows)

    unresolved_reasons = []
    for fill, summary in shared_fill_summaries.items():
        candidates = summary["candidate_zone_codes"]
        group_count = summary["signature_group_count"]
        if fill == "#896129":
            unresolved_reasons.append(
                f"{fill} ({'/'.join(candidates)}) has one vector overlay signature group for two legend codes."
            )
        elif group_count > len(candidates) * 3:
            unresolved_reasons.append(
                f"{fill} ({'/'.join(candidates)}) has {group_count} noisy vector overlay groups for {len(candidates)} codes."
            )

    return {
        "verdict": "HALT",
        "reason": "PDF hatch/overlay data cannot produce a production-ready 21-code semantic mapping without operator QA.",
        "source_url": SOURCE_URL,
        "pdf_text_probe": text_probe,
        "shared_fill_overlay_summaries": shared_fill_summaries,
        "rendered_legend_profiles": legend_profiles,
        "unresolved_reasons": unresolved_reasons,
        "arcgis_search_probe": arcgis_search_probe(),
        "city_page_probe": city_page_probe(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", help="Optional local official Wayzata zoning PDF")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = build_report(args.pdf)
    print(json.dumps(report, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
