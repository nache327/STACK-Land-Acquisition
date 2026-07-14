"""Bind NJ parcels' zoning_code from the NJTPA Zoning Atlas 082025 layer.

Statewide source (covers all 13 NJTPA counties, Cloudflare-gated — a browser
User-Agent passes; httpx/requests default-UA gets 403, so we shell out to curl):

    https://gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas_082025/MapServer/0

Zone code  = ``Abbreviated_District_Name`` (e.g. "RS-6", "GB-3", "LI", "D-C").
Long name  = ``Full_District_Name``.
Bind logic = centroid-within (parcel.centroid inside an Atlas polygon), EPSG:4326.
Write-once = only fills rows where ``zoning_code IS NULL`` (replace=false / COALESCE
             semantics — never clobbers an existing bind). Sets
             ``zoning_code_source = 'njtpa_atlas_082025'`` for provenance.

DRY-RUN by default (no DB write): reports centroid-within coverage % + would-be
zone distribution + a cross-jurisdiction (#38) spot-check. Pass ``--apply`` to write.

Usage:
    python scripts/bind_nj_atlas082025.py --jid <JID> --county Union            # dry-run
    python scripts/bind_nj_atlas082025.py --jid <JID> --county Union --apply     # write

Requires: shapely, asyncpg (global env). Uses curl for the Atlas download.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402
from shapely.validation import make_valid  # noqa: E402

from scripts._db import get_sync_dsn  # noqa: E402

ATLAS = ("https://gis.njtpa.org/server/rest/services/LandUse/"
         "NJTPA_Zoning_Atlas_082025/MapServer/0/query")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PROVENANCE = "njtpa_atlas_082025"
PAGE = 2000  # Atlas maxRecordCount


def download_atlas(county: str) -> list:
    """Page the Atlas via curl (browser-UA), return (geom, code, jurisdiction) tuples."""
    where = quote(f"County='{county}'")
    out = []
    offset = 0
    while True:
        # orderByFields=OBJECTID is REQUIRED: ArcGIS resultOffset paging without a
        # stable sort shifts page boundaries between requests → silently skips /
        # duplicates features (dropped Winfield + part of Rahway in testing).
        url = (f"{ATLAS}?where={where}"
               "&outFields=Abbreviated_District_Name,Full_District_Name,Jurisdiction"
               "&orderByFields=OBJECTID"
               f"&returnGeometry=true&outSR=4326&resultOffset={offset}"
               f"&resultRecordCount={PAGE}&f=geojson")
        with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
            path = tf.name
        subprocess.run(["curl", "-sL", "-A", UA, url, "-o", path], check=True)
        fc = json.load(open(path))
        feats = fc.get("features", [])
        for f in feats:
            g = f.get("geometry")
            if not g:
                continue
            try:
                geom = shape(g)
            except Exception:  # noqa: BLE001
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
            if geom.is_empty:
                continue
            a = f["properties"]
            out.append((geom, a.get("Abbreviated_District_Name"), a.get("Jurisdiction")))
        if len(feats) < PAGE:
            break
        offset += PAGE
    return out


async def run(jid: str, county: str, apply: bool) -> None:
    polys_data = download_atlas(county)
    polys = [p[0] for p in polys_data]
    codes = [p[1] for p in polys_data]
    juris = [p[2] for p in polys_data]
    print(f"Atlas {county} polygons loaded: {len(polys)}")
    tree = STRtree(polys)

    conn = await asyncpg.connect(get_sync_dsn())
    rows = await conn.fetch(
        """SELECT id, city, ST_X(centroid::geometry) lng, ST_Y(centroid::geometry) lat
           FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NULL AND centroid IS NOT NULL""",
        jid,
    )
    print(f"NULL-zoning parcels to test: {len(rows)}")

    matched = 0
    by_city: dict = defaultdict(lambda: [0, 0])
    zone_by_city: dict = defaultdict(Counter)
    juris_mismatch: Counter = Counter()
    updates: list = []  # (id, code)

    for r in rows:
        city = r["city"]
        by_city[city][0] += 1
        pt = Point(r["lng"], r["lat"])
        hit = None
        for idx in tree.query(pt):
            if polys[idx].contains(pt):
                hit = idx
                break
        if hit is not None:
            code = codes[hit]
            if not code:
                continue
            matched += 1
            by_city[city][1] += 1
            zone_by_city[city][code] += 1
            updates.append((r["id"], str(code).strip()))
            if juris[hit] and city and juris[hit].lower() not in city.lower():
                juris_mismatch[(city, juris[hit])] += 1

    total = len(rows)
    print(f"\n=== COVERAGE: {matched}/{total} = {100*matched/total:.1f}% would bind ===")
    print("\n=== by city (would-bind / tested / %) ===")
    for city, (t, m) in sorted(by_city.items(), key=lambda x: -x[1][0]):
        if t < 50:
            continue
        print(f"  {str(city):<26} {m:>6}/{t:<6} {100*m/t:5.1f}%")

    print("\n=== #38 cross-jurisdiction matches (boundary slivers) ===")
    if not juris_mismatch:
        print("  none")
    else:
        tot_mm = sum(juris_mismatch.values())
        print(f"  {tot_mm} total ({100*tot_mm/max(matched,1):.2f}% of matches)")
        for (city, aj), n in juris_mismatch.most_common(10):
            print(f"    city={city!r} <- atlas juris={aj!r}  n={n}")

    if not apply:
        print("\n[DRY-RUN] no DB write. Re-run with --apply to bind.")
        await conn.close()
        return

    print(f"\n[APPLY] writing {len(updates)} zoning_code + provenance='{PROVENANCE}' (write-once)…")
    written = 0
    async with conn.transaction():
        for pid, code in updates:
            res = await conn.execute(
                """UPDATE parcels SET zoning_code=$1, zoning_code_source=$2
                   WHERE id=$3 AND zoning_code IS NULL""",
                code, PROVENANCE, pid,
            )
            if res.endswith("1"):
                written += 1
    print(f"[APPLY] rows written: {written}")
    now_bound = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL", jid)
    tot_j = await conn.fetchval("SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1", jid)
    print(f"[APPLY] jurisdiction now {now_bound}/{tot_j} bound ({100*now_bound/tot_j:.1f}%)")
    await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jid", required=True)
    ap.add_argument("--county", required=True, help="Atlas County value, e.g. 'Union'")
    ap.add_argument("--apply", action="store_true", help="write to DB (default: dry-run)")
    args = ap.parse_args()
    asyncio.run(run(args.jid, args.county, args.apply))


if __name__ == "__main__":
    main()
