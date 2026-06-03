"""Op-5 discovery classify — Phase 0 of the factory.

For each muni in `backend/data/{county}_zoning_directory.json` (or fallback
to `nj_municipalities.json`), probe the `map_url` and classify the asset as
one of:

    vector            PDF with extractable vector linework (pdfplumber lines > 50)
    raster            PDF rendered primarily as images OR a .jpg / .jpeg / .png map
    text_only_legend  deferred to the per-muni runner (Master plan §Phase-0)
    absent            HTTP 404 / timeout / malformed / no map_url at all

Per-muni budget is 60 s; failures default to ``absent`` (carve-out).

Output: ``/tmp/op5_factory/{county}_classification.json`` containing a list
of records ``[{muni_code, muni_name, class, map_url, ordinance_url,
confidence, error}, ...]``. The orchestrator reads this file to partition
the muni list into factory-routable (vector) vs operator-routable
(raster + text-only) before Phase 1.

Idempotency: re-running on a county appends only the munis that are missing
from the prior classification file. ``--force`` re-classifies everything.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from op5_per_muni_runner import (  # noqa: E402  (sibling script import)
    ARTIFACT_ROOT,
    DATA_DIR,
    MuniRecord,
    load_county_directory,
)

LOGGER = logging.getLogger("op5_discovery_classify")

PER_MUNI_TIMEOUT_S = 60.0
VECTOR_LINE_THRESHOLD = 50  # pdfplumber.pages[0].lines len > 50 -> vector


@dataclass
class ClassificationRecord:
    muni_code: str
    muni_name: str
    cls: str               # vector|raster|absent  (text_only_legend deferred)
    map_url: Optional[str]
    ordinance_url: Optional[str]
    confidence: float
    error: Optional[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("cls")
        return d


def classification_output_path(county: str, root: Path = ARTIFACT_ROOT) -> Path:
    return root / f"{county.strip().lower()}_classification.json"


def _is_image_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"))


async def classify_one(muni: MuniRecord) -> ClassificationRecord:
    """Single-muni probe + classify. Never raises — failure -> absent."""
    if not muni.map_url:
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=None,
            ordinance_url=muni.ordinance_url,
            confidence=1.0,
            error="no map_url in directory",
        )

    if _is_image_path(muni.map_url):
        # Don't bother downloading bytes to confirm — file extension is
        # adequate signal. The runner re-validates on the heavy path.
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="raster",
            map_url=muni.map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.85,
            error=None,
        )

    try:
        import httpx
        import pdfplumber
    except Exception as exc:  # noqa: BLE001
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=muni.map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.0,
            error=f"missing classify dependency: {exc}",
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=PER_MUNI_TIMEOUT_S,
        ) as client:
            r = await client.get(
                muni.map_url,
                headers={"User-Agent": "ParcelLogic/1.0 Op5DiscoveryClassify"},
            )
            r.raise_for_status()
            payload = r.content
            ctype = r.headers.get("content-type", "").lower()
    except Exception as exc:  # noqa: BLE001
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=muni.map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.9,
            error=f"download failed: {exc}",
        )

    if "pdf" not in ctype and not payload[:4].startswith(b"%PDF"):
        # Not a PDF -> classify by content-type / URL signal.
        if "image" in ctype or _is_image_path(muni.map_url):
            return ClassificationRecord(
                muni_code=muni.muni_code,
                muni_name=muni.muni_name,
                cls="raster",
                map_url=muni.map_url,
                ordinance_url=muni.ordinance_url,
                confidence=0.85,
                error=None,
            )
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=muni.map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.6,
            error=f"unexpected content-type: {ctype!r}",
        )

    try:
        # pdfplumber is sync; offload.
        def _count_lines() -> int:
            with pdfplumber.open(io.BytesIO(payload)) as pdf:
                if not pdf.pages:
                    return 0
                page = pdf.pages[0]
                return len(list(getattr(page, "lines", []) or []))

        loop = asyncio.get_running_loop()
        line_count = await asyncio.wait_for(
            loop.run_in_executor(None, _count_lines), timeout=PER_MUNI_TIMEOUT_S
        )
    except Exception as exc:  # noqa: BLE001
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=muni.map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.5,
            error=f"pdfplumber parse failed: {exc}",
        )

    if line_count > VECTOR_LINE_THRESHOLD:
        cls = "vector"
        conf = 0.95
    else:
        cls = "raster"
        conf = 0.8
    return ClassificationRecord(
        muni_code=muni.muni_code,
        muni_name=muni.muni_name,
        cls=cls,
        map_url=muni.map_url,
        ordinance_url=muni.ordinance_url,
        confidence=conf,
        error=None if cls else f"line_count={line_count}",
    )


async def classify_county(
    county: str,
    *,
    max_parallel: int = 8,
    data_dir: Path = DATA_DIR,
    artifact_root: Path = ARTIFACT_ROOT,
    force: bool = False,
) -> list[dict]:
    rows = load_county_directory(county, data_dir=data_dir)
    output_path = classification_output_path(county, root=artifact_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prior: dict[str, dict] = {}
    if output_path.exists() and not force:
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            for r in existing:
                key = r.get("muni_code") or r.get("muni_name")
                if key:
                    prior[str(key).lower()] = r
        except json.JSONDecodeError:
            LOGGER.warning("malformed prior classification at %s; re-classifying", output_path)

    semaphore = asyncio.Semaphore(max_parallel)

    async def _do(muni: MuniRecord) -> dict:
        key = (muni.muni_code or muni.muni_name).lower()
        if key in prior:
            return prior[key]
        async with semaphore:
            t0 = time.time()
            try:
                rec = await asyncio.wait_for(classify_one(muni), timeout=PER_MUNI_TIMEOUT_S)
            except asyncio.TimeoutError:
                rec = ClassificationRecord(
                    muni_code=muni.muni_code,
                    muni_name=muni.muni_name,
                    cls="absent",
                    map_url=muni.map_url,
                    ordinance_url=muni.ordinance_url,
                    confidence=0.0,
                    error=f"timeout > {PER_MUNI_TIMEOUT_S}s",
                )
            LOGGER.info(
                "classified %s -> %s (%.2fs)", muni.muni_name, rec.cls, time.time() - t0,
            )
            return rec.to_dict()

    results = await asyncio.gather(*[_do(m) for m in rows])
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--county", required=True)
    ap.add_argument("--max-parallel", type=int, default=8)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--log-level", default=os.environ.get("OP5_LOG_LEVEL", "INFO"))
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        results = asyncio.run(classify_county(
            args.county,
            max_parallel=args.max_parallel,
            data_dir=args.data_dir,
            artifact_root=args.artifact_root,
            force=args.force,
        ))
    except (FileNotFoundError, KeyError) as exc:
        LOGGER.error("classification failed: %s", exc)
        return 2
    summary = {"vector": 0, "raster": 0, "absent": 0, "text_only_legend": 0}
    for r in results:
        summary[r.get("class", "absent")] = summary.get(r.get("class", "absent"), 0) + 1
    LOGGER.info(
        "%s totals: vector=%d raster=%d absent=%d",
        args.county, summary.get("vector", 0), summary.get("raster", 0), summary.get("absent", 0),
    )
    print(json.dumps({"county": args.county, "totals": summary, "n": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
