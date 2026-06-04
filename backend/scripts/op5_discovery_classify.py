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

try:
    from op5_lib.arcgis_lookup import (  # noqa: E402
        ArcgisSource,
        lookup_arcgis_source,
        probe_feature_server,
    )
except Exception:  # noqa: BLE001 — tests should still import this module
    ArcgisSource = None  # type: ignore[assignment]
    lookup_arcgis_source = None  # type: ignore[assignment]
    probe_feature_server = None  # type: ignore[assignment]

LOGGER = logging.getLogger("op5_discovery_classify")

PER_MUNI_TIMEOUT_S = 60.0
VECTOR_LINE_THRESHOLD = 50  # pdfplumber.pages[0].lines len > 50 -> vector

# Website discovery (CP-Pre Finding 3 / C1): when a directory row lacks
# `map_url`, we scan the muni website for a likely zoning-map link before
# falling back to ``absent``.
DISCOVERY_TIMEOUT_S = 30.0          # total wall-clock budget per muni
DISCOVERY_FETCH_TIMEOUT_S = 12.0    # per-HTTP-request timeout
# Use a real browser UA — several muni CMSes (Maplewood etc.) return
# HTTP 403 to unfamiliar bots.
DISCOVERY_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DISCOVERY_HIGH_CONFIDENCE = 0.7     # >= triggers immediate return

# Generic paths to try if the homepage offers no candidate. CivicPlus
# (DocumentCenter), Granicus, eCode360 are the common NJ muni CMSes.
COMMON_PROBE_PATHS = [
    "/zoning", "/planning",
    "/government/departments/planning",
    "/government/departments/planning-zoning",
    "/government/departments/zoning",
    "/departments/planning",
    "/departments/planning-zoning",
    "/departments/zoning",
    "/Planning", "/Zoning",
    "/sitemap", "/site-map", "/maps",
]

# Reject any candidate href matching these patterns — they are calendar,
# events, news, alerts, board agendas, NOT zoning maps.
_REJECT_HREF_RE = re.compile(
    r"(Calendar\.aspx|CivicAlerts|NewsFlash|AgendaCenter|/news/|/events?/|/m/newsflash)",
    re.I,
)

# Score table — matches highest-priority pattern wins.
_MAP_EXT_RE = re.compile(r"\.(pdf|jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_PDF_EXT_RE = re.compile(r"\.pdf(?:[?#]|$)", re.I)
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_ZONING_MAP_RE = re.compile(r"zoning[\s_-]*map|zoning%20map", re.I)
_ZONING_RE = re.compile(r"\bzoning\b", re.I)
_MASTER_PLAN_RE = re.compile(r"master[\s_-]*plan", re.I)
_PLANNING_RE = re.compile(r"\b(planning|planning[\s_-]board)\b", re.I)

# Reject obvious non-map PDFs even when they contain "zoning"
# (applications, checklists, ordinances-as-text, faqs, fees, letters,
#  meeting cancellations, board bulletins, hours/contacts).
_NON_MAP_KEYWORDS = (
    "application", "checklist", "worksheet", "calc", "ordinance",
    "faq", "fee schedule", "permit application", "report", "minutes",
    "agenda", "notice", "newsletter", "letter", "cancellation",
    "bulletin", "meeting", "hours", "contact", "board ", "_meeting",
    "schedule", "appeal", "variance", "submission", "instruction",
    "guide", "info ", "information",
)


@dataclass
class ClassificationRecord:
    muni_code: str
    muni_name: str
    cls: str               # vector|raster|absent|arcgis_verified|arcgis_candidate|njsea
    map_url: Optional[str]
    ordinance_url: Optional[str]
    confidence: float
    error: Optional[str]
    map_url_source: str = "directory"  # directory | website_discovery | arcgis | none
    feature_server_url: Optional[str] = None
    where_clause: Optional[str] = None
    source_label: Optional[str] = None
    tenant_host: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("cls")
        return d


# ── map_url discovery from website (CP-Pre Finding 3 / C1) ────────────────


def _score_candidate(href: str, text: str) -> float:
    """Score a candidate link 0..1.0 for being a zoning map.

    Scoring rules (per CP-Pre Finding 3/C1 spec, conservatively tuned
    to reject obvious non-map PDFs):
      * Reject calendar/news/event/agenda hrefs outright.
      * Reject PDFs matching application/checklist/ordinance/meeting/etc.
      * PDF whose href/text contains "zoning map" -> 1.0
      * Image whose href/text contains "zoning map" -> 0.85
      * PDF whose href/text contains "zoning" AND "map" -> 0.75
      * Image whose href/text contains "zoning" AND "map" -> 0.65
      * Master plan PDF with "map" -> 0.5
      * Bare /zoning HTML page -> 0.3
      * Planning page -> 0.3
    """
    if _REJECT_HREF_RE.search(href):
        return 0.0
    haystack = f"{href} {text}".lower()
    if any(k in haystack for k in _NON_MAP_KEYWORDS):
        return 0.0
    is_pdf = bool(_PDF_EXT_RE.search(href))
    is_img = bool(_IMG_EXT_RE.search(href))

    if _ZONING_MAP_RE.search(haystack):
        if is_pdf:
            return 1.0
        if is_img:
            return 0.85
        return 0.5
    if _ZONING_RE.search(haystack) and "map" in haystack:
        if is_pdf:
            return 0.75
        if is_img:
            return 0.65
        return 0.35
    if _ZONING_RE.search(haystack):
        # Bare "zoning" hit — mid-low priority follow only.
        return 0.3
    if _MASTER_PLAN_RE.search(haystack) and "map" in haystack:
        if is_pdf:
            return 0.5
        if is_img:
            return 0.4
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

    visited: set[str] = set()
    best_so_far: list = [0.0, ""]  # mutable [score, href]

    async def _scan_page(client, page_url: str) -> Optional[str]:
        """Return a >=0.7 hit or None; record best mid-confidence in best_so_far."""
        if page_url in visited:
            return None
        visited.add(page_url)
        html = await asyncio.wait_for(
            _fetch(client, page_url),
            timeout=min(DISCOVERY_FETCH_TIMEOUT_S, max(1.0, time_left())),
        )
        if not html:
            return None
        links = _extract_links_bs4(html, page_url)
        scored = [(score, href, text) for (href, text) in links
                  if (score := _score_candidate(href, text)) > 0.0]
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, href, _ in scored:
            if score >= DISCOVERY_HIGH_CONFIDENCE:
                return href
            if score > best_so_far[0]:
                best_so_far[0] = score
                best_so_far[1] = href
        return None

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=DISCOVERY_FETCH_TIMEOUT_S,
        ) as client:
            # 1. Scan homepage.
            hit = await _scan_page(client, website_url)
            if hit:
                return hit

            # 2. If homepage had no direct hit, try a small set of common
            #    deep paths (planning / zoning pages) on the same origin.
            #    Also follow the highest-scoring mid-confidence link from
            #    the homepage one level deeper.
            parsed = urlparse(website_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            probe_urls = [urljoin(origin + "/", p.lstrip("/")) for p in COMMON_PROBE_PATHS]
            if best_so_far[1] and not _MAP_EXT_RE.search(best_so_far[1]):
                probe_urls.insert(0, best_so_far[1])

            for url in probe_urls:
                if time_left() <= 2.0:
                    break
                if url in visited:
                    continue
                hit = await _scan_page(client, url)
                if hit:
                    return hit

            # 3. Try sitemap.xml — many CivicPlus / Granicus sites expose
            #    every PDF in the document center via the sitemap.
            if time_left() > 3.0:
                sitemap_url = urljoin(origin + "/", "sitemap.xml")
                if sitemap_url not in visited:
                    try:
                        r = await asyncio.wait_for(
                            client.get(sitemap_url, headers={"User-Agent": DISCOVERY_USER_AGENT}),
                            timeout=min(DISCOVERY_FETCH_TIMEOUT_S, max(1.0, time_left())),
                        )
                        if r.status_code < 400 and r.text:
                            visited.add(sitemap_url)
                            url_pattern = re.compile(r'https?://[^\s<>"\'`]+', re.I)
                            for u in url_pattern.findall(r.text):
                                u_low = u.lower()
                                if "zoning" in u_low and "map" in u_low and _MAP_EXT_RE.search(u):
                                    return u
                    except Exception:  # noqa: BLE001
                        pass

            # 4. Accept the strongest mid-confidence PDF/image hit if any.
            if best_so_far[0] >= 0.5 and _MAP_EXT_RE.search(best_so_far[1]):
                return best_so_far[1]
            return None
    except asyncio.TimeoutError:
        LOGGER.info("discovery timed out for %s (%s)", muni_name, website_url)
        if best_so_far[0] >= 0.5 and _MAP_EXT_RE.search(best_so_far[1]):
            return best_so_far[1]
        return None
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("discovery error for %s: %s", muni_name, exc)
        return None


def classification_output_path(county: str, root: Path = ARTIFACT_ROOT) -> Path:
    return root / f"{county.strip().lower()}_classification.json"


def _is_image_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"))


async def _probe_feature_server_async(
    feature_server_url: str, where_clause: Optional[str],
) -> bool:
    """Run the (sync) probe_feature_server in a thread so we don't block."""
    if probe_feature_server is None:
        return False
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: probe_feature_server(feature_server_url, where_clause),
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug(
            "feature-server probe error %s (%s): %s",
            feature_server_url, where_clause, exc,
        )
        return False


async def classify_one(muni: MuniRecord) -> ClassificationRecord:
    """Single-muni probe + classify. Never raises — failure -> absent.

    Order:
      1. ArcGIS lookup (verified tenant -> candidate tenant -> NJSEA). If a
         FeatureServer is found AND a returnCountOnly probe returns >0,
         classify as ``arcgis_<confidence>`` (or ``njsea``) and skip the
         PDF/vision path entirely. This is the master-identified critical
         path for Westwood + the 10 NJSEA Meadowlands towns + Paramus etc.
      2. Existing PDF path (vector / raster / absent).
    """
    # ── ArcGIS-first branch (CP-Pre Finding 5) ──────────────────────────
    if lookup_arcgis_source is not None:
        try:
            arc = lookup_arcgis_source(muni.muni_name, "NJ")
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("arcgis_lookup raised for %s: %s", muni.muni_name, exc)
            arc = None
        if arc is not None:
            alive = await _probe_feature_server_async(
                arc.feature_server_url, arc.where_clause,
            )
            if alive:
                cls_label = "njsea" if arc.confidence == "njsea" else f"arcgis_{arc.confidence}"
                return ClassificationRecord(
                    muni_code=muni.muni_code,
                    muni_name=muni.muni_name,
                    cls=cls_label,
                    map_url=arc.feature_server_url,
                    ordinance_url=muni.ordinance_url,
                    confidence=0.95 if arc.confidence == "verified" else 0.85,
                    error=None,
                    map_url_source="arcgis",
                    feature_server_url=arc.feature_server_url,
                    where_clause=arc.where_clause,
                    source_label=arc.source_label,
                    tenant_host=arc.tenant_host,
                )
            LOGGER.info(
                "arcgis lookup hit %s (%s) but probe returned 0; falling through to PDF",
                muni.muni_name, arc.source_label,
            )

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
    summary = {
        "vector": 0, "raster": 0, "absent": 0, "text_only_legend": 0,
        "arcgis_verified": 0, "arcgis_candidate": 0, "njsea": 0,
    }
    for r in results:
        summary[r.get("class", "absent")] = summary.get(r.get("class", "absent"), 0) + 1
    LOGGER.info(
        "%s totals: vector=%d raster=%d absent=%d arcgis_verified=%d arcgis_candidate=%d njsea=%d",
        args.county,
        summary.get("vector", 0), summary.get("raster", 0), summary.get("absent", 0),
        summary.get("arcgis_verified", 0), summary.get("arcgis_candidate", 0),
        summary.get("njsea", 0),
    )
    print(json.dumps({"county": args.county, "totals": summary, "n": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
