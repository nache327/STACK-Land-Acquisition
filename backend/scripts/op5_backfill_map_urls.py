"""Op-5 map_url backfill — Pre-build C compliance (CP-Pre Finding 3 / C1).

For each county directory JSON (essex/middlesex_nj/monmouth/burlington),
for every muni with `map_url == null`, attempt to discover a zoning-map
URL from `website_url` via lightweight HTTP scanning, then write the
discovered URL back into the JSON in place (preserving key order).

Per-muni budget: 30s wall clock. Polite rate limiting: 1-2 req/sec
per origin domain.

Usage:

    python backend/scripts/op5_backfill_map_urls.py            # all 4 counties
    python backend/scripts/op5_backfill_map_urls.py --county essex
    python backend/scripts/op5_backfill_map_urls.py --dry-run  # don't write

Why this script lives next to `op5_discovery_classify.py`:
PR #179 originally shipped 0/140 map_url populated; Phase 0 discovery
would otherwise classify every new-county muni as `absent`. This backfill
runs the same discovery logic ahead of factory launch so the directory
JSONs hold the canonical `map_url` value where one can be found.

Discovery logic is vendored inline so this script is runnable from any
branch (PR #178 ships the canonical copy in `op5_discovery_classify.py`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

LOGGER = logging.getLogger("op5_backfill_map_urls")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"
DEFAULT_COUNTIES = ["essex", "middlesex_nj", "monmouth", "burlington"]

# Discovery params — must match op5_discovery_classify.py
DISCOVERY_TIMEOUT_S = 30.0
DISCOVERY_FETCH_TIMEOUT_S = 12.0
# Use a real browser UA — several muni CMSes (Maplewood, ParkRidge, etc.)
# return HTTP 403 to unfamiliar bots.
DISCOVERY_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DISCOVERY_HIGH_CONFIDENCE = 0.7

# Generic paths to try if the homepage offers no candidate. CivicPlus
# (DocumentCenter), Granicus, eCode360 are the common NJ muni CMSes.
COMMON_PROBE_PATHS = [
    "/zoning",
    "/planning",
    "/government/departments/planning",
    "/government/departments/planning-zoning",
    "/government/departments/zoning",
    "/departments/planning",
    "/departments/planning-zoning",
    "/departments/zoning",
    "/Planning",
    "/Zoning",
    "/sitemap",
    "/site-map",
    "/maps",
]

# Reject any candidate href matching these patterns — they are calendar,
# events, news, alerts, board agendas, NOT zoning maps.
_REJECT_HREF_RE = re.compile(
    r"(Calendar\.aspx|CivicAlerts|NewsFlash|AgendaCenter|/news/|/events?/|/m/newsflash)",
    re.I,
)

_MAP_EXT_RE = re.compile(r"\.(pdf|jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_PDF_EXT_RE = re.compile(r"\.pdf(?:[?#]|$)", re.I)
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|tif|tiff)(?:[?#]|$)", re.I)
_ZONING_MAP_RE = re.compile(r"zoning[\s_-]*map|zoning%20map", re.I)
_ZONING_RE = re.compile(r"\bzoning\b", re.I)
_MASTER_PLAN_RE = re.compile(r"master[\s_-]*plan", re.I)
_PLANNING_RE = re.compile(r"\b(planning|planning[\s_-]board)\b", re.I)
_HREF_RE = re.compile(
    r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _score_candidate(href: str, text: str) -> float:
    # Reject calendar/news/event pages outright — these masquerade as
    # "zoning" or "planning" hits because the agenda mentions the boards.
    if _REJECT_HREF_RE.search(href):
        return 0.0
    haystack = f"{href} {text}".lower()
    is_pdf = bool(_PDF_EXT_RE.search(href))
    is_img = bool(_IMG_EXT_RE.search(href))

    # Reject obvious non-map PDFs even when they contain "zoning"
    # (applications, checklists, ordinances-as-text, faqs, fees, letters,
    #  meeting cancellations, board bulletins, hours/contacts).
    NON_MAP_KEYWORDS = (
        "application", "checklist", "worksheet", "calc", "ordinance",
        "faq", "fee schedule", "permit application", "report", "minutes",
        "agenda", "notice", "newsletter", "letter", "cancellation",
        "bulletin", "meeting", "hours", "contact", "board ", "_meeting",
        "schedule", "appeal", "variance", "submission", "instruction",
        "guide", "info ", "information",
    )
    if any(k in haystack for k in NON_MAP_KEYWORDS):
        return 0.0

    if _ZONING_MAP_RE.search(haystack):
        if is_pdf:
            return 1.0
        if is_img:
            return 0.85
        return 0.5
    # Plain "zoning" only counts as a high-confidence map hit if the link
    # text/href ALSO contains "map" — otherwise it's likely an ordinance,
    # an application form, or a permit doc, not a zoning map.
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


def _extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
            text = " ".join(a.get_text(" ", strip=True).split())
            out.append((urljoin(base_url, href), text))
        return out
    except Exception:  # noqa: BLE001
        # Regex fallback
        out = []
        for m in _HREF_RE.finditer(html):
            href = (m.group(1) or "").strip()
            text = _TAG_STRIP_RE.sub(" ", m.group(2) or "")
            text = " ".join(text.split())
            if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
            out.append((urljoin(base_url, href), text))
        return out


async def _fetch(client, url: str) -> Optional[str]:
    try:
        r = await client.get(
            url,
            headers={"User-Agent": DISCOVERY_USER_AGENT, "Accept": "text/html,*/*;q=0.5"},
            timeout=DISCOVERY_FETCH_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("fetch failed %s: %s", url, exc)
        return None
    if r.status_code >= 400:
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
    if not website_url:
        return None
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("httpx missing: %s", exc)
        return None

    started = time.time()

    def time_left() -> float:
        return total_budget_s - (time.time() - started)

    visited: set[str] = set()
    best_so_far: tuple[float, str] = (0.0, "")

    async def _scan_page(client, page_url: str) -> Optional[str]:
        """Return a >=0.7 hit or None; record best mid-confidence in best_so_far."""
        nonlocal best_so_far
        if page_url in visited:
            return None
        visited.add(page_url)
        html = await asyncio.wait_for(
            _fetch(client, page_url),
            timeout=min(DISCOVERY_FETCH_TIMEOUT_S, max(1.0, time_left())),
        )
        if not html:
            return None
        links = _extract_links(html, page_url)
        scored = [(score, href, text) for (href, text) in links
                  if (score := _score_candidate(href, text)) > 0.0]
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, href, _ in scored:
            if score >= DISCOVERY_HIGH_CONFIDENCE:
                return href
            if score > best_so_far[0]:
                best_so_far = (score, href)
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
            # If the best mid-confidence link from homepage is HTML, follow
            # it before the generic probes.
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
            #    every PDF in the document center via the sitemap. Look
            #    for "*zoning*map*" patterns by direct URL substring.
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
                            # Find URL patterns in sitemap text — works for
                            # both <loc> XML and plain text.
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
        LOGGER.info("discovery timeout for %s (%s)", muni_name, website_url)
        # If we found ANY mid-confidence PDF/image before timing out, ship it.
        if best_so_far[0] >= 0.5 and _MAP_EXT_RE.search(best_so_far[1]):
            return best_so_far[1]
        return None
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("discovery error for %s: %s", muni_name, exc)
        return None


# ── per-origin rate limiter (1-2 req/sec) ─────────────────────────────────


class _PerOriginGate:
    def __init__(self, min_interval_s: float = 0.6):
        self.min_interval_s = min_interval_s
        self.last: dict[str, float] = {}
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, url: str) -> None:
        origin = urlparse(url).netloc.lower()
        async with self.locks[origin]:
            now = time.time()
            wait = self.last.get(origin, 0.0) + self.min_interval_s - now
            if wait > 0:
                await asyncio.sleep(wait)
            self.last[origin] = time.time()


# ── backfill driver ────────────────────────────────────────────────────────


async def backfill_county(
    county: str,
    *,
    data_dir: Path = DATA_DIR,
    dry_run: bool = False,
    max_parallel: int = 6,
) -> dict:
    """Backfill map_url in {county}_zoning_directory.json. Returns summary dict."""
    path = data_dir / f"{county}_zoning_directory.json"
    rows = json.loads(path.read_text(encoding="utf-8"))

    total = len(rows)
    needs = [r for r in rows if not r.get("map_url") and r.get("website_url")]
    LOGGER.info("[%s] %d/%d munis need map_url discovery", county, len(needs), total)

    gate = _PerOriginGate(min_interval_s=0.6)
    sem = asyncio.Semaphore(max_parallel)
    discovered_count = 0
    started = time.time()

    async def _do(row: dict) -> None:
        nonlocal discovered_count
        async with sem:
            await gate.wait(row["website_url"])
            t0 = time.time()
            url = await discover_map_url_from_website(
                row["website_url"], row.get("muni_name") or row.get("muni_code", ""),
            )
            dt = time.time() - t0
            if url:
                row["map_url"] = url
                discovered_count += 1
                LOGGER.info(
                    "[%s] DISCOVERED %s -> %s (%.1fs)",
                    county, row.get("muni_name"), url, dt,
                )
            else:
                LOGGER.info(
                    "[%s] no map for %s (%.1fs)",
                    county, row.get("muni_name"), dt,
                )

    await asyncio.gather(*[_do(r) for r in needs])
    elapsed = time.time() - started

    if not dry_run:
        path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    return {
        "county": county,
        "total_munis": total,
        "needed_discovery": len(needs),
        "discovered": discovered_count,
        "elapsed_s": round(elapsed, 1),
        "dry_run": dry_run,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--county", action="append", help="restrict to a county (repeatable); default: all 4")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-parallel", type=int, default=6)
    ap.add_argument("--log-level", default="INFO")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    counties = args.county or DEFAULT_COUNTIES
    all_summaries = []
    for c in counties:
        s = asyncio.run(backfill_county(
            c,
            data_dir=args.data_dir,
            dry_run=args.dry_run,
            max_parallel=args.max_parallel,
        ))
        all_summaries.append(s)
        print(json.dumps(s, indent=2))
    print("\n=== ALL COUNTIES ===")
    grand_total = sum(s["total_munis"] for s in all_summaries)
    grand_discovered = sum(s["discovered"] for s in all_summaries)
    grand_needed = sum(s["needed_discovery"] for s in all_summaries)
    grand_elapsed = sum(s["elapsed_s"] for s in all_summaries)
    print(json.dumps({
        "counties": [s["county"] for s in all_summaries],
        "total_munis": grand_total,
        "needed_discovery": grand_needed,
        "discovered": grand_discovered,
        "discovery_rate_pct": round(100.0 * grand_discovered / grand_needed, 1) if grand_needed else 0.0,
        "elapsed_s": round(grand_elapsed, 1),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
