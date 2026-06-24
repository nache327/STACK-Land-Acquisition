"""Phase 7H.x — Medford NJ Class B per-muni zoning adapter.

NACHE HAND-OFF ARTIFACT — PREP, DO NOT FIRE from this PR.

Medford Township is a Burlington County, NJ municipality. Burlington is nache's
domain; this script is a hand-off proof artifact, not an authorization to fire.

Pattern: PR #334 Winnetka single-file adapter + Burlington county/muni matrix
discipline. Burlington remains the product jurisdiction; Medford is preserved as
the municipality key in zoning raw_attributes and parcel filters:

  - jurisdiction_id       = Burlington County, NJ
  - parcels.city          = "Medford township"
  - zoning raw stamp      = municipality="Medford township"
  - zone_use_matrix scope = municipality="Medford township"

Diagnostic PR #369 / prior bind-test context:
  - ZoningHub FeatureServer is live and code-bearing.
  - Source has 94 zoning polygons.
  - Zone code field is `Layer`.
  - Prior Stage-1 bind-test reached 9,877 / 9,880 Medford parcels zoned
    by centroid PIP, with remaining matrix gap only GD / CC / PD.

Source:
  https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/
  ME0295_ZoningDistricts_04282023/FeatureServer/0

Idempotency:
  A fire/dry-run wraps Medford zoning cleanup, Medford parcel zoning reset,
  zoning INSERT, spatial backfill, and a preview report in one transaction.
  --dry-run raises a rollback sentinel so no prod writes survive. Real fire
  requires --i-know-this-writes-to-prod.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import shape

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("medford_nj")

BURLINGTON_JID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"
JURISDICTION_NAME = "Burlington County, NJ"
JURISDICTION_STATE = "NJ"
MUNI = "Medford township"
ZONING_AUTHORITY = "Medford Township"

ZONING_LAYER_URL = (
    "https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/"
    "ME0295_ZoningDistricts_04282023/FeatureServer/0"
)
ZONING_WHERE = "Layer IS NOT NULL"
ZONING_CODE_FIELD = "Layer"

ORDINANCE_URL = "https://ecode360.com/ME0295"
MAP_URL = "https://medfordtownship.com/wp-content/uploads/2025/02/Zoning-Map1-8-2025-ORD-2025-1.pdf"

PAGE_SIZE = 2000
MIN_MEDFORD_PARCELS = 1000

# Burlington / Medford sanity envelope.
BBOX_LON_RANGE = (-75.00, -74.70)
BBOX_LAT_RANGE = (39.78, 40.05)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_geom(geom_json: dict | None) -> Any:
    if not geom_json:
        return None
    try:
        geom = shape(geom_json)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.is_empty:
            return None
        return geom
    except Exception:
        return None


async def _fetch_count(client: httpx.AsyncClient) -> int:
    response = await client.get(
        f"{ZONING_LAYER_URL}/query",
        params={"where": ZONING_WHERE, "returnCountOnly": "true", "f": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


async def _fetch_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(
            f"{ZONING_LAYER_URL}/query",
            params={
                "where": ZONING_WHERE,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "orderByFields": "FID",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        out.extend(batch)
        logger.info("fetched %d Medford zoning features (cum %d)", len(batch), len(out))
        if len(batch) < PAGE_SIZE:
            return out
        offset += PAGE_SIZE


def _build_zoning_rows(features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {"geom_skipped": 0, "blank_zone": 0}
    rows: list[dict[str, Any]] = []
    for feat in features:
        attrs = feat.get("properties") or {}
        geom = _parse_geom(feat.get("geometry"))
        if geom is None:
            stats["geom_skipped"] += 1
            continue
        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            stats["geom_skipped"] += 1
            continue
        zone_code = _clean_text(attrs.get(ZONING_CODE_FIELD))
        if not zone_code:
            stats["blank_zone"] += 1
            continue
        raw = {
            "source_url": ZONING_LAYER_URL,
            "source_kind": "arcgis_feature_server",
            "source_filter": ZONING_WHERE,
            "municipality": MUNI,
            "muni_name": MUNI,
            "muni_type": "township",
            "zoning_authority": ZONING_AUTHORITY,
            "ordinance_url": ORDINANCE_URL,
            "map_url": MAP_URL,
            "zone_code_field": ZONING_CODE_FIELD,
            "ingested_at": "2026-06-23",
        }
        for key, value in attrs.items():
            if value is not None:
                raw[key] = value
        geom_wkt = geom.wkt
        geom_hash = hashlib.md5((zone_code + geom_wkt).encode()).hexdigest()
        rows.append(
            {
                "zone_code": zone_code,
                "zone_name": zone_code,
                "geom_wkt": geom_wkt,
                "raw_attributes": json.dumps(raw),
                "geom_hash": geom_hash,
            }
        )
    return rows, stats


async def _verify_burlington(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        "SELECT id, name, state FROM jurisdictions WHERE id=$1::uuid",
        BURLINGTON_JID,
    )
    if not row:
        raise RuntimeError(f"Burlington JID not found: {BURLINGTON_JID}")
    if row["state"] != JURISDICTION_STATE or row["name"] != JURISDICTION_NAME:
        raise RuntimeError(f"unexpected Burlington jurisdiction row: {dict(row)}")


async def _insert_zoning_rows(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> int:
    records = [
        (
            BURLINGTON_JID,
            row["zone_code"],
            row["zone_name"],
            row["geom_wkt"],
            row["raw_attributes"],
            row["geom_hash"],
        )
        for row in rows
    ]
    await conn.executemany(
        """
        INSERT INTO zoning_districts (
            jurisdiction_id, zone_code, zone_name, zone_class,
            geom, centroid, raw_attributes, source, human_reviewed,
            geom_hash, created_at, updated_at
        ) VALUES (
            $1::uuid, $2, $3, 'unknown'::zone_class_enum,
            ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
            ST_Centroid(ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326)))),
            $5::jsonb, 'arcgis'::zone_source_enum, false,
            $6, NOW(), NOW()
        )
        """,
        records,
    )
    return len(rows)


async def _spatial_backfill(
    conn: asyncpg.Connection,
    nearest_meters: float,
) -> tuple[int, int]:
    contained_status = await conn.execute(
        """
        UPDATE parcels target
           SET zoning_code = sub.zone_code,
               zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, z.zone_code, z.zone_class
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_code, zd.zone_class
                      FROM zoning_districts zd
                     WHERE zd.jurisdiction_id = $1::uuid
                       AND zd.raw_attributes->>'municipality' = $2
                       AND zd.geom IS NOT NULL
                       AND ST_Contains(zd.geom, COALESCE(p.centroid, ST_Centroid(p.geom)))
                     ORDER BY ST_Area(zd.geom) ASC, zd.id
                     LIMIT 1
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.city ILIKE 'Medford township%'
                 AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        BURLINGTON_JID,
        MUNI,
    )
    nearest_status = await conn.execute(
        """
        UPDATE parcels target
           SET zoning_code = sub.zone_code,
               zone_class = sub.zone_class,
               zone_binding_method = $3,
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, z.zone_code, z.zone_class
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_code, zd.zone_class
                      FROM zoning_districts zd
                     WHERE zd.jurisdiction_id = $1::uuid
                       AND zd.raw_attributes->>'municipality' = $2
                       AND zd.geom IS NOT NULL
                       AND ST_DWithin(
                           zd.geom::geography,
                           COALESCE(p.centroid, ST_Centroid(p.geom))::geography,
                           $4
                       )
                     ORDER BY ST_Distance(
                         zd.geom::geography,
                         COALESCE(p.centroid, ST_Centroid(p.geom))::geography
                     )
                     LIMIT 1
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.city ILIKE 'Medford township%'
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        BURLINGTON_JID,
        MUNI,
        f"nearest_{int(round(nearest_meters))}m",
        float(nearest_meters),
    )
    return int(contained_status.split()[-1]), int(nearest_status.split()[-1])


async def _medford_bbox(conn: asyncpg.Connection) -> list[float]:
    row = await conn.fetchrow(
        """
        SELECT
            ST_XMin(ST_Extent(geom)) AS minx,
            ST_YMin(ST_Extent(geom)) AS miny,
            ST_XMax(ST_Extent(geom)) AS maxx,
            ST_YMax(ST_Extent(geom)) AS maxy
          FROM parcels
         WHERE jurisdiction_id = $1::uuid
           AND city ILIKE 'Medford township%'
           AND geom IS NOT NULL
        """,
        BURLINGTON_JID,
    )
    if row is None or row["minx"] is None:
        raise RuntimeError("no Medford parcel geometry")
    bbox = [float(row["minx"]), float(row["miny"]), float(row["maxx"]), float(row["maxy"])]
    if not (
        BBOX_LON_RANGE[0] <= bbox[0] <= BBOX_LON_RANGE[1]
        and BBOX_LAT_RANGE[0] <= bbox[1] <= BBOX_LAT_RANGE[1]
    ):
        raise RuntimeError(
            f"Medford bbox {bbox} outside expected range "
            f"(lon {BBOX_LON_RANGE}, lat {BBOX_LAT_RANGE})"
        )
    return bbox


async def _summary(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        WITH p AS (
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (
                    WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                )::int AS bound,
                COUNT(*) FILTER (WHERE zone_binding_method = 'contained')::int AS contained,
                COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%')::int AS nearest,
                COUNT(*) FILTER (WHERE raw IS NULL OR raw='{}'::jsonb)::int AS raw_empty
              FROM parcels
             WHERE jurisdiction_id = $1::uuid
               AND city ILIKE 'Medford township%'
        ),
        z AS (
            SELECT
                COUNT(*)::int AS districts,
                COUNT(DISTINCT zone_code)::int AS codes,
                COUNT(*) FILTER (
                    WHERE raw_attributes IS NULL OR raw_attributes='{}'::jsonb
                )::int AS zoning_raw_empty
              FROM zoning_districts
             WHERE jurisdiction_id = $1::uuid
               AND raw_attributes->>'municipality' = $2
        )
        SELECT * FROM p, z
        """,
        BURLINGTON_JID,
        MUNI,
    )
    return dict(row)


async def _run(dry_run: bool, nearest_meters: float) -> int:
    started = time.monotonic()
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Medford NJ Class B zoning hand-off ===")
    print(f"jurisdiction : {JURISDICTION_NAME} ({BURLINGTON_JID})")
    print(f"municipality : {MUNI}")
    print(f"source       : {ZONING_LAYER_URL}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        source_count = await _fetch_count(client)
        features = await _fetch_features(client)

    rows, stats = _build_zoning_rows(features)
    distinct = sorted({row["zone_code"] for row in rows})
    print("\n[source]")
    print(f"  source count       : {source_count:,}")
    print(f"  features fetched   : {len(features):,}")
    print(f"  zoning rows built  : {len(rows):,}")
    print(f"  build stats        : {stats}")
    print(f"  distinct codes     : {len(distinct)}")
    print(f"  sample codes       : {', '.join(distinct[:25])}")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await _verify_burlington(conn)
        try:
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = 0")

                before = await _summary(conn)
                print("\n[before]")
                print(
                    f"  Medford parcels {before['total']:,}; "
                    f"bound {before['bound']:,}; existing Medford zoning rows "
                    f"{before['districts']:,}"
                )
                if before["total"] < MIN_MEDFORD_PARCELS:
                    raise RuntimeError(
                        f"Medford parcel gate failed: {before['total']} < {MIN_MEDFORD_PARCELS}"
                    )

                cleared_zoning = await conn.execute(
                    """
                    DELETE FROM zoning_districts
                     WHERE jurisdiction_id=$1::uuid
                       AND raw_attributes->>'municipality' = $2
                    """,
                    BURLINGTON_JID,
                    MUNI,
                )
                print(f"[idempotency] cleared {cleared_zoning.split()[-1]} Medford zoning rows")

                reset_parcels = await conn.execute(
                    """
                    UPDATE parcels
                       SET zoning_code = NULL,
                           zone_class = NULL,
                           zone_binding_method = NULL,
                           updated_at = NOW()
                     WHERE jurisdiction_id = $1::uuid
                       AND city ILIKE 'Medford township%'
                    """,
                    BURLINGTON_JID,
                )
                print(f"[idempotency] reset {reset_parcels.split()[-1]} Medford parcels")

                inserted = await _insert_zoning_rows(conn, rows)
                print(f"[zoning] inserted rows: {inserted:,}")

                contained, nearest = await _spatial_backfill(conn, nearest_meters)
                print(f"[spatial] contained UPDATEd {contained:,}")
                print(f"[spatial] nearest_{int(round(nearest_meters))}m UPDATEd {nearest:,}")

                bbox = await _medford_bbox(conn)
                print(f"[bbox] {bbox}")

                after = await _summary(conn)
                cov = 100.0 * after["bound"] / after["total"] if after["total"] else 0.0
                near_pct = 100.0 * after["nearest"] / after["total"] if after["total"] else 0.0
                print("\n=== 5-GATE PREVIEW ===")
                print(f"GATE 1 cov {cov:.1f}% (>=70%) — {'PASS' if cov >= 70 else 'SUB'}")
                print(f"GATE 2 near {near_pct:.1f}% (<30%) — {'PASS' if near_pct < 30 else 'OVER'}")
                print(f"GATE 3 parcel raw empty {after['raw_empty']} — {'PASS' if after['raw_empty'] == 0 else 'FAIL'}")
                print(f"GATE 4 zoning raw empty {after['zoning_raw_empty']} — {'PASS' if after['zoning_raw_empty'] == 0 else 'FAIL'}")
                print(f"GATE 5 districts {after['districts']} / codes {after['codes']} — {'PASS' if after['districts'] > 0 and after['codes'] > 0 else 'FAIL'}")
                print(
                    f"  parcels {after['total']:,} bound {after['bound']:,} "
                    f"contained {after['contained']:,} nearest {after['nearest']:,}"
                )

                distribution = await conn.fetch(
                    """
                    SELECT zoning_code, COUNT(*) AS n
                      FROM parcels
                     WHERE jurisdiction_id=$1::uuid
                       AND city ILIKE 'Medford township%'
                       AND zoning_code IS NOT NULL
                     GROUP BY 1
                     ORDER BY 2 DESC, zoning_code
                    """,
                    BURLINGTON_JID,
                )
                print("\nZoning-code distribution:")
                for row in distribution:
                    print(f"  {row['zoning_code']:10s} {row['n']:>6,}")

                missing_matrix = await conn.fetch(
                    """
                    SELECT p.zoning_code, COUNT(*) AS parcels
                      FROM parcels p
                      LEFT JOIN zone_use_matrix zum
                        ON zum.jurisdiction_id = p.jurisdiction_id
                       AND zum.zone_code = p.zoning_code
                       AND COALESCE(zum.municipality, '') = $2
                       AND zum.deleted_at IS NULL
                     WHERE p.jurisdiction_id = $1::uuid
                       AND p.city ILIKE 'Medford township%'
                       AND p.zoning_code IS NOT NULL
                       AND btrim(p.zoning_code) <> ''
                       AND zum.zone_code IS NULL
                     GROUP BY p.zoning_code
                     ORDER BY COUNT(*) DESC, p.zoning_code
                    """,
                    BURLINGTON_JID,
                    MUNI,
                )
                print("\nMatrix gaps after zoning preview:")
                if not missing_matrix:
                    print("  none")
                for row in missing_matrix:
                    print(f"  {row['zoning_code']:10s} {row['parcels']:>6,}")

                if dry_run:
                    raise _RollbackForDryRun()

        except _RollbackForDryRun:
            print("\n(DRY-RUN — transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    print(f"\ncompleted in {(time.monotonic() - started) / 60:.1f} min")
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the tx context manager to trigger rollback."""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing — pass --dry-run for rollback rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_run(args.dry_run, args.nearest_within_meters)))
