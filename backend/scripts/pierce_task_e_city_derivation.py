"""Task E (Pierce WA city derivation, Phase 6B.1 follow-up).

PR #267 ingested 328,832 Pierce parcels under Pierce County, WA jid
47ff33c8-… but `parcels.city` is uniformly NULL because the upstream
Washington State Current Parcels feed publishes null `SITUS_CITY_NM` for
every Pierce row. All 17 source-field alternates were dead. The HALT
report (`docs/OP5_PIERCE_WA_CITY_FIELD_HALT.md`) recommended the
spatial-join forward fix.

This script implements that fix:

  1. Fetch the canonical WA city limits layer (Census 2020 TIGER place
     boundaries) — 281 incorporated WA cities under
     services1.arcgis.com/slSNGMtvwLJi21om/.../WA_City_Limits/FeatureServer/0
  2. Stage them into a temp table (PostGIS GiST-indexed)
  3. UPDATE parcels SET city = wcl.NAME WHERE ST_Within(centroid, geom)
     scoped to jurisdiction_id = Pierce County's
  4. Verify Gig Harbor count ≈ 3,000 per US Census (2020 population
     12,029 + ~4,000 single-family homes is the rough order)
  5. Spot-check 5 random Gig Harbor parcels for plausible street addresses
  6. Drop temp table

Subcommands:

  preflight  Fetch + report distinct city counts; NO DB writes
  fire       Real prod UPDATE (~3-10 min wall-clock for 328k parcels +
             281 polygons)

Hard rules honored:
  - raw_attributes preserved (Norfolk gate) — only updates parcels.city
  - municipality matches prod_city_value (PR #233 title-case discipline
    — TIGER NAME field is title-case)
  - No matrix authoring (orchestrator's domain)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely.geometry import MultiPolygon, Polygon

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("pierce_task_e")

PIERCE_JID = "47ff33c8-14ec-4298-827e-c770f416d2b6"  # registered in PR #267
WA_CITY_LIMITS_URL = (
    "https://services1.arcgis.com/slSNGMtvwLJi21om/arcgis/rest/services/"
    "WA_City_Limits/FeatureServer/0"
)
ARCGIS_PAGE_SIZE = 500
TEMP_TABLE = "pierce_task_e_wa_city_limits"


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _fetch_wa_cities() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": "1=1", "outFields": "NAME,STATEFP,PLACEFP,GEOID20",
                "returnGeometry": "true", "outSR": 4326,
                "resultOffset": offset, "resultRecordCount": ARCGIS_PAGE_SIZE,
                "f": "json",
            }
            r = await client.get(f"{WA_CITY_LIMITS_URL}/query", params=params)
            r.raise_for_status()
            batch = r.json().get("features", [])
            features.extend(batch)
            logger.info("fetched %d (cumulative %d) offset=%d",
                        len(batch), len(features), offset)
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """Build a MULTIPOLYGON where each ring is its own polygon body.

    TIGER 2020 place boundaries (and some other ArcGIS sources) use ring
    windings that the prior outer-vs-hole heuristic (negative-area = outer)
    mis-classified — Tacoma's 3-ring polygon collapsed to a tiny inner
    ring, leaving every Tacoma parcel uncoupled. Punting topology to
    PostGIS via ST_MakeValid + ST_BuildArea is the robust choice: emit
    each ring as a separate polygon, then let PostGIS reconstruct holes
    on the way in (the INSERT wraps this in ST_Multi(ST_MakeValid(...))).
    """
    ring_wkts = []
    for r in rings:
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: WA City Limits fetch ===\n")
    features = await _fetch_wa_cities()
    print(f"Fetched {len(features)} cities (expect ~281)")
    sample = [f["attributes"]["NAME"] for f in features[:10]]
    print(f"First 10 city names: {sample}")
    # Pierce-area sanity check — Gig Harbor should be in the list
    names = [f["attributes"]["NAME"] for f in features]
    pierce_subset = [n for n in names if n in {
        "Gig Harbor", "Tacoma", "Lakewood", "Puyallup", "University Place",
        "Bonney Lake", "Sumner", "Fircrest", "DuPont", "Steilacoom",
    }]
    print(f"\nExpected Pierce-area cities found: {sorted(pierce_subset)}")
    # Geometry probe on Gig Harbor
    gh = next((f for f in features if f["attributes"]["NAME"] == "Gig Harbor"), None)
    if gh:
        rings = gh["geometry"]["rings"]
        n_pts = sum(len(r) for r in rings)
        print(f"\nGig Harbor: {len(rings)} ring(s), {n_pts} total vertices")
    print("\n(NO DB WRITES.)")
    return 0


async def _fire() -> int:
    print(f"\n=== FIRE: Pierce Task E spatial-join city derivation ===\n")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # Pre-fire snapshot
        p = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE city IS NOT NULL) AS with_city,
                   COUNT(*) FILTER (WHERE city IS NULL) AS null_city
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            PIERCE_JID,
        )
        print(f"PRE-FIRE: Pierce parcels {p['total']:,}  with city: {p['with_city']:,}  "
              f"null city: {p['null_city']:,}")

        # Phase A — fetch + stage WA city limits into temp table
        print("\n[fetch] Pulling 281 WA city polygons (Census 2020 TIGER)…")
        features = await _fetch_wa_cities()
        print(f"[fetch] Got {len(features)} cities")

        print(f"\n[stage] Creating temp table {TEMP_TABLE}…")
        await conn.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE}")
        await conn.execute(f"""
            CREATE TABLE {TEMP_TABLE} (
                place_id text PRIMARY KEY,
                name text NOT NULL,
                geom geometry(MultiPolygon, 4326) NOT NULL
            )
        """)
        for f in features:
            attrs = f.get("attributes", {})
            geom = f.get("geometry")
            if not geom or "rings" not in geom:
                continue
            try:
                wkt = _rings_to_wkt(geom["rings"])
            except Exception as exc:
                logger.warning("Skipping %s (ring parse): %s",
                               attrs.get("NAME"), exc)
                continue
            await conn.execute(
                f"""
                INSERT INTO {TEMP_TABLE} (place_id, name, geom)
                VALUES (
                    $1, $2,
                    ST_Multi(ST_MakeValid(ST_GeomFromText($3, 4326)))
                )
                """,
                attrs.get("GEOID20") or attrs.get("PLACEFP"),
                attrs.get("NAME"),
                wkt,
            )
        n_staged = await conn.fetchval(f"SELECT COUNT(*) FROM {TEMP_TABLE}")
        print(f"[stage] {n_staged} city polygons staged")

        print(f"\n[stage] Building GiST index on {TEMP_TABLE}.geom…")
        await conn.execute(f"CREATE INDEX {TEMP_TABLE}_geom_idx ON {TEMP_TABLE} USING GIST (geom)")

        # Phase B — spatial-join UPDATE scoped to Pierce
        print("\n[update] UPDATE parcels SET city = wcl.name WHERE ST_Within(...)…")
        status = await conn.execute(
            f"""
            UPDATE parcels p
               SET city = c.name, updated_at = NOW()
              FROM {TEMP_TABLE} c
             WHERE p.jurisdiction_id = $1::uuid
               AND p.geom IS NOT NULL
               AND p.city IS NULL
               AND ST_Within(ST_Centroid(p.geom), c.geom)
            """,
            PIERCE_JID,
        )
        try:
            n_updated = int(status.split()[-1])
        except (ValueError, IndexError):
            n_updated = -1
        print(f"[update] UPDATEd {n_updated:,} parcels with city values")

        # Phase C — verification
        print("\n=== POST-FIRE VERIFICATION ===")
        p2 = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE city IS NOT NULL) AS with_city,
                   COUNT(*) FILTER (WHERE city IS NULL) AS null_city
               FROM parcels WHERE jurisdiction_id = $1::uuid""",
            PIERCE_JID,
        )
        cov = 100.0 * p2["with_city"] / p2["total"] if p2["total"] else 0
        print(f"Post-fire: total {p2['total']:,}  with city {p2['with_city']:,} ({cov:.1f}%)  "
              f"null {p2['null_city']:,}")
        print(f"Δ: +{p2['with_city'] - p['with_city']:,} parcels gained city")

        # City distribution
        rows = await conn.fetch(
            """SELECT city, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id = $1::uuid AND city IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC LIMIT 15""",
            PIERCE_JID,
        )
        print(f"\nTop 15 Pierce cities (post-fire):")
        for r in rows:
            flag = "  ← Gig Harbor target (US Census ~3-4k)" if r["city"] == "Gig Harbor" else ""
            print(f"  {r['city']:25s} {r['n']:>7,}{flag}")

        # Spot-check 5 Gig Harbor parcels
        gh_sample = await conn.fetch(
            """SELECT apn, raw->>'SITUS_ADDRESS' AS addr,
                       ST_AsText(ST_Centroid(geom)) AS centroid
               FROM parcels WHERE jurisdiction_id = $1::uuid AND city = 'Gig Harbor'
               ORDER BY RANDOM() LIMIT 5""",
            PIERCE_JID,
        )
        if gh_sample:
            print(f"\nSpot-check — 5 random Gig Harbor parcels:")
            for r in gh_sample:
                print(f"  apn={r['apn']}  addr={r['addr']}  centroid={r['centroid']}")

        # Phase D — drop temp table
        print(f"\n[cleanup] DROP {TEMP_TABLE}")
        await conn.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE}")

    finally:
        await conn.close()
    return 0


async def main(args) -> int:
    if args.subcommand == "preflight":
        return await _preflight()
    if args.subcommand == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
            return 2
        return await _fire()
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("preflight", help="Fetch + report; NO DB writes")
    fire = sub.add_parser("fire", help="Real prod UPDATE")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args)))
