"""New Rochelle (Westchester County NY) — self-storage Stage-4 verdicts.

Grounded in the City of New Rochelle Zoning Ordinance, Chapter 331 (eCode360, fetched via
curl+browser-UA 2026-07-09; DOM-position parse — the article page interleaves sibling district
sections, so self-storage placements were resolved by their litem anchors, e.g. "331-59A(13)").
asyncpg human-UPSERT (catch #29), municipality='New Rochelle' (matches parcels.city EXACTLY; the
m.municipality=p.city join is case-sensitive). Catch #38: City of New Rochelle, Westchester NY.
NY parcels already spatially bound (no rebind). Idempotent.

Ordinance facts (verbatim-verified via DOM anchors across the full Ch. 331 article): "Self-storage
facility" is NAMED as a use in EXACTLY four districts — LSR, LSR-1, LI, LI-H — and nowhere else
(affirmative-provision, catch #57). Of these, only LI and LSR have parcels in New Rochelle (LI-H,
LSR-1 = 0 parcels).

  LI  Light Industry District (§331-59.A(13)) -> PERMITTED (0.95). "Self-storage facility" is a
     PERMITTED PRINCIPAL use (subsection A, item 13, Added 4-20-2004 by Ord. No. 90-2004; litem anchor
     331-59A(13)). Self-storage by-right. 443 parcels = the armed pool.
  LSR Large Scale Retail District (§331-58 C + §331-105.1) -> CONDITIONAL (0.88). "Self-storage
     facility, as regulated by §331-105.1" under "Uses allowed by special permit"; §331-105.1: Planning
     Board special permit, self-storage as a transitional/buffer use, lot NOT exceeding 2 acres.
     -> conditional (special permit; note the ≤2-acre cap narrows the ≥1.5ac needle window to 1.5-2.0ac). 96 parcels.
  I   Industry District (§331-60) -> PROHIBITED (0.80). Self-storage not named (not among the 4 storage
     districts) -> silence / affirmative-provision. 2 parcels.
  NB  Neighborhood Business (§331-56) -> PROHIBITED (0.82). Self-storage not named -> silence.
  DB  Downtown Business (§331-57) -> PROHIBITED (0.82). Self-storage not named -> silence.
  DMU Downtown Mixed Use (§331-47) -> PROHIBITED (0.80). Self-storage not named -> silence.
  DMUR Downtown Mixed Use Urban Renewal (§331-48) -> PROHIBITED (0.80). Not named -> silence.
  C - 1M General Commercial Modified (§331-55) -> PROHIBITED (0.82). Not named -> silence.
  CR - 1 -> PROHIBITED (0.78). Not among the 4 storage districts -> silence.

Armed pool = LI (443, PERMITTED) + LSR (96, conditional, ≤2ac). Everything else prohibited (self-storage
affirmatively provided only in LSR/LSR-1/LI/LI-H). Residential (R1/R2/RMF/ROS) not verdicted.

Run: python scripts/_apply_new_rochelle_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "New Rochelle"

VERDICTS = {
    "LI": ("permitted", "permitted", 0.95, "Light Industry District",
           "§331-59.A(13) 'Self-storage facility' is a PERMITTED PRINCIPAL use (Added 4-20-2004 by Ord. No. 90-2004; litem anchor 331-59A(13)) -> self-storage by-right"),
    "LSR": ("conditional", "unclear", 0.88, "Large Scale Retail District",
            "§331-58 'Uses allowed by special permit': 'Self-storage facility, as regulated by §331-105.1'; §331-105.1 Planning Board special permit as transitional/buffer use, lot NOT exceeding 2 acres -> conditional (special permit; ≤2ac cap)"),
    "I": ("prohibited", "unclear", 0.80, "Industry District",
          "§331-60; self-storage not named (self-storage affirmatively provided only in LSR/LSR-1/LI/LI-H) -> silence rule"),
    "NB": ("prohibited", "unclear", 0.82, "Neighborhood Business District",
           "§331-56; self-storage not named -> silence rule"),
    "DB": ("prohibited", "unclear", 0.82, "Downtown Business District",
           "§331-57; self-storage not named -> silence rule"),
    "DMU": ("prohibited", "unclear", 0.80, "Downtown Mixed Use District",
            "§331-47; self-storage not named -> silence rule"),
    "DMUR": ("prohibited", "unclear", 0.80, "Downtown Mixed Use Urban Renewal District",
             "§331-48; self-storage not named -> silence rule"),
    "C - 1M": ("prohibited", "unclear", 0.82, "General Commercial Modified District",
               "§331-55; self-storage not named -> silence rule"),
    "CR - 1": ("prohibited", "unclear", 0.78, "CR-1 District",
               "self-storage not among the four storage-permitting districts (LSR/LSR-1/LI/LI-H) -> silence rule"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,$4::use_permission_enum,$4::use_permission_enum,
  $5::use_permission_enum,'unclear',$6::jsonb,$7,$9,true,'human',$10,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = settings.database_url.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for zc, (ss, li, conf, zname, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "City of New Rochelle Zoning Ordinance, Ch. 331",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"New Rochelle {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} New Rochelle rows:")
        for r in rows:
            print(f"  {r['zone_code']:8} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
