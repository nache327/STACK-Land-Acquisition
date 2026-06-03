"""Additive asyncpg PostGIS ingest for Op-5 factory polygons.

This helper is the additive insert path the Garfield/Fort Lee/Hackensack
adjudication scripts used during the proof. It tags every row with
``raw_attributes->>'op5_town'`` so the spatial backfill (PR #172) and the
audit can scope to just the muni we just ingested without touching the
existing op-5 proof districts on preview.

Hard rule: REFUSE to run unless ``DATABASE_URL`` contains the preview
ref ``bbvywbpxwsoyvdvygvyw``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger("op5_lib.ingestion_helpers")

PREVIEW_REF = "bbvywbpxwsoyvdvygvyw"
BERGEN_ID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"


def load_db_url() -> str:
    """Read DATABASE_URL from env or repo-root ``.env``.

    Returns the native ``postgresql://`` form (asyncpg dialect prefix
    stripped) — asyncpg connect doesn't accept the SQLAlchemy URI scheme.
    """
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        for candidate in (Path(".env"), Path(__file__).resolve().parents[3] / ".env"):
            if candidate.exists():
                for line in candidate.read_text().splitlines():
                    if line.startswith("DATABASE_URL="):
                        raw = line.split("=", 1)[1].strip()
                        break
                if raw:
                    break
    if not raw:
        raise RuntimeError("DATABASE_URL not found in environment or .env")
    return raw.replace("postgresql+asyncpg://", "postgresql://")


def assert_preview_url(url: str) -> None:
    """Refuse to run if the URL doesn't point at the Op-5 preview branch."""
    if PREVIEW_REF not in url:
        raise RuntimeError(
            f"Refusing Op-5 factory ingest: DATABASE_URL is not preview ref {PREVIEW_REF}"
        )


def zone_class_guess(code: str) -> str:
    """Cheap zone-class inference. The matrix step is the source of truth;
    this just ensures the NOT-NULL enum column has a non-bogus value.
    """
    if not code:
        return "unknown"
    upper = code.strip().upper()
    if upper.startswith("R") or "RES" in upper:
        return "residential"
    if upper.startswith("B") or upper.startswith("C") or "COMM" in upper:
        return "commercial"
    if upper.startswith("I") or upper.startswith("LM") or "IND" in upper:
        return "industrial"
    if upper in {"P", "PARK", "OS", "OPEN"}:
        return "open_space"
    if "MIXED" in upper or upper.startswith("MX"):
        return "mixed_use"
    return "unknown"


async def lookup_jurisdiction_id(
    conn,  # asyncpg.Connection
    *, county: str, state: str = "NJ",
) -> Optional[str]:
    """Find the parcels-bearing jurisdiction id for the county.

    Tries ``ILIKE '%<county>%'`` AND ``state = <state>`` first. Bergen has
    a known UUID so we short-circuit there to avoid mis-matching parent
    jurisdiction rows.
    """
    if county.strip().lower() == "bergen":
        return BERGEN_ID
    row = await conn.fetchrow(
        """
        SELECT id::text AS id
        FROM jurisdictions
        WHERE state = $1
          AND name ILIKE $2
        ORDER BY name
        LIMIT 1
        """,
        state,
        f"%{county}%",
    )
    return row["id"] if row else None


async def ingest_polygons_additive(
    conn,  # asyncpg.Connection
    *,
    jurisdiction_id: str,
    op5_town: str,
    polygons: list[dict],
    confidence_default: float = 0.75,
) -> int:
    """Additive insert of factory polygons.

    Each polygon dict shape::

        {
            "zone_code": "R-1",
            "confidence": 0.92,
            "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]},
            "color_rgb": [r, g, b],  # optional
        }

    We delete any prior rows tagged with the SAME ``op5_town`` so re-runs
    are idempotent within the factory tag-namespace, but we never touch
    other towns' rows or non-factory rows.
    """
    # Clear any prior factory rows for THIS muni only (idempotent re-run).
    await conn.execute(
        """
        DELETE FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
          AND raw_attributes->>'op5_town' = $2
          AND raw_attributes->>'op5_factory' = 'true'
        """,
        jurisdiction_id,
        op5_town,
    )
    inserted = 0
    for poly in polygons:
        zone_code = (poly.get("zone_code") or "").strip()
        if not zone_code:
            continue
        geom = poly.get("geometry")
        if not geom:
            continue
        geom_json = json.dumps(geom)
        # geom_hash mirrors zoning_ingestion._geom_hash so the dedup key
        # behaves the same way across paths.
        geom_hash = hashlib.sha1(geom_json.encode()).hexdigest()[:32]
        raw_attributes = {
            "op5_town": op5_town,
            "op5_factory": "true",
            "op5_factory_stage": "cp3",
            "op5_zone_code": zone_code,
            "confidence": poly.get("confidence", confidence_default),
        }
        if poly.get("color_rgb"):
            raw_attributes["op5_color_rgb"] = poly["color_rgb"]
        await conn.execute(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class, raw_attributes,
                geom, centroid, source, confidence, human_reviewed, geom_hash, updated_at
            ) VALUES (
                $1::uuid, $2, $2, $3::zone_class_enum, $4::jsonb,
                ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON($5)), 4326),
                ST_PointOnSurface(ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON($5)), 4326)),
                'ordinance'::zone_source_enum, $6, false, $7, now()
            )
            ON CONFLICT ON CONSTRAINT uq_zoning_districts_jur_code_hash DO NOTHING
            """,
            jurisdiction_id,
            zone_code,
            zone_class_guess(zone_code),
            json.dumps(raw_attributes),
            geom_json,
            float(poly.get("confidence", confidence_default)),
            geom_hash,
        )
        inserted += 1
    return inserted
