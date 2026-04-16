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

# Common zone code patterns for Utah / generic US municipalities
_ZONE_CODE_RE = re.compile(
    r"\b(M[12L]L?|CBP?|CP|CG|C[CSNO]B?|R[-\s]?[1-9](?:[-\s]\d+)?|RM[-\s]?\d*H?|RMH?|OS|OF?|PF|IN|A[-\s]?1?|ML)\b",
    re.IGNORECASE,
)

# Section number patterns: "9-13-040", "9.13.040", "18.35.020(B)"
_SECTION_NUM_RE = re.compile(
    r"^(?P<num>\d+[-\.]\d+[-\.]\d+(?:[A-Za-z])?)[.\s]+(?P<heading>[^\n]{3,120})",
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
    if source == "municode":
        return await _fetch_municode(url)
    elif source == "ecode360":
        return await _fetch_generic(url)   # fallback until Phase 5 Playwright
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
    """Return 'municode' | 'ecode360' | 'american_legal' | 'generic'."""
    u = url.lower()
    if "municode.com" in u:
        return "municode"
    if "ecode360.com" in u:
        return "ecode360"
    if "amlegal.com" in u or "american-legal.com" in u:
        return "american_legal"
    return "generic"


# ─── Source-specific fetchers ────────────────────────────────────────────────

async def _fetch_municode(url: str) -> list[OrdinanceSection]:
    """
    Fetch from Municode.  Their site is a React SPA so the initial HTML may
    not include content.  We attempt to scrape what we can; Phase 5 will use
    Playwright to execute the JavaScript.
    """
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0, headers=_BROWSER_HEADERS
    ) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Cannot reach Municode URL ({exc})") from exc

        soup = BeautifulSoup(resp.text, "lxml")

        # Municode sometimes includes readable content in <script type="application/ld+json">
        # or in inline server-rendered HTML
        sections = _extract_zoning_sections_from_soup(soup)

        if not sections:
            raise RuntimeError(
                "Municode page did not return parseable HTML content.  "
                "This usually means the page is JavaScript-only.  "
                "Workarounds: (1) upload a PDF of the zoning chapter, "
                "(2) paste the direct chapter URL, or "
                "(3) wait for Phase 5 (Playwright support)."
            )

        return sections


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
