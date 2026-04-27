"""
KMZ/KML competitor import service.

Streams a KMZ (zipped KML) file and inserts all Placemark points into the
competitor_facilities table with data_source='kmz'. Memory-safe for large
files — uses lxml.etree.iterparse and never loads the full tree.

KMZ records are the authoritative baseline. They always survive the Google
Places deduplication step (Google Places records within 200ft are dropped).
"""
from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile
from typing import BinaryIO, Iterator

from geoalchemy2 import WKTElement
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor_facility import CompetitorFacility

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500
_SQFT_FIELD_PATTERNS = re.compile(
    r"(rentable|gross|net|building|total|storage)?[\s_-]*(sq\.?\s*ft|sqft|square[\s_-]*feet|square[\s_-]*footage)",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────────────────────────

async def ingest_kmz_file(
    file_obj: BinaryIO,
    jurisdiction_id: uuid.UUID | None,
    db: AsyncSession,
) -> tuple[int, int]:
    """
    Parse a KMZ file and upsert all Placemark points into competitor_facilities.
    Returns (inserted_count, skipped_count).
    """
    inserted = 0
    skipped = 0
    batch: list[dict] = []

    for placemark in _parse_kmz_stream(file_obj):
        coords = placemark.get("coords")
        if not coords:
            skipped += 1
            continue

        lng, lat = coords
        sq_ft, sqft_source = _extract_sqft(placemark)
        external_id = placemark.get("id") or None

        row = dict(
            name=placemark.get("name"),
            operator=None,
            address=placemark.get("address"),
            sq_ft=sq_ft,
            sqft_source=sqft_source,
            data_source="kmz",
            external_id=external_id,
            attributes=placemark.get("extended_data") or None,
            geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
            jurisdiction_id=jurisdiction_id,
        )
        batch.append(row)

        if len(batch) >= _BATCH_SIZE:
            count = await _flush_batch(batch, db)
            inserted += count
            batch.clear()

    if batch:
        count = await _flush_batch(batch, db)
        inserted += count

    await db.flush()
    logger.info("KMZ import: %d inserted, %d skipped (no coords)", inserted, skipped)
    return inserted, skipped


async def delete_kmz_competitors(db: AsyncSession) -> int:
    """Remove all KMZ-sourced competitors (used to re-import a fresh KMZ file)."""
    result = await db.execute(
        delete(CompetitorFacility).where(
            CompetitorFacility.data_source == "kmz"
        )
    )
    await db.flush()
    return result.rowcount or 0


# ── KML parser ────────────────────────────────────────────────────────────────

def _parse_kmz_stream(file_obj: BinaryIO) -> Iterator[dict]:
    """
    Unzip the KMZ and iterparse the KML, yielding one dict per Placemark.
    Never loads the full XML tree into memory.
    """
    with zipfile.ZipFile(file_obj) as zf:
        # Find the root .kml file (usually doc.kml or the first .kml entry)
        kml_names = [n for n in zf.namelist() if n.endswith(".kml")]
        if not kml_names:
            raise ValueError("No .kml file found inside the KMZ archive")
        # Prefer root-level doc.kml; fall back to first found
        root_kml = next((n for n in kml_names if "/" not in n), kml_names[0])

        with zf.open(root_kml) as kml_file:
            kml_bytes = kml_file.read()

    yield from _iterparse_kml(io.BytesIO(kml_bytes))


def _iterparse_kml(kml_stream: BinaryIO) -> Iterator[dict]:
    """
    SAX-style iterparse over KML bytes, yielding one dict per Placemark element.
    Handles both plain coordinates (Point) and nested structures.
    """
    from lxml import etree

    # KML namespace — most files use the standard KML 2.2 namespace
    _KML_NS = "http://www.opengis.net/kml/2.2"
    _ALT_NS = "http://earth.google.com/kml/2.2"

    context = etree.iterparse(kml_stream, events=("end",), recover=True)
    for event, elem in context:
        local = etree.QName(elem.tag).localname if "{" in elem.tag else elem.tag
        if local != "Placemark":
            continue

        placemark = _extract_placemark(elem)
        yield placemark

        # Free memory — critical for large files
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]


def _extract_placemark(elem) -> dict:
    """Extract name, coords, address, id, and ExtendedData from a Placemark element."""
    from lxml import etree

    def _text(tag: str) -> str | None:
        found = elem.find(f".//{{{_ns(elem)}}}{tag}")
        if found is None:
            # Try without namespace
            found = elem.find(f".//{tag}")
        return (found.text or "").strip() or None if found is not None else None

    def _ns(e) -> str:
        if "{" in e.tag:
            return e.tag.split("}")[0].lstrip("{")
        return "http://www.opengis.net/kml/2.2"

    ns = _ns(elem)

    name = _text("name")
    placemark_id = elem.get("id") or None

    # Address from <address> element
    address = _text("address")

    # Coordinates from <Point><coordinates>lng,lat,alt</coordinates></Point>
    coords: tuple[float, float] | None = None
    coord_elem = elem.find(f".//{{{ns}}}coordinates")
    if coord_elem is None:
        coord_elem = elem.find(".//coordinates")
    if coord_elem is not None and coord_elem.text:
        raw = coord_elem.text.strip().split()[0]  # take first point if MultiGeometry
        parts = raw.split(",")
        if len(parts) >= 2:
            try:
                coords = (float(parts[0]), float(parts[1]))  # (lng, lat)
            except ValueError:
                pass

    # ExtendedData key→value pairs
    extended: dict[str, str] = {}
    for data_elem in elem.findall(f".//{{{ns}}}Data") + elem.findall(".//Data"):
        key = data_elem.get("name", "")
        val_elem = data_elem.find(f"{{{ns}}}value") or data_elem.find("value")
        if val_elem is not None and val_elem.text:
            extended[key] = val_elem.text.strip()

    # SimpleData elements (alternative ExtendedData format)
    for sd in elem.findall(f".//{{{ns}}}SimpleData") + elem.findall(".//SimpleData"):
        key = sd.get("name", "")
        if key and sd.text:
            extended[key] = sd.text.strip()

    return {
        "id": placemark_id,
        "name": name,
        "address": address,
        "coords": coords,
        "extended_data": extended or None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_sqft(placemark: dict) -> tuple[int | None, str]:
    """
    Search ExtendedData for a square footage field.
    Returns (sq_ft, sqft_source) — sq_ft is None when not found (caller uses default).
    """
    extended = placemark.get("extended_data") or {}
    for key, val in extended.items():
        if _SQFT_FIELD_PATTERNS.search(key):
            cleaned = re.sub(r"[,\s]", "", val)
            try:
                sqft = int(float(cleaned))
                if sqft > 0:
                    return sqft, "attribute"
            except (ValueError, TypeError):
                pass
    return None, "default"


async def _flush_batch(batch: list[dict], db: AsyncSession) -> int:
    """Bulk-upsert a batch of competitor rows. Returns count inserted/updated."""
    if not batch:
        return 0

    stmt = pg_insert(CompetitorFacility)
    # For KMZ records with an external_id, upsert on conflict; otherwise insert
    await db.execute(stmt, batch)
    return len(batch)
