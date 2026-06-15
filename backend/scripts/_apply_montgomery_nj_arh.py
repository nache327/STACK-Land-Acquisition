"""Correct Montgomery Township NJ (Somerset) ARH verdict — conditional -> prohibited.

ARH = §16-4.13 Age-Restricted Housing District (residential; no commercial storage named).
The prior verdict was a heuristic mis-inference ("zone_class=agricultural" -> conditional,
cites=None). Nache-directed correction with citation. ARH exists ONLY in Montgomery township,
so we write a muni-specific human verdict (scorer prefers muni-specific over county-default).

MR/SI (§16-4.7 Mountain Residential/Special Industrial) is NOT touched here — it is ambiguous
("Special Industrial" may legitimately permit warehouse) and held for the §16-4.7 use-list paste.

Apply via ON CONFLICT DO UPDATE (reverse-direction discipline #13). Idempotent.
Run: python scripts/_apply_montgomery_nj_arh.py
"""
import asyncio
import json

import asyncpg

JUR = "394ef40c-ca0d-4d57-9b11-dc5417430240"  # Somerset County, NJ
MUNI = "Montgomery township"
CITE = "§16-4.13 — Age-Restricted Housing District; residential use only, no commercial storage named"

SQL = """
INSERT INTO zone_use_matrix
    (jurisdiction_id, zone_code, zone_name, municipality,
     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
     citations, cited_subsection, confidence, human_reviewed, classification_source, notes,
     created_at, updated_at)
VALUES
    ($1, 'ARH', 'Age-Restricted Housing District', $2,
     'prohibited','prohibited','prohibited','prohibited',
     $3::jsonb, $4, 0.95, true, 'human', $5, now(), now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality, '')) WHERE deleted_at IS NULL
DO UPDATE SET
    self_storage='prohibited', mini_warehouse='prohibited',
    light_industrial='prohibited', luxury_garage_condo='prohibited',
    citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
    confidence=0.95, human_reviewed=true, classification_source='human',
    zone_name=EXCLUDED.zone_name, notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        cites = json.dumps([{"ordinance": "Montgomery Township NJ Land Development, Chapter 16",
                             "section": "§16-4.13", "basis": "Age-Restricted Housing District — residential; no warehouse/self-storage use named"}])
        note = "ARH Age-Restricted Housing District = self_storage prohibited (§16-4.13). Corrects prior heuristic conditional (mis-inferred agricultural). Nache-directed."
        async with con.transaction():
            await con.execute(SQL, JUR, MUNI, cites, CITE, note)
        row = await con.fetchrow(
            "SELECT self_storage::text ss, human_reviewed hr, confidence c, cited_subsection cs "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND zone_code='ARH' AND municipality=$2 AND deleted_at IS NULL",
            JUR, MUNI)
        print(f"ARH (Montgomery township): self_storage={row['ss']} human_reviewed={row['hr']} conf={row['c']}")
        print(f"  cite: {row['cs']}")
        # confirm MR/SI untouched
        mrsi = await con.fetchrow(
            "SELECT self_storage::text ss, classification_source::text src FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND zone_code='MR/SI' AND municipality IS NULL AND deleted_at IS NULL", JUR)
        print(f"MR/SI (unchanged, held): self_storage={mrsi['ss']} src={mrsi['src']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
