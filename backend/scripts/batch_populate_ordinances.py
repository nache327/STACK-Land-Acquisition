"""
Batch ordinance scraper — pre-populates zone_use_matrix for all Zoneomics
jurisdictions in one or more US states.

Usage:
    python scripts/batch_populate_ordinances.py --states UT NJ PA FL TX NV
    python scripts/batch_populate_ordinances.py --states UT --limit 5   # test run

How it works:
  1. Scrapes zoneomics.com/code/{state} to get every city URL
  2. For each city, fetches the chapter list and picks chapters whose titles
     suggest they contain zoning use tables (commercial, industrial, etc.)
  3. Fetches + parses each relevant chapter with Claude
  4. Upserts results into zone_use_matrix (confidence-gated so better data wins)
  5. Creates a minimal Jurisdiction row if one doesn't exist yet
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ── make app importable from the backend root ──────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.models.zone_use_matrix import ZoneUseMatrix
from app.services.ordinance_fetcher import fetch_from_url
from app.services.ordinance_parser import parse_ordinance_sections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ZONEOMICS_BASE = "https://www.zoneomics.com/code"

# Cities where Zoneomics has no content — use direct PDF/HTML URLs instead
MANUAL_OVERRIDES: dict[str, list[str]] = {
    "lehi-UT": [
        "https://www.lehi-ut.gov/media/0y2bxpc1/tbl05030-b-nonresidential-zones.pdf",
        "https://www.lehi-ut.gov/media/ktwl0egv/ch08permitteduses.pdf",
        "https://www.lehi-ut.gov/media/plhlbcda/ch05zoningdistricts.pdf",
    ],
}
CENSUS_API = "https://api.census.gov/data/2022/acs/acs5"
MIN_POPULATION = 15_000

# US Census FIPS codes for each state
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}

STATE_CODES = {
    "utah": "UT", "new-jersey": "NJ", "pennsylvania": "PA",
    "florida": "FL", "texas": "TX", "nevada": "NV",
    "alabama": "AL", "alaska": "AK", "arizona": "AZ",
    "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "new-hampshire": "NH",
    "new-mexico": "NM", "new-york": "NY", "north-carolina": "NC",
    "north-dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "rhode-island": "RI", "south-carolina": "SC",
    "south-dakota": "SD", "tennessee": "TN", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west-virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

# Chapter titles that likely contain zoning use tables — broad to catch varied naming
USE_TABLE_KEYWORDS = [
    "commercial", "manufacturing", "industrial", "business",
    "mixed use", "mixed-use", "employment",
    "permitted use", "use regulation", "use table", "land use", "use matrix",
    "zone district", "zoning district", "zone establishment",
    "regulations within",
    "office", "warehouse", "flex",
]

# Exclude chapters that match keywords above but are clearly not use tables
EXCLUDE_KEYWORDS = [
    "sign", "parking", "wireless", "accessory dwelling", "enforcement",
    "administration", "general provision", "definition", "subdivision",
    "appeal", "non-conforming", "nonconforming", "flood", "wetland",
    "landscape", "lighting", "trail", "senior", "disability", "cannabis",
    "short term rental", "annexation", "water", "sewer",
]


# ─── Census population filter ────────────────────────────────────────────────

def _normalize_city_name(name: str) -> str:
    """Normalize a city name to match Zoneomics slug style.
    'Salt Lake City city, Utah' → 'salt-lake-city'
    """
    # Strip state suffix (", Utah")
    name = re.sub(r",.*$", "", name).strip()
    # Strip place-type suffixes
    name = re.sub(
        r"\b(city|town|village|township|borough|CDP|municipality|"
        r"unified government|metro government|urban county)\b",
        "", name, flags=re.I,
    ).strip()
    # Lowercase, replace spaces/special chars with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return name


async def get_populated_cities(state_code: str, min_pop: int = MIN_POPULATION) -> set[str]:
    """
    Query Census ACS5 for all places in a state with population >= min_pop.
    Returns a set of normalized city-name slugs (e.g. {'draper', 'provo', ...}).
    """
    fips = STATE_FIPS.get(state_code.upper())
    if not fips:
        logger.warning("No FIPS code for state %s — skipping population filter", state_code)
        return set()

    url = (
        f"{CENSUS_API}?get=NAME,B01003_001E"
        f"&for=place:*&in=state:{fips}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as exc:
        logger.warning("Census API failed for %s: %s — skipping population filter", state_code, exc)
        return set()

    # rows[0] is header: ['NAME', 'B01003_001E', 'state', 'place']
    populated = set()
    for row in rows[1:]:
        try:
            pop = int(row[1]) if row[1] else 0
        except (ValueError, TypeError):
            pop = 0
        if pop >= min_pop:
            populated.add(_normalize_city_name(row[0]))

    logger.info("  %d places in %s with population >= %d", len(populated), state_code, min_pop)
    return populated


def _city_slug_matches(city_slug: str, populated: set[str]) -> bool:
    """Check if a Zoneomics city slug (e.g. 'salt-lake-city-UT') is in the populated set."""
    # Strip state suffix: 'salt-lake-city-UT' → 'salt-lake-city'
    name = re.sub(r"-[A-Z]{2}$", "", city_slug)
    return name in populated


# ─── Zoneomics scraping helpers ───────────────────────────────────────────────

async def get_cities_for_state(state_slug: str, client: httpx.AsyncClient) -> list[str]:
    """Return list of city URL slugs like ['draper-UT', 'provo-UT', ...]"""
    url = f"{ZONEOMICS_BASE}/{state_slug}"
    try:
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to fetch state page %s: %s", url, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cities = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Match /code/city-ST pattern
        m = re.match(r"^/code/([a-z0-9][a-z0-9\-]+-[A-Z]{2})$", href)
        if m:
            cities.append(m.group(1))
    return list(dict.fromkeys(cities))  # dedupe, preserve order


async def get_relevant_chapters(city_slug: str, client: httpx.AsyncClient) -> list[str]:
    """
    Fetch the city's Zoneomics page and return URLs of chapters that likely
    contain zoning use tables based on title keywords.
    Falls back to MANUAL_OVERRIDES for cities not indexed by Zoneomics.
    """
    if city_slug in MANUAL_OVERRIDES:
        logger.info("  %s — using manual override (%d URLs)", city_slug, len(MANUAL_OVERRIDES[city_slug]))
        return MANUAL_OVERRIDES[city_slug]

    url = f"{ZONEOMICS_BASE}/{city_slug}"
    try:
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch city page %s: %s", url, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen_hrefs: set[str] = set()
    relevant = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.match(rf"^/code/{re.escape(city_slug)}/chapter_\d+$", href):
            continue
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        title = a.get_text(strip=True).lower()
        if any(kw in title for kw in USE_TABLE_KEYWORDS) and \
           not any(ex in title for ex in EXCLUDE_KEYWORDS):
            relevant.append(f"https://www.zoneomics.com{href}")

    return relevant


# ─── DB helpers ───────────────────────────────────────────────────────────────

async def get_or_create_jurisdiction(
    db, city_slug: str, state_code: str
) -> Jurisdiction:
    """Return existing Jurisdiction or create a minimal stub."""
    # Convert slug like "draper-UT" → "Draper, UT"
    city_part = city_slug[: -(len(state_code) + 1)]  # strip "-UT"
    city_name = city_part.replace("-", " ").title()
    full_name = f"{city_name}, {state_code}"

    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.name == full_name)
    )
    j = result.scalars().first()
    if j is None:
        j = Jurisdiction(name=full_name, state=state_code, county=None)
        db.add(j)
        await db.flush()
        logger.info("  Created jurisdiction stub: %s", full_name)
    return j


async def upsert_zones(db, jurisdiction_id, zones, deduped: bool = False) -> int:
    """Confidence-gated upsert — only overwrites if new confidence is higher."""
    seen: dict[str, object] = {}
    for z in zones:
        if z.code not in seen or z.confidence > seen[z.code].confidence:
            seen[z.code] = z

    count = 0
    for zone in seen.values():
        stmt = pg_insert(ZoneUseMatrix).values(
            jurisdiction_id=jurisdiction_id,
            zone_code=zone.code,
            zone_name=zone.name,
            self_storage=zone.self_storage,
            mini_warehouse=zone.mini_warehouse,
            light_industrial=zone.light_industrial,
            luxury_garage_condo=zone.luxury_garage_condo,
            citations=[c.model_dump() for c in zone.citations] if zone.citations else None,
            confidence=zone.confidence,
            notes=zone.notes,
        ).on_conflict_do_update(
            constraint="uq_zone_matrix",
            set_=dict(
                zone_name=zone.name,
                self_storage=zone.self_storage,
                mini_warehouse=zone.mini_warehouse,
                light_industrial=zone.light_industrial,
                luxury_garage_condo=zone.luxury_garage_condo,
                citations=[c.model_dump() for c in zone.citations] if zone.citations else None,
                confidence=zone.confidence,
                notes=zone.notes,
            ),
            where=ZoneUseMatrix.confidence < zone.confidence,
        )
        await db.execute(stmt)
        count += 1
    return count


# ─── Per-city processor ───────────────────────────────────────────────────────

async def process_city(city_slug: str, state_code: str, dry_run: bool = False) -> dict:
    """
    Full pipeline for one city. Returns a result dict.
    Creates its own DB session.
    """
    result = {
        "city": city_slug,
        "chapters_found": 0,
        "zones_saved": 0,
        "skipped": False,
        "error": None,
    }

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; ZoningFinderBot/1.0)"},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        chapter_urls = await get_relevant_chapters(city_slug, client)

    if not chapter_urls:
        logger.info("  %s — no relevant chapters found, skipping", city_slug)
        result["skipped"] = True
        return result

    result["chapters_found"] = len(chapter_urls)
    logger.info("  %s — %d relevant chapters: %s", city_slug, len(chapter_urls),
                [u.split("/")[-1] for u in chapter_urls])

    if dry_run:
        return result

    all_zones = []
    for ch_url in chapter_urls:
        try:
            sections = await fetch_from_url(ch_url)
            if not sections:
                continue
            combined = "\n\n".join(
                f"[Section {s.section_id}: {s.heading}]\n{s.text}" for s in sections
            )
            city_name = city_slug[: -(len(state_code) + 1)].replace("-", " ").title()
            output = await parse_ordinance_sections(combined, f"{city_name}, {state_code}", [])
            all_zones.extend(output.zones)
            logger.info("    %s → %d zones parsed", ch_url.split("/")[-1], len(output.zones))
            await asyncio.sleep(1)  # be polite to Zoneomics
        except Exception as exc:
            logger.warning("    Failed %s: %s", ch_url, exc)

    if not all_zones:
        result["skipped"] = True
        return result

    async with async_session_maker() as db:
        try:
            j = await get_or_create_jurisdiction(db, city_slug, state_code)
            j.ordinance_url = f"{ZONEOMICS_BASE}/{city_slug}"
            saved = await upsert_zones(db, j.id, all_zones)
            await db.commit()
            result["zones_saved"] = saved
        except Exception as exc:
            logger.error("  DB error for %s: %s", city_slug, exc)
            result["error"] = str(exc)

    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(states: list[str], limit: int | None, dry_run: bool, concurrency: int) -> None:
    # Map CLI state codes (UT, NJ…) to Zoneomics slugs (utah, new-jersey…)
    slug_to_code = {v: k for k, v in
                    {slug: code for slug, code in STATE_CODES.items()}.items()}
    # Invert properly
    code_to_slug = {code: slug for slug, code in STATE_CODES.items()}

    all_cities: list[tuple[str, str]] = []  # (city_slug, state_code)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; ZoningFinderBot/1.0)"},
        follow_redirects=True,
    ) as client:
        for state_code in states:
            state_slug = code_to_slug.get(state_code.upper())
            if not state_slug:
                logger.error("Unknown state code: %s", state_code)
                continue
            logger.info("Fetching city list for %s (%s)…", state_code, state_slug)
            cities = await get_cities_for_state(state_slug, client)
            logger.info("  Found %d cities in %s", len(cities), state_code)

            # Filter by population
            populated = await get_populated_cities(state_code.upper(), min_pop=MIN_POPULATION)
            if populated:
                before = len(cities)
                cities = [c for c in cities if _city_slug_matches(c, populated)]
                logger.info("  After population filter (>=%d): %d → %d cities",
                            MIN_POPULATION, before, len(cities))

            all_cities.extend((c, state_code.upper()) for c in cities)
            await asyncio.sleep(0.5)

    if limit:
        all_cities = all_cities[:limit]

    logger.info("Processing %d cities total (dry_run=%s, concurrency=%d)",
                len(all_cities), dry_run, concurrency)

    # Process with bounded concurrency
    sem = asyncio.Semaphore(concurrency)
    success = skipped = errors = total_zones = 0

    async def bounded(city_slug, state_code):
        async with sem:
            r = await process_city(city_slug, state_code, dry_run=dry_run)
            await asyncio.sleep(0.5)
            return r

    tasks = [bounded(cs, sc) for cs, sc in all_cities]
    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        r = await coro
        if r["error"]:
            errors += 1
            logger.error("FAIL %s: %s", r["city"], r["error"])
        elif r["skipped"]:
            skipped += 1
        else:
            success += 1
            total_zones += r["zones_saved"]
        if i % 10 == 0:
            logger.info("Progress: %d/%d (✓%d skip%d err%d zones%d)",
                        i, len(all_cities), success, skipped, errors, total_zones)

    logger.info("\n=== DONE ===")
    logger.info("Cities processed: %d", len(all_cities))
    logger.info("Successful:       %d", success)
    logger.info("Skipped:          %d (no relevant chapters found)", skipped)
    logger.info("Errors:           %d", errors)
    logger.info("Total zones saved: %d", total_zones)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch-populate zone_use_matrix from Zoneomics")
    parser.add_argument("--states", nargs="+", required=True,
                        help="State codes to process, e.g. UT NJ PA FL TX NV")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max cities to process (for test runs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover chapters only, don't call Claude or write to DB")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="Number of cities to process in parallel (default 3)")
    args = parser.parse_args()

    asyncio.run(main(args.states, args.limit, args.dry_run, args.concurrency))
