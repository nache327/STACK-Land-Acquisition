"""
POST /api/parse-pdf-table

Downloads a zoning ordinance PDF and extracts the Table of Uses into
structured zone → permission data using two methods:

  1. pdfplumber — coordinate-based column mapping (fast, deterministic)
  2. Claude Vision — Anthropic's native PDF document API (fallback)

Both paths return the same response schema so callers never need to know
which method ran.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
from typing import Any

import httpx
import pdfplumber
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["pdf-parser"])


# ── Response model ─────────────────────────────────────────────────────────────

class ParsePdfResponse(BaseModel):
    # use_name → {zone_code → "permitted" | "conditional" | "prohibited"}
    uses: dict[str, dict[str, str]]
    # Ordered list of zone codes found in the header row
    zone_columns: list[str]
    confidence: float          # 0.0–1.0
    method: str                # "pdfplumber" | "claude-vision" | "failed"
    warnings: list[str]


class ParsePdfRequest(BaseModel):
    url: str


# ── Router ─────────────────────────────────────────────────────────────────────

@router.post("/parse-pdf-table", response_model=ParsePdfResponse)
async def parse_pdf_table(body: ParsePdfRequest) -> ParsePdfResponse:
    """
    Download a PDF and extract its Table of Uses into structured data.

    Tries pdfplumber first (coordinate-based, deterministic). If confidence
    is below 0.65 falls back to Claude Vision (Anthropic PDF document API).
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(
                body.url,
                headers={"User-Agent": "ParcelLogic/1.0 ZoningVerifier"},
            )
            r.raise_for_status()
            pdf_bytes = r.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}")

    # Run pdfplumber synchronously in a thread (it's CPU-bound)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _parse_with_pdfplumber, pdf_bytes
    )

    # If pdfplumber found a high-confidence result, return immediately
    if result.confidence >= 0.65:
        return result

    # Fallback: Claude Vision
    vision_result = await _parse_with_claude_vision(pdf_bytes, result.warnings)
    if vision_result is not None and vision_result.confidence > result.confidence:
        return vision_result

    return result


# ── pdfplumber extractor ───────────────────────────────────────────────────────

# Zone codes are short, ALL-CAPS, optionally hyphenated/slashed
_ZONE_CODE_RE = re.compile(r"^[A-Z]{1,3}(?:[-/][A-Z0-9]{1,4})?$")


def _looks_like_zone_code(text: str) -> bool:
    if len(text) < 1 or len(text) > 10:
        return False
    return bool(_ZONE_CODE_RE.match(text))


def _nearest_zone(
    x: float,
    zone_headers: dict[float, str],
    max_dist: float = 20.0,
) -> str | None:
    if not zone_headers:
        return None
    closest_x, closest_zone = min(zone_headers.items(), key=lambda kv: abs(kv[0] - x))
    return closest_zone if abs(closest_x - x) <= max_dist else None


def _parse_with_pdfplumber(pdf_bytes: bytes) -> ParsePdfResponse:
    warnings: list[str] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # zone x-position → zone code (accumulated across all pages)
            all_zone_headers: dict[float, str] = {}
            # use_name → {zone_code → "permitted" | "conditional"}
            use_rows: dict[str, dict[str, str]] = {}

            for page in pdf.pages:
                words = page.extract_words(x_tolerance=5, y_tolerance=5)
                if not words:
                    continue

                # Group words into rows by quantised y-position
                rows_by_y: dict[int, list[dict[str, Any]]] = {}
                for w in words:
                    y_key = round(float(w["top"]) / 5) * 5
                    rows_by_y.setdefault(y_key, []).append(w)

                # ── Find header rows ──────────────────────────────────────────
                # A header row has ≥3 zone-code tokens all to the right of x=150.
                for _y, row_words in sorted(rows_by_y.items()):
                    right_words = [w for w in row_words if float(w["x0"]) > 150]
                    zone_candidates = [
                        w for w in right_words if _looks_like_zone_code(w["text"])
                    ]
                    if len(zone_candidates) >= 3:
                        for w in zone_candidates:
                            all_zone_headers[float(w["x0"])] = w["text"]

                if not all_zone_headers:
                    continue

                # ── Find use rows ─────────────────────────────────────────────
                # A use row has a use-name on the left (x < 200) and P/C markers
                # in the zone columns (x > 200).
                PERMISSION_TOKENS = {"P", "C", "P1", "P2", "P3", "C1", "C2"}
                for _y, row_words in sorted(rows_by_y.items()):
                    left_words = [w for w in row_words if float(w["x0"]) < 200]
                    right_markers = [
                        w
                        for w in row_words
                        if float(w["x0"]) > 200 and w["text"].upper() in PERMISSION_TOKENS
                    ]

                    if not left_words or not right_markers:
                        continue

                    # Build use name from left column words sorted by x
                    use_name = " ".join(
                        w["text"]
                        for w in sorted(left_words, key=lambda w: float(w["x0"]))
                    ).strip()

                    # Skip section/column headers and footnote lines
                    if (
                        len(use_name) < 4
                        or use_name.upper() in {"USE", "DISTRICT", "ZONE", "NOTES", "USES"}
                        or use_name.upper().startswith("NOTES:")
                    ):
                        continue

                    # Map each P/C marker to the nearest zone column
                    permission_map: dict[str, str] = {}
                    for marker in right_markers:
                        zone = _nearest_zone(float(marker["x0"]), all_zone_headers)
                        if zone is None:
                            continue
                        val = (
                            "permitted"
                            if marker["text"].upper().startswith("P")
                            else "conditional"
                        )
                        # Permitted beats conditional if two markers land in the same column
                        if zone not in permission_map or val == "permitted":
                            permission_map[zone] = val

                    if permission_map:
                        # Merge with existing entry for the same use name (multi-page tables)
                        if use_name in use_rows:
                            use_rows[use_name].update(permission_map)
                        else:
                            use_rows[use_name] = permission_map

            if not all_zone_headers:
                return ParsePdfResponse(
                    uses={},
                    zone_columns=[],
                    confidence=0.1,
                    method="pdfplumber",
                    warnings=["No zone header row found — PDF may not contain a columnar use table"],
                )

            zone_columns = [v for _, v in sorted(all_zone_headers.items())]

            # Confidence: ramps up with number of zones found and use rows extracted
            n_zones = len(zone_columns)
            n_uses = len(use_rows)
            confidence = min(0.97, 0.4 + 0.04 * n_zones + 0.05 * min(n_uses, 5))

            if n_uses == 0:
                warnings.append("Zone header found but no use rows with P/C markers extracted")
                confidence = 0.3

            return ParsePdfResponse(
                uses=use_rows,
                zone_columns=zone_columns,
                confidence=confidence,
                method="pdfplumber",
                warnings=warnings,
            )

    except Exception as exc:
        return ParsePdfResponse(
            uses={},
            zone_columns=[],
            confidence=0.0,
            method="pdfplumber",
            warnings=[f"pdfplumber error: {exc}"],
        )


# ── Claude Vision fallback ─────────────────────────────────────────────────────

_VISION_PROMPT = """This is a zoning ordinance PDF. Find the Table of Uses (also called Use Matrix, Table of Permitted Uses, or Land Use Table).

Extract ONLY the rows related to storage, warehousing, or garage/vehicle uses (e.g. "Storage Units", "Mini Warehouse", "Moving and Storage", "Self Storage", "Vehicle Storage", "Garage", "Truck Terminal", etc.).

For each matching row:
1. Give the EXACT use name as it appears in the table
2. For EVERY zone column in the table, state whether it shows:
   - P or P1/P2 → "permitted"
   - C or C1/C2 → "conditional"
   - blank, dash, or N → "prohibited"

Return ONLY a JSON object in this exact format, nothing else:
{
  "uses": {
    "Storage Units, Climate Controlled Indoor": {
      "NC": "prohibited",
      "C": "permitted",
      "C-H": "permitted",
      "LI": "permitted"
    }
  },
  "zone_columns": ["NC", "C", "C-H", "CR", "C-1", "BP", "LI", "MU", "T/M", "PF", "HI"],
  "confidence": 0.95
}

Rules:
- Include ALL zone columns in "zone_columns" (even zones where the use is prohibited)
- Mark any zone where the cell is blank or has a dash as "prohibited"
- If there is no storage/warehouse/garage row at all, return {"uses": {}, "zone_columns": [...all zones...], "confidence": 0.8}
- Do not include any other text outside the JSON object
"""


async def _parse_with_claude_vision(
    pdf_bytes: bytes,
    prior_warnings: list[str],
) -> ParsePdfResponse | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic  # lazy import — only needed for fallback path

        b64 = base64.standard_b64encode(pdf_bytes).decode()

        client = anthropic.Anthropic(api_key=api_key)

        # Run in executor (anthropic SDK is sync)
        def _call() -> anthropic.types.Message:
            return client.messages.create(
                model="claude-opus-4-7",
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": _VISION_PROMPT},
                        ],
                    }
                ],
            )

        msg = await asyncio.get_event_loop().run_in_executor(None, _call)

        raw = (
            msg.content[0].text
            if msg.content and hasattr(msg.content[0], "text")
            else ""
        )

        # Extract the JSON object from the response
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return None

        data = json.loads(json_match.group())
        uses_raw: dict[str, dict[str, str]] = data.get("uses", {})
        zone_columns: list[str] = data.get("zone_columns", [])
        confidence: float = float(data.get("confidence", 0.8))

        # Normalize permission values to our canonical strings
        uses: dict[str, dict[str, str]] = {}
        for use_name, perms in uses_raw.items():
            uses[use_name] = {
                zone: (
                    "permitted"
                    if str(v).lower().startswith("p")
                    else "conditional"
                    if str(v).lower().startswith("c")
                    else "prohibited"
                )
                for zone, v in perms.items()
            }

        return ParsePdfResponse(
            uses=uses,
            zone_columns=zone_columns,
            confidence=confidence,
            method="claude-vision",
            warnings=[],
        )

    except Exception as exc:
        return ParsePdfResponse(
            uses={},
            zone_columns=[],
            confidence=0.0,
            method="claude-vision",
            warnings=[f"Claude Vision error: {exc}"],
        )
