"""One-shot: ingest NJDCA's statewide Municipal_Zoning directory into
`zoning_sources` so we have an authoritative-source registry for all
564 NJ municipalities.

What NJDCA provides (per muni):
  - Muni        : 4-digit MOD-IV code (e.g. '0337' = Westampton Twp)
  - Municipali  : muni name (e.g. 'Westampton Township')
  - County_1    : county name (e.g. 'Burlington')
  - Map         : URL to the muni's zoning map PDF
  - Ordinance   : URL to the ordinance text (typically ecode360)
  - Website     : muni contact page

Output: two rows per muni in `zoning_sources` —
  source_type='pdf_map'    source_url=<Map>
  source_type='ordinance'  source_url=<Ordinance>

Both with discovered_by='njdca_directory' and confidence_label='discovered'
(operator must promote to 'verified' after spot-checking — same QA gate
the existing zoning_discovery pipeline uses).

jurisdiction_id maps to the COUNTY jurisdiction (e.g. Burlington
d316fb43). municipality_name carries the muni granularity per
schema comment.

Idempotent: matched on (state='NJ', municipality_name, source_type,
discovered_by='njdca_directory'). Re-running upserts URLs if NJDCA
publishes corrections.

After running, the registry can drive per-muni router selection:
  - Has working ArcGIS endpoint? -> Tier A (_backfill-zoning)
  - Has shapefile URL?           -> Tier B (_upload-zoning)
  - Has block-table PDF?         -> Tier C (CSV + APN-prefix JOIN)
  - Polygon-only PDF?            -> Tier D (multimodal classifier)
  - Ordinance only?              -> Tier E (matrix-only, low confidence)
"""
from __future__ import annotations

import asyncio
import sys

import asyncpg
import httpx

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
NJDCA_FS = (
    "https://services.arcgis.com/Aur8tCo478N3VovT/arcgis/rest/services/"
    "Municipal_Zoning/FeatureServer/0"
)
DISCOVERED_BY = "njdca_directory"


async def fetch_all_njdca_rows() -> list[dict]:
    """Page through the NJDCA FeatureServer (maxRecordCount=2000)."""
    out: list[dict] = []
    offset = 0
    page = 2000
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as cli:
        while True:
            r = await cli.get(f"{NJDCA_FS}/query", params={
                "where": "1=1",
                "outFields": "Muni,Municipali,County_1,Map,Ordinance,Website",
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": page,
                "orderByFields": "Muni ASC",
            })
            r.raise_for_status()
            feats = r.json().get("features", [])
            if not feats:
                break
            out.extend(f.get("attributes") or {} for f in feats)
            if len(feats) < page:
                break
            offset += page
    return out


async def load_county_jurisdictions(conn: asyncpg.Connection) -> dict[str, str]:
    """Build {lower(county_name): jurisdiction_id} for NJ counties."""
    rows = await conn.fetch(
        "SELECT id, name FROM jurisdictions WHERE state='NJ' "
        "ORDER BY name"
    )
    out: dict[str, str] = {}
    for r in rows:
        nm = (r["name"] or "").lower()
        # Names look like 'Burlington County, NJ' or 'Bergen County, NJ'
        # — strip ' county, nj' suffix to make matching robust.
        key = nm.replace(" county, nj", "").replace(", nj", "").strip()
        out[key] = str(r["id"])
    return out


async def main() -> int:
    print("Fetching NJDCA Municipal_Zoning directory ...")
    rows = await fetch_all_njdca_rows()
    print(f"  {len(rows):,} muni rows pulled")

    if not rows:
        print("  empty response — aborting")
        return 1

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        county_jids = await load_county_jurisdictions(conn)
        print(f"  loaded {len(county_jids)} NJ county jurisdictions for joining")

        # Pre-state
        pre = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_sources WHERE discovered_by=$1",
            DISCOVERED_BY,
        )
        print(f"  pre:  {pre:,} existing zoning_sources rows from {DISCOVERED_BY!r}")

        inserted = 0
        updated = 0
        skipped_no_url = 0
        skipped_no_county_match = 0

        for attrs in rows:
            muni_code  = (attrs.get("Muni") or "").strip()
            muni_name  = (attrs.get("Municipali") or "").strip()
            county     = (attrs.get("County_1") or "").strip()
            map_url    = (attrs.get("Map") or "").strip() or None
            ord_url    = (attrs.get("Ordinance") or "").strip() or None
            website    = (attrs.get("Website") or "").strip() or None

            if not muni_name:
                skipped_no_url += 1
                continue

            jid = county_jids.get(county.lower())
            if jid is None:
                skipped_no_county_match += 1
                # Still record the row — jurisdiction_id NULL is allowed.
                pass

            notes_parts = [f"NJDCA MOD-IV code: {muni_code}"]
            if website:
                notes_parts.append(f"Website: {website}")
            notes = " | ".join(notes_parts)

            for source_type, url in (("pdf_map", map_url), ("ordinance", ord_url)):
                if not url:
                    continue
                # Upsert by (state, municipality_name, source_type, discovered_by).
                # No partial unique index exists, so do SELECT-then-UPDATE/INSERT.
                existing_id = await conn.fetchval(
                    """
                    SELECT id FROM zoning_sources
                     WHERE state = 'NJ'
                       AND municipality_name = $1
                       AND source_type       = $2
                       AND discovered_by     = $3
                    """,
                    muni_name, source_type, DISCOVERED_BY,
                )
                if existing_id is None:
                    await conn.execute(
                        """
                        INSERT INTO zoning_sources (
                          jurisdiction_id, municipality_name, county, state,
                          source_type, source_url,
                          title, confidence_label, validation_status,
                          discovered_by, notes,
                          last_verified_at
                        ) VALUES (
                          $1::uuid, $2, $3, 'NJ',
                          $4, $5,
                          $6, 'discovered', 'pending',
                          $7, $8,
                          NULL
                        )
                        """,
                        jid, muni_name, county,
                        source_type, url,
                        f"{muni_name} — {source_type} (via NJDCA directory)",
                        DISCOVERED_BY, notes,
                    )
                    inserted += 1
                else:
                    await conn.execute(
                        """
                        UPDATE zoning_sources
                           SET source_url      = $1,
                               jurisdiction_id = COALESCE($2::uuid, jurisdiction_id),
                               county          = $3,
                               notes           = $4,
                               updated_at      = now()
                         WHERE id = $5
                        """,
                        url, jid, county, notes, existing_id,
                    )
                    updated += 1

        # Post-state
        post = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_sources WHERE discovered_by=$1",
            DISCOVERED_BY,
        )
        print()
        print(f"  inserted: {inserted:,}")
        print(f"  updated:  {updated:,}")
        print(f"  skipped (no muni name):    {skipped_no_url}")
        print(f"  skipped (no county match): {skipped_no_county_match}")
        print(f"  post: {post:,} rows from {DISCOVERED_BY!r}")

        # Westampton sanity check
        print()
        print("Westampton rows:")
        rows = await conn.fetch(
            """
            SELECT source_type, source_url, county, jurisdiction_id
              FROM zoning_sources
             WHERE state='NJ'
               AND municipality_name ILIKE 'Westampton%'
               AND discovered_by=$1
             ORDER BY source_type
            """,
            DISCOVERED_BY,
        )
        for r in rows:
            print(f"  [{r['source_type']:9s}] {r['source_url']}")
            print(f"             jurisdiction_id={r['jurisdiction_id']}  county={r['county']!r}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
