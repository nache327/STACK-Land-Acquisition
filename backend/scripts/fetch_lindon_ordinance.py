"""
Fetch Lindon Title 17 zoning chapters from municipal.codes and populate
zone_use_matrix using the ordinance parser (Claude).

The site is behind Cloudflare — uses Playwright so the managed challenge
is solved by a real browser. All 10 chapters share one browser session
so the Cloudflare cookie is only obtained once.

Run from the backend/ directory:
    python scripts/fetch_lindon_ordinance.py

Prerequisites (one-time):
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env BEFORE any app module is imported so pydantic-settings picks up the
# values when it initialises the Settings singleton at import time.
import os as _os
from dotenv import dotenv_values as _dv
for _k, _v in _dv(Path(__file__).parent.parent / ".env").items():
    if _k not in _os.environ:  # don't overwrite real env vars
        _os.environ[_k] = _v

from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_maker
from app.models.zone_use_matrix import ClassificationSource, ZoneUseMatrix
from app.services.ordinance_fetcher import (
    OrdinanceSection,
    _MAX_ORDINANCE_CHARS,
    _MAX_SECTION_CHARS,
    _find_district_codes,
    _split_into_sections,
)
from app.services.ordinance_parser import parse_ordinance_sections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

JURISDICTION_NAME = "Lindon, UT"

# The 10 Lindon Title 17 chapters that contain use regulations
CHAPTER_URLS = [
    "https://lindon.municipal.codes/Code/17.41",  # Residential zones
    "https://lindon.municipal.codes/Code/17.42",  # MU – Multiple Use
    "https://lindon.municipal.codes/Code/17.43",  # Community Facilities
    "https://lindon.municipal.codes/Code/17.47",  # Light Industrial
    "https://lindon.municipal.codes/Code/17.48",  # Heavy Industrial
    "https://lindon.municipal.codes/Code/17.49",  # PUD
    "https://lindon.municipal.codes/Code/17.50",  # Overlay
    "https://lindon.municipal.codes/Code/17.51",  # Special Purpose
    "https://lindon.municipal.codes/Code/17.54",  # Conditional Use Permits
    "https://lindon.municipal.codes/Code/17.55",  # Permitted Uses & Standards
]

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_all_chapters() -> list[OrdinanceSection]:
    """
    Open one Playwright browser session, load all chapters in sequence,
    and return their text as OrdinanceSection objects.

    The first page load solves the Cloudflare challenge; subsequent loads
    in the same context reuse the cf_clearance cookie and are much faster.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    all_sections: list[OrdinanceSection] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
        page = await ctx.new_page()

        for url in CHAPTER_URLS:
            logger.info("Fetching %s …", url)
            try:
                # First page: wait for full network settle (Cloudflare challenge)
                # Subsequent pages: domcontentloaded is enough (cookie already set)
                wait = "networkidle" if url == CHAPTER_URLS[0] else "domcontentloaded"
                try:
                    await page.goto(url, wait_until=wait, timeout=60_000)
                except Exception:
                    pass  # timeout on networkidle is OK — grab whatever rendered

                # Wait for the main content element
                for selector in ("article", "main", "section"):
                    try:
                        await page.wait_for_selector(selector, timeout=8_000)
                        break
                    except Exception:
                        continue

                html = await page.content()
            except Exception as exc:
                logger.warning("  Failed to fetch %s: %s", url, exc)
                continue

            soup = BeautifulSoup(html, "lxml")

            # Strip navigation chrome
            for noise in soup.select(
                "nav, header, footer, aside, [class*='sidebar'], [class*='toc']"
            ):
                noise.decompose()

            text = soup.get_text(separator="\n", strip=True)
            if len(text) < 100:
                logger.warning("  Got almost no text from %s — Cloudflare may have blocked", url)
                continue

            logger.info("  Got %d chars from %s", len(text), url)

            # Parse into sections; fall back to one blob if no section numbers found
            chapter_id = url.rstrip("/").split("/")[-1]
            sections = _split_into_sections(text)
            if not sections:
                h = soup.find(["h1", "h2", "h3"])
                heading = h.get_text(strip=True) if h else chapter_id
                sections = [OrdinanceSection(
                    section_id=chapter_id,
                    heading=heading,
                    text=text[:_MAX_SECTION_CHARS],
                    district_codes=_find_district_codes(text),
                )]
            all_sections.extend(sections)

        await browser.close()

    logger.info("Collected %d ordinance sections across %d chapters", len(all_sections), len(CHAPTER_URLS))
    return all_sections


async def run() -> None:
    # ── Step 1: fetch ordinance text ──────────────────────────────────────────
    sections = await fetch_all_chapters()
    if not sections:
        logger.error("No sections fetched — aborting.")
        return

    combined = "\n\n".join(
        f"[Section {s.section_id}: {s.heading}]\n{s.text}"
        for s in sections
    )[:_MAX_ORDINANCE_CHARS]

    logger.info("Combined text: %d chars — sending to Claude …", len(combined))

    # ── Step 2: get Lindon jurisdiction id + known zone codes ─────────────────
    async with async_session_maker() as db:
        r = await db.execute(text(
            "SELECT id FROM jurisdictions WHERE name ILIKE '%lindon%' LIMIT 1"
        ))
        row = r.one_or_none()
        if row is None:
            logger.error("Lindon jurisdiction not found in DB. Run a Lindon job first.")
            return
        jur_id = row[0]

        r2 = await db.execute(text(
            "SELECT DISTINCT zoning_code FROM parcels "
            "WHERE jurisdiction_id = :jid AND zoning_code IS NOT NULL"
        ), {"jid": jur_id})
        known_codes = sorted({row[0] for row in r2.fetchall() if row[0]})

    logger.info("Known zone codes (%d): %s", len(known_codes), ", ".join(known_codes[:20]))

    # ── Step 3: parse with Claude ─────────────────────────────────────────────
    output = await parse_ordinance_sections(combined, JURISDICTION_NAME, known_codes)
    logger.info("Claude returned %d zone classifications", len(output.zones))

    # ── Step 4: upsert into zone_use_matrix ───────────────────────────────────
    async with async_session_maker() as db:
        saved = 0
        for zone in output.zones:
            citations_val = [c.model_dump() for c in zone.citations] if zone.citations else None
            stmt = pg_insert(ZoneUseMatrix).values(
                jurisdiction_id=jur_id,
                zone_code=zone.code,
                zone_name=zone.name,
                self_storage=zone.self_storage,
                mini_warehouse=zone.mini_warehouse,
                light_industrial=zone.light_industrial,
                luxury_garage_condo=zone.luxury_garage_condo,
                citations=citations_val,
                confidence=zone.confidence,
                notes=zone.notes,
                classification_source=ClassificationSource.llm,
            ).on_conflict_do_update(
                constraint="uq_zone_matrix",
                set_=dict(
                    zone_name=zone.name,
                    self_storage=zone.self_storage,
                    mini_warehouse=zone.mini_warehouse,
                    light_industrial=zone.light_industrial,
                    luxury_garage_condo=zone.luxury_garage_condo,
                    citations=citations_val,
                    confidence=zone.confidence,
                    notes=zone.notes,
                    classification_source=ClassificationSource.llm,
                ),
                where=(
                    (ZoneUseMatrix.human_reviewed == False) &  # noqa: E712
                    (ZoneUseMatrix.classification_source != ClassificationSource.human)
                ),
            )
            await db.execute(stmt)
            saved += 1
        await db.commit()

    logger.info("Saved %d zone matrix rows for %s", saved, JURISDICTION_NAME)

    # ── Step 5: print summary ─────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"LINDON ZONE MATRIX — {saved} zones classified")
    print(f"{'='*70}")
    header = f"{'Zone':<12} {'Self-Storage':<16} {'Mini-Wh':<12} {'Garage Condo':<14} {'Conf'}"
    print(header)
    print("-" * len(header))
    for zone in sorted(output.zones, key=lambda z: z.code):
        print(
            f"{zone.code:<12} {zone.self_storage:<16} {zone.mini_warehouse:<12} "
            f"{zone.luxury_garage_condo:<14} {zone.confidence:.2f}"
        )
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run())
