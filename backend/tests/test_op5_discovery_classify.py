"""Tests for op5_discovery_classify map_url discovery (CP-Pre Finding 3 / C1)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from op5_discovery_classify import (  # type: ignore  # noqa: E402
    _score_candidate,
    _extract_links_bs4,
    _extract_links_regex,
    discover_map_url_from_website,
)


# ── Pure-function scoring tests ───────────────────────────────────────────


def test_score_pdf_zoning_map_is_top_priority():
    s = _score_candidate("https://x.gov/files/zoning_map_2024.pdf", "Zoning Map (PDF)")
    assert s == 1.0


def test_score_pdf_zoning_map_with_extra_qualifier():
    # "Township Zoning Map" -> 1.0 (contains "zoning map" phrase)
    s = _score_candidate("https://x.gov/Township_Zoning_Map.pdf", "Township Zoning Map")
    assert s == 1.0


def test_score_zoning_pdf_with_map_in_text():
    # href has "zoning" + text has "Map" -> 0.75
    s = _score_candidate("https://x.gov/zoning_2024.pdf", "Zoning Districts Map")
    assert s == 0.75


def test_score_zoning_ordinance_pdf_is_rejected():
    # "ordinance" is a NON_MAP_KEYWORD -> reject
    s = _score_candidate("https://x.gov/zoning_ordinance.pdf", "Zoning Ordinance")
    assert s == 0.0


def test_score_zoning_application_pdf_is_rejected():
    # "application" rejection guards against false positives like Verona
    s = _score_candidate(
        "https://x.gov/Residential_Zoning_Application_Checklist.pdf",
        "Residential Zoning Application",
    )
    assert s == 0.0


def test_score_image_zoning_map():
    s = _score_candidate("https://x.gov/maps/zoning_map.jpg", "Zoning Map")
    assert s == 0.85


def test_score_planning_html_is_low():
    s = _score_candidate("https://x.gov/departments/planning", "Planning Board")
    # planning HTML -> 0.3
    assert 0.0 < s <= 0.3


def test_score_unrelated_link_is_zero():
    assert _score_candidate("https://x.gov/news", "Latest News") == 0.0


def test_score_calendar_event_link_is_rejected():
    # CivicPlus Calendar.aspx is a hard reject even with "Planning Board" text
    s = _score_candidate(
        "https://muni.gov/Calendar.aspx?EID=42",
        "Planning Board Regular Meeting",
    )
    assert s == 0.0


def test_score_master_plan_pdf():
    # Master Plan PDF with "map" but without "zoning" word -> 0.5
    s = _score_candidate("https://x.gov/master_plan_land_use_map_2018.pdf", "Master Plan Map")
    assert s == 0.5


# ── Link extraction tests ────────────────────────────────────────────────


HOMEPAGE_WITH_DIRECT_LINK = """
<html><body>
<nav><a href="/about">About</a></nav>
<main>
  <h2>Departments</h2>
  <ul>
    <li><a href="/files/zoning_map_2024.pdf">Zoning Map (PDF)</a></li>
    <li><a href="/planning">Planning Board</a></li>
    <li><a href="/news">News</a></li>
  </ul>
</main>
</body></html>
"""

HOMEPAGE_WITH_INTERMEDIATE_LINK = """
<html><body>
<nav><a href="/about">About</a></nav>
<main>
  <ul>
    <li><a href="/planning">Planning Department</a></li>
    <li><a href="/contact">Contact</a></li>
  </ul>
</main>
</body></html>
"""

PLANNING_PAGE_WITH_MAP = """
<html><body>
<h1>Planning Department</h1>
<p>Find our zoning resources below:</p>
<ul>
  <li><a href="/assets/maps/township_zoning_map.pdf">Township Zoning Map</a></li>
  <li><a href="/assets/master_plan.pdf">Master Plan 2020</a></li>
</ul>
</body></html>
"""

EMPTY_HOMEPAGE = """
<html><body>
<h1>Welcome</h1>
<p>No links of interest.</p>
<a href="/news">News</a>
<a href="/contact">Contact</a>
</body></html>
"""


def test_extract_links_bs4_resolves_relative():
    links = _extract_links_bs4(HOMEPAGE_WITH_DIRECT_LINK, "https://muni.gov/")
    hrefs = [h for (h, _) in links]
    assert "https://muni.gov/files/zoning_map_2024.pdf" in hrefs
    assert "https://muni.gov/planning" in hrefs


def test_extract_links_regex_matches_bs4_subset():
    bs4_links = _extract_links_bs4(HOMEPAGE_WITH_DIRECT_LINK, "https://muni.gov/")
    regex_links = _extract_links_regex(HOMEPAGE_WITH_DIRECT_LINK, "https://muni.gov/")
    bs4_hrefs = {h for (h, _) in bs4_links}
    regex_hrefs = {h for (h, _) in regex_links}
    # regex extractor should catch every <a href=…> the bs4 path catches
    assert bs4_hrefs == regex_hrefs


# ── End-to-end discover_map_url_from_website tests ───────────────────────


class _StubResponse:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "text/html"):
        self._text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    @property
    def text(self) -> str:
        return self._text


class _StubAsyncClient:
    """Minimal httpx.AsyncClient stand-in that serves a dict of url -> html."""

    _pages: dict = {}

    def __init__(self, *args, **kwargs):
        self._pages = _StubAsyncClient._pages

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str, headers=None, timeout=None):  # noqa: D401
        if url in self._pages:
            return _StubResponse(self._pages[url])
        return _StubResponse("", status_code=404)


def _run(coro):
    return asyncio.run(coro)


def _install_httpx_stub(pages: dict):
    """Inject a fake httpx module into sys.modules so the in-function
    `import httpx` inside discover_map_url_from_website picks up the stub."""
    import types
    _StubAsyncClient._pages = pages
    fake = types.ModuleType("httpx")
    fake.AsyncClient = _StubAsyncClient  # type: ignore[attr-defined]
    sys.modules["httpx"] = fake


def _uninstall_httpx_stub(saved):
    if saved is None:
        sys.modules.pop("httpx", None)
    else:
        sys.modules["httpx"] = saved


def test_discovery_finds_high_confidence_pdf_on_homepage():
    saved = sys.modules.get("httpx")
    _install_httpx_stub({"https://muni.gov/": HOMEPAGE_WITH_DIRECT_LINK})
    try:
        result = _run(discover_map_url_from_website("https://muni.gov/", "Test Muni"))
    finally:
        _uninstall_httpx_stub(saved)
    assert result == "https://muni.gov/files/zoning_map_2024.pdf"


def test_discovery_follows_planning_page_one_level_deep():
    saved = sys.modules.get("httpx")
    _install_httpx_stub({
        "https://muni.gov/": HOMEPAGE_WITH_INTERMEDIATE_LINK,
        "https://muni.gov/planning": PLANNING_PAGE_WITH_MAP,
    })
    try:
        result = _run(discover_map_url_from_website("https://muni.gov/", "Test Muni"))
    finally:
        _uninstall_httpx_stub(saved)
    assert result == "https://muni.gov/assets/maps/township_zoning_map.pdf"


def test_discovery_returns_none_when_nothing_matches():
    saved = sys.modules.get("httpx")
    _install_httpx_stub({"https://muni.gov/": EMPTY_HOMEPAGE})
    try:
        result = _run(discover_map_url_from_website("https://muni.gov/", "Test Muni"))
    finally:
        _uninstall_httpx_stub(saved)
    assert result is None


def test_discovery_returns_none_for_empty_website_url():
    assert _run(discover_map_url_from_website(None, "X")) is None
    assert _run(discover_map_url_from_website("", "X")) is None
