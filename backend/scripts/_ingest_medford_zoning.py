"""Burlington Prompt 2 (re-anchored) — Medford zoning bind-test.

Ingest Medford's ZoningHub zoning polygons into zoning_districts, then centroid
point-in-polygon join to populate parcels.zoning_code for Medford parcels, then a
coverage report. NO verdict apply (held pending §412 paste). Mount Laurel / Moorestown
untouched. Idempotent: skips ingest if this source_url is already loaded.

Source: ME0295_ZoningDistricts_04282023 FeatureServer (zone code in `Layer` field,
CAD-export from MedfordZoning2023.dwg). Pulled as GeoJSON outSR=4326 to match parcels
(SRID 4326). zoning_districts has no `municipality` column -> stored in raw_attributes.
Run: python scripts/_ingest_medford_zoning.py
"""
import asyncio
import hashlib
import json

import asyncpg
import httpx

B = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"  # Burlington County, NJ
MUNI = "Medford township"
FS = ("https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/"
      "ME0295_ZoningDistricts_04282023/FeatureServer/0")


async def fetch_features():
    params = {"where": "1=1", "outFields": "Layer", "outSR": "4326",
              "resultRecordCount": "2000", "f": "geojson"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{FS}/query", params=params)
        r.raise_for_status()
        return r.json().get("features", [])


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    feats = await fetch_features()
    print(f"fetched {len(feats)} Medford polygons from ZoningHub FS")

    con = await asyncpg.connect(url, timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='180s'")
        # idempotency guard
        already = await con.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1 AND raw_attributes->>'source_url'=$2",
            B, FS)
        if already:
            print(f"already ingested ({already} rows) — skipping insert (replace_existing=false)")
        else:
            ins = 0
            for f in feats:
                code = (f.get("properties", {}).get("Layer") or "").strip()
                geom = f.get("geometry")
                if not code or not geom:
                    continue
                gj = json.dumps(geom)
                raw = json.dumps({"municipality": MUNI, "source_url": FS,
                                  "ingest_date": "2026-06-16", "layer": code})
                ghash = hashlib.md5((code + gj).encode()).hexdigest()
                await con.execute("""
                    INSERT INTO zoning_districts
                      (jurisdiction_id, zone_code, zone_name, zone_class, geom, centroid,
                       source, human_reviewed, raw_attributes, geom_hash, created_at, updated_at)
                    VALUES ($1,$2,$3,'unknown',
                      ST_SetSRID(ST_GeomFromGeoJSON($4),4326),
                      ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON($4),4326)),
                      'arcgis', false, $5::jsonb, $6, now(), now())
                """, B, code, code, gj, raw, ghash)
                ins += 1
            print(f"inserted {ins} zoning_districts rows for {MUNI}")
            codes = await con.fetch(
                "SELECT zone_code, COUNT(*) c FROM zoning_districts WHERE jurisdiction_id=$1 "
                "AND raw_attributes->>'municipality'=$2 GROUP BY 1 ORDER BY 2 DESC", B, MUNI)
            print("distinct district codes:", {r['zone_code']: r['c'] for r in codes})

        # spatial join: centroid PIP -> parcels.zoning_code (Medford only).
        # Correlated scalar subquery (LATERAL can't reference UPDATE target p);
        # EXISTS guard so we only set parcels that actually land in a district.
        print("\nspatial-join: Medford parcel centroids -> zoning_districts ...")
        upd = await con.execute("""
            UPDATE parcels p SET zoning_code = (
                SELECT z.zone_code FROM zoning_districts z
                WHERE z.jurisdiction_id=$1 AND z.raw_attributes->>'municipality'=$2
                  AND ST_Contains(z.geom, COALESCE(p.centroid, ST_Centroid(p.geom)))
                ORDER BY ST_Area(z.geom) ASC LIMIT 1)
            WHERE p.jurisdiction_id=$1 AND p.city ILIKE 'Medford township%' AND p.geom IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM zoning_districts z2
                WHERE z2.jurisdiction_id=$1 AND z2.raw_attributes->>'municipality'=$2
                  AND ST_Contains(z2.geom, COALESCE(p.centroid, ST_Centroid(p.geom))))
        """, B, MUNI)
        print("UPDATE:", upd)

        # coverage report
        tot = await con.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1 AND city ILIKE 'Medford township%'", B)
        zc = await con.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1 AND city ILIKE 'Medford township%' AND zoning_code IS NOT NULL", B)
        print(f"\n=== COVERAGE: Medford township parcels={tot} | zoned={zc} ({100*zc/tot:.1f}%) ===")
        dist = await con.fetch("""SELECT zoning_code, COUNT(*) c, COUNT(*) FILTER(WHERE acres BETWEEN 1.5 AND 15) ge15
            FROM parcels WHERE jurisdiction_id=$1 AND city ILIKE 'Medford township%' AND zoning_code IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC""", B)
        for r in dist:
            star = '  <-- verdict-relevant' if r['zoning_code'] in ('PI', 'HC-1', 'HC-2') else ''
            print(f"   {r['zoning_code']:8} parcels={r['c']:5} (1.5-15ac {r['ge15']}){star}")
        # split detection: parcels whose geom intersects >1 Medford district
        splits = await con.fetchval("""
            SELECT COUNT(*) FROM (
              SELECT p.id FROM parcels p JOIN zoning_districts z
                ON z.jurisdiction_id=$1 AND z.raw_attributes->>'municipality'=$2 AND ST_Intersects(z.geom, p.geom)
              WHERE p.jurisdiction_id=$1 AND p.city ILIKE 'Medford township%' AND p.geom IS NOT NULL
              GROUP BY p.id HAVING COUNT(*)>1) s""", B, MUNI)
        print(f"   split parcels (geom intersects >1 district; centroid-assigned): {splits}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
