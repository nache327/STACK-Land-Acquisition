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
    if source in ("municipal_codes", "municode"):
        # These are JS SPAs / Cloudflare-protected — need a real browser.
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
    """Return 'municipal_codes' | 'municode' | 'ecode360' | 'american_legal' | 'generic'."""
    u = url.lower()
    if ".municipal.codes" in u:
        return "municipal_codes"
    if "municode.com" in u:
        return "municode"
    if "ecode360.com" in u:
        return "ecode360"
    if "amlegal.com" in u or "american-legal.com" in u:
        return "american_legal"
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

            # For municipal.codes: detect a chapter-listing / TOC page and crawl sub-pages.
            # A listing page has few words of actual ordinance text but many chapter links.
            if ".municipal.codes" in url and _is_listing_page(soup, url):
                sections = await _crawl_chapter_links(page, soup, url)
                if sections:
                    return sections

            # Single-page extraction path (also runs as fallback after empty crawl)
            for noise in soup.select("nav, header, footer, aside, [class*='sidebar'], [class*='toc']"):
                noise.decompose()

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


async def _crawl_chapter_links(page, soup: BeautifulSoup, base_url: str) -> list[OrdinanceSection]:
    """
    Given a listing/TOC page, follow each chapter link and accumulate sections
    that contain use-regulation content.

    Strategy:
      - Collect links that go one level deeper than the current URL path
        (e.g. /Code/17 → /Code/17.04, /Code/17.42, …)
      - Skip sub-section links (too deep) to avoid hundreds of tiny pages
      - Only keep pages that mention permitted/conditional/prohibited uses
      - Cap at 30 chapters; reuse the same browser context so the Cloudflare
        cookie is already valid and subsequent loads are fast (~2–5 s each)
    """
    from urllib.parse import urljoin, urlparse

    parsed_base = urlparse(base_url)
    base_path = parsed_base.path.rstrip("/")

    # Collect unique chapter-level links (one path segment deeper than base_path)
    chapter_urls: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"].split("#")[0])
        p = urlparse(full)
        if p.netloc != parsed_base.netloc:
            continue
        candidate_path = p.path.rstrip("/")
        # Must start with base_path + "." and have no further "/" after that
        if not candidate_path.startswith(base_path + "."):
            continue
        remainder = candidate_path[len(base_path) + 1:]  # e.g. "42" or "42.010"
        if "." in remainder:
            continue  # skip sub-section links (/Code/17.42.010)
        if full not in seen:
            seen.add(full)
            chapter_urls.append(full)

    all_sections: list[OrdinanceSection] = []
    for chapter_url in chapter_urls[:30]:
        try:
            try:
                await page.goto(chapter_url, wait_until="domcontentloaded", timeout=30_000)
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

            ch_text = ch_soup.get_text(separator="\n", strip=True)

            # Only keep chapters with actual use-regulation language
            if not re.search(
                r"\b(permitted|conditional|prohibited|allowed use|use matrix|storage|warehouse)\b",
                ch_text, re.I,
            ):
                continue

            sections = _split_into_sections(ch_text)
            if not sections and len(ch_text) > 200:
                # Page has relevant text but no parseable section numbers —
                # return as one blob with the chapter code as the section id
                chapter_id = chapter_url.rstrip("/").split("/")[-1]
                h = ch_soup.find(re.compile(r"^h[1-3]$"))
                heading = h.get_text(strip=True) if h else chapter_id
                sections = [OrdinanceSection(
                    section_id=chapter_id,
                    heading=heading,
                    text=ch_text[:_MAX_SECTION_CHARS],
                    district_codes=_find_district_codes(ch_text),
                )]
            all_sections.extend(sections)
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

def _extract_zoning_sections_from_soup(soup: BeautifulSoup) -> list[OrdinanceSection]:
    """
    Find the main content element and extract zoning district sections.
    Looks for common content wrapper IDs/classes.
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
