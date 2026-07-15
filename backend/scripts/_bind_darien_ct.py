"""Bind Darien CT parcels' zoning_code from the town parcel GIS ZONING attribute.

Source: Town of Darien ArcGIS org (services7.arcgis.com/QoSt1vkU9IRboBnD),
`Darien_Current_Parcels/FeatureServer/0` — each parcel carries a `ZONING` field and a
`PIN` (e.g. "02-027-00"). Our parcels.apn = '18850-' + PIN (18850 = Darien CT town code),
so this is a precise ATTRIBUTE join by APN (no geometry / centroid ambiguity).

Write-once: only fills rows where zoning_code IS NULL; sets zoning_code_source='darien_ct_parcels_gis'.
Dry-run by default; --apply writes. Reads the cached PIN→ZONING JSON (or re-downloads via curl+UA).

Run:  cd backend && python scripts/_bind_darien_ct.py            # dry-run
      cd backend && python scripts/_bind_darien_ct.py --apply     # write
"""
from __future__ import annotations
import argparse, asyncio, json, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import asyncpg
from scripts._db import get_sync_dsn

JID = "9b27e214-367c-4652-8385-99b09fe38cd6"
PREFIX = "18850-"
PROVENANCE = "darien_ct_parcels_gis"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
Q = ("https://services7.arcgis.com/QoSt1vkU9IRboBnD/arcgis/rest/services/"
     "Darien_Current_Parcels/FeatureServer/0/query")
BAD = {None, "", "NULL", "NONE"}


def download_pins() -> dict:
    out: dict = {}
    off = 0
    while True:
        url = (Q + "?where=1=1&outFields=PIN,ZONING&returnGeometry=false"
               "&orderByFields=OBJECTID&resultOffset=" + str(off) + "&resultRecordCount=2000&f=json")
        with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
            path = tf.name
        subprocess.run(["curl", "-sL", "-A", UA, url, "-o", path], check=True)
        fs = json.load(open(path)).get("features", [])
        for f in fs:
            a = f["attributes"]
            out[a.get("PIN")] = a.get("ZONING")
        if len(fs) < 2000:
            break
        off += 2000
    return out


async def run(apply: bool) -> None:
    pin2zone = download_pins()
    print(f"Darien parcel-GIS PINs: {len(pin2zone)}")
    con = await asyncpg.connect(get_sync_dsn())
    rows = await con.fetch(
        "SELECT id, apn FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NULL", JID)
    print(f"NULL-zoning parcels: {len(rows)}")
    updates = []
    miss = 0
    dist = Counter()
    for r in rows:
        apn = r["apn"] or ""
        pin = apn[len(PREFIX):] if apn.startswith(PREFIX) else apn
        z = pin2zone.get(pin)
        if z in BAD:
            miss += 1
            continue
        updates.append((r["id"], str(z).strip()))
        dist[str(z).strip()] += 1
    total = len(rows)
    print(f"\n=== COVERAGE: {len(updates)}/{total} = {100*len(updates)/total:.1f}% would bind ===")
    print(f"  no PIN match / null zoning: {miss}")
    print("  would-be zoning distribution:")
    for z, n in dist.most_common():
        print(f"    {z:12} {n}")
    if not apply:
        print("\n[DRY-RUN] no write. Re-run with --apply.")
        await con.close()
        return
    print(f"\n[APPLY] writing {len(updates)} (write-once, provenance={PROVENANCE})…")
    ids = [int(i) for i, _ in updates]
    zc = [z for _, z in updates]
    res = await con.execute(
        """UPDATE parcels AS p SET zoning_code=v.code, zoning_code_source=$3
           FROM unnest($1::bigint[], $2::text[]) AS v(id, code)
           WHERE p.id=v.id AND p.zoning_code IS NULL""", ids, zc, PROVENANCE)
    print("  ", res)
    bound = await con.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL", JID)
    tot = await con.fetchval("SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1", JID)
    print(f"  now bound {bound}/{tot} ({100*bound/tot:.1f}%)")
    await con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    asyncio.run(run(ap.parse_args().apply))
