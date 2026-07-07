"""Task #86 — batched, resumable city stamp from a municipal-BOUNDARIES layer.

A JOB, not a migration (0042 lesson): batched commits, progress-logged, safe to
interrupt and rerun (fill-NULL-only makes it self-resuming). Stamps
city_source='boundary_spatial' (constraint 2 provenance).

USAGE (from backend/):
  python scripts/backfill_city_from_boundaries.py --jurisdiction <uuid> \
      --url <ArcGIS layer url> --name-field TOWN \
      [--where "COUNTY='MIDDLESEX'"] [--batch 20000] [--dry-run]

Verified sources (recon manifest _lake_il_task86_recon_manifest.md):
  Middlesex/Norfolk MA:
    --url https://services1.arcgis.com/hGdibHYSPO59RG1h/ArcGIS/rest/services/Massachusetts_Municipalities_Hosted/FeatureServer/0
    --name-field TOWN  --where "COUNTY='MIDDLESEX'"   (resp. 'NORFOLK')
  Lake County IL:
    --url https://maps.lakecountyil.gov/arcgis/rest/services/GISMapping/WABBoundaries/MapServer/1
    --name-field MUNI_NAME

POST-STAMP GATES (constraint 4) printed at the end: % stamped, distinct-muni
list ⊆ boundary names (zero cross-county), 20-parcel spot-check sample.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import httpx
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from _db import get_sync_dsn  # noqa: E402


def fetch_boundaries(url: str, name_field: str, where: str) -> list[tuple[str, str]]:
    """Page through the ArcGIS layer; return [(muni_name, wkt_polygon)]."""
    out, offset = [], 0
    while True:
        r = httpx.get(f"{url}/query", params={
            "where": where or "1=1", "outFields": name_field, "returnGeometry": "true",
            "outSR": "4326", "f": "geojson", "resultOffset": offset,
            "resultRecordCount": 200,
        }, timeout=120)
        r.raise_for_status()
        feats = r.json().get("features", [])
        for f in feats:
            name = (f.get("properties") or {}).get(name_field)
            geom = f.get("geometry")
            if name and geom:
                g = shape(geom)
                if not g.is_valid:
                    g = g.buffer(0)
                if not g.is_empty:
                    out.append((str(name).strip(), g.wkt))
        print(f"  boundaries fetched: {len(out)} (offset {offset})", flush=True)
        if len(feats) < 200:
            break
        offset += len(feats)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--name-field", required=True)
    ap.add_argument("--where", default="1=1")
    ap.add_argument("--batch", type=int, default=20000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    bounds = fetch_boundaries(a.url, a.name_field, a.where)
    if not bounds:
        raise SystemExit("no boundaries fetched — check url/where/name-field")
    print(f"{len(bounds)} municipal polygons; stamping jurisdiction {a.jurisdiction}")

    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=7200)
    try:
        await con.execute("SET statement_timeout = 0")
        pre = await con.fetchrow(
            "SELECT count(*) t, count(city) c FROM parcels WHERE jurisdiction_id=$1::uuid",
            a.jurisdiction)
        print(f"pre: {pre['c']:,}/{pre['t']:,} have city")
        if a.dry_run:
            print("dry-run: stopping before writes"); return

        # boundary temp table (session-scoped; single connection throughout)
        await con.execute(
            "CREATE TEMP TABLE _muni_bounds (name text, geom geometry(GEOMETRY, 4326))")
        await con.executemany(
            "INSERT INTO _muni_bounds VALUES ($1, ST_GeomFromText($2, 4326))", bounds)
        await con.execute("CREATE INDEX ON _muni_bounds USING gist (geom)")

        total = 0
        while True:
            # Batched, fill-NULL-only, keyset via LIMIT; each statement
            # autocommits (no explicit tx) => interrupt-safe.
            status = await con.execute(f"""
                UPDATE parcels p
                SET city = sub.name, city_source = 'boundary_spatial'
                FROM (
                    SELECT p2.id, b.name
                    FROM parcels p2
                    JOIN LATERAL (
                        SELECT name FROM _muni_bounds b
                        WHERE ST_Within(ST_Centroid(p2.geom), b.geom) LIMIT 1
                    ) b ON true
                    WHERE p2.jurisdiction_id = $1::uuid AND p2.city IS NULL
                      AND p2.geom IS NOT NULL
                    LIMIT {int(a.batch)}
                ) sub
                WHERE p.id = sub.id
            """, a.jurisdiction)
            n = int(status.split()[-1])
            total += n
            print(f"  stamped +{n:,} (total {total:,})", flush=True)
            if n < a.batch:
                break

        # ── POST-STAMP GATES (constraint 4) ─────────────────────────────
        post = await con.fetchrow("""
            SELECT count(*) t, count(city) c, count(DISTINCT city) m
            FROM parcels WHERE jurisdiction_id=$1::uuid""", a.jurisdiction)
        pct = post['c'] / post['t'] * 100 if post['t'] else 0
        print(f"GATE 1 — coverage: {post['c']:,}/{post['t']:,} ({pct:.1f}%) across {post['m']} munis")
        allowed = {n for n, _ in bounds}
        stamped = {r['city'] for r in await con.fetch(
            "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND city_source='boundary_spatial'", a.jurisdiction)}
        rogue = stamped - allowed
        print(f"GATE 2 — cross-boundary names: {sorted(rogue) if rogue else 'NONE (clean)'}")
        sample = await con.fetch("""
            SELECT apn, address, city FROM parcels
            WHERE jurisdiction_id=$1::uuid AND city_source='boundary_spatial'
            ORDER BY random() LIMIT 20""", a.jurisdiction)
        print("GATE 3 — 20-parcel spot-check (eyeball address vs town):")
        for s in sample:
            print(f"    {s['apn']:<20} {(s['address'] or '-')[:36]:<37} -> {s['city']}")
        print(json.dumps({"jurisdiction": a.jurisdiction, "stamped": total,
                          "coverage_pct": round(pct, 1), "munis": post['m'],
                          "rogue": sorted(rogue)}))
    finally:
        await con.close()


asyncio.run(main())
