"""
KMZ/KML competitor import service.

Parses a KMZ (zipped KML) file and inserts all Placemark points into the
competitor_facilities table with data_source='kmz'. Uses full-tree parse
(lxml.etree.parse) so that Style/StyleMap definitions can be resolved for
operator brand extraction.

KMZ records are the authoritative baseline. They always survive the Google
Places deduplication step (Google Places records within 200ft are dropped).
"""
from __future__ import annotations

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

# Map icon filename prefix → operator/brand name
_ICON_TO_OPERATOR: dict[str, str] = {
    "CS Logo": "CubeSmart",
    "PS Logo": "Public Storage",
    "Extra_Space_Storage": "Extra Space Storage",
    "LS Logo": "Life Storage",
    "UH Logo": "Life Storage",  # Uncle Bob's rebranded to Life Storage
    "iStorage": "iStorage",
    "Planet Logo": "Planet Self Storage",
    "Store Space": "Store Space",
    "SROA": "Storage Rentals of America",
    "storem": "StoreMart",
    "SM": "StorageMart",
    "EXR Logo": "Extra Space Storage",  # Extra Space Realty sister brand
    "Simply Logo": "Simply Self Storage",
    "Sentinel": "Sentinel Self Storage",
    "STACK A": "STACK Storage",
    "Privy Properties": "Privy Properties",
}

# Generic Google Maps pushpin colors — no brand, treated as independent
_PUSHPIN_RE = re.compile(r"maps\.google\.com/mapfiles/kml/pushpin")


def _icon_href_to_operator(href: str) -> str | None:
    """Resolve an icon href to an operator brand name, or None if unrecognized."""
    if not href or _PUSHPIN_RE.search(href):
        return None  # generic pushpin = independent/unknown operator
    fname = href.split("/")[-1].rsplit(".", 1)[0]  # strip path + extension
    # Try longest-match first so "Extra_Space_Storage_02" doesn't match "SM"
    for key in sorted(_ICON_TO_OPERATOR, key=len, reverse=True):
        if fname.startswith(key) or key.replace(" ", "_") in fname:
            return _ICON_TO_OPERATOR[key]
    return None


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

        pin_type = placemark.get("pin_type", "unknown")
        if pin_type in ("white", "green"):
            skipped += 1
            continue

        lng, lat = coords
        sq_ft, sqft_source = _extract_sqft(placemark)
        external_id = placemark.get("id") or None

        # Merge pin_type and icon_href into attributes
        attrs: dict = dict(placemark.get("extended_data") or {})
        attrs["pin_type"] = pin_type
        icon_href = placemark.get("icon_href", "")
        if icon_href:
            attrs["icon_href"] = icon_href

        row = dict(
            name=placemark.get("name"),
            operator=placemark.get("operator"),
            address=placemark.get("address"),
            sq_ft=sq_ft,
            sqft_source=sqft_source,
            data_source="kmz",
            external_id=external_id,
            attributes=attrs or None,
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
    logger.info("KMZ import: %d inserted, %d skipped (no point coords)", inserted, skipped)
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
    Unzip the KMZ and parse the KML with full-tree parsing so Style/StyleMap
    elements can be resolved for operator brand extraction.
    """
    from lxml import etree

    with zipfile.ZipFile(file_obj) as zf:
        kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise ValueError("No .kml file found inside the KMZ archive")
        root_kml = next((n for n in kml_names if "/" not in n), kml_names[0])
        with zf.open(root_kml) as f:
            kml_bytes = f.read()

    root = etree.fromstring(kml_bytes)
    ns = root.nsmap.get(None, "")
    p = f"{{{ns}}}" if ns else ""

    # Build style_id → icon href map
    style_icon: dict[str, str] = {}
    # Build style_id → color (ABGR hex string from <IconStyle><color>)
    style_color: dict[str, str] = {}
    for style in root.iter(f"{p}Style"):
        sid = style.get("id")
        icon = style.find(f".//{p}Icon/{p}href")
        if sid and icon is not None and icon.text:
            style_icon[sid] = icon.text.strip()
        color_el = style.find(f".//{p}IconStyle/{p}color")
        if sid and color_el is not None and color_el.text:
            style_color[sid] = color_el.text.strip().lower()

    # Build styleMap_id → normal style_id (follow normal pair)
    style_map: dict[str, str] = {}
    for sm in root.iter(f"{p}StyleMap"):
        smid = sm.get("id")
        if not smid:
            continue
        for pair in sm.findall(f"{p}Pair"):
            key = pair.find(f"{p}key")
            url = pair.find(f"{p}styleUrl")
            if key is not None and key.text == "normal" and url is not None:
                style_map[smid] = url.text.lstrip("#")

    def _resolve_icon(style_url: str) -> str:
        sid = style_url.lstrip("#")
        if sid in style_map:
            sid = style_map[sid]
        return style_icon.get(sid, "")

    def _resolve_color(style_url: str) -> str:
        sid = style_url.lstrip("#")
        if sid in style_map:
            sid = style_map[sid]
        return style_color.get(sid, "")

    def _classify_pin_type(href: str, color: str) -> str:
        fname = href.split("/")[-1].rsplit(".", 1)[0].lower() if href else ""
        # REIT operator icon → "reit"
        if href and _icon_href_to_operator(href) is not None:
            return "reit"
        # Yellow pushpin
        if "ylw" in fname or "ylw" in href.lower():
            return "yellow"
        # White pushpin
        if "wht" in fname or color == "ffffffff":
            return "white"
        # Green pushpin
        if "grn" in fname or color in ("ff00ff00", "ff008000"):
            return "green"
        return "unknown"

    for pm in root.iter(f"{p}Placemark"):
        # Resolve style for this placemark
        su_el = pm.find(f"{p}styleUrl")
        if su_el is None:
            su_el = pm.find("styleUrl")
        pin_type = "unknown"
        icon_href = ""
        if su_el is not None and su_el.text:
            icon_href = _resolve_icon(su_el.text.strip())
            color = _resolve_color(su_el.text.strip())
            pin_type = _classify_pin_type(icon_href, color)

        placemark = _extract_placemark(pm, p, _resolve_icon, pin_type, icon_href)
        yield placemark


def _extract_placemark(elem, p: str, resolve_icon, pin_type: str = "unknown", icon_href: str = "") -> dict:
    """Extract coord, name, operator, address, and extended data from a Placemark."""

    def _find(tag: str):
        """Find child with namespace prefix, falling back to no-namespace."""
        el = elem.find(f"{p}{tag}")
        if el is None:
            el = elem.find(tag)
        return el

    def _find_deep(tag: str):
        """Descendant search with namespace prefix, falling back to no-namespace."""
        el = elem.find(f".//{p}{tag}")
        if el is None:
            el = elem.find(f".//{tag}")
        return el

    name_el = _find("name")
    name = (name_el.text or "").strip() or None if name_el is not None else None

    placemark_id = elem.get("id") or None

    addr_el = _find("address")
    address = (addr_el.text or "").strip() or None if addr_el is not None else None

    # Operator from styleUrl → icon href → brand map
    su_el = _find("styleUrl")
    operator: str | None = None
    if su_el is not None and su_el.text:
        href = resolve_icon(su_el.text.strip())
        operator = _icon_href_to_operator(href)

    # Coordinates — only from Point (skip Polygon/LineString)
    coords: tuple[float, float] | None = None
    point_el = _find_deep("Point")
    if point_el is not None:
        coord_el = point_el.find(f"{p}coordinates")
        if coord_el is None:
            coord_el = point_el.find("coordinates")
        if coord_el is not None and coord_el.text:
            raw = coord_el.text.strip().split()[0]
            parts = raw.split(",")
            if len(parts) >= 2:
                try:
                    coords = (float(parts[0]), float(parts[1]))
                except ValueError:
                    pass

    # ExtendedData
    extended: dict[str, str] = {}
    for data_el in list(elem.findall(f".//{p}Data")) + list(elem.findall(".//Data")):
        key = data_el.get("name", "")
        val = data_el.find(f"{p}value")
        if val is None:
            val = data_el.find("value")
        if key and val is not None and val.text:
            extended[key] = val.text.strip()
    for sd in list(elem.findall(f".//{p}SimpleData")) + list(elem.findall(".//SimpleData")):
        key = sd.get("name", "")
        if key and sd.text:
            extended[key] = sd.text.strip()

    return {
        "id": placemark_id,
        "name": name,
        "operator": operator,
        "address": address,
        "coords": coords,
        "extended_data": extended or None,
        "pin_type": pin_type,
        "icon_href": icon_href,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_sqft(placemark: dict) -> tuple[int | None, str]:
    """Search ExtendedData for a square footage field."""
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
    """Bulk-insert a batch of competitor rows."""
    if not batch:
        return 0
    stmt = pg_insert(CompetitorFacility)
    await db.execute(stmt, batch)
    return len(batch)
