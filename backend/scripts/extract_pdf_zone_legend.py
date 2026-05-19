"""extract_pdf_zone_legend — pull the zone-code legend out of a vector zoning PDF.

Outputs JSON of `{code, description, page_x, page_y, font_size}` per detected
legend entry. Operator imports this into QGIS as the seed attribute table when
assigning `zone_code` to polygons.

Empirically validated on Garfield NJ PDF (2026-05-18 pilot, this iteration):
detected 11 real zone codes (R-1, R-1A, R-2, R-3, R-TH, B-1, B-2, LM, CA, RDVT, P)
mixed with ~25 noise entries. Operator filter step is still needed but
total operator-zone-code-entry time drops from ~10 min to ~2 min.

Usage:
    python -m scripts.extract_pdf_zone_legend /path/to/town.pdf > legend.json
    python -m scripts.extract_pdf_zone_legend --csv /path/to/town.pdf > legend.csv

Limitations (intentional — fix only if pilot data demands it):
  - Heuristic only. Will surface non-legend uppercase short tokens
    (DISCLAIMER → AIMER, mapmaker names, etc.). Operator filters.
  - Description right-of-code heuristic is coarse (joins surrounding words).
    Good enough as a memory aid; the ordinance has the canonical description.
  - Vector PDFs only (the function reads pdfplumber words, which need
    embedded text). Raster PDFs will return [] — operator reads the legend
    visually.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pdfplumber  # type: ignore


# Words that ARE candidate zone codes if they appear in upper-case short form.
# Real zone-code grammar across NJ municipalities: 1-4 letters, optional dash,
# optional 1-3 digits, optional trailing letter. Examples: R-1, R-1A, B-2, LM,
# CAP, RDVT, OS, MU-1, C-1A, AC-2, etc.
_ZONE_CODE_RE = re.compile(r"^[A-Z]{1,4}(-?\d{1,3}[A-Z]{0,2})?$")

# Tokens that match the regex but are NEVER zone codes — they're noise.
_HARD_FILTER = frozenset({
    "CITY", "BERGEN", "NEW", "JERSEY", "NJ", "MAP", "OF", "THE", "AND", "OR",
    "TO", "IN", "ON", "FOR", "BY", "LEGEND", "ZONING", "ZONE", "BOROUGH",
    "TOWNSHIP", "VILLAGE", "TOWN", "COUNTY", "DISCLAIMER", "NOTE", "EZ2R",
    "AIMER",  # DISCLAIMER artifact
    "LIZZETTE",  # text from the map maker signature line
})

# Two-character "doubled letter" tokens (AA, BB, …) — always noise.
_DOUBLED_RE = re.compile(r"^([A-Z])\1$")


def extract_legend(pdf_path: str, page_index: int = 0) -> list[dict]:
    """Return a list of `{code, description, page_x, page_y, font_size}` dicts.

    `description` is a best-effort right-of-code text block (up to 8 words).
    Operator's job to filter + cleanup; this is a starter table.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if page_index >= len(pdf.pages):
            return []
        page = pdf.pages[page_index]
        words = page.extract_words(extra_attrs=["size", "fontname"])

    # Pass 1 — collect candidate code words.
    candidates: list[dict] = []
    for w in words:
        t = (w.get("text") or "").strip()
        if not t or len(t) > 8 or len(t) < 1:
            continue
        if t in _HARD_FILTER:
            continue
        if _DOUBLED_RE.match(t):
            continue
        if not _ZONE_CODE_RE.match(t):
            continue
        candidates.append({
            "code": t,
            "page_x": float(w.get("x0", 0)),
            "page_y": float(w.get("top", 0)),
            "size": round(float(w.get("size", 0)), 1),
            "fontname": w.get("fontname", ""),
        })

    # Pass 2 — for each candidate, find descriptor words to its right (same row, ≤500pt away).
    seen_codes: dict[str, dict] = {}
    for c in candidates:
        # Right-neighbors in the same horizontal band
        neighbors = [
            w for w in words
            if c["page_x"] < float(w.get("x0", 0)) < c["page_x"] + 500
            and abs(float(w.get("top", 0)) - c["page_y"]) < 20
            and (w.get("text") or "").strip() != c["code"]
        ]
        neighbors.sort(key=lambda w: float(w.get("x0", 0)))
        descr = " ".join((w.get("text") or "") for w in neighbors[:8]).strip()
        # Keep the first occurrence of each unique code (legend is typically at top of map).
        if c["code"] not in seen_codes:
            seen_codes[c["code"]] = {
                **c,
                "description": descr[:120],
            }

    # Sort by font size desc then by y (top-to-bottom) — legend entries are
    # usually largest + grouped near top of the column.
    out = sorted(
        seen_codes.values(),
        key=lambda x: (-x["size"], x["page_y"], x["page_x"]),
    )
    return out


def to_csv(entries: list[dict]) -> str:
    rows = ["code,description,size,page_x,page_y"]
    for e in entries:
        d = (e.get("description") or "").replace('"', "'").replace(",", " ")
        rows.append(f'{e["code"]},"{d}",{e["size"]},{e["page_x"]:.1f},{e["page_y"]:.1f}')
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract zoning legend codes from a vector PDF.")
    p.add_argument("pdf", help="path to the PDF")
    p.add_argument("--csv", action="store_true", help="emit CSV instead of JSON")
    p.add_argument("--page", type=int, default=0, help="page index (default 0)")
    args = p.parse_args(argv)

    if not Path(args.pdf).exists():
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 2

    entries = extract_legend(args.pdf, page_index=args.page)
    if args.csv:
        sys.stdout.write(to_csv(entries))
    else:
        json.dump({"source": args.pdf, "count": len(entries), "entries": entries}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
