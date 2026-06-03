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
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from op5_per_muni_runner import (  # noqa: E402  (sibling script import)
    ARTIFACT_ROOT,
    DATA_DIR,
    MuniRecord,
    load_county_directory,
)

LOGGER = logging.getLogger("op5_discovery_classify")

PER_MUNI_TIMEOUT_S = 60.0
VECTOR_LINE_THRESHOLD = 50  # pdfplumber.pages[0].lines len > 50 -> vector

# Website discovery (CP-Pre Finding 3 / C1): when a directory row lacks
# `map_url`, we scan the muni website for a likely zoning-map link before
# falling back to ``absent``.
DISCOVERY_TIMEOUT_S = 30.0          # total wall-clock budget per muni
DISCOVERY_FETCH_TIMEOUT_S = 12.0    # per-HTTP-request timeout
DISCOVERY_USER_AGENT = "ParcelLogic/1.0 Op5MapURLDiscovery"
DISCOVERY_HIGH_CONFIDENCE = 0.7     # >= triggers immediate return

# Score table — matches highest-priority pattern wins.
# Each entry: (regex against href+text lowercased, file ext class, score).
_MAP_EXT_RE = re.compile(r"\.(pdf|jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_PDF_EXT_RE = re.compile(r"\.pdf(?:[?#]|$)", re.I)
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_ZONING_MAP_RE = re.compile(r"zoning[\s_-]*map|zoning%20map", re.I)
_ZONING_RE = re.compile(r"\bzoning\b", re.I)
_MASTER_PLAN_RE = re.compile(r"master[\s_-]*plan", re.I)
_PLANNING_RE = re.compile(r"\b(planning|planning[\s_-]board)\b", re.I)


@dataclass
class ClassificationRecord:
    muni_code: str
    muni_name: str
    cls: str               # vector|raster|absent  (text_only_legend deferred)
    map_url: Optional[str]
    ordinance_url: Optional[str]
    confidence: float
    error: Optional[str]
    map_url_source: str = "directory"  # directory | website_discovery | none

    def to_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("cls")
        return d


# ── map_url discovery from website (CP-Pre Finding 3 / C1) ────────────────


def _score_candidate(href: str, text: str) -> float:
    """Score a candidate link 0..1.0 for being a zoning map.

    Scoring rules (per CP-Pre Finding 3/C1 spec):
      * PDF link whose href contains "zoning map" -> 1.0
      * PDF link whose href/text contains "zoning" -> 0.7
      * Image link (jpg/png/etc.) whose href/text contains "zoning" -> 0.6
      * Master plan PDF -> 0.5
      * /planning directory HTML link -> 0.3
    """
    haystack = f"{href} {text}".lower()
    is_pdf = bool(_PDF_EXT_RE.search(href))
    is_img = bool(_IMG_EXT_RE.search(href))

    if _ZONING_MAP_RE.search(haystack):
        if is_pdf:
            return 1.0
        if is_img:
            return 0.85
        # HTML link that itself names "zoning map" — still worth following
        return 0.5
    if _ZONING_RE.search(haystack):
        if is_pdf:
            return 0.7
        if is_img:
            return 0.6
        # bare /zoning HTML page -> mid-low priority follow
        return 0.3
    if _MASTER_PLAN_RE.search(haystack):
        if is_pdf:
            return 0.5
        return 0.2
    if _PLANNING_RE.search(haystack):
        return 0.3
    return 0.0


def _extract_links_bs4(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return list of (absolute_href, link_text) tuples."""
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        return _extract_links_regex(html, base_url)
    out: list[tuple[str, str]] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:  # noqa: BLE001
        return _extract_links_regex(html, base_url)
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        abs_href = urljoin(base_url, href)
        out.append((abs_href, text))
    return out


_HREF_RE = re.compile(
    r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _extract_links_regex(html: str, base_url: str) -> list[tuple[str, str]]:
    """Fallback link extractor when bs4 is missing."""
    out: list[tuple[str, str]] = []
    for m in _HREF_RE.finditer(html):
        href = m.group(1) or ""
        text = _TAG_STRIP_RE.sub(" ", m.group(2) or "")
        text = " ".join(text.split())
        if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        out.append((urljoin(base_url, href), text))
    return out


async def _fetch(client, url: str) -> Optional[str]:
    """GET a URL and return text if response looks like HTML."""
    try:
        r = await client.get(
            url,
            headers={"User-Agent": DISCOVERY_USER_AGENT, "Accept": "text/html,*/*;q=0.5"},
            timeout=DISCOVERY_FETCH_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("discovery fetch failed for %s: %s", url, exc)
        return None
    if r.status_code >= 400:
        LOGGER.debug("discovery fetch %s -> HTTP %d", url, r.status_code)
        return None
    ctype = r.headers.get("content-type", "").lower()
    if ctype and "html" not in ctype and "xml" not in ctype and "text" not in ctype:
        return None
    try:
        return r.text
    except Exception:  # noqa: BLE001
        return None


async def discover_map_url_from_website(
    website_url: Optional[str],
    muni_name: str,
    *,
    total_budget_s: float = DISCOVERY_TIMEOUT_S,
) -> Optional[str]:
    """Discover a zoning-map URL from a muni website.

    Strategy:
      1. Fetch homepage, score every <a> link.
      2. If a >= 0.7 candidate exists, return its absolute URL.
      3. Otherwise, follow the highest-scoring candidate (likely a
         `/planning` or `/zoning` HTML page) ONE level deeper and re-scan.
      4. Total wall-clock cap = ``total_budget_s`` (default 30s).

    Pure httpx + bs4 (regex fallback). No Playwright per CP-Pre Finding 3.
    """
    if not website_url:
        return None
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("httpx missing — cannot discover map_url for %s: %s", muni_name, exc)
        return None

    started = time.time()

    def time_left() -> float:
        return total_budget_s - (time.time() - started)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=DISCOVERY_FETCH_TIMEOUT_S,
        ) as client:
            html = await asyncio.wait_for(
                _fetch(client, website_url),
                timeout=min(DISCOVERY_FETCH_TIMEOUT_S, max(1.0, time_left())),
            )
            if not html:
                return None

            links = _extract_links_bs4(html, website_url)
            scored = [(score, href, text) for (href, text) in links if (score := _score_candidate(href, text)) > 0.0]
            scored.sort(key=lambda t: t[0], reverse=True)
            if not scored:
                return None

            top_score, top_href, _ = scored[0]
            if top_score >= DISCOVERY_HIGH_CONFIDENCE:
                return top_href

            # Mid-confidence: follow the top candidate one level deeper IF
            # it's HTML (not a direct PDF — those we'd have already kept).
            if time_left() <= 1.0:
                return None
            if _MAP_EXT_RE.search(top_href):
                # It's a PDF/img link, just below threshold — accept it.
                return top_href

            html2 = await asyncio.wait_for(
                _fetch(client, top_href),
                timeout=min(DISCOVERY_FETCH_TIMEOUT_S, max(1.0, time_left())),
            )
            if not html2:
                return None
            links2 = _extract_links_bs4(html2, top_href)
            scored2 = [(score, href, text) for (href, text) in links2 if (score := _score_candidate(href, text)) > 0.0]
            scored2.sort(key=lambda t: t[0], reverse=True)
            if scored2 and scored2[0][0] >= DISCOVERY_HIGH_CONFIDENCE:
                return scored2[0][1]
            # If a moderate PDF/img sits on the second page, accept it.
            if scored2 and _MAP_EXT_RE.search(scored2[0][1]) and scored2[0][0] >= 0.5:
                return scored2[0][1]
            return None
    except asyncio.TimeoutError:
        LOGGER.info("discovery timed out for %s (%s)", muni_name, website_url)
        return None
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("discovery error for %s: %s", muni_name, exc)
        return None


def classification_output_path(county: str, root: Path = ARTIFACT_ROOT) -> Path:
    return root / f"{county.strip().lower()}_classification.json"


def _is_image_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"))


async def classify_one(muni: MuniRecord) -> ClassificationRecord:
    """Single-muni probe + classify. Never raises — failure -> absent."""
    map_url = muni.map_url
    map_url_source = "directory" if map_url else "none"

    # Fallback: if the directory row has no map_url, try discovering one
    # from the muni website (CP-Pre Finding 3 / C1).
    if not map_url and muni.website_url:
        discovered = await discover_map_url_from_website(
            muni.website_url, muni.muni_name,
        )
        if discovered:
            map_url = discovered
            map_url_source = "website_discovery"
            LOGGER.info(
                "discovered map_url for %s from website: %s",
                muni.muni_name, discovered,
            )

    if not map_url:
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=None,
            ordinance_url=muni.ordinance_url,
            confidence=1.0,
            error="no map_url in directory and none discovered from website",
            map_url_source="none",
        )

    if _is_image_path(map_url):
        # Don't bother downloading bytes to confirm — file extension is
        # adequate signal. The runner re-validates on the heavy path.
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="raster",
            map_url=map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.85,
            error=None,
            map_url_source=map_url_source,
        )

    try:
        import httpx
        import pdfplumber
    except Exception as exc:  # noqa: BLE001
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.0,
            error=f"missing classify dependency: {exc}",
            map_url_source=map_url_source,
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=PER_MUNI_TIMEOUT_S,
        ) as client:
            r = await client.get(
                map_url,
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
            map_url=map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.9,
            error=f"download failed: {exc}",
            map_url_source=map_url_source,
        )

    if "pdf" not in ctype and not payload[:4].startswith(b"%PDF"):
        # Not a PDF -> classify by content-type / URL signal.
        if "image" in ctype or _is_image_path(map_url):
            return ClassificationRecord(
                muni_code=muni.muni_code,
                muni_name=muni.muni_name,
                cls="raster",
                map_url=map_url,
                ordinance_url=muni.ordinance_url,
                confidence=0.85,
                error=None,
                map_url_source=map_url_source,
            )
        return ClassificationRecord(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            cls="absent",
            map_url=map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.6,
            error=f"unexpected content-type: {ctype!r}",
            map_url_source=map_url_source,
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
            map_url=map_url,
            ordinance_url=muni.ordinance_url,
            confidence=0.5,
            error=f"pdfplumber parse failed: {exc}",
            map_url_source=map_url_source,
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
        map_url=map_url,
        ordinance_url=muni.ordinance_url,
        confidence=conf,
        error=None if cls else f"line_count={line_count}",
        map_url_source=map_url_source,
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
                    map_url_source="directory" if muni.map_url else "none",
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
