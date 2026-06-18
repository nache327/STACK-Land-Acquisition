"""Phase 7B.1 — Maricopa County AZ city limits spatial-join (Pierce Task E pattern).

Companion to ingest_maricopa_az_parcels.py. Per Diagnostic PR #232: raw
`PropertyCity='SCOTTSDALE'` parcel bbox FAILS the 50% Class A primitive
against Scottsdale's city zoning layer — postal-city noise extends well
beyond actual city limits. This script ingests the canonical Maricopa
County city limits layer and rewrites parcels.city via spatial join,
giving Phase 7B.2 per-muni registration a clean substrate.

Same shape as PR #285 Pierce Task E (WA City Limits → Pierce parcels).

Source: Maricopa County GIS Reference/ParcelCityCounty/MapServer/1
  https://gis.maricopa.gov/arcgis/rest/services/Reference/
  ParcelCityCounty/MapServer/1

Live probes (2026-06-18):
  - Feature count : 646 polygons (dissolved by CityName from
                    CityOrdinance_RISC annexation feature class)
  - Geom          : Polygon, SR 102100 (Web Mercator → outSR=4326)
  - Code field    : CityName (e.g. 'SCOTTSDALE', 'PARADISE VALLEY')
  - Aux field     : FullCityName ('City of Scottsdale', 'Town of …')
  - Authority     : Same publisher as Parcel_Data_View (county GIS)

All 5 target munis confirmed present as distinct polygons:
  SCOTTSDALE, PARADISE VALLEY, CAVE CREEK, FOUNTAIN HILLS, CAREFREE

Subcommands:

  preflight  Probe layer + count target-muni polygons. NO DB WRITES.
  fire       Ingest city polygons + rewrite Maricopa parcels.city via
             ST_Within(centroid, city_polygon). Idempotent.

Hard rules honored:
  - PR #285 WKT-via-PostGIS + PR #303 degenerate-ring skip
  - UPPERCASE CityName preserved (matches PropertyCity verbatim)
  - raw_attributes preserved on parcels (Norfolk gate — UPDATE only
    touches parcels.city; raw column untouched)
  - Skip ROLLBACK preflight at scale (PR #253)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("maricopa_city_limits")

LAYER_URL = (
    "https://gis.maricopa.gov/arcgis/rest/services/"
    "Reference/ParcelCityCounty/MapServer/1"
)
TARGET_MUNIS = (
    "SCOTTSDALE", "PARADISE VALLEY", "CAVE CREEK",
    "FOUNTAIN HILLS", "CAREFREE",
)
PAGE_SIZE = 1000


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _fetch_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": 4326, "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE, "f": "json",
            "orderByFields": "OBJECTID",
        }
        r = await client.get(f"{LAYER_URL}/query", params=params)
        r.raise_for_status()
        batch = r.json().get("features", [])
        features.extend(batch)
        logger.info("fetched %d (cumulative %d) offset=%d",
                    len(batch), len(features), offset)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return features


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """PR #285 + PR #303 — emit each ring as separate polygon body in
    MULTIPOLYGON, skip degenerate rings (<4 points), let PostGIS
    reconstruct topology via ST_Multi(ST_MakeValid(...))."""
    ring_wkts = []
    for r in rings:
        if len(r) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Maricopa city limits ===\n")
    async with httpx.AsyncClient(timeout=120.0) as client:
        features = await _fetch_features(client)
    print(f"  total features  : {len(features)}")
    by_city: dict[str, int] = {}
    for f in features:
        cn = (f.get("attributes") or {}).get("CityName") or "(blank)"
        by_city[cn] = by_city.get(cn, 0) + 1
    print(f"  distinct cities : {len(by_city)}")
    print(f"\n  Top 15 by polygon count:")
    for c, n in sorted(by_city.items(), key=lambda x: -x[1])[:15]:
        print(f"    {c:25s} {n}")
    print(f"\n  Target munis presence:")
    for m in TARGET_MUNIS:
        n = by_city.get(m, 0)
        print(f"    {m:18s} {n} polygons")
    print("\n(NO DB WRITES)")
    return 0


async def _fire(jid: str) -> int:
    print(f"\n=== FIRE: Maricopa city limits spatial-join ===\n")
    print(f"  target jurisdiction: {jid}")
    async with httpx.AsyncClient(timeout=120.0) as client:
        features = await _fetch_features(client)

    target_polys: list[tuple[str, str]] = []
    skipped = 0
    for f in features:
        attrs = f.get("attributes") or {}
        cn = attrs.get("CityName")
        if cn not in TARGET_MUNIS:
            continue
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            skipped += 1
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping %s polygon: %s", cn, exc)
            skipped += 1
            continue
        target_polys.append((cn, wkt))

    print(f"\n  target polygons collected: {len(target_polys)} (skipped {skipped})")
    by_muni: dict[str, int] = {}
    for cn, _ in target_polys:
        by_muni[cn] = by_muni.get(cn, 0) + 1
    for m in TARGET_MUNIS:
        print(f"    {m:18s} {by_muni.get(m, 0)} polygons → city='{m}'")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        await conn.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS _maricopa_city_limits (
                city_name text,
                geom geometry(MultiPolygon, 4326)
            )
            """
        )
        await conn.execute("TRUNCATE _maricopa_city_limits")
        for cn, wkt in target_polys:
            await conn.execute(
                """
                INSERT INTO _maricopa_city_limits (city_name, geom)
                VALUES ($1, ST_Multi(ST_MakeValid(ST_GeomFromText($2, 4326))))
                """,
                cn, wkt,
            )
        print(f"\n[stage] {len(target_polys)} city-limit polygons staged")

        print(f"\n[rewrite] UPDATE parcels.city via ST_Within centroid…")
        s = await conn.execute(
            """
            UPDATE parcels target
            SET city = sub.city_name
            FROM (
                SELECT p.id AS parcel_id, m.city_name
                FROM parcels p,
                LATERAL (
                    SELECT cl.city_name
                    FROM _maricopa_city_limits cl
                    WHERE ST_Within(ST_Centroid(p.geom), cl.geom)
                    ORDER BY cl.city_name LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.geom IS NOT NULL
            ) sub
            WHERE target.id = sub.parcel_id
              AND (target.city IS DISTINCT FROM sub.city_name)
            """,
            jid,
        )
        n_updated = int(s.split()[-1]) if s.split() else -1
        print(f"[rewrite] parcels.city rewritten on {n_updated} rows")

        print(f"\n=== Per-muni post-rewrite counts ===")
        for muni in TARGET_MUNIS:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2",
                jid, muni,
            )
            print(f"  city={muni:18s}: {n:,} parcels (city-limit prefilter)")

    finally:
        await conn.close()
    return 0


async def main(args) -> int:
    if args.cmd == "preflight":
        return await _preflight()
    if args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
            return 2
        return await _fire(args.maricopa_jid)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    fire = sub.add_parser("fire")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument(
        "--maricopa-jid", required=True,
        help="Maricopa County, AZ jurisdiction UUID from ingest_maricopa_az_parcels register",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args)))
