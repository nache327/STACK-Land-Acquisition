"""
Ordinance text fetcher — Phase 3 full implementation.

Given a URL (Municode / eCode360 / city website) or an uploaded PDF, extracts
the text of the zoning chapter, preserving section numbers.

Returns a list of OrdinanceSection objects ready for the parser.

Note: Municode and eCode360 are JavaScript SPAs.  This module fetches whatever
static HTML the server returns (enough for many codes) and splits it into
sections.  Phase 5 will add Playwright to handle fully JS-rendered pages.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class OrdinanceSection:
    section_id: str          # e.g. "9-13-040"
    heading: str             # e.g. "M1 Light Industrial District — Permitted Uses"
    text: str                # Section body text
    district_codes: list[str] = field(default_factory=list)  # Zone codes found in this section


# ─── Constants ───────────────────────────────────────────────────────────────

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Generic US zone code patterns (industrial, commercial, residential, mixed-use, ag, open space)
_ZONE_CODE_RE = re.compile(
    r"\b("
    # Industrial: I-1, I-2, LI, LI-1, HI, M-1, M1, ML, MU
    r"(?:LI|HI|M[12L]L?|IN?)[-\s]?\d*"
    r"|(?:I|M)[-\s]\d{1,2}"
    # Commercial: B-1, B-2, C-1, CB, CG, GC, CC, LC, HC, NC, SC, TC, CBP
    r"|(?:GC|LC|HC|NC|SC|TC|RC|CC|CB|CBP?|CP|CG|C[CSNO]B?|C|B)[-\s]?\d{0,2}"
    # Office/Business Park: OF, OB, OC, BP, BP-1
    r"|(?:OF?|OB|OC|BP|PBD)[-\s]?\d{0,2}"
    # Mixed-Use / TOD: MU-1, MU-2, TOD, TOD-1
    r"|(?:MU|TOD)[-\s]?\d{0,2}"
    # Residential: R-1, R-2, RM, RS, RR, RMH, R1, R2, RA-1
    r"|R(?:M|R|S|H|A)?[-\s]?\d*(?:[-\s]\d+)?"
    # Open Space / Public: OS, PF, PR, PL
    r"|(?:OS|PF|PR|PL)[-\s]?\d{0,2}"
    # Agricultural: A-1, AG, RR-1
    r"|(?:AG|A[-\s]?\d*)"
    r")\b",
    re.IGNORECASE,
)

# Link text / href patterns that indicate an appendix or use-table page
_APPENDIX_LINK_RE = re.compile(
    r"\b(appendix|use[-\s]?table|table[-\s]of[-\s]uses?|permitted[-\s]uses?"
    r"|land[-\s]use[-\s]table|use[-\s]matrix|schedule[-\s]of[-\s]uses?)\b",
    re.IGNORECASE,
)
# municipal.codes appendix paths begin with /Code/Ax (e.g. /Code/AxA, /Code/AxA-Table)
_MUNI_CODES_APPENDIX_RE = re.compile(r"/Code/Ax", re.IGNORECASE)
# amlegal.com chapter page paths: /codes/{city}/{version}/{code}/{node-id}
# where node-id is four dash-separated numbers like 0-0-0-22474
_AMLEGAL_NODE_RE = re.compile(r"^/codes/[^/]+/[^/]+/[^/]+/\d+-\d+-\d+-\d+$")

# Section number patterns — handles many US ordinance formats:
#   "9-13-040", "9.13.040", "18.35.020(B)"  (three-part numeric)
#   "14.25", "18.35"                          (two-part numeric)
#   "§ 153.045", "§153.45"                   (section symbol)
#   "Sec. 14.20.030", "Section 14-300"       (word prefix)
#   "Art. III", "Article 5"                  (article prefix, for land use tables)
_SECTION_NUM_RE = re.compile(
    r"^(?:§+\s*|[Ss]ec(?:tion)?\.?\s*|[Aa]rt(?:icle)?\.?\s*)?"
    r"(?P<num>\d+(?:[-\.]\d+){1,3}(?:[A-Za-z])?)"
    r"[.\s:–—]+(?P<heading>[^\n]{3,120})",
    re.MULTILINE,
)

# Maximum characters to send per ordinance (keep Claude context reasonable)
_MAX_ORDINANCE_CHARS = 80_000
_MAX_SECTION_CHARS = 12_000


# ─── Public API ──────────────────────────────────────────────────────────────

async def fetch_from_url(url: str) -> list[OrdinanceSection]:
    """
    Detect the source type and fetch ordinance sections.
    Raises RuntimeError if the URL cannot be fetched.
    """
    source = detect_source_type(url)
    if source in ("municipal_codes", "municode", "american_legal"):
        # JS SPAs / Cloudflare-protected — need a real browser.
        return await _fetch_with_playwright(url)
    elif source == "ecode360":
        return await _fetch_generic(url)
    else:
        return await _fetch_generic(url)


async def fetch_from_pdf(pdf_path: Path) -> list[OrdinanceSection]:
    """Extract ordinance sections from an uploaded PDF using pdfplumber."""
    import pdfplumber  # optional dep — installed in pyproject.toml

    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]
    full_text = "\n".join(pages_text)

    sections = _split_into_sections(full_text)
    if sections:
        return sections

    # Fall back — return full text as one blob
    return [OrdinanceSection(
        section_id="full_document",
        heading="Full Document",
        text=full_text[:_MAX_ORDINANCE_CHARS],
        district_codes=_find_district_codes(full_text),
    )]


def detect_source_type(url: str) -> str:
    """Return 'municipal_codes' | 'municode' | 'ecode360' | 'american_legal' | 'generic'.

    Any domain in _JS_SPA_DOMAINS is treated as a JS SPA and routed to Playwright.
    Add new municipal code platforms here as they are encountered.
    """
    u = url.lower()
    if ".municipal.codes" in u:
        return "municipal_codes"
    if "amlegal.com" in u or "american-legal.com" in u:
        return "american_legal"
    # All other known JS SPA / Cloudflare-protected municipal code platforms
    _JS_SPA_DOMAINS = (
        "municode.com",
        "municipalcodeonline.com",
        "sterlingcodifiers.com",
        "codepublishing.com",
        "generalcode.com",
        "codexonline.com",
        "ecode360.com",
        "codelibrary.amlegal.com",
    )
    if any(d in u for d in _JS_SPA_DOMAINS):
        return "municode"  # all routed through _fetch_with_playwright
    return "generic"


# ─── Source-specific fetchers ────────────────────────────────────────────────

async def _fetch_with_playwright(url: str) -> list[OrdinanceSection]:
    """
    Fetch a JS-rendered or Cloudflare-protected ordinance page using Playwright.

    Required for:
      - municipal.codes  (Cloudflare managed challenge + React SPA)
      - library.municode.com  (React SPA, no SSR content)

    For municipal.codes, if the initial URL is a chapter-listing page (Title-level
    index like /Code/17), automatically crawls each zone chapter link to find the
    actual use tables.  The first page load passes the Cloudflare cookie, so
    subsequent pages in the same browser context are fast.

    Falls back to a clear error if Playwright / Chromium is not installed.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is not installed — required for this ordinance source.  "
            "Run: pip install playwright && playwright install chromium\n"
            "Workaround: upload a PDF of the zoning chapter instead."
        )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=_BROWSER_HEADERS["User-Agent"],
                locale="en-US",
            )
            page = await ctx.new_page()

            # First load — may trigger Cloudflare challenge; wait for full render
            try:
                await page.goto(url, wait_until="networkidle", timeout=60_000)
            except Exception:
                pass

            for selector in ("article", "main", "[class*='chapter']", "[class*='content']"):
                try:
                    await page.wait_for_selector(selector, timeout=8_000)
                    break
                except Exception:
                    continue

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # For municipal.codes: detect TOC page → crawl sub-pages.
            if ".municipal.codes" in url and _is_listing_page(soup, url):
                sections = await _crawl_chapter_links(page, soup, url)
                if sections:
                    return sections

            # For amlegal.com: walk Next Doc links within the parent title.
            # Title boundaries are derived from the left sidebar node IDs.
            if "amlegal.com" in url:
                sections = await _crawl_amlegal_chapters(page, soup, url)
                if sections:
                    return sections

            # Non-listing page: check for appendix links even on content pages
            # (handles case where user lands on a chapter page, not the TOC)
            appendix_urls = _find_appendix_links(soup, url)
            if appendix_urls:
                for aurl in appendix_urls[:3]:
                    try:
                        secs = await _fetch_page_sections(page, aurl)
                        has_matrix = any(
                            re.search(r"\|\s*[PCN]\s*\|", s.text, re.I) for s in secs
                        )
                        if secs and has_matrix:
                            return secs
                    except Exception:
                        continue

            # Single-page extraction — reuse _fetch_page_sections logic
            for noise in soup.select("nav, header, footer, aside, [class*='sidebar'], [class*='toc']"):
                noise.decompose()

            tables_md = _extract_tables_as_markdown(soup)
            if tables_md:
                import copy
                soup_copy = copy.copy(soup)
                for t in soup_copy.find_all("table"):
                    t.decompose()
                prose = soup_copy.get_text(separator="\n", strip=True)
                combined_text = f"{prose}\n\n--- USE MATRIX TABLES ---\n\n{tables_md}"
                if len(combined_text) > 200:
                    return [OrdinanceSection(
                        section_id="use_matrix",
                        heading="Use Matrix / Table of Permitted Uses",
                        text=combined_text[:_MAX_ORDINANCE_CHARS],
                        district_codes=_find_district_codes(combined_text),
                    )]

            sections = _extract_zoning_sections_from_soup(soup)
            if sections:
                return sections

            text = soup.get_text(separator="\n", strip=True)
            sections = _split_into_sections(text)
            if sections:
                return sections

        finally:
            await browser.close()

    raise RuntimeError(
        f"Playwright loaded {url!r} but found no parseable ordinance content.  "
        "Try uploading a PDF of the zoning chapter instead."
    )


def _is_listing_page(soup: BeautifulSoup, url: str) -> bool:
    """
    Return True if this page is a table-of-contents / chapter index rather than
    actual ordinance content.  Heuristic: very short visible text + several links.
    """
    text = soup.get_text(separator=" ", strip=True)
    word_count = len(text.split())
    link_count = len(soup.find_all("a", href=True))
    return word_count < 600 and link_count >= 5


def _find_appendix_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Scan all links on a page for appendix / use-table indicators.
    Returns deduplicated absolute URLs on the same host, appendix links only.

    Two signals:
      1. Link text or href matches _APPENDIX_LINK_RE (generic keyword match)
      2. For municipal.codes: href path matches /Code/Ax* pattern
    """
    from urllib.parse import urljoin, urlparse
    parsed_base = urlparse(base_url)
    found: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]
        full = urljoin(base_url, href)
        p = urlparse(full)
        if p.netloc != parsed_base.netloc:
            continue
        if full in seen:
            continue
        link_text = a.get_text(strip=True)
        is_appendix = (
            _APPENDIX_LINK_RE.search(link_text)
            or _APPENDIX_LINK_RE.search(href)
            or _MUNI_CODES_APPENDIX_RE.search(p.path)
        )
        if is_appendix:
            seen.add(full)
            found.append(full)

    return found


async def _fetch_page_sections(page, url: str) -> list[OrdinanceSection]:
    """
    Fetch a single page with Playwright and extract OrdinanceSection objects.
    Shared by both appendix and chapter crawl paths.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        pass
    try:
        await page.wait_for_selector("article, main", timeout=6_000)
    except Exception:
        pass

    ch_html = await page.content()
    ch_soup = BeautifulSoup(ch_html, "lxml")
    for noise in ch_soup.select("nav, header, footer, aside, [class*='sidebar'], [class*='toc']"):
        noise.decompose()

    # Table-aware extraction first (preserves use matrix column structure)
    tables_md = _extract_tables_as_markdown(ch_soup)
    if tables_md:
        import copy
        soup_copy = copy.copy(ch_soup)
        for t in soup_copy.find_all("table"):
            t.decompose()
        prose = soup_copy.get_text(separator="\n", strip=True)
        combined = f"{prose}\n\n--- USE MATRIX TABLES ---\n\n{tables_md}"
        return [OrdinanceSection(
            section_id=url.rstrip("/").split("/")[-1],
            heading="Use Matrix / Table of Permitted Uses",
            text=combined[:_MAX_ORDINANCE_CHARS],
            district_codes=_find_district_codes(combined),
        )]

    ch_text = ch_soup.get_text(separator="\n", strip=True)
    if not re.search(
        r"\b(permitted|conditional|prohibited|allowed use|use matrix|storage|warehouse)\b",
        ch_text, re.I,
    ):
        return []

    sections = _split_into_sections(ch_text)
    if not sections and len(ch_text) > 200:
        chapter_id = url.rstrip("/").split("/")[-1]
        h = ch_soup.find(re.compile(r"^h[1-3]$"))
        heading = h.get_text(strip=True) if h else chapter_id
        sections = [OrdinanceSection(
            section_id=chapter_id,
            heading=heading,
            text=ch_text[:_MAX_SECTION_CHARS],
            district_codes=_find_district_codes(ch_text),
        )]
    return sections


async def _crawl_amlegal_chapters(page, initial_soup: BeautifulSoup, initial_url: str) -> list[OrdinanceSection]:
    """
    For codelibrary.amlegal.com: navigate to the parent title page and walk
    'Next Doc' links forward, collecting content until we cross into the next title.

    Strategy:
      1. Extract all title-level node IDs from div.codenav__left-inner
      2. Find parent title (largest title node ID < current node ID)
      3. Navigate to that parent title URL
      4. Walk Next Doc forward; stop when node ID >= next-title boundary
    """
    from urllib.parse import urljoin, urlparse

    def _amlegal_node_num(url_str: str) -> int | None:
        """Return the integer portion of an amlegal 0-0-0-NNNNN node ID."""
        m = re.search(r"/(\d+-\d+-\d+-(\d+))(?:[#?]|$)", url_str)
        return int(m.group(2)) if m else None

    def _next_doc_url(soup: BeautifulSoup, base: str) -> str | None:
        for div in soup.select("div.bottom-right__doc.bottom-right--right"):
            a = div.find("a", href=True)
            if a:
                return urljoin(base, a["href"])
        return None

    def _extract_content(soup: BeautifulSoup, page_url: str) -> list[OrdinanceSection]:
        """Extract zoning sections from an already-loaded amlegal page soup.
        amlegal renders all chapter sections inside div.codenav__section-body.
        """
        import copy as _copy

        section_body = soup.find("div", class_="codenav__section-body")
        if not section_body:
            return []

        s = _copy.copy(section_body)
        # Strip share/download/print/bookmark noise (non-content UI elements)
        for noise in s.find_all(class_=re.compile(r"share|download|bookmark|print|button", re.I)):
            noise.decompose()
        for noise in s.find_all("button"):
            noise.decompose()

        tables_md = _extract_tables_as_markdown(s)
        if tables_md:
            s2 = _copy.copy(s)
            for t in s2.find_all("table"):
                t.decompose()
            prose = s2.get_text(separator="\n", strip=True)
            combined = f"{prose}\n\n--- USE MATRIX TABLES ---\n\n{tables_md}"
            return [OrdinanceSection(
                section_id=page_url.rstrip("/").split("/")[-1],
                heading="Use Matrix / Table of Permitted Uses",
                text=combined[:_MAX_ORDINANCE_CHARS],
                district_codes=_find_district_codes(combined),
            )]

        ch_text = s.get_text(separator="\n", strip=True)
        if not re.search(
            r"\b(permitted|conditional|prohibited|allowed use|storage|warehouse|zone(?:s|d)?|district)\b",
            ch_text, re.I,
        ):
            return []

        sections = _split_into_sections(ch_text)
        if not sections and len(ch_text) > 200:
            chapter_id = page_url.rstrip("/").split("/")[-1]
            heading_el = s.find(re.compile(r"^h[1-3]$"))
            heading = heading_el.get_text(strip=True) if heading_el else chapter_id
            sections = [OrdinanceSection(
                section_id=chapter_id,
                heading=heading,
                text=ch_text[:_MAX_ORDINANCE_CHARS],
                district_codes=_find_district_codes(ch_text),
            )]
        return sections

    parsed = urlparse(initial_url)
    base_dir = "/".join(parsed.path.rstrip("/").split("/")[:-1])
    current_num = _amlegal_node_num(initial_url) or 0

    # Gather title-level node IDs from the left sidebar
    title_nums: list[int] = []
    left_nav = initial_soup.select_one("div.codenav__left-inner")
    if left_nav:
        for a in left_nav.find_all("a", href=True):
            href = a["href"]
            if not href.startswith(base_dir + "/"):
                href = urljoin(initial_url, href)
            n = _amlegal_node_num(href)
            if n:
                text = a.get_text(strip=True).upper()
                if text.startswith(("TITLE ", "PART ", "ARTICLE ")):
                    title_nums.append(n)
    title_nums = sorted(set(title_nums))

    # Parent title: largest title node < current
    parent_num = max((n for n in title_nums if n < current_num), default=None)
    # Stop boundary: smallest title node > current
    stop_at = min((n for n in title_nums if n > current_num), default=None)

    all_sections: list[OrdinanceSection] = []
    # Section URLs from TOC-only chapter pages to fetch after the main walk
    pending_section_urls: list[str] = []
    seen_pending: set[str] = set()

    def _collect_chapter_section_links(soup: BeautifulSoup, page_url: str) -> list[str]:
        """
        On a TOC-only chapter page, collect ALL sub-section links — not just
        those with "permitted" in the text.  Content filtering happens later
        in _extract_content (which already skips non-zoning pages).

        Looks in:
          1. div.codenav__section-body — inline TOC links
          2. div.codenav__right       — right-sidebar section list (SSR-rendered)
        Both containers are checked; duplicates are suppressed via seen_pending.
        """
        collected: list[str] = []
        for container_sel in ("div.codenav__section-body", "div.codenav__right"):
            container = soup.select_one(container_sel)
            if not container:
                continue
            for a in container.find_all("a", href=True):
                href = a["href"].split("#")[0]
                full = urljoin(page_url, href)
                p = urlparse(full)
                if p.netloc != parsed.netloc:
                    continue
                if not _AMLEGAL_NODE_RE.match(p.path.rstrip("/")):
                    continue
                n = _amlegal_node_num(full)
                if n is None:
                    continue
                if stop_at and n >= stop_at:
                    continue
                if full not in seen_pending:
                    seen_pending.add(full)
                    collected.append(full)
        return collected

    # Always extract content from the initial page first — the user may have
    # navigated directly to a rich section page (e.g. "Permitted Uses" for C-G).
    # This is kept even when we later walk from the parent title, so we never
    # silently discard content the user explicitly loaded.
    init_body_el = initial_soup.find("div", class_="codenav__section-body")
    init_body_len = len(init_body_el.get_text(strip=True)) if init_body_el else 0
    init_has_table = bool(init_body_el and init_body_el.find("table"))
    if init_body_len < 3000 and not init_has_table:
        pending_section_urls.extend(
            _collect_chapter_section_links(initial_soup, initial_url)
        )
    else:
        all_sections.extend(_extract_content(initial_soup, initial_url))
        seen_pending.add(initial_url)  # don't re-fetch via pending

    # Navigate to parent title to walk from the beginning of the title
    if parent_num:
        parent_url = f"{parsed.scheme}://{parsed.netloc}{base_dir}/0-0-0-{parent_num}"
        try:
            await page.goto(parent_url, wait_until="load", timeout=45_000)
        except Exception:
            pass
        parent_html = await page.content()
        parent_soup = BeautifulSoup(parent_html, "lxml")
        current_soup = parent_soup
        current_url = parent_url
    else:
        # Already at title level or no parent found — start from initial page
        current_soup = initial_soup
        current_url = initial_url

    # Walk Next Doc forward within the title
    for _ in range(40):
        nurl = _next_doc_url(current_soup, current_url)
        if not nurl:
            break
        next_num = _amlegal_node_num(nurl)
        if stop_at and next_num and next_num >= stop_at:
            break

        try:
            await page.goto(nurl, wait_until="load", timeout=45_000)
        except Exception:
            try:
                await page.goto(nurl, wait_until="commit", timeout=30_000)
                await page.wait_for_timeout(2_000)
            except Exception:
                break

        html = await page.content()
        next_soup = BeautifulSoup(html, "lxml")

        # Detect TOC-only chapter pages (small body = just a list of section links).
        # IMPORTANT: measure text length only — pages that are mostly HTML tables
        # (e.g. use matrices) will have short plain-text but rich table content.
        # Check for tables before deciding this is a barren TOC page.
        body_el = next_soup.find("div", class_="codenav__section-body")
        body_len = len(body_el.get_text(strip=True)) if body_el else 0
        has_table = bool(body_el and body_el.find("table"))
        if body_len < 3000 and not has_table:
            pending_section_urls.extend(
                _collect_chapter_section_links(next_soup, nurl)
            )
        else:
            all_sections.extend(_extract_content(next_soup, nurl))

        current_soup = next_soup
        current_url = nurl

    # Fetch section pages collected from TOC-only chapter pages
    for surl in pending_section_urls[:50]:
        try:
            await page.goto(surl, wait_until="load", timeout=45_000)
        except Exception:
            try:
                await page.goto(surl, wait_until="commit", timeout=30_000)
                await page.wait_for_timeout(2_000)
            except Exception:
                continue
        html = await page.content()
        sec_soup = BeautifulSoup(html, "lxml")
        all_sections.extend(_extract_content(sec_soup, surl))

    return all_sections


async def _crawl_chapter_links(page, soup: BeautifulSoup, base_url: str) -> list[OrdinanceSection]:
    """
    Given a listing/TOC page, follow links to collect ordinance sections.

    Phase A: appendix / use-table links fetched FIRST (highest priority).
      If any appendix page contains a P/C/N use matrix, return ONLY those
      sections — no need to dilute the clean matrix with 80k chars of prose.

    Phase B: chapter-level links (one path segment deeper than base_path).
      Only runs if Phase A found no usable table.
    """
    from urllib.parse import urljoin, urlparse

    parsed_base = urlparse(base_url)
    base_path = parsed_base.path.rstrip("/")

    # ── Phase A: appendix / use-table pages ───────────────────────────────────
    appendix_urls = _find_appendix_links(soup, base_url)
    appendix_sections: list[OrdinanceSection] = []
    for aurl in appendix_urls[:5]:
        try:
            secs = await _fetch_page_sections(page, aurl)
            appendix_sections.extend(secs)
        except Exception:
            continue

    # If appendix contained a real use matrix (has P/C/N table cells), return it
    # immediately — don't add noisy chapter prose on top of a clean matrix.
    has_use_matrix = any(
        re.search(r"\|\s*[PCN]\s*\|", s.text, re.I)
        or "use matrix" in s.heading.lower()
        for s in appendix_sections
    )
    if has_use_matrix:
        return appendix_sections

    # ── Phase B: chapter-level links ──────────────────────────────────────────
    seen: set[str] = {u for u in appendix_urls}
    chapter_urls: list[str] = []

    is_amlegal = "amlegal.com" in parsed_base.netloc
    # For amlegal: parent dir is everything before the last path segment (the node ID)
    amlegal_parent = "/".join(base_path.split("/")[:-1]) if is_amlegal else ""

    # For amlegal: only search links in the main content area (not the sidebar nav
    # which lists ALL city titles). A copy avoids mutating the caller's soup.
    if is_amlegal:
        import copy as _copy
        content_soup = _copy.copy(soup)
        for noise in content_soup.select("nav, header, footer, aside, [class*='sidebar'], [class*='nav'], [class*='toc']"):
            noise.decompose()
        link_source = content_soup
    else:
        link_source = soup

    for a in link_source.find_all("a", href=True):
        full = urljoin(base_url, a["href"].split("#")[0])
        p = urlparse(full)
        if p.netloc != parsed_base.netloc:
            continue
        candidate_path = p.path.rstrip("/")

        if is_amlegal:
            # amlegal: sibling node IDs in the same code directory
            if not _AMLEGAL_NODE_RE.match(candidate_path):
                continue
            if not candidate_path.startswith(amlegal_parent + "/"):
                continue
            if candidate_path == base_path:
                continue  # skip the TOC page itself
        else:
            # municipal.codes: chapter links are base_path.XX (one level deeper)
            if not candidate_path.startswith(base_path + "."):
                continue
            remainder = candidate_path[len(base_path) + 1:]
            if "." in remainder:
                continue

        if full not in seen:
            seen.add(full)
            chapter_urls.append(full)

    all_sections: list[OrdinanceSection] = list(appendix_sections)
    for chapter_url in chapter_urls[:30]:
        try:
            secs = await _fetch_page_sections(page, chapter_url)
            all_sections.extend(secs)
        except Exception:
            continue

    return all_sections


async def _fetch_municode(url: str) -> list[OrdinanceSection]:
    """Kept for reference — now routed through _fetch_with_playwright."""
    return await _fetch_with_playwright(url)


async def _fetch_generic(url: str) -> list[OrdinanceSection]:
    """HTTP fetch with BeautifulSoup.  Works for most static city websites."""
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0, headers=_BROWSER_HEADERS
    ) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Cannot fetch URL ({exc})") from exc

        content_type = resp.headers.get("content-type", "")

        # If the server returns a PDF, save to a temp file and use pdfplumber
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(resp.content)
                tmp = Path(f.name)
            try:
                return await fetch_from_pdf(tmp)
            finally:
                tmp.unlink(missing_ok=True)

        soup = BeautifulSoup(resp.text, "lxml")
        sections = _extract_zoning_sections_from_soup(soup)

        if not sections:
            # Last resort: dump all visible text and split
            raw = soup.get_text(separator="\n", strip=True)
            sections = _split_into_sections(raw)

        return sections


# ─── HTML / text extraction helpers ─────────────────────────────────────────

def _table_to_markdown(table) -> str:
    """
    Convert a BeautifulSoup <table> element to a markdown table string,
    preserving zone-column / use-row relationships for use matrices.
    Returns empty string if the table has no usable rows.
    """
    rows_out: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["th", "td"])]
        if cells:
            rows_out.append(cells)

    if not rows_out:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows_out)
    rows_out = [r + [""] * (max_cols - len(r)) for r in rows_out]

    lines: list[str] = []
    for i, row in enumerate(rows_out):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * max_cols) + "|")

    return "\n".join(lines)


def _extract_tables_as_markdown(soup: BeautifulSoup) -> str:
    """
    Find all <table> elements that look like use matrices (≥3 columns, ≥4 rows)
    and return them as concatenated markdown tables.
    """
    parts: list[str] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 4:
            continue
        first_row_cells = rows[0].find_all(["th", "td"])
        if len(first_row_cells) < 3:
            continue
        md = _table_to_markdown(table)
        if md:
            parts.append(md)
    return "\n\n".join(parts)


def _extract_zoning_sections_from_soup(soup: BeautifulSoup) -> list[OrdinanceSection]:
    """
    Find the main content element and extract zoning district sections.
    Looks for common content wrapper IDs/classes.
    If the page contains HTML tables (use matrices), convert them to markdown
    first so zone-column relationships are preserved.
    """
    # Try common content containers
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"content|main|article|ordinance", re.I))
        or soup.find(class_=re.compile(r"content|main|article|ordinance|chapter", re.I))
        or soup.body
    )
    if not main:
        return []

    # Check for use-matrix tables and preserve their structure as markdown
    tables_md = _extract_tables_as_markdown(main)

    if tables_md:
        # Combine table markdown with surrounding prose text (headings, notes)
        # Remove table elements from soup copy so get_text() doesn't double-count
        import copy
        main_copy = copy.copy(main)
        for t in main_copy.find_all("table"):
            t.decompose()
        prose = main_copy.get_text(separator="\n", strip=True)
        text = f"{prose}\n\n--- USE MATRIX TABLES ---\n\n{tables_md}"
    else:
        text = main.get_text(separator="\n", strip=True)

    # Only worth parsing if it has substantial zoning content
    if len(text) < 200:
        return []

    return _split_into_sections(text)


def _split_into_sections(text: str) -> list[OrdinanceSection]:
    """
    Split ordinance text into sections using section-number headings as
    delimiters.  Filters to sections that mention zoning/storage keywords.
    """
    matches = list(_SECTION_NUM_RE.finditer(text))

    if not matches:
        # No section numbers — return as single blob if it has zoning keywords
        has_zoning = re.search(
            r"\b(zoning|zone|district|permitted|storage|warehouse|industrial|commercial)\b",
            text, re.I,
        )
        if has_zoning and len(text.strip()) > 100:
            return [OrdinanceSection(
                section_id="document",
                heading="Ordinance Text",
                text=text[:_MAX_ORDINANCE_CHARS],
                district_codes=_find_district_codes(text),
            )]
        return []

    sections: list[OrdinanceSection] = []
    for i, match in enumerate(matches):
        section_id = match.group("num")
        heading = match.group("heading").strip()[:200]

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()[:_MAX_SECTION_CHARS]

        codes = _find_district_codes(section_text)
        is_relevant = bool(
            codes or re.search(
                r"\b(permitted|prohibited|conditional|storage|warehouse|industrial|commercial|zoning)\b",
                section_text, re.I,
            )
        )

        if is_relevant:
            sections.append(OrdinanceSection(
                section_id=section_id,
                heading=heading,
                text=section_text,
                district_codes=codes,
            ))

    return sections


def _find_district_codes(text: str) -> list[str]:
    """Return deduplicated zone codes found in text."""
    seen: dict[str, None] = {}
    for m in _ZONE_CODE_RE.finditer(text):
        seen[m.group(0).upper()] = None
    return list(seen)


# ─── Ordinance URL discovery ─────────────────────────────────────────────────

def _city_to_slug(jurisdiction_name: str) -> str:
    """Convert 'Draper City, UT' → 'draper', 'Salt Lake City, UT' → 'salt_lake_city'."""
    name = re.sub(r",\s*[A-Z]{2}\s*$", "", jurisdiction_name).strip()
    name = re.sub(
        r"\b(city|town|village|township|municipality|unincorporated)\b", "", name, flags=re.I
    ).strip()
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


async def discover_ordinance_url(jurisdiction_name: str, state: str) -> str | None:
    """
    Try to find the zoning ordinance URL for a jurisdiction by probing
    common Municode and eCode360 URL patterns.  Returns the first URL
    that returns HTTP 200, or None if nothing is found.
    """
    slug = _city_to_slug(jurisdiction_name)
    st = state.lower()

    candidates = [
        f"https://library.municode.com/{st}/{slug}/codes/code_of_ordinances",
        f"https://library.municode.com/{st}/{slug}/codes/municipal_code",
        f"https://library.municode.com/{st}/{slug}/codes/zoning_ordinance",
        f"https://library.municode.com/{st}/{slug}/codes/land_development_code",
        f"https://www.ecode360.com/{slug}",
    ]

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=10.0, headers=_BROWSER_HEADERS
    ) as client:
        for url in candidates:
            try:
                resp = await client.head(url)
                if resp.status_code == 200:
                    return url
            except httpx.HTTPError:
                continue

    return None
